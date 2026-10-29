from datetime import date
from math import sqrt
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.playbook_registry import Playbook

Side = Literal["buy", "sell"]
OptionType = Literal["call", "put"]
LiquidityRating = Literal["good", "fair", "poor", "unknown"]
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._-]{1,15}$")

DISCLAIMER = "Educational analysis, not investment advice."


class OptionLeg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    side: Side
    option_type: OptionType
    strike: float = Field(gt=0)
    expiration: date

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper().removeprefix("_")
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Symbol contains invalid characters.")
        return normalized


class AnalysisPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_type: Literal["single", "strategy"]
    legs: list[OptionLeg] = Field(min_length=1, max_length=2)


class LegQuote(OptionLeg):
    bid: float | None = None
    ask: float | None = None
    iv: float | None = None
    delta: float | None = None
    theta: float | None = None
    open_interest: float | None = None
    volume: float | None = None

    def mid_price(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        if self.bid <= 0 or self.ask <= 0 or self.ask < self.bid:
            return None
        return (self.bid + self.ask) / 2


class Liquidity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bid_ask_spread_pct: float | None
    open_interest: float | None
    volume: float | None
    rating: LiquidityRating


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_move: float
    low: float
    high: float
    days_to_expiration: int
    atm_iv: float


class PositionMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    net_credit_debit: float
    max_profit: float | None
    max_loss: float | None
    breakeven: float | None
    probability_positive: float | None
    theta_daily: float | None
    iv_rank: float | None
    event_flags: list[str]
    liquidity: Liquidity
    scenario_1sigma: Scenario | None
    warnings: list[str]


def executable_mid(leg: LegQuote) -> float:
    mid = leg.mid_price()
    if mid is None:
        raise ValueError(
            "Executable quotes are unavailable for "
            f"{leg.symbol} {leg.option_type} {_strike_text(leg.strike)} "
            f"{leg.expiration.isoformat()}."
        )
    return mid


def format_header(display_name: str, legs: list[OptionLeg]) -> str:
    symbol = legs[0].symbol.upper()
    expiration = legs[0].expiration.isoformat()
    if len(legs) == 1:
        leg = legs[0]
        return f"{display_name} {symbol} {_strike_text(leg.strike)} {expiration}"
    short_leg = next(leg for leg in legs if leg.side == "sell")
    long_leg = next(leg for leg in legs if leg.side == "buy")
    return (
        f"{display_name} {symbol} {_strike_text(short_leg.strike)}/"
        f"{_strike_text(long_leg.strike)} {expiration}"
    )


def compute_metrics(
    *,
    legs: list[LegQuote],
    playbook: Playbook,
    underlying_price: float | None,
    as_of: date,
    atm_iv: float | None,
) -> PositionMetrics:
    mids = [executable_mid(leg) for leg in legs]
    net_per_share = sum(
        (1 if leg.side == "sell" else -1) * mid for leg, mid in zip(legs, mids)
    )
    net_credit_debit = _money(net_per_share * 100)

    warnings: list[str] = ["iv_rank_unavailable"]
    max_profit, max_loss, breakeven = _bounded_outcomes(legs, net_per_share)
    probability_positive = _probability_positive(legs, net_per_share)
    if probability_positive is None:
        warnings.append("delta_unavailable")

    theta_daily = _theta_daily(legs)
    if theta_daily is None:
        warnings.append("theta_unavailable")

    days_to_expiration = (legs[0].expiration - as_of).days
    scenario = _scenario(underlying_price, atm_iv, days_to_expiration)
    if scenario is None:
        warnings.append("scenario_1sigma_unavailable")

    return PositionMetrics(
        net_credit_debit=net_credit_debit,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven=breakeven,
        probability_positive=probability_positive,
        theta_daily=theta_daily,
        iv_rank=None,
        event_flags=[
            key
            for key in ("earnings", "dividends", "macro")
            if playbook.event_sensitivity.get(key)
        ],
        liquidity=_liquidity(legs),
        scenario_1sigma=scenario,
        warnings=warnings,
    )


def _bounded_outcomes(
    legs: list[LegQuote],
    net_per_share: float,
) -> tuple[float | None, float | None, float | None]:
    if len(legs) == 1:
        leg = legs[0]
        premium = abs(net_per_share)
        if leg.side == "buy":
            max_profit = (
                None
                if leg.option_type == "call"
                else _money((leg.strike - premium) * 100)
            )
            max_loss = _money(premium * 100)
        else:
            max_profit = _money(premium * 100)
            max_loss = (
                None
                if leg.option_type == "call"
                else _money((leg.strike - premium) * 100)
            )
        breakeven = (
            leg.strike + premium
            if leg.option_type == "call"
            else leg.strike - premium
        )
        return max_profit, max_loss, _money(breakeven)

    width = abs(legs[0].strike - legs[1].strike)
    is_credit = net_per_share > 0
    if is_credit:
        max_profit = _money(net_per_share * 100)
        max_loss = _money((width - net_per_share) * 100)
        short_leg = next(leg for leg in legs if leg.side == "sell")
        breakeven = (
            short_leg.strike - net_per_share
            if short_leg.option_type == "put"
            else short_leg.strike + net_per_share
        )
    else:
        debit = -net_per_share
        max_profit = _money((width - debit) * 100)
        max_loss = _money(debit * 100)
        long_leg = next(leg for leg in legs if leg.side == "buy")
        breakeven = (
            long_leg.strike + debit
            if long_leg.option_type == "call"
            else long_leg.strike - debit
        )
    return max_profit, max_loss, _money(breakeven)


def _probability_positive(
    legs: list[LegQuote],
    net_per_share: float,
) -> float | None:
    if len(legs) == 1:
        leg = legs[0]
        if leg.delta is None:
            return None
        magnitude = abs(leg.delta)
        return _probability(magnitude if leg.side == "buy" else 1 - magnitude)

    anchor = (
        next(leg for leg in legs if leg.side == "sell")
        if net_per_share > 0
        else next(leg for leg in legs if leg.side == "buy")
    )
    if anchor.delta is None:
        return None
    magnitude = abs(anchor.delta)
    return _probability(1 - magnitude if net_per_share > 0 else magnitude)


def _theta_daily(legs: list[LegQuote]) -> float | None:
    if any(leg.theta is None for leg in legs):
        return None
    total = sum(
        (1 if leg.side == "buy" else -1) * (leg.theta or 0.0) * 100 for leg in legs
    )
    return _money(total)


def _liquidity(legs: list[LegQuote]) -> Liquidity:
    mids = [leg.mid_price() for leg in legs]
    spreads = [
        (leg.ask - leg.bid) / mid * 100
        for leg, mid in zip(legs, mids)
        if mid is not None and leg.ask is not None and leg.bid is not None
    ]
    spread_pct = (
        round(max(spreads), 2) if len(spreads) == len(legs) else None
    )
    open_interest = (
        min(leg.open_interest for leg in legs if leg.open_interest is not None)
        if all(leg.open_interest is not None for leg in legs)
        else None
    )
    volume = (
        min(leg.volume for leg in legs if leg.volume is not None)
        if all(leg.volume is not None for leg in legs)
        else None
    )
    if spread_pct is None:
        rating: LiquidityRating = "unknown"
    elif spread_pct <= 5 and open_interest is not None and open_interest >= 500:
        rating = "good"
    elif spread_pct <= 15 and open_interest is not None and open_interest >= 100:
        rating = "fair"
    else:
        rating = "poor"
    return Liquidity(
        bid_ask_spread_pct=spread_pct,
        open_interest=open_interest,
        volume=volume,
        rating=rating,
    )


def _scenario(
    underlying_price: float | None,
    atm_iv: float | None,
    days_to_expiration: int,
) -> Scenario | None:
    if underlying_price is None or underlying_price <= 0:
        return None
    if atm_iv is None or atm_iv <= 0:
        return None
    if days_to_expiration <= 0:
        return None
    move = underlying_price * atm_iv * sqrt(days_to_expiration / 365)
    return Scenario(
        expected_move=round(move, 2),
        low=round(underlying_price - move, 2),
        high=round(underlying_price + move, 2),
        days_to_expiration=days_to_expiration,
        atm_iv=round(atm_iv, 4),
    )


def _money(value: float) -> float:
    return round(value + 0.0, 2)


def _probability(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 4)


def _strike_text(value: float) -> str:
    return f"{value:g}"
