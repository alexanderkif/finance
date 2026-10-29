import re
from datetime import date, datetime
from typing import Literal

import httpx
from agent.graph import AnalysisResult, run_analysis
from core.cboe_provider import CboePayloadError, parse_occ_symbol
from core.gemini_provider import (
    ExtractedPosition,
    GeminiConfigurationError,
    GeminiRateLimitError,
    GeminiRequestError,
    GeminiResponseError,
    extract_position,
)
from core.metrics import AnalysisPosition
from core.playbook_registry import PlaybookKey, load_playbooks
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from routers.options import get_options_provider

router = APIRouter()
_PLAYBOOKS = load_playbooks()
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._-]{1,15}$")
_VERTICAL_KEYS: dict[tuple[str, str], PlaybookKey] = {
    ("buy", "call"): "bull_call_spread",
    ("sell", "call"): "bear_call_spread",
    ("buy", "put"): "bull_put_spread",
    ("sell", "put"): "bear_put_spread",
}
_SINGLE_KEYS: dict[tuple[str, str], PlaybookKey] = {
    ("buy", "call"): "long_call",
    ("buy", "put"): "long_put",
    ("sell", "call"): "short_call",
    ("sell", "put"): "short_put",
}
_FIELD_ORDER = ("side", "option_type", "strike", "expiration")


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2_000)
    default_symbol: str = Field(default="SPY", max_length=15)

    @field_validator("message")
    @classmethod
    def require_non_whitespace_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be empty.")
        return value.strip()

    @field_validator("default_symbol")
    @classmethod
    def normalize_default_symbol(cls, value: str) -> str:
        normalized = value.strip().upper().removeprefix("_")
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Default symbol contains invalid characters.")
        return normalized


class AnalysisRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: AnalysisPosition
    intent: Literal["open", "close", "roll"]
    detected_language: str = Field(min_length=2, max_length=24)


class ExampleLeg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: Literal["buy", "sell"]
    option_type: Literal["call", "put"]
    strike: float
    expiration: date


class ExampleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    message: str
    description: str
    legs: list[ExampleLeg]
    current_price: float
    source: Literal["cboe_delayed"] = "cboe_delayed"
    as_of: datetime


class ParsedLeg(BaseModel):
    symbol: str
    side: Literal["buy", "sell"] | None
    option_type: Literal["call", "put"] | None
    strike: float | None
    expiration: date | None


class ParseResponse(BaseModel):
    position_type: Literal["single", "strategy"]
    legs: list[ParsedLeg]
    missing_fields: list[str]
    detected_language: str
    strategy_key: PlaybookKey | None = None


def parse_expiration(value: str | None) -> date | None:
    if value is None:
        return None
    for date_format in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise GeminiResponseError("Gemini returned an invalid expiration date.")


def classify_vertical(legs: list[ParsedLeg]) -> PlaybookKey | None:
    if len(legs) != 2:
        return None
    first, second = legs
    if (
        first.symbol != second.symbol
        or first.option_type is None
        or first.option_type != second.option_type
        or first.expiration is None
        or first.expiration != second.expiration
        or first.strike is None
        or second.strike is None
        or first.strike == second.strike
        or first.side is None
        or second.side is None
        or first.side == second.side
    ):
        return None

    lower_leg = first if first.strike < second.strike else second
    if lower_leg.side is None or first.option_type is None:
        return None
    return _PLAYBOOKS[_VERTICAL_KEYS[(lower_leg.side, first.option_type)]].strategy_key


def classify_strategy(legs: list[ParsedLeg]) -> PlaybookKey | None:
    if len(legs) == 1:
        leg = legs[0]
        if leg.side is None or leg.option_type is None:
            return None
        return _PLAYBOOKS[_SINGLE_KEYS[(leg.side, leg.option_type)]].strategy_key
    return classify_vertical(legs)


def build_parse_response(
    extracted: ExtractedPosition,
    default_symbol: str,
) -> ParseResponse:
    if len(extracted.legs) > 2:
        raise HTTPException(
            status_code=422,
            detail="Strategies with more than two legs are not supported.",
        )

    legs = [
        ParsedLeg(
            symbol=(item.symbol or default_symbol).strip().upper().removeprefix("_"),
            side=item.side,
            option_type=item.option_type,
            strike=item.strike,
            expiration=parse_expiration(item.expiration),
        )
        for item in extracted.legs
    ]
    missing_fields = [
        field
        for field in _FIELD_ORDER
        if any(getattr(leg, field) is None for leg in legs)
    ]
    strategy_key = classify_strategy(legs)
    if len(legs) == 2 and strategy_key is None and not missing_fields:
        missing_fields.append("strategy_type")

    response: dict[str, object] = {
        "position_type": "single" if len(legs) == 1 else "strategy",
        "legs": legs,
        "missing_fields": missing_fields,
        "detected_language": extracted.detected_language,
    }
    if strategy_key is not None:
        response["strategy_key"] = strategy_key

    return ParseResponse.model_validate(response)


@router.post(
    "/api/analysis/parse",
    response_model=ParseResponse,
    response_model_exclude_unset=True,
)
async def parse_analysis(
    body: ParseRequest,
    request: Request,
) -> ParseResponse:
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise HTTPException(status_code=503, detail="Analysis service is not ready.")

    try:
        extracted = await extract_position(client, body.message)
        return build_parse_response(extracted, body.default_symbol)
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GeminiRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except GeminiRequestError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except GeminiResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post(
    "/api/analysis/run",
    response_model=AnalysisResult,
)
async def run_analysis_endpoint(
    body: AnalysisRunRequest,
    request: Request,
) -> AnalysisResult:
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise HTTPException(status_code=503, detail="Analysis service is not ready.")

    legs = body.position.legs
    if body.position.position_type == "single" and len(legs) != 1:
        raise HTTPException(
            status_code=422,
            detail="A single option position must have exactly one leg.",
        )
    if body.position.position_type == "strategy" and len(legs) != 2:
        raise HTTPException(
            status_code=422,
            detail="A strategy position must have exactly two legs.",
        )

    parsed_legs = [
        ParsedLeg(
            symbol=leg.symbol,
            side=leg.side,
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
        )
        for leg in legs
    ]
    strategy_key = classify_strategy(parsed_legs)
    if strategy_key is None:
        raise HTTPException(
            status_code=422,
            detail="The legs do not form a supported single option or vertical spread.",
        )

    try:
        return await run_analysis(
            client=client,
            provider=get_options_provider(request),
            position=body.position,
            playbook=_PLAYBOOKS[strategy_key],
            strategy_key=strategy_key,
            intent=body.intent,
            detected_language=body.detected_language,
        )
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GeminiRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except GeminiRequestError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except GeminiResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except httpx.HTTPStatusError as error:
        status_code = 404 if error.response.status_code == 404 else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"CBOE market provider returned HTTP {error.response.status_code}.",
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail="CBOE market data could not be reached.",
        ) from error
    except CboePayloadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/api/analysis/example/{symbol}", response_model=ExampleResponse)
async def get_analysis_example(
    symbol: str,
    request: Request,
) -> ExampleResponse:
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise HTTPException(status_code=503, detail="Analysis service is not ready.")

    provider = get_options_provider(request)
    try:
        chain = await provider.get_chain(symbol)
        quote = await provider.get_market_quote(symbol)
    except httpx.HTTPStatusError as error:
        status_code = 404 if error.response.status_code == 404 else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"CBOE market provider returned HTTP {error.response.status_code}.",
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail="CBOE market data could not be reached.",
        ) from error
    except CboePayloadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if quote.price is None or quote.price <= 0:
        raise HTTPException(
            status_code=422,
            detail="An underlying quote is required to build an example.",
        )

    as_of = chain.as_of.date()
    puts = []
    for contract in chain.contracts:
        parsed = parse_occ_symbol(contract.option)
        if parsed is None or parsed.option_type != "put":
            continue
        if parsed.expiration <= as_of:
            continue
        if contract.bid is None or contract.ask is None:
            continue
        if contract.bid <= 0 or contract.ask <= 0:
            continue
        puts.append(parsed)
    if not puts:
        raise HTTPException(
            status_code=422,
            detail="No executable put contracts were found for this symbol.",
        )

    expirations = sorted({parsed.expiration for parsed in puts})
    expiration = min(
        expirations,
        key=lambda value: _expiration_score(value, as_of),
    )
    strikes = sorted(
        {parsed.strike for parsed in puts if parsed.expiration == expiration}
    )
    target = quote.price * 0.99
    short_candidates = [strike for strike in strikes if strike <= target]
    if not short_candidates:
        short_candidates = [strike for strike in strikes if strike < quote.price]
    if not short_candidates:
        raise HTTPException(
            status_code=422,
            detail="No put strike below the underlying price was found.",
        )
    short_strike = max(short_candidates)
    lower_strikes = [strike for strike in strikes if strike < short_strike]
    if not lower_strikes:
        raise HTTPException(
            status_code=422,
            detail="No lower put strike was found for a spread example.",
        )
    long_strike = max(lower_strikes)

    short_text = f"{short_strike:g}"
    long_text = f"{long_strike:g}"
    days_to_expiration = (expiration - as_of).days
    message = (
        f"Sell the {short_text} put and buy the {long_text} put on "
        f"{quote.symbol} expiring {expiration.isoformat()} to open a "
        "defined-risk bull put spread."
    )
    description = (
        f"{quote.symbol} is near {quote.price:.2f}. This {short_text}/{long_text} "
        f"put spread expires in {days_to_expiration} days: selling the {short_text} "
        f"put and buying the {long_text} put caps the loss at the strike width "
        "minus the credit received."
    )
    return ExampleResponse(
        symbol=quote.symbol,
        message=message,
        description=description,
        legs=[
            ExampleLeg(
                symbol=quote.symbol,
                side="sell",
                option_type="put",
                strike=short_strike,
                expiration=expiration,
            ),
            ExampleLeg(
                symbol=quote.symbol,
                side="buy",
                option_type="put",
                strike=long_strike,
                expiration=expiration,
            ),
        ],
        current_price=quote.price,
        as_of=chain.as_of,
    )


def _expiration_score(expiration: date, as_of: date) -> tuple[int, int]:
    days = (expiration - as_of).days
    in_window = 0 if 21 <= days <= 60 else 1
    return (in_window, abs(days - 40))
