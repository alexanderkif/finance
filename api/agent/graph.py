import json
from datetime import datetime
from typing import Literal

import httpx
from core.cboe_provider import (
    CboeOptionQuote,
    CboeOptionsProvider,
    parse_occ_symbol,
    select_atm_iv,
)
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
    recommendation: str
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
    detected_language: str
    disclaimer: str = DISCLAIMER
    source: Literal["cboe_delayed"] = "cboe_delayed"
    as_of: datetime
    degraded: bool
    warnings: list[str]


async def run_analysis(
    *,
    client: httpx.AsyncClient,
    provider: CboeOptionsProvider,
    position: AnalysisPosition,
    playbook: Playbook,
    strategy_key: PlaybookKey,
    intent: Literal["open", "close", "roll"],
    detected_language: str,
    historical_candles: list[Candle] | None = None,
) -> AnalysisResult:
    symbol = position.legs[0].symbol
    expiration = position.legs[0].expiration

    chain = await provider.get_chain(symbol, expiration)
    market = await provider.get_market_quote(symbol)
    quotes = [_quote_for(chain.contracts, leg) for leg in position.legs]

    metrics = compute_metrics(
        legs=quotes,
        playbook=playbook,
        underlying_price=market.price,
        as_of=chain.as_of.date(),
        atm_iv=select_atm_iv(chain.contracts, market.price, expiration),
        historical_candles=historical_candles,
    )
    header = format_header(playbook.display_name, position.legs)
    recommendation = await _synthesize(
        client,
        playbook=playbook,
        position=position,
        header=header,
        metrics=metrics,
        market_price=market.price,
        change_pct=market.change_pct,
        intent=intent,
        detected_language=detected_language,
    )

    warnings = [*metrics.warnings, *chain.warnings]
    return AnalysisResult(
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
        detected_language=detected_language,
        as_of=chain.as_of,
        degraded=bool(warnings),
        warnings=warnings,
    )


def _quote_for(contracts: list[CboeOptionQuote], leg: OptionLeg) -> LegQuote:
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
    raise ValueError(
        "No listed contract matches "
        f"{leg.symbol} {leg.option_type} {leg.strike:g} expiring "
        f"{leg.expiration.isoformat()}. Check the strike and expiration, "
        "or send a new description."
    )


async def _synthesize(
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
