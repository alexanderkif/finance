from datetime import date
from typing import Literal

from core.cboe_provider import CboeOptionQuote
from core.chat_models import ChatDraft, ChatDraftLeg, ChatDraftSuggestions
from core.metrics import AnalysisPosition, OptionLeg, OptionType, Side, format_header
from core.option_parsing import (
    ParsedLeg,
    classify_strategy,
)
from core.option_parsing import (
    missing_fields as strategy_missing_fields,
)
from core.playbook_registry import Playbook, PlaybookKey
from core.reference_edits import nearest_strikes, strike_ladder
from pydantic import BaseModel, ConfigDict

LegRole = Literal["short", "long"]


class DraftCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: ChatDraft
    suggestions: ChatDraftSuggestions
    missing: list[str]
    warnings: list[str]
    strategy_key: PlaybookKey | None
    confirm_summary: str | None
    confirm_position: AnalysisPosition | None


_STRATEGY_LEGS: dict[PlaybookKey, list[tuple[Side, OptionType, LegRole]]] = {
    "long_call": [("buy", "call", "long")],
    "long_put": [("buy", "put", "long")],
    "short_call": [("sell", "call", "short")],
    "short_put": [("sell", "put", "short")],
    "bull_put_spread": [("sell", "put", "short"), ("buy", "put", "long")],
    "bear_put_spread": [("buy", "put", "long"), ("sell", "put", "short")],
    "bull_call_spread": [("buy", "call", "long"), ("sell", "call", "short")],
    "bear_call_spread": [("sell", "call", "short"), ("buy", "call", "long")],
}


def complete_draft(
    draft: ChatDraft,
    contracts: list[CboeOptionQuote],
    underlying_price: float | None,
    as_of: date,
    *,
    strategy_hint: PlaybookKey | None = None,
    playbooks: dict[PlaybookKey, Playbook],
) -> DraftCompletion:
    warnings: list[str] = []
    suggested: set[str] = set()
    legs = [leg.model_copy() for leg in draft.legs]
    classified = _classify_complete(legs)
    if strategy_hint is not None and (
        len(legs) == 1 or len(_STRATEGY_LEGS[strategy_hint]) == len(legs)
    ):
        strategy_key = strategy_hint
    else:
        strategy_key = classified or strategy_hint or _infer_strategy(legs)
    if strategy_key is None:
        missing = _missing(legs)
        if len(legs) == 2 and not missing:
            warnings.append("ambiguous_spread_direction")
        return _incomplete(
            draft,
            legs,
            strategy_key,
            missing or ["strategy_type"],
            warnings,
            suggested,
        )

    expected = _STRATEGY_LEGS[strategy_key]
    if len(legs) != len(expected):
        legs = _rebuild_legs(legs, expected, suggested)

    option_type = expected[0][1]
    expirations = _expirations(contracts, option_type)
    expiration = _select_expiration(legs, expirations, as_of)
    if expiration is None:
        missing = _missing(legs)
        if "expiration" not in missing:
            missing.append("expiration")
        warnings.append("expiration_unavailable")
        return _incomplete(
            draft,
            legs,
            strategy_key,
            missing,
            warnings,
            suggested,
        )
    requested_expirations = {
        leg.expiration for leg in legs if leg.expiration is not None
    }
    if requested_expirations and expiration not in requested_expirations:
        warnings.append(
            "The requested expiration is not listed; "
            f"using {expiration.isoformat()}."
        )
        suggested.add("expiration")
    elif not requested_expirations:
        suggested.add("expiration")
    for leg in legs:
        leg.expiration = expiration

    ladder = strike_ladder(contracts, option_type, expiration)
    if not ladder:
        warnings.append("strikes_unavailable")
        return _incomplete(
            draft,
            legs,
            strategy_key,
            _missing(legs) or ["strike"],
            warnings,
            suggested,
        )

    _assign_sides_types(legs, expected, suggested)
    _assign_strikes(
        legs,
        expected,
        ladder,
        underlying_price,
        strategy_key,
        suggested,
        warnings,
    )
    for leg in legs:
        leg.symbol = legs[0].symbol
    if (
        len(legs) == 2
        and legs[0].strike is not None
        and legs[0].strike == legs[1].strike
    ):
        warnings.append(
            "No distinct listed strikes are available for this spread."
        )
        legs[1].strike = None

    strategy_missing = _missing(legs)
    if strategy_missing:
        return _incomplete(
            draft,
            legs,
            strategy_key,
            strategy_missing,
            warnings,
            suggested,
        )

    position = AnalysisPosition(
        position_type="single" if len(legs) == 1 else "strategy",
        legs=[
            OptionLeg(
                symbol=leg.symbol,
                side=leg.side,
                option_type=leg.option_type,
                strike=leg.strike,
                expiration=leg.expiration,
            )
            for leg in legs
            if leg.side is not None
            and leg.option_type is not None
            and leg.strike is not None
            and leg.expiration is not None
        ],
    )
    playbook = playbooks[strategy_key]
    summary = format_header(playbook.display_name, position.legs)
    short_leg = next((leg for leg in legs if leg.side == "sell"), None)
    long_leg = next((leg for leg in legs if leg.side == "buy"), None)
    suggestions = ChatDraftSuggestions(
        fields=sorted(suggested),
        expiration=expiration,
        strike=short_leg.strike if short_leg is not None else legs[0].strike,
        long_strike=(
            long_leg.strike
            if long_leg is not None and len(legs) > 1
            else None
        ),
        width=_width(legs, ladder),
    )
    completed = ChatDraft(
        position_type="single" if len(legs) == 1 else "strategy",
        legs=legs,
        strategy_key=strategy_key,
        reference=None,
        intent=draft.intent,
    )
    return DraftCompletion(
        draft=completed,
        suggestions=suggestions,
        missing=[],
        warnings=warnings,
        strategy_key=strategy_key,
        confirm_summary=summary,
        confirm_position=position,
    )


def _incomplete(
    original: ChatDraft,
    legs: list[ChatDraftLeg],
    strategy_key: PlaybookKey | None,
    missing: list[str],
    warnings: list[str],
    suggested: set[str],
) -> DraftCompletion:
    draft = ChatDraft(
        position_type="single" if len(legs) == 1 else "strategy",
        legs=legs,
        strategy_key=strategy_key,
        reference=original.reference,
        intent=original.intent,
    )
    return DraftCompletion(
        draft=draft,
        suggestions=ChatDraftSuggestions(
            fields=sorted(suggested),
            expiration=legs[0].expiration if legs else None,
            strike=legs[0].strike if legs else None,
            long_strike=legs[1].strike if len(legs) > 1 else None,
            width=_width(legs, []),
        ),
        missing=missing,
        warnings=warnings,
        strategy_key=strategy_key,
        confirm_summary=None,
        confirm_position=None,
    )


def _classify_complete(legs: list[ChatDraftLeg]) -> PlaybookKey | None:
    parsed = [
        ParsedLeg(
            symbol=leg.symbol,
            side=leg.side,
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
        )
        for leg in legs
    ]
    if strategy_missing_fields(parsed):
        return None
    return classify_strategy(parsed)


def _infer_strategy(legs: list[ChatDraftLeg]) -> PlaybookKey | None:
    if len(legs) == 1:
        leg = legs[0]
        if leg.option_type is None:
            return None
        if leg.side is None:
            return "long_call" if leg.option_type == "call" else "long_put"
        return (
            "long_call"
            if leg.side == "buy" and leg.option_type == "call"
            else "long_put"
            if leg.side == "buy"
            else "short_call"
            if leg.option_type == "call"
            else "short_put"
        )
    if len(legs) == 2:
        types = {leg.option_type for leg in legs}
        sides = {leg.side for leg in legs}
        if len(types) == 1 and None not in types and sides == {"buy", "sell"}:
            return None
    return None


def _rebuild_legs(
    legs: list[ChatDraftLeg],
    expected: list[tuple[Side, OptionType, LegRole]],
    suggested: set[str],
) -> list[ChatDraftLeg]:
    supplied = legs[0]
    if supplied.side is None:
        suggested.add("side")
    if supplied.option_type is None:
        suggested.add("option_type")
    target_index = 0
    if supplied.side is not None:
        for index, (side, _, _) in enumerate(expected):
            if side == supplied.side:
                target_index = index
                break
    return [
        ChatDraftLeg(
            symbol=supplied.symbol,
            side=side,
            option_type=option_type,
            strike=supplied.strike if index == target_index else None,
            expiration=supplied.expiration if index == target_index else None,
        )
        for index, (side, option_type, _) in enumerate(expected)
    ]


def _assign_sides_types(
    legs: list[ChatDraftLeg],
    expected: list[tuple[Side, OptionType, LegRole]],
    suggested: set[str],
) -> None:
    for index, (side, option_type, _) in enumerate(expected):
        if index >= len(legs):
            legs.append(
                ChatDraftLeg(
                    symbol=legs[0].symbol,
                    side=side,
                    option_type=option_type,
                )
            )
            suggested.update({"side", "option_type"})
            continue
        leg = legs[index]
        if leg.side is None:
            leg.side = side
            suggested.add("side")
        if leg.option_type is None:
            leg.option_type = option_type
            suggested.add("option_type")


def _assign_strikes(
    legs: list[ChatDraftLeg],
    expected: list[tuple[Side, OptionType, LegRole]],
    ladder: list[float],
    underlying_price: float | None,
    strategy_key: PlaybookKey,
    suggested: set[str],
    warnings: list[str],
) -> None:
    for index, leg in enumerate(legs):
        if leg.strike is not None:
            resolved = _nearest_listed(ladder, leg.strike)
            if resolved != leg.strike:
                warnings.append(
                    f"{_text(leg.strike)} is not listed; using {_text(resolved)}."
                )
                suggested.add("strike" if leg.side == "sell" else "long_strike")
            leg.strike = resolved

    if len(legs) == 1:
        if legs[0].strike is None:
            if underlying_price is None:
                warnings.append("underlying_price_unavailable")
                return
            legs[0].strike = _single_strike(
                ladder,
                underlying_price,
                strategy_key,
            )
            suggested.add("strike")
        return

    if len(legs) == 2 and all(leg.strike is not None for leg in legs):
        return
    if underlying_price is None:
        warnings.append("underlying_price_unavailable")
        return

    short_index = _index(legs, "sell")
    long_index = _index(legs, "buy")
    short_leg = legs[short_index] if short_index is not None else None
    long_leg = legs[long_index] if long_index is not None else None

    if short_leg is not None and short_leg.strike is not None:
        short_leg.strike = _listed(ladder, short_leg.strike)
        if long_leg is not None and long_leg.strike is None:
            long_leg.strike = _step(
                ladder,
                short_leg.strike,
                _long_delta_from_short(strategy_key),
                warnings,
            )
            suggested.add("long_strike")
        return
    if long_leg is not None and long_leg.strike is not None:
        long_leg.strike = _listed(ladder, long_leg.strike)
        if short_leg is not None and short_leg.strike is None:
            short_leg.strike = _step(
                ladder,
                long_leg.strike,
                _short_delta_from_long(strategy_key),
                warnings,
            )
            suggested.add("strike")
        return

    anchor = _spread_anchor(ladder, underlying_price, strategy_key)
    if strategy_key in {"bull_put_spread", "bear_call_spread"}:
        if short_leg is not None:
            short_leg.strike = anchor
        if long_leg is not None:
            long_leg.strike = _step(
                ladder,
                anchor,
                _long_delta_from_short(strategy_key),
                warnings,
            )
    else:
        if long_leg is not None:
            long_leg.strike = anchor
        if short_leg is not None:
            short_leg.strike = _step(
                ladder,
                anchor,
                _short_delta_from_long(strategy_key),
                warnings,
            )
    suggested.update({"strike", "long_strike"})


def _long_delta_from_short(strategy_key: PlaybookKey) -> int:
    return 2 if strategy_key in {"bear_put_spread", "bear_call_spread"} else -2


def _short_delta_from_long(strategy_key: PlaybookKey) -> int:
    return 2 if strategy_key in {"bull_put_spread", "bull_call_spread"} else -2


def _single_strike(
    ladder: list[float],
    price: float,
    strategy_key: PlaybookKey,
) -> float:
    if strategy_key == "short_call":
        above = [value for value in ladder if value > price]
        return above[0] if above else ladder[-1]
    if strategy_key == "short_put":
        below = [value for value in ladder if value < price]
        return below[-1] if below else ladder[0]
    return min(ladder, key=lambda value: abs(value - price))


def _spread_anchor(
    ladder: list[float],
    price: float,
    strategy_key: PlaybookKey,
) -> float:
    if strategy_key == "bull_put_spread":
        below = [value for value in ladder if value <= price * 0.99]
        return below[-1] if below else _single_strike(ladder, price, "short_put")
    if strategy_key == "bear_call_spread":
        above = [value for value in ladder if value >= price * 1.01]
        return above[0] if above else _single_strike(ladder, price, "short_call")
    return min(ladder, key=lambda value: abs(value - price))


def _step(
    ladder: list[float],
    strike: float,
    delta: int,
    warnings: list[str],
) -> float:
    index = _strike_index(ladder, strike)
    if index is None:
        return strike
    target = max(0, min(len(ladder) - 1, index + delta))
    if target != index + delta:
        warnings.append(
            "Not enough listed strike steps for the default width; used the widest available."
        )
    return ladder[target]


def _select_expiration(
    legs: list[ChatDraftLeg],
    expirations: list[date],
    as_of: date,
) -> date | None:
    for leg in legs:
        if leg.expiration is not None and leg.expiration in expirations:
            return leg.expiration
    future = [value for value in expirations if value > as_of]
    if not future:
        return None
    preferred = [value for value in future if 21 <= (value - as_of).days <= 60]
    pool = preferred or future
    return min(pool, key=lambda value: abs((value - as_of).days - 40))


def _expirations(
    contracts: list[CboeOptionQuote],
    option_type: OptionType,
) -> list[date]:
    from core.cboe_provider import parse_occ_symbol

    values = set()
    for contract in contracts:
        parsed = parse_occ_symbol(contract.option)
        if parsed is not None and parsed.option_type == option_type:
            values.add(parsed.expiration)
    return sorted(values)


def _nearest_listed(ladder: list[float], strike: float) -> float:
    return min(ladder, key=lambda value: abs(value - strike))


def _listed(ladder: list[float], strike: float) -> float:
    return strike if _strike_index(ladder, strike) is not None else _nearest_listed(ladder, strike)


def _strike_index(ladder: list[float], strike: float) -> int | None:
    for index, value in enumerate(ladder):
        if abs(value - strike) <= 1e-9:
            return index
    return None


def _index(legs: list[ChatDraftLeg], side: Side) -> int | None:
    for index, leg in enumerate(legs):
        if leg.side == side:
            return index
    return None


def _missing(legs: list[ChatDraftLeg]) -> list[str]:
    return [
        field
        for field in ("side", "option_type", "strike", "expiration")
        if any(getattr(leg, field) is None for leg in legs)
    ]


def _width(legs: list[ChatDraftLeg], ladder: list[float]) -> int | None:
    if len(legs) != 2 or not ladder:
        return None
    strikes = [leg.strike for leg in legs]
    if any(value is None for value in strikes):
        return None
    first, second = sorted(value for value in strikes if value is not None)
    return sum(1 for value in ladder if first <= value < second)


def _text(value: float) -> str:
    return f"{value:g}"


def nearest_hint(
    contracts: list[CboeOptionQuote],
    option_type: OptionType,
    expiration: date,
    strike: float,
) -> str:
    values = nearest_strikes(contracts, option_type, expiration, strike)
    if not values:
        return ""
    return "Nearby listed strikes: " + ", ".join(_text(value) for value in values) + "."
