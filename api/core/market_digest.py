from datetime import datetime
from typing import Literal

from core.chat_models import ChatMarketSnapshot
from core.indicators import Candle, ChartRange
from core.patterns import CandlestickPattern, detect_patterns
from pydantic import BaseModel, ConfigDict, Field

Trend = Literal["up", "down", "sideways", "unknown"]
VixRegime = Literal["calm", "elevated", "panic", "unknown"]


class DigestHeadline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    publisher: str | None = None
    published_at: datetime | None = None


class MarketDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    price: float | None
    change_pct: float | None
    vix: float | None
    vix_regime: VixRegime
    support: list[float]
    resistance: list[float]
    latest_close: float | None
    period_change_pct: float | None
    sma20: float | None
    sma50: float | None
    rsi14: float | None
    trend: Trend
    distance_to_support_pct: float | None
    distance_to_resistance_pct: float | None
    recent_candles: list[Candle]
    patterns: list[CandlestickPattern]
    headlines: list[DigestHeadline] = Field(default_factory=list)
    range: ChartRange
    chart_source: str | None
    as_of: datetime | None
    chart_as_of: datetime | None
    degraded: bool
    warnings: list[str]


def build_market_digest(snapshot: ChatMarketSnapshot) -> MarketDigest:
    latest_close = snapshot.candles[-1].c if snapshot.candles else snapshot.price
    period_change_pct = _period_change_pct(snapshot.candles)
    sma20 = _sma_value(snapshot, 20)
    sma50 = _sma_value(snapshot, 50)
    rsi14 = _latest_value(snapshot)
    trend = _trend(snapshot.candles, latest_close, sma20, sma50)
    return MarketDigest(
        symbol=snapshot.symbol,
        price=snapshot.price,
        change_pct=snapshot.change_pct,
        vix=snapshot.vix,
        vix_regime=_vix_regime(snapshot.vix),
        support=list(snapshot.support),
        resistance=list(snapshot.resistance),
        latest_close=latest_close,
        period_change_pct=period_change_pct,
        sma20=sma20,
        sma50=sma50,
        rsi14=rsi14,
        trend=trend,
        distance_to_support_pct=_distance_to_support_pct(
            snapshot.price, snapshot.support
        ),
        distance_to_resistance_pct=_distance_to_resistance_pct(
            snapshot.price, snapshot.resistance
        ),
        recent_candles=snapshot.candles[-20:],
        patterns=detect_patterns(snapshot.candles),
        headlines=[
            DigestHeadline(
                title=headline.title,
                publisher=headline.publisher,
                published_at=headline.published_at,
            )
            for headline in snapshot.news
        ],
        range=snapshot.range,
        chart_source=snapshot.chart_source,
        as_of=snapshot.as_of,
        chart_as_of=snapshot.chart_as_of,
        degraded=snapshot.degraded,
        warnings=list(snapshot.warnings),
    )


def _sma_value(snapshot: ChatMarketSnapshot, period: int) -> float | None:
    for series in snapshot.sma:
        if series.period == period and series.points:
            return series.points[-1].value
    return None


def _latest_value(snapshot: ChatMarketSnapshot) -> float | None:
    if not snapshot.rsi.points:
        return None
    return snapshot.rsi.points[-1].value


def _period_change_pct(candles: list[Candle]) -> float | None:
    if len(candles) < 2:
        return None
    first = candles[0].c
    last = candles[-1].c
    if first == 0:
        return None
    return round((last - first) / first * 100, 2)


def _trend(
    candles: list[Candle],
    latest_close: float | None,
    sma20: float | None,
    sma50: float | None,
) -> Trend:
    if latest_close is not None and sma20 is not None and sma50 is not None:
        if latest_close > sma20 > sma50:
            return "up"
        if latest_close < sma20 < sma50:
            return "down"
        return "sideways"
    if len(candles) >= 20:
        reference = candles[-20].c
        if reference == 0:
            return "unknown"
        change = (candles[-1].c - reference) / reference
        if change > 0.01:
            return "up"
        if change < -0.01:
            return "down"
        return "sideways"
    return "unknown"


def _vix_regime(vix: float | None) -> VixRegime:
    if vix is None:
        return "unknown"
    if vix < 20:
        return "calm"
    if vix < 30:
        return "elevated"
    return "panic"


def _distance_to_support_pct(
    price: float | None,
    support: list[float],
) -> float | None:
    if price is None or price <= 0:
        return None
    below = [level for level in support if level <= price]
    if not below:
        return None
    nearest = max(below)
    return round((price - nearest) / price * 100, 2)


def _distance_to_resistance_pct(
    price: float | None,
    resistance: list[float],
) -> float | None:
    if price is None or price <= 0:
        return None
    above = [level for level in resistance if level >= price]
    if not above:
        return None
    nearest = min(above)
    return round((nearest - price) / price * 100, 2)
