from datetime import datetime
from typing import Literal

from core.indicators import Candle
from pydantic import BaseModel, ConfigDict

PatternDirection = Literal["bullish", "bearish", "neutral"]


class CandlestickPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    direction: PatternDirection
    t: datetime
    description: str


def detect_patterns(
    candles: list[Candle],
    *,
    lookback: int = 12,
    limit: int = 5,
) -> list[CandlestickPattern]:
    if len(candles) < 2:
        return []
    start = max(1, len(candles) - lookback)
    found: list[CandlestickPattern] = []
    for index in range(start, len(candles)):
        previous = candles[index - 1]
        current = candles[index]
        pattern = _two_candle_pattern(previous, current) or _single_candle_pattern(
            current
        )
        if pattern is not None:
            found.append(pattern)
    return list(reversed(found))[:limit]


def _single_candle_pattern(candle: Candle) -> CandlestickPattern | None:
    body = abs(candle.c - candle.o)
    full_range = candle.h - candle.l
    if full_range <= 0:
        return None
    upper_shadow = candle.h - max(candle.c, candle.o)
    lower_shadow = min(candle.c, candle.o) - candle.l
    if body <= 0.1 * full_range:
        return CandlestickPattern(
            name="doji",
            direction="neutral",
            t=candle.t,
            description="Open and close are nearly equal, showing indecision.",
        )
    if (
        body <= 0.35 * full_range
        and lower_shadow >= 2 * body
        and upper_shadow <= body
    ):
        return CandlestickPattern(
            name="hammer",
            direction="bullish",
            t=candle.t,
            description="Long lower shadow with a small body, a potential reversal cue.",
        )
    if (
        body <= 0.35 * full_range
        and upper_shadow >= 2 * body
        and lower_shadow <= body
    ):
        return CandlestickPattern(
            name="shooting_star",
            direction="bearish",
            t=candle.t,
            description="Long upper shadow with a small body, a potential reversal cue.",
        )
    return None


def _two_candle_pattern(
    previous: Candle,
    current: Candle,
) -> CandlestickPattern | None:
    previous_bullish = previous.c > previous.o
    current_bullish = current.c > current.o
    previous_body = abs(previous.c - previous.o)
    current_body = abs(current.c - current.o)
    if current.h <= previous.h and current.l >= previous.l:
        return CandlestickPattern(
            name="inside_bar",
            direction="neutral",
            t=current.t,
            description="The current range sits inside the previous range.",
        )
    if (
        previous_body > 0
        and current_body > 0
        and not previous_bullish
        and current_bullish
        and current.o <= previous.c
        and current.c >= previous.o
    ):
        return CandlestickPattern(
            name="bullish_engulfing",
            direction="bullish",
            t=current.t,
            description="A bullish body fully covers the previous bearish body.",
        )
    if (
        previous_body > 0
        and current_body > 0
        and previous_bullish
        and not current_bullish
        and current.o >= previous.c
        and current.c <= previous.o
    ):
        return CandlestickPattern(
            name="bearish_engulfing",
            direction="bearish",
            t=current.t,
            description="A bearish body fully covers the previous bullish body.",
        )
    return None
