from datetime import date, datetime
from typing import Literal

from core.gemini_provider import GeminiResponseError
from core.playbook_registry import PlaybookKey
from pydantic import BaseModel

Side = Literal["buy", "sell"]
OptionType = Literal["call", "put"]

FIELD_ORDER = ("side", "option_type", "strike", "expiration")

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


class ParsedLeg(BaseModel):
    symbol: str
    side: Side | None
    option_type: OptionType | None
    strike: float | None
    expiration: date | None


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
    return _VERTICAL_KEYS[(lower_leg.side, first.option_type)]


def classify_strategy(legs: list[ParsedLeg]) -> PlaybookKey | None:
    if len(legs) == 1:
        leg = legs[0]
        if leg.side is None or leg.option_type is None:
            return None
        return _SINGLE_KEYS[(leg.side, leg.option_type)]
    return classify_vertical(legs)


def missing_fields(legs: list[ParsedLeg]) -> list[str]:
    return [
        field
        for field in FIELD_ORDER
        if any(getattr(leg, field) is None for leg in legs)
    ]
