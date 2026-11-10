import json
import re
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import date, datetime
from typing import Literal

import httpx
from agent.graph import AnalysisResult, run_analysis_events
from core.cboe_history_provider import CboeHistoryError
from core.cboe_provider import (
    CboeOptionQuote,
    CboePayloadError,
    CboeRateLimitedError,
    CboeUnavailableError,
    parse_occ_symbol,
)
from core.finnhub_provider import (
    FinnhubConfigurationError,
    FinnhubRateLimitError,
    FinnhubRequestError,
    NewsHeadline,
)
from core.gemini_provider import (
    ExtractedPosition,
    GeminiConfigurationError,
    GeminiRateLimitError,
    GeminiRequestError,
    GeminiResponseError,
    extract_position,
)
from core.guardrails import GuardrailViolation, check_chat_request
from core.indicators import Candle
from core.metrics import AnalysisPosition, OptionLeg, format_header
from core.option_parsing import (
    FIELD_ORDER,
    ParsedLeg,
    classify_strategy,
    parse_expiration,
)
from core.playbook_registry import Playbook, PlaybookKey, load_playbooks
from core.reference_edits import (
    ReferenceEdit,
    ReferenceResolutionError,
    resolve_reference_position,
)
from core.twelvedata_provider import TwelveDataError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from routers.chart import get_cboe_history_provider, get_twelve_data_provider
from routers.market import get_finnhub_provider
from routers.options import get_options_provider

router = APIRouter()
_PLAYBOOKS = load_playbooks()
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._-]{1,15}$")
_CBOE_RATE_LIMIT_DETAIL = (
    "The CBOE delayed-quote service is rate limited. "
    "Wait about a minute, then try again."
)
_CBOE_UNAVAILABLE_DETAIL = (
    "CBOE market data is temporarily unavailable. "
    "Please try again in about a minute."
)
_CBOE_UNREACHABLE_DETAIL = (
    "CBOE market data could not be reached. Check the connection and try again."
)


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2_000)
    default_symbol: str = Field(default="SPY", max_length=15)
    context: list[AnalysisPosition] = Field(default_factory=list, max_length=3)

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

    position: AnalysisPosition | None = None
    context: list[AnalysisPosition] = Field(default_factory=list, max_length=3)
    reference: ReferenceEdit | None = None
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


class ParseResponse(BaseModel):
    position_type: Literal["single", "strategy"]
    legs: list[ParsedLeg]
    missing_fields: list[str]
    detected_language: str
    strategy_key: PlaybookKey | None = None
    header: str | None = None
    reference: ReferenceEdit | None = None


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
        for field in FIELD_ORDER
        if any(getattr(leg, field) is None for leg in legs)
    ]
    reference = _parse_reference(extracted.reference)
    strategy_key = classify_strategy(legs)
    if len(legs) == 2 and strategy_key is None and not missing_fields:
        if reference is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "I could not apply that change to the previous position. "
                    "Please name the full position instead."
                ),
            )
        raise HTTPException(
            status_code=422,
            detail=(
                "I can only analyze one option or one two-leg vertical spread "
                "per message. Those legs do not form a supported vertical "
                "spread; please send one position at a time."
            ),
        )

    response: dict[str, object] = {
        "position_type": "single" if len(legs) == 1 else "strategy",
        "legs": legs,
        "missing_fields": missing_fields,
        "detected_language": extracted.detected_language,
    }
    if strategy_key is not None:
        response["strategy_key"] = strategy_key
    if reference is not None:
        response["reference"] = reference
    elif strategy_key is not None and not missing_fields:
        response["header"] = format_header(
            _PLAYBOOKS[strategy_key].display_name,
            [_complete_leg(leg) for leg in legs],
        )

    return ParseResponse.model_validate(response)


def _complete_leg(leg: ParsedLeg) -> OptionLeg:
    if (
        leg.side is None
        or leg.option_type is None
        or leg.strike is None
        or leg.expiration is None
    ):
        raise HTTPException(
            status_code=422,
            detail="The option position is missing required fields.",
        )
    return OptionLeg(
        symbol=leg.symbol,
        side=leg.side,
        option_type=leg.option_type,
        strike=leg.strike,
        expiration=leg.expiration,
    )


def _parse_reference(
    reference: object,
) -> ReferenceEdit | None:
    if reference is None:
        return None
    kind = getattr(reference, "kind", None)
    if kind is None:
        return None
    try:
        return ReferenceEdit(
            kind=kind,
            strikes=getattr(reference, "strikes", None),
            direction=getattr(reference, "direction", None),
            expiration=parse_expiration(getattr(reference, "expiration", None)),
        )
    except (ValueError, ValidationError, GeminiResponseError):
        return None


@router.post(
    "/api/analysis/parse",
    response_model=ParseResponse,
    response_model_exclude_unset=True,
)
async def parse_analysis(
    body: ParseRequest,
    request: Request,
) -> ParseResponse:
    try:
        check_chat_request(
            body.message,
            body.default_symbol,
            has_context=bool(body.context),
        )
    except GuardrailViolation as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise HTTPException(status_code=503, detail="Analysis service is not ready.")

    try:
        extracted = await extract_position(
            client,
            body.message,
            context=[position.model_dump(mode="json") for position in body.context],
            default_symbol=body.default_symbol,
        )
        return build_parse_response(extracted, body.default_symbol)
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GeminiRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except GeminiRequestError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except GeminiResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


async def _load_historical_candles(
    request: Request,
    symbol: str,
) -> list[Candle] | None:
    history = get_cboe_history_provider(request)
    if history.supports(symbol):
        try:
            return await history.get_index_candles(symbol, "1y")
        except CboeHistoryError:
            pass
    try:
        return await get_twelve_data_provider(request).get_daily_candles(symbol, "1y")
    except (TwelveDataError, ValueError):
        return None
    except Exception:
        return None


async def _load_analysis_news(
    request: Request,
    symbol: str,
) -> tuple[list[NewsHeadline], list[str]]:
    try:
        news = await get_finnhub_provider(request).get_analysis_headlines(symbol)
    except FinnhubConfigurationError:
        return [], ["news_provider_not_configured"]
    except FinnhubRateLimitError:
        return [], ["news_rate_limited"]
    except (FinnhubRequestError, ValueError):
        return [], ["news_unavailable"]
    except Exception:
        return [], ["news_unavailable"]
    if not news:
        return [], ["news_unavailable"]
    return news, []


PositionResolver = Callable[
    [list[CboeOptionQuote], datetime],
    tuple[AnalysisPosition, PlaybookKey, Playbook],
]


def _prepare_run(
    body: AnalysisRunRequest,
) -> tuple[str, date, PositionResolver]:
    if body.reference is not None:
        if not body.context:
            raise HTTPException(
                status_code=422,
                detail=(
                    "I need the previous position before I can apply that "
                    "change. Please describe the full position."
                ),
            )
        base = body.context[-1]
        symbol = base.legs[0].symbol
        reference = body.reference
        expiration = reference.expiration or base.legs[0].expiration

        def resolve_reference(
            contracts: list[CboeOptionQuote],
            _as_of: datetime,
        ) -> tuple[AnalysisPosition, PlaybookKey, Playbook]:
            position = resolve_reference_position(
                reference,
                body.context,
                contracts,
                expiration,
            )
            return position, *_classify_position(position)

        return symbol, expiration, resolve_reference

    if body.position is None:
        raise HTTPException(
            status_code=422,
            detail="A complete option position is required.",
        )
    position = body.position
    legs = position.legs
    if position.position_type == "single" and len(legs) != 1:
        raise HTTPException(
            status_code=422,
            detail="A single option position must have exactly one leg.",
        )
    if position.position_type == "strategy" and len(legs) != 2:
        raise HTTPException(
            status_code=422,
            detail="A strategy position must have exactly two legs.",
        )
    strategy_key, playbook = _classify_position(position)

    def resolve_position(
        _contracts: list[CboeOptionQuote],
        _as_of: datetime,
    ) -> tuple[AnalysisPosition, PlaybookKey, Playbook]:
        return position, strategy_key, playbook

    return position.legs[0].symbol, position.legs[0].expiration, resolve_position


def _classify_position(
    position: AnalysisPosition,
) -> tuple[PlaybookKey, Playbook]:
    strategy_key = classify_strategy(
        [
            ParsedLeg(
                symbol=leg.symbol,
                side=leg.side,
                option_type=leg.option_type,
                strike=leg.strike,
                expiration=leg.expiration,
            )
            for leg in position.legs
        ]
    )
    if strategy_key is None:
        raise HTTPException(
            status_code=422,
            detail="The legs do not form a supported single option or vertical spread.",
        )
    return strategy_key, _PLAYBOOKS[strategy_key]


async def _analysis_events(
    request: Request,
    body: AnalysisRunRequest,
    *,
    include_synthesis: bool = True,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncGenerator[dict[str, object], None]:
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise HTTPException(status_code=503, detail="Analysis service is not ready.")

    symbol, expiration, resolve_position = _prepare_run(body)
    async for event in run_analysis_events(
        client=client,
        provider=get_options_provider(request),
        symbol=symbol,
        expiration=expiration,
        resolve_position=resolve_position,
        intent=body.intent,
        detected_language=body.detected_language,
        history_loader=lambda: _load_historical_candles(request, symbol),
        news_loader=lambda: _load_analysis_news(request, symbol),
        include_synthesis=include_synthesis,
        is_disconnected=is_disconnected,
    ):
        yield event


async def compute_analysis(
    request: Request,
    body: AnalysisRunRequest,
) -> AnalysisResult:
    result: AnalysisResult | None = None
    async for event in _analysis_events(request, body, include_synthesis=False):
        if event["type"] == "result":
            result = AnalysisResult.model_validate(event["result"])
    if result is None:
        raise HTTPException(
            status_code=502,
            detail="The analysis ended without a result. Please try again.",
        )
    return result


@router.post(
    "/api/analysis/run",
    response_model=AnalysisResult,
)
async def run_analysis_endpoint(
    body: AnalysisRunRequest,
    request: Request,
) -> AnalysisResult:
    result: AnalysisResult | None = None
    try:
        async for event in _analysis_events(request, body):
            if event["type"] == "result":
                result = AnalysisResult.model_validate(event["result"])
    except Exception as error:
        raise _to_http_exception(error) from error

    if result is None:
        raise HTTPException(
            status_code=502,
            detail="The analysis ended without a result. Please try again.",
        )
    return result


@router.post(
    "/api/analysis/run/stream",
    response_model=None,
    responses={200: {"content": {"application/x-ndjson": {}}}},
)
async def run_analysis_stream(
    body: AnalysisRunRequest,
    request: Request,
) -> StreamingResponse:
    async def generate() -> AsyncGenerator[str, None]:
        try:
            async for event in _analysis_events(
                request,
                body,
                is_disconnected=request.is_disconnected,
            ):
                yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
        except Exception as error:
            http_error = _to_http_exception(error)
            yield json.dumps(
                {
                    "type": "error",
                    "status": http_error.status_code,
                    "detail": str(http_error.detail),
                },
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


def _to_http_exception(error: Exception) -> HTTPException:
    if isinstance(error, HTTPException):
        return error
    if isinstance(error, GeminiConfigurationError):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(error, GeminiRateLimitError):
        return HTTPException(status_code=429, detail=str(error))
    if isinstance(error, (GeminiRequestError, GeminiResponseError)):
        return HTTPException(status_code=502, detail=str(error))
    if isinstance(error, CboeRateLimitedError):
        return HTTPException(status_code=429, detail=_CBOE_RATE_LIMIT_DETAIL)
    if isinstance(error, CboeUnavailableError):
        return HTTPException(status_code=502, detail=_CBOE_UNAVAILABLE_DETAIL)
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code == 404:
            return HTTPException(
                status_code=404,
                detail="No CBOE market data was found for this symbol.",
            )
        return HTTPException(status_code=502, detail=_CBOE_UNAVAILABLE_DETAIL)
    if isinstance(error, httpx.RequestError):
        return HTTPException(status_code=502, detail=_CBOE_UNREACHABLE_DETAIL)
    if isinstance(error, CboePayloadError):
        return HTTPException(status_code=502, detail=str(error))
    if isinstance(error, (ValueError, ReferenceResolutionError)):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(
        status_code=502,
        detail="The analysis service failed. Please try again in a moment.",
    )


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
    except CboeRateLimitedError as error:
        raise HTTPException(status_code=429, detail=_CBOE_RATE_LIMIT_DETAIL) from error
    except CboeUnavailableError as error:
        raise HTTPException(status_code=502, detail=_CBOE_UNAVAILABLE_DETAIL) from error
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="No CBOE market data was found for this symbol.",
            ) from error
        raise HTTPException(status_code=502, detail=_CBOE_UNAVAILABLE_DETAIL) from error
    except httpx.RequestError as error:
        raise HTTPException(status_code=502, detail=_CBOE_UNREACHABLE_DETAIL) from error
    except CboePayloadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if quote.price is None or quote.price <= 0:
        raise HTTPException(
            status_code=422,
            detail="An underlying quote is required to build an example.",
        )

    if chain.as_of is None:
        raise HTTPException(
            status_code=422,
            detail="The option chain is unavailable for this symbol.",
        )
    as_of_at = chain.as_of
    as_of = as_of_at.date()
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
        f"{quote.symbol} expiring {expiration.isoformat()} for a "
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
        as_of=as_of_at,
    )


def _expiration_score(expiration: date, as_of: date) -> tuple[int, int]:
    days = (expiration - as_of).days
    in_window = 0 if 21 <= days <= 60 else 1
    return (in_window, abs(days - 40))
