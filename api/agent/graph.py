import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine
from datetime import date, datetime
from typing import Any, Literal

import httpx
from core.cboe_provider import (
    CboeOptionQuote,
    CboeOptionsProvider,
    parse_occ_symbol,
    select_atm_iv,
)
from core.finnhub_provider import NewsHeadline
from core.gemini_provider import GeminiResponseError, generate_structured
from core.indicators import Candle
from core.metrics import (
    DISCLAIMER,
    AnalysisPosition,
    LegQuote,
    Liquidity,
    OptionLeg,
    PositionMetrics,
    Scenario,
    compute_metrics,
    format_header,
)
from core.playbook_registry import Playbook, PlaybookKey
from core.reference_edits import nearest_strikes
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.prompts import SYNTHESIS_RESPONSE_SCHEMA, SYNTHESIS_SYSTEM_INSTRUCTION


class SynthesisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: str = Field(min_length=20, max_length=2000)


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_key: PlaybookKey
    intent: Literal["open", "close", "roll"]
    header: str
    recommendation: str = Field(default="", max_length=2000)
    probability_positive: float | None
    max_profit: float | None
    max_loss: float | None
    net_credit_debit: float
    breakeven: float | None
    theta_daily: float | None
    iv_rank: float | None
    current_iv: float | None
    hv_20d: float | None
    hv_60d: float | None
    hv_rank: float | None
    iv_hv_ratio: float | None
    event_flags: list[str]
    liquidity: Liquidity
    scenario_1sigma: Scenario | None
    scenario_2sigma: Scenario | None
    news: list[NewsHeadline] = Field(default_factory=list)
    news_source: Literal["finnhub"] | None = None
    news_as_of: datetime | None = None
    detected_language: str
    disclaimer: str = DISCLAIMER
    source: Literal["cboe_delayed"] = "cboe_delayed"
    as_of: datetime
    degraded: bool
    warnings: list[str]


PositionResolver = Callable[
    [list[CboeOptionQuote], datetime],
    tuple[AnalysisPosition, PlaybookKey, Playbook],
]


async def run_analysis_events(
    *,
    client: httpx.AsyncClient,
    provider: CboeOptionsProvider,
    symbol: str,
    expiration: date,
    resolve_position: PositionResolver,
    intent: Literal["open", "close", "roll"],
    detected_language: str,
    history_loader: Callable[[], Coroutine[Any, Any, list[Candle] | None]],
    news_loader: Callable[
        [], Coroutine[Any, Any, tuple[list[NewsHeadline], list[str]]]
    ],
    include_synthesis: bool = True,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncGenerator[dict[str, object], None]:
    history_task = asyncio.create_task(history_loader())
    news_task = asyncio.create_task(news_loader())
    synthesis_task: asyncio.Task[str] | None = None
    try:
        if await _disconnected(is_disconnected):
            return
        yield _stage("history", "started", "Loading price history for volatility context")
        yield _stage("news", "started", "Loading recent headlines")

        if await _disconnected(is_disconnected):
            return
        yield _stage("chain", "started", "Loading the option chain")
        chain = await provider.get_chain(symbol, expiration)
        yield _stage(
            "chain",
            "done",
            f"{len(chain.contracts)} contracts for {expiration.isoformat()}",
        )
        for warning in chain.warnings:
            yield {"type": "warning", "code": warning}
        if chain.as_of is None:
            raise ValueError(
                "The option chain is unavailable for this symbol. "
                "Please try again in a minute."
            )

        if await _disconnected(is_disconnected):
            return
        yield _stage("quote", "started", "Loading the underlying quote")
        market = await provider.get_market_quote(symbol)
        yield _stage(
            "quote",
            "done",
            f"{market.symbol} {market.price:g}"
            if market.price is not None
            else "Quote unavailable",
        )

        position, strategy_key, playbook = resolve_position(
            chain.contracts,
            chain.as_of,
        )
        header = format_header(playbook.display_name, position.legs)
        yield {
            "type": "position",
            "position": position.model_dump(mode="json"),
            "header": header,
        }

        historical_candles = await history_task
        yield _stage(
            "history",
            "done",
            f"{len(historical_candles)} daily candles"
            if historical_candles
            else "History unavailable",
        )

        news, news_warnings = await news_task
        news_as_of = _news_as_of(news)
        yield _stage(
            "news",
            "done",
            f"{len(news)} recent headlines" if news else "No recent headlines",
        )
        if news:
            yield {
                "type": "news",
                "news": [headline.model_dump(mode="json") for headline in news],
                "source": "finnhub",
                "as_of": (
                    news_as_of.isoformat().replace("+00:00", "Z")
                    if news_as_of is not None
                    else None
                ),
            }
        for warning in news_warnings:
            yield {"type": "warning", "code": warning}

        if await _disconnected(is_disconnected):
            return
        yield _stage("metrics", "started", "Calculating position metrics")
        quotes = [quote_for(chain.contracts, leg) for leg in position.legs]
        metrics = compute_metrics(
            legs=quotes,
            playbook=playbook,
            underlying_price=market.price,
            as_of=chain.as_of.date(),
            atm_iv=select_atm_iv(chain.contracts, market.price, expiration),
            historical_candles=historical_candles,
        )
        yield _stage("metrics", "done", header)

        recommendation = ""
        if include_synthesis:
            if await _disconnected(is_disconnected):
                return
            yield _stage("synthesis", "started", "Writing the assessment")
            synthesis_task = asyncio.create_task(
                synthesize(
                    client,
                    playbook=playbook,
                    position=position,
                    header=header,
                    metrics=metrics,
                    market_price=market.price,
                    change_pct=market.change_pct,
                    intent=intent,
                    detected_language=detected_language,
                    news=news,
                )
            )
            while not synthesis_task.done():
                done, _ = await asyncio.wait({synthesis_task}, timeout=10)
                if done:
                    break
                if await _disconnected(is_disconnected):
                    synthesis_task.cancel()
                    return
                yield {"type": "heartbeat"}
            recommendation = synthesis_task.result()
            yield _stage("synthesis", "done", "Assessment ready")

        warnings = [*metrics.warnings, *chain.warnings, *news_warnings]
        result = AnalysisResult(
            strategy_key=strategy_key,
            intent=intent,
            header=header,
            recommendation=recommendation,
            probability_positive=metrics.probability_positive,
            max_profit=metrics.max_profit,
            max_loss=metrics.max_loss,
            net_credit_debit=metrics.net_credit_debit,
            breakeven=metrics.breakeven,
            theta_daily=metrics.theta_daily,
            iv_rank=metrics.iv_rank,
            current_iv=metrics.current_iv,
            hv_20d=metrics.hv_20d,
            hv_60d=metrics.hv_60d,
            hv_rank=metrics.hv_rank,
            iv_hv_ratio=metrics.iv_hv_ratio,
            event_flags=metrics.event_flags,
            liquidity=metrics.liquidity,
            scenario_1sigma=metrics.scenario_1sigma,
            scenario_2sigma=metrics.scenario_2sigma,
            news=news,
            news_source="finnhub" if news else None,
            news_as_of=news_as_of,
            detected_language=detected_language,
            as_of=chain.as_of,
            degraded=bool(warnings),
            warnings=warnings,
        )
        yield {"type": "result", "result": result.model_dump(mode="json")}
    finally:
        for task in (history_task, news_task, synthesis_task):
            if task is not None and not task.done():
                task.cancel()


def _stage(identifier: str, status: str, label: str) -> dict[str, object]:
    return {
        "type": "stage",
        "id": identifier,
        "status": status,
        "label": label,
    }


async def _disconnected(
    is_disconnected: Callable[[], Awaitable[bool]] | None,
) -> bool:
    return bool(is_disconnected is not None and await is_disconnected())


def _news_as_of(news: list[NewsHeadline]) -> datetime | None:
    return max(
        (
            headline.published_at
            for headline in news
            if headline.published_at is not None
        ),
        default=None,
    )


def quote_for(contracts: list[CboeOptionQuote], leg: OptionLeg) -> LegQuote:
    for contract in contracts:
        parsed = parse_occ_symbol(contract.option)
        if parsed is None:
            continue
        if parsed.expiration != leg.expiration:
            continue
        if parsed.option_type != leg.option_type:
            continue
        if abs(parsed.strike - leg.strike) > 1e-6:
            continue
        return LegQuote(
            symbol=leg.symbol,
            side=leg.side,
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
            bid=contract.bid,
            ask=contract.ask,
            iv=contract.iv,
            delta=contract.delta,
            theta=contract.theta,
            open_interest=contract.open_interest,
            volume=contract.volume,
        )
    nearby = nearest_strikes(
        contracts,
        leg.option_type,
        leg.expiration,
        leg.strike,
    )
    hint = (
        " Nearby listed strikes: "
        + ", ".join(f"{value:g}" for value in nearby)
        + "."
        if nearby
        else ""
    )
    raise ValueError(
        "No listed contract matches "
        f"{leg.symbol} {leg.option_type} {leg.strike:g} expiring "
        f"{leg.expiration.isoformat()}. Check the strike and expiration, "
        f"or send a new description.{hint}"
    )


async def synthesize(
    client: httpx.AsyncClient,
    *,
    playbook: Playbook,
    position: AnalysisPosition,
    header: str,
    metrics: PositionMetrics,
    market_price: float | None,
    change_pct: float | None,
    intent: str,
    detected_language: str,
    news: list[NewsHeadline] | None = None,
) -> str:
    metric_facts = metrics.model_dump(mode="json")
    metric_facts.pop("iv_rank", None)
    payload = {
        "strategy": {
            "display_name": playbook.display_name,
            "ideal_conditions": playbook.ideal_conditions,
            "risk_flags": playbook.risk_flags,
            "event_sensitivity": playbook.event_sensitivity,
        },
        "intent": intent,
        "header": header,
        "language": detected_language,
        "legs": [leg.model_dump(mode="json") for leg in position.legs],
        "metrics": metric_facts,
        "market": {
            "underlying_price": market_price,
            "change_pct": change_pct,
        },
        "recent_news": [
            {
                "title": headline.title,
                "publisher": headline.publisher,
                "published_at": (
                    headline.published_at.isoformat()
                    if headline.published_at is not None
                    else None
                ),
            }
            for headline in (news or [])
        ],
    }
    decoded = await generate_structured(
        client,
        system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION,
        response_schema=SYNTHESIS_RESPONSE_SCHEMA,
        message=json.dumps(payload, ensure_ascii=False),
        temperature=0.2,
    )
    try:
        return SynthesisOutput.model_validate(decoded).recommendation
    except ValidationError as error:
        raise GeminiResponseError(
            "Gemini returned an invalid structured analysis result."
        ) from error
