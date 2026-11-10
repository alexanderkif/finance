import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, cast

import httpx
from core.cboe_provider import (
    CboeOptionQuote,
    CboePayloadError,
    CboeRateLimitedError,
    CboeUnavailableError,
    parse_occ_symbol,
)
from core.finnhub_provider import (
    EarningsEvent,
    FinnhubConfigurationError,
    FinnhubRateLimitError,
    FinnhubRequestError,
    NewsHeadline,
)
from core.indicators import ChartRange
from core.metrics import AnalysisPosition, OptionLeg
from core.twelvedata_provider import (
    DividendEvent,
    TwelveDataConfigurationError,
    TwelveDataError,
    TwelveDataRateLimitError,
    TwelveDataRequestError,
)
from fastapi import HTTPException, Request
from routers.analysis import AnalysisRunRequest, compute_analysis
from routers.chart import get_chart, get_twelve_data_provider
from routers.market import get_finnhub_provider
from routers.options import get_options_chain, get_options_provider

from agent.graph import AnalysisResult

_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._-]{1,15}$")
_CHART_RANGES = {"1mo", "3mo", "6mo", "1y", "5y"}
_TOOL_LABELS = {
    "get_quote": "Loading quote",
    "get_chart": "Loading chart",
    "get_option_expirations": "Loading expirations",
    "get_option_chain": "Loading option chain",
    "get_news": "Loading news",
    "get_dividends": "Loading dividends",
    "get_earnings": "Loading earnings",
    "switch_instrument": "Switching instrument",
    "set_chart_toggles": "Updating chart indicators",
    "set_theme": "Updating theme",
    "set_chart_range": "Updating chart range",
    "compute_position": "Computing metrics",
}

TOOL_DECLARATIONS: list[dict[str, object]] = [
    {
        "name": "get_quote",
        "description": (
            "Get the delayed quote, percent change, VIX, and timestamps for a "
            "symbol."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {"symbol": {"type": "STRING"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_chart",
        "description": (
            "Get recent daily candles, SMA 20/50, RSI 14, support, and "
            "resistance for a symbol."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "symbol": {"type": "STRING"},
                "range": {
                    "type": "STRING",
                    "enum": ["1mo", "3mo", "6mo", "1y", "5y"],
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_option_expirations",
        "description": "List listed option expirations for a symbol.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"symbol": {"type": "STRING"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_option_chain",
        "description": (
            "Get a bounded slice of the listed option chain for one expiration, "
            "sorted by distance from the underlying price."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "symbol": {"type": "STRING"},
                "expiration": {"type": "STRING", "description": "YYYY-MM-DD"},
                "option_type": {"type": "STRING", "enum": ["call", "put"]},
                "limit": {
                    "type": "INTEGER",
                    "description": "Number of strikes to return, 5-40.",
                },
            },
            "required": ["symbol", "expiration", "option_type"],
        },
    },
    {
        "name": "get_news",
        "description": "Get recent ticker-specific news headlines.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"symbol": {"type": "STRING"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_dividends",
        "description": "Get recent dividend dates and amounts for a symbol.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"symbol": {"type": "STRING"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_earnings",
        "description": "Get recent and upcoming earnings dates for a symbol.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"symbol": {"type": "STRING"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "switch_instrument",
        "description": (
            "Switch the dashboard to another instrument. Call only when the user "
            "explicitly asks to switch or confirms a switch."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {"symbol": {"type": "STRING"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "set_chart_toggles",
        "description": (
            "Turn chart indicators on or off. Use when the user asks to show or "
            "hide SMA20, SMA50, RSI, or support/resistance levels."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "sma20": {"type": "BOOLEAN"},
                "sma50": {"type": "BOOLEAN"},
                "rsi": {"type": "BOOLEAN"},
                "levels": {"type": "BOOLEAN"},
            },
        },
    },
    {
        "name": "set_theme",
        "description": "Switch the page theme.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "theme": {"type": "STRING", "enum": ["light", "dark"]}
            },
            "required": ["theme"],
        },
    },
    {
        "name": "set_chart_range",
        "description": "Change the chart history range.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "range": {
                    "type": "STRING",
                    "enum": ["1mo", "3mo", "6mo", "1y", "5y"],
                }
            },
            "required": ["range"],
        },
    },
    {
        "name": "compute_position",
        "description": (
            "Compute deterministic strategy metrics for one option or one two-leg "
            "vertical spread. Use this for probability, max profit/loss, "
            "breakeven, theta, volatility, liquidity, and event-sensitivity "
            "questions. Write the explanation yourself."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "legs": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "symbol": {"type": "STRING"},
                            "side": {
                                "type": "STRING",
                                "enum": ["buy", "sell"],
                            },
                            "option_type": {
                                "type": "STRING",
                                "enum": ["call", "put"],
                            },
                            "strike": {"type": "NUMBER"},
                            "expiration": {
                                "type": "STRING",
                                "description": "YYYY-MM-DD",
                            },
                        },
                        "required": [
                            "symbol",
                            "side",
                            "option_type",
                            "strike",
                            "expiration",
                        ],
                    },
                },
                "intent": {
                    "type": "STRING",
                    "enum": ["open", "close", "roll"],
                    "description": "Defaults to open.",
                },
            },
            "required": ["legs"],
        },
    },
]


@dataclass
class ToolResult:
    payload: dict[str, object]
    label: str
    detail: str | None = None
    card: AnalysisResult | None = None
    switch: dict[str, object] | None = None
    ui_actions: list[dict[str, object]] = field(default_factory=list)
    failed: bool = False


class ToolError(ValueError):
    pass


def _symbol(arguments: dict[str, object]) -> str:
    raw = arguments.get("symbol")
    if not isinstance(raw, str):
        raise ToolError("A symbol is required.")
    normalized = raw.strip().upper().removeprefix("_").removeprefix("^")
    if not _SYMBOL_PATTERN.fullmatch(normalized):
        raise ToolError("The symbol contains invalid characters.")
    return normalized


def _expiration(arguments: dict[str, object]) -> date:
    raw = arguments.get("expiration")
    if not isinstance(raw, str):
        raise ToolError("An expiration date is required.")
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise ToolError("The expiration must use YYYY-MM-DD.") from error


def _option_type(arguments: dict[str, object]) -> Literal["call", "put"]:
    raw = arguments.get("option_type")
    if raw not in ("call", "put"):
        raise ToolError("The option type must be call or put.")
    return cast(Literal["call", "put"], raw)


def _limit(arguments: dict[str, object], default: int = 20) -> int:
    raw = arguments.get("limit")
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ToolError("The limit must be an integer.")
    return max(5, min(40, raw))


async def execute_tool(
    request: Request,
    name: str,
    arguments: dict[str, object],
) -> ToolResult:
    label = _TOOL_LABELS.get(name, name)
    try:
        if name == "get_quote":
            return await _get_quote(request, arguments)
        if name == "get_chart":
            return await _get_chart(request, arguments)
        if name == "get_option_expirations":
            return await _get_option_expirations(request, arguments)
        if name == "get_option_chain":
            return await _get_option_chain(request, arguments)
        if name == "get_news":
            return await _get_news(request, arguments)
        if name == "get_dividends":
            return await _get_dividends(request, arguments)
        if name == "get_earnings":
            return await _get_earnings(request, arguments)
        if name == "switch_instrument":
            return _switch_instrument(arguments)
        if name == "set_chart_toggles":
            return _set_chart_toggles(arguments)
        if name == "set_theme":
            return _set_theme(arguments)
        if name == "set_chart_range":
            return _set_chart_range(arguments)
        if name == "compute_position":
            return await _compute_position(request, arguments)
    except ToolError as error:
        return ToolResult(
            payload={"error": str(error)},
            label=label,
            detail=str(error),
            failed=True,
        )
    except HTTPException as error:
        message = str(error.detail)
        return ToolResult(
            payload={"error": message},
            label=label,
            detail=message,
            failed=True,
        )
    except ValueError as error:
        message = str(error)
        return ToolResult(
            payload={"error": message},
            label=label,
            detail=message,
            failed=True,
        )
    except Exception:
        message = f"The {name} tool failed. Try again."
        return ToolResult(
            payload={"error": message},
            label=label,
            detail=message,
            failed=True,
        )
    return ToolResult(
        payload={"error": f"Unknown tool: {name}"},
        label=label,
        detail=f"Unknown tool: {name}",
        failed=True,
    )


async def _get_quote(
    request: Request,
    arguments: dict[str, object],
) -> ToolResult:
    symbol = _symbol(arguments)
    provider = get_options_provider(request)
    try:
        quote = await provider.get_market_quote(symbol)
    except (
        httpx.HTTPStatusError,
        httpx.RequestError,
        CboePayloadError,
        CboeRateLimitedError,
        CboeUnavailableError,
        ValueError,
    ):
        return ToolResult(
            payload={"error": "The quote is unavailable."},
            label="Loading quote",
            detail="The quote provider is unavailable.",
            failed=True,
        )
    vix = None
    try:
        vix_quote = await provider.get_index_quote("VIX")
        vix = vix_quote.price
    except (
        httpx.HTTPStatusError,
        httpx.RequestError,
        CboePayloadError,
        CboeRateLimitedError,
        CboeUnavailableError,
        ValueError,
    ):
        vix = None
    return ToolResult(
        payload={
            "symbol": quote.symbol,
            "price": quote.price,
            "change_pct": quote.change_pct,
            "vix": vix,
            "as_of": quote.as_of.isoformat(),
            "source": "cboe_delayed",
        },
        label="Loading quote",
        detail=f"{quote.symbol} {quote.price:g}" if quote.price is not None else None,
    )


async def _get_chart(
    request: Request,
    arguments: dict[str, object],
) -> ToolResult:
    symbol = _symbol(arguments)
    raw_range = arguments.get("range")
    range_value: ChartRange = (
        cast(ChartRange, raw_range) if raw_range in _CHART_RANGES else "6mo"
    )
    try:
        chart = await get_chart(symbol, request, range_period=range_value)
    except HTTPException as error:
        return ToolResult(
            payload={"error": str(error.detail)},
            label="Loading chart",
            detail=str(error.detail),
            failed=True,
        )
    except Exception:
        return ToolResult(
            payload={"error": "The chart is unavailable."},
            label="Loading chart",
            detail="The chart provider is unavailable.",
            failed=True,
        )
    sma = {
        str(series.period): _last_indicator_value(series.points)
        for series in chart.sma
    }
    return ToolResult(
        payload={
            "symbol": chart.symbol,
            "range": chart.range,
            "source": chart.source,
            "as_of": chart.as_of.isoformat() if chart.as_of else None,
            "degraded": chart.degraded,
            "warnings": chart.warnings,
            "support": chart.support,
            "resistance": chart.resistance,
            "sma": sma,
            "rsi14": _last_indicator_value(chart.rsi.points),
            "candles": [
                candle.model_dump(mode="json") for candle in chart.candles[-10:]
            ],
        },
        label="Loading chart",
        detail=f"{len(chart.candles)} daily candles",
    )


async def _get_option_expirations(
    request: Request,
    arguments: dict[str, object],
) -> ToolResult:
    symbol = _symbol(arguments)
    chain = await get_options_chain(symbol, request)
    expirations = sorted(
        {
            parsed.expiration
            for contract in chain.contracts
            if (parsed := parse_occ_symbol(contract.option)) is not None
        }
    )
    if not expirations:
        return ToolResult(
            payload={
                "error": "No listed expirations are available.",
                "warnings": chain.warnings,
            },
            label="Loading expirations",
            detail="No listed expirations are available.",
            failed=True,
        )
    return ToolResult(
        payload={
            "symbol": chain.symbol,
            "expirations": [value.isoformat() for value in expirations],
            "as_of": chain.as_of.isoformat() if chain.as_of else None,
            "warnings": chain.warnings,
        },
        label="Loading expirations",
        detail=f"{len(expirations)} listed expirations",
    )


async def _get_option_chain(
    request: Request,
    arguments: dict[str, object],
) -> ToolResult:
    symbol = _symbol(arguments)
    expiration = _expiration(arguments)
    option_type = _option_type(arguments)
    limit = _limit(arguments)
    chain = await get_options_chain(symbol, request, expiration=expiration)
    provider = get_options_provider(request)
    price = None
    try:
        quote = await provider.get_market_quote(symbol)
        price = quote.price
    except Exception:
        price = None
    contracts: list[tuple[float, CboeOptionQuote]] = []
    for contract in chain.contracts:
        parsed = parse_occ_symbol(contract.option)
        if (
            parsed is None
            or parsed.expiration != expiration
            or parsed.option_type != option_type
        ):
            continue
        contracts.append((parsed.strike, contract))
    if not contracts:
        return ToolResult(
            payload={
                "error": "No listed contracts match that expiration and type.",
                "warnings": chain.warnings,
            },
            label="Loading option chain",
            detail="No listed contracts match the request.",
            failed=True,
        )
    contracts.sort(
        key=lambda item: (
            abs(item[0] - price) if price is not None else item[0],
            item[0],
        )
    )
    selected = contracts[:limit]
    return ToolResult(
        payload={
            "symbol": chain.symbol,
            "expiration": expiration.isoformat(),
            "option_type": option_type,
            "underlying_price": price,
            "as_of": chain.as_of.isoformat() if chain.as_of else None,
            "warnings": chain.warnings,
            "contracts": [
                {
                    "option": contract.option,
                    "strike": parsed.strike,
                    "bid": contract.bid,
                    "ask": contract.ask,
                    "iv": contract.iv,
                    "delta": contract.delta,
                    "gamma": contract.gamma,
                    "theta": contract.theta,
                    "vega": contract.vega,
                    "open_interest": contract.open_interest,
                    "volume": contract.volume,
                }
                for parsed, contract in (
                    (parse_occ_symbol(contract.option), contract)
                    for _, contract in selected
                )
                if parsed is not None
            ],
        },
        label="Loading option chain",
        detail=f"{len(selected)} listed contracts",
    )


async def _get_news(
    request: Request,
    arguments: dict[str, object],
) -> ToolResult:
    symbol = _symbol(arguments)
    try:
        news = await get_finnhub_provider(request).get_analysis_headlines(symbol)
    except FinnhubConfigurationError:
        return _optional_data_result(
            "Loading news",
            "News is not configured.",
            "news_provider_not_configured",
        )
    except FinnhubRateLimitError:
        return _optional_data_result(
            "Loading news",
            "The news provider is rate limited.",
            "news_rate_limited",
        )
    except (FinnhubRequestError, ValueError):
        return _optional_data_result(
            "Loading news",
            "News is unavailable.",
            "news_unavailable",
        )
    return ToolResult(
        payload={
            "symbol": symbol,
            "news": [_headline_payload(headline) for headline in news],
            "warnings": [] if news else ["news_unavailable"],
        },
        label="Loading news",
        detail=f"{len(news)} recent headlines" if news else "No recent headlines",
    )


async def _get_dividends(
    request: Request,
    arguments: dict[str, object],
) -> ToolResult:
    symbol = _symbol(arguments)
    try:
        dividends = await get_twelve_data_provider(request).get_dividends(symbol)
    except TwelveDataConfigurationError:
        return _optional_data_result(
            "Loading dividends",
            "The dividend provider is not configured.",
            "dividends_provider_not_configured",
        )
    except TwelveDataRateLimitError:
        return _optional_data_result(
            "Loading dividends",
            "The dividend provider is rate limited.",
            "dividends_rate_limited",
        )
    except (TwelveDataRequestError, TwelveDataError, ValueError):
        return _optional_data_result(
            "Loading dividends",
            "Dividends are unavailable.",
            "dividends_unavailable",
        )
    return ToolResult(
        payload={
            "symbol": symbol,
            "dividends": [_dividend_payload(event) for event in dividends],
            "warnings": [] if dividends else ["dividends_unavailable"],
        },
        label="Loading dividends",
        detail=f"{len(dividends)} dividend events",
    )


async def _get_earnings(
    request: Request,
    arguments: dict[str, object],
) -> ToolResult:
    symbol = _symbol(arguments)
    try:
        earnings = await get_finnhub_provider(request).get_earnings(symbol)
    except FinnhubConfigurationError:
        return _optional_data_result(
            "Loading earnings",
            "The earnings provider is not configured.",
            "earnings_provider_not_configured",
        )
    except FinnhubRateLimitError:
        return _optional_data_result(
            "Loading earnings",
            "The earnings provider is rate limited.",
            "earnings_rate_limited",
        )
    except (FinnhubRequestError, ValueError):
        return _optional_data_result(
            "Loading earnings",
            "Earnings are unavailable.",
            "earnings_unavailable",
        )
    return ToolResult(
        payload={
            "symbol": symbol,
            "earnings": [_earnings_payload(event) for event in earnings],
            "warnings": [] if earnings else ["earnings_unavailable"],
        },
        label="Loading earnings",
        detail=f"{len(earnings)} earnings events",
    )


async def _compute_position(
    request: Request,
    arguments: dict[str, object],
) -> ToolResult:
    raw_legs = arguments.get("legs")
    if not isinstance(raw_legs, list) or not 1 <= len(raw_legs) <= 2:
        raise ToolError("One or two legs are required.")
    legs: list[OptionLeg] = []
    for raw in raw_legs:
        if not isinstance(raw, dict):
            raise ToolError("Each leg must be an object.")
        symbol = raw.get("symbol")
        side = raw.get("side")
        option_type = raw.get("option_type")
        strike = raw.get("strike")
        expiration = raw.get("expiration")
        if not isinstance(symbol, str) or side not in ("buy", "sell"):
            raise ToolError("Each leg needs a symbol and a buy or sell side.")
        if option_type not in ("call", "put"):
            raise ToolError("Each leg needs a call or put option type.")
        if isinstance(strike, bool) or not isinstance(strike, int | float):
            raise ToolError("Each leg needs a positive strike.")
        if not isinstance(expiration, str):
            raise ToolError("Each leg needs an expiration date.")
        legs.append(
            OptionLeg(
                symbol=symbol.strip().upper().removeprefix("_"),
                side=cast(Literal["buy", "sell"], side),
                option_type=cast(Literal["call", "put"], option_type),
                strike=float(strike),
                expiration=date.fromisoformat(expiration),
            )
        )
    position = AnalysisPosition(
        position_type="single" if len(legs) == 1 else "strategy",
        legs=legs,
    )
    raw_intent = arguments.get("intent", "open")
    intent = (
        cast(Literal["open", "close", "roll"], raw_intent)
        if raw_intent in ("open", "close", "roll")
        else "open"
    )
    result = await compute_analysis(
        request,
        AnalysisRunRequest(
            position=position,
            intent=intent,
            detected_language="English",
        ),
    )
    return ToolResult(
        payload=result.model_dump(mode="json"),
        label="Computing metrics",
        detail=result.header,
        card=result,
    )


def _set_chart_toggles(arguments: dict[str, object]) -> ToolResult:
    keys: tuple[Literal["sma20", "sma50", "rsi", "levels"], ...] = (
        "sma20",
        "sma50",
        "rsi",
        "levels",
    )
    toggles: dict[str, bool] = {}
    for key in keys:
        if key not in arguments:
            continue
        value = arguments[key]
        if not isinstance(value, bool):
            raise ToolError(f"The {key} toggle must be a boolean.")
        toggles[key] = value
    if not toggles:
        raise ToolError("At least one chart toggle is required.")
    actions = [
        {"type": "chart_toggle", "key": key, "value": value}
        for key, value in toggles.items()
    ]
    return ToolResult(
        payload={"toggles": toggles},
        label="Updating chart indicators",
        detail=", ".join(
            f"{key} {'on' if value else 'off'}" for key, value in toggles.items()
        ),
        ui_actions=actions,
    )


def _set_theme(arguments: dict[str, object]) -> ToolResult:
    theme = arguments.get("theme")
    if theme not in ("light", "dark"):
        raise ToolError("The theme must be light or dark.")
    return ToolResult(
        payload={"theme": theme},
        label="Updating theme",
        detail=str(theme),
        ui_actions=[{"type": "theme", "value": theme}],
    )


def _set_chart_range(arguments: dict[str, object]) -> ToolResult:
    range_value = arguments.get("range")
    if range_value not in _CHART_RANGES:
        raise ToolError("The chart range must be 1mo, 3mo, 6mo, 1y, or 5y.")
    return ToolResult(
        payload={"range": range_value},
        label="Updating chart range",
        detail=str(range_value),
        ui_actions=[{"type": "chart_range", "value": range_value}],
    )


def _switch_instrument(arguments: dict[str, object]) -> ToolResult:
    symbol = _symbol(arguments)
    return ToolResult(
        payload={"symbol": symbol},
        label="Switching instrument",
        detail=symbol,
        switch={
            "symbol": symbol,
            "explicit": True,
            "reason": "The user requested a switch.",
        },
    )


def _optional_data_result(
    label: str,
    detail: str,
    code: str,
) -> ToolResult:
    return ToolResult(
        payload={"error": detail, "warnings": [code]},
        label=label,
        detail=detail,
    )


def _last_indicator_value(points) -> float | None:
    if not points:
        return None
    return points[-1].value


def _headline_payload(headline: NewsHeadline) -> dict[str, object]:
    return {
        "title": headline.title,
        "url": headline.url,
        "publisher": headline.publisher,
        "published_at": (
            headline.published_at.isoformat()
            if headline.published_at is not None
            else None
        ),
    }


def _dividend_payload(event: DividendEvent) -> dict[str, object]:
    return {"ex_date": event.ex_date.isoformat(), "amount": event.amount}


def _earnings_payload(event: EarningsEvent) -> dict[str, object]:
    return {
        "date": event.date.isoformat(),
        "quarter": event.quarter,
        "year": event.year,
        "eps_estimate": event.eps_estimate,
        "eps_actual": event.eps_actual,
        "revenue_estimate": event.revenue_estimate,
        "revenue_actual": event.revenue_actual,
    }
