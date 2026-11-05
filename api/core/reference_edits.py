from datetime import date
from typing import Literal

from core.cboe_provider import CboeOptionQuote, parse_occ_symbol
from core.metrics import AnalysisPosition, OptionLeg
from pydantic import BaseModel, ConfigDict, Field, model_validator

ReferenceKind = Literal["same", "shift", "widen", "narrow", "expiration"]
ReferenceDirection = Literal["up", "down"]


class ReferenceResolutionError(ValueError):
    pass


class ReferenceEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ReferenceKind
    strikes: int | None = Field(default=None, ge=1, le=20)
    direction: ReferenceDirection | None = None
    expiration: date | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> "ReferenceEdit":
        if self.kind == "shift" and (
            self.strikes is None or self.direction is None
        ):
            raise ValueError("A strike shift needs a count and a direction.")
        if self.kind in ("widen", "narrow") and self.strikes is None:
            raise ValueError("A width change needs a strike count.")
        if self.kind == "expiration" and self.expiration is None:
            raise ValueError("An expiration change needs a date.")
        return self


def resolve_reference_position(
    reference: ReferenceEdit,
    context: list[AnalysisPosition],
    contracts: list[CboeOptionQuote],
    target_expiration: date,
) -> AnalysisPosition:
    if not context:
        raise ReferenceResolutionError(
            "I need the previous position before I can apply that change."
        )
    base = context[-1]

    if reference.kind == "same":
        return AnalysisPosition(
            position_type=base.position_type,
            legs=[leg.model_copy() for leg in base.legs],
        )

    if reference.kind == "expiration":
        expiration = reference.expiration or target_expiration
        legs = [
            leg.model_copy(update={"expiration": expiration})
            for leg in base.legs
        ]
        _ensure_legs_are_listed(legs, contracts)
        return AnalysisPosition(position_type=base.position_type, legs=legs)

    if reference.kind == "shift":
        count = reference.strikes or 0
        direction = reference.direction
        delta = count if direction == "up" else -count
        legs = [
            _move_leg(leg, contracts, delta)
            for leg in base.legs
        ]
        return AnalysisPosition(position_type=base.position_type, legs=legs)

    if len(base.legs) != 2:
        raise ReferenceResolutionError(
            "A width change needs a two-leg vertical spread."
        )

    short_leg = next(leg for leg in base.legs if leg.side == "sell")
    long_leg = next(leg for leg in base.legs if leg.side == "buy")
    is_put_spread = long_leg.option_type == "put"
    widening = reference.kind == "widen"
    count = reference.strikes or 0
    if is_put_spread:
        delta = -count if widening else count
    else:
        delta = count if widening else -count
    moved_long = _move_leg(long_leg, contracts, delta)
    if is_put_spread and moved_long.strike >= short_leg.strike:
        raise ReferenceResolutionError(
            "That width change would remove the spread. "
            "Choose a smaller width change."
        )
    if not is_put_spread and moved_long.strike <= short_leg.strike:
        raise ReferenceResolutionError(
            "That width change would remove the spread. "
            "Choose a smaller width change."
        )
    legs = [
        leg.model_copy() if leg.side == "sell" else moved_long
        for leg in base.legs
    ]
    return AnalysisPosition(position_type=base.position_type, legs=legs)


def _move_leg(
    leg: OptionLeg,
    contracts: list[CboeOptionQuote],
    delta: int,
) -> OptionLeg:
    ladder = strike_ladder(contracts, leg.option_type, leg.expiration)
    if not ladder:
        raise ReferenceResolutionError(
            f"No listed {leg.option_type} strikes are available for "
            f"{leg.symbol} {leg.expiration.isoformat()}."
        )
    index = _strike_index(ladder, leg.strike)
    if index is None:
        raise ReferenceResolutionError(
            f"{_strike_text(leg.strike)} is not in the listed strike ladder. "
            f"{_nearest_hint(ladder, leg.strike)}"
        )
    next_index = index + delta
    if next_index < 0 or next_index >= len(ladder):
        direction = "higher" if delta > 0 else "lower"
        raise ReferenceResolutionError(
            f"There are not enough listed strikes {direction} than "
            f"{_strike_text(leg.strike)}. {_nearest_hint(ladder, leg.strike)}"
        )
    return leg.model_copy(update={"strike": ladder[next_index]})


def _ensure_legs_are_listed(
    legs: list[OptionLeg],
    contracts: list[CboeOptionQuote],
) -> None:
    for leg in legs:
        ladder = strike_ladder(contracts, leg.option_type, leg.expiration)
        if _strike_index(ladder, leg.strike) is None:
            raise ReferenceResolutionError(
                "No listed contract matches the requested expiration. "
                f"{_nearest_hint(ladder, leg.strike)}"
            )


def strike_ladder(
    contracts: list[CboeOptionQuote],
    option_type: Literal["call", "put"],
    expiration: date,
) -> list[float]:
    strikes = set()
    for contract in contracts:
        parsed = parse_occ_symbol(contract.option)
        if parsed is None:
            continue
        if parsed.option_type != option_type or parsed.expiration != expiration:
            continue
        strikes.add(parsed.strike)
    return sorted(strikes)


def nearest_strikes(
    contracts: list[CboeOptionQuote],
    option_type: Literal["call", "put"],
    expiration: date,
    strike: float,
    limit: int = 5,
) -> list[float]:
    ladder = strike_ladder(contracts, option_type, expiration)
    return sorted(ladder, key=lambda value: abs(value - strike))[:limit]


def _strike_index(ladder: list[float], strike: float) -> int | None:
    for index, value in enumerate(ladder):
        if abs(value - strike) <= 1e-9:
            return index
    return None


def _nearest_hint(ladder: list[float], strike: float) -> str:
    if not ladder:
        return "No listed strikes are available for that expiration."
    nearest = sorted(ladder, key=lambda value: abs(value - strike))[:5]
    return "Nearby listed strikes: " + ", ".join(
        _strike_text(value) for value in nearest
    ) + "."


def _strike_text(value: float) -> str:
    return f"{value:g}"
