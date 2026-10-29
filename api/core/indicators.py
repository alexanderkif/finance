from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ChartRange = Literal["1mo", "3mo", "6mo", "1y", "5y"]
RANGE_OUTPUT_SIZES: dict[ChartRange, int] = {
    "1mo": 22,
    "3mo": 66,
    "6mo": 132,
    "1y": 260,
    "5y": 1_300,
}


class Candle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: float | None = None


class IndicatorPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t: datetime
    value: float


class IndicatorSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: int
    points: list[IndicatorPoint]


def simple_moving_average(
    candles: list[Candle],
    period: int,
) -> IndicatorSeries:
    points: list[IndicatorPoint] = []
    if period <= 0 or len(candles) < period:
        return IndicatorSeries(period=period, points=points)
    closes = [candle.c for candle in candles]
    running = sum(closes[:period])
    points.append(
        IndicatorPoint(t=candles[period - 1].t, value=round(running / period, 2))
    )
    for index in range(period, len(closes)):
        running += closes[index] - closes[index - period]
        points.append(
            IndicatorPoint(t=candles[index].t, value=round(running / period, 2))
        )
    return IndicatorSeries(period=period, points=points)


def relative_strength_index(
    candles: list[Candle],
    period: int = 14,
) -> IndicatorSeries:
    points: list[IndicatorPoint] = []
    if period <= 0 or len(candles) <= period:
        return IndicatorSeries(period=period, points=points)
    closes = [candle.c for candle in candles]
    average_gain = 0.0
    average_loss = 0.0
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        average_gain += max(change, 0.0)
        average_loss += max(-change, 0.0)
    average_gain /= period
    average_loss /= period
    points.append(
        IndicatorPoint(
            t=candles[period].t,
            value=_rsi_value(average_gain, average_loss),
        )
    )
    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
        points.append(
            IndicatorPoint(
                t=candles[index].t,
                value=_rsi_value(average_gain, average_loss),
            )
        )
    return IndicatorSeries(period=period, points=points)


def chart_levels(
    candles: list[Candle],
    current_price: float | None = None,
    *,
    max_levels: int = 3,
    window: int = 2,
    tolerance: float = 0.005,
) -> tuple[list[float], list[float]]:
    if not candles:
        return [], []
    price = current_price if current_price is not None else candles[-1].c
    highs, lows = pivot_levels(candles, window=window)
    levels = _cluster_levels(highs + lows, tolerance=tolerance)
    supports = sorted(
        (level for level in levels if level < price),
        reverse=True,
    )[:max_levels]
    resistances = sorted(
        (level for level in levels if level > price),
    )[:max_levels]
    return supports, resistances


def pivot_levels(
    candles: list[Candle],
    *,
    window: int = 2,
) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for index in range(window, len(candles) - window):
        neighbours = (
            candles[index - window : index] + candles[index + 1 : index + window + 1]
        )
        if all(candles[index].h > candle.h for candle in neighbours):
            highs.append(candles[index].h)
        if all(candles[index].l < candle.l for candle in neighbours):
            lows.append(candles[index].l)
    return highs, lows


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0
    relative_strength = average_gain / average_loss
    return round(100 - 100 / (1 + relative_strength), 2)


def _cluster_levels(
    values: list[float],
    *,
    tolerance: float,
) -> list[float]:
    ordered = sorted(value for value in values if value > 0)
    groups: list[list[float]] = []
    for value in ordered:
        if groups and abs(value - groups[-1][-1]) / groups[-1][-1] <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [round(sum(group) / len(group), 2) for group in groups]
