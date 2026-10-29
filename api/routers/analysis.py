import re
from datetime import date, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.gemini_provider import (
    ExtractedPosition,
    GeminiConfigurationError,
    GeminiRateLimitError,
    GeminiRequestError,
    GeminiResponseError,
    extract_position,
)
from core.playbook_registry import PlaybookKey, load_playbooks

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
