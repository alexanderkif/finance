from datetime import datetime
from typing import Annotated, Literal

import httpx
from core.cboe_history_provider import (
    CboeHistoryError,
    CboeHistoryProvider,
)
from core.indicators import (
    Candle,
    ChartRange,
    IndicatorSeries,
    chart_levels,
    relative_strength_index,
    simple_moving_average,
)
from core.twelvedata_provider import (
    TwelveDataConfigurationError,
    TwelveDataError,
    TwelveDataNotFoundError,
    TwelveDataPlanError,
    TwelveDataProvider,
    TwelveDataRateLimitError,
)
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

router = APIRouter()

ChartSource = Literal["twelve_data", "cboe_index_history"]


class ChartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    range: ChartRange
    interval: Literal["1d"]
    candles: list[Candle]
    sma: list[IndicatorSeries]
    rsi: IndicatorSeries
    support: list[float]
    resistance: list[float]
    source: ChartSource | None
    as_of: datetime | None
    degraded: bool
    warnings: list[str]


def get_twelve_data_provider(request: Request) -> TwelveDataProvider:
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise TypeError("Market data client is not ready.")
    provider = getattr(request.app.state, "twelve_data_provider", None)
    provider_client = getattr(request.app.state, "twelve_data_provider_client", None)
    if not isinstance(provider, TwelveDataProvider) or provider_client is not client:
        provider = TwelveDataProvider(client)
        request.app.state.twelve_data_provider = provider
        request.app.state.twelve_data_provider_client = client
    return provider


def get_cboe_history_provider(request: Request) -> CboeHistoryProvider:
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise TypeError("Market data client is not ready.")
    provider = getattr(request.app.state, "cboe_history_provider", None)
    provider_client = getattr(request.app.state, "cboe_history_provider_client", None)
    if not isinstance(provider, CboeHistoryProvider) or provider_client is not client:
        provider = CboeHistoryProvider(client)
        request.app.state.cboe_history_provider = provider
        request.app.state.cboe_history_provider_client = client
    return provider


@router.get("/api/chart/{symbol}", response_model=ChartResponse)
async def get_chart(
    symbol: str,
    request: Request,
    range_period: Annotated[
        ChartRange,
        Query(alias="range", description="History period for the chart."),
    ] = "6mo",
    interval: Annotated[
        Literal["1d"],
        Query(description="Candle interval."),
    ] = "1d",
) -> ChartResponse:
    normalized_symbol = symbol.strip().upper().removeprefix("_").removeprefix("^")
    if not normalized_symbol:
        raise HTTPException(status_code=422, detail="Symbol must not be empty.")

    candles: list[Candle] | None = None
    source: ChartSource | None = None
    history = get_cboe_history_provider(request)
    if history.supports(normalized_symbol):
        try:
            candles = await history.get_index_candles(
                normalized_symbol,
                range_period,
            )
            source = "cboe_index_history"
        except CboeHistoryError:
            candles = None

    if candles is None:
        try:
            candles = await get_twelve_data_provider(request).get_daily_candles(
                normalized_symbol,
                range_period,
            )
            source = "twelve_data"
        except TwelveDataPlanError:
            return _unavailable(
                normalized_symbol,
                range_period,
                interval,
                "symbol_requires_paid_plan",
            )
        except TwelveDataNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except TwelveDataConfigurationError:
            return _unavailable(
                normalized_symbol,
                range_period,
                interval,
                "candles_provider_not_configured",
            )
        except TwelveDataRateLimitError:
            return _unavailable(
                normalized_symbol,
                range_period,
                interval,
                "candles_rate_limited",
            )
        except TwelveDataError:
            return _unavailable(
                normalized_symbol,
                range_period,
                interval,
                "candles_unavailable",
            )

    if candles is None or not candles:
        return _unavailable(
            normalized_symbol,
            range_period,
            interval,
            "candles_unavailable",
        )

    warnings: list[str] = []
    if not any((candle.v or 0) > 0 for candle in candles):
        warnings.append("volume_unavailable")

    sma_series = [
        simple_moving_average(candles, 20),
        simple_moving_average(candles, 50),
    ]
    rsi_series = relative_strength_index(candles, 14)
    support, resistance = chart_levels(candles)

    return ChartResponse(
        symbol=normalized_symbol,
        range=range_period,
        interval=interval,
        candles=candles,
        sma=sma_series,
        rsi=rsi_series,
        support=support,
        resistance=resistance,
        source=source,
        as_of=candles[-1].t,
        degraded=bool(warnings),
        warnings=warnings,
    )


def _unavailable(
    symbol: str,
    range_period: ChartRange,
    interval: Literal["1d"],
    warning: str,
) -> ChartResponse:
    return ChartResponse(
        symbol=symbol,
        range=range_period,
        interval=interval,
        candles=[],
        sma=[],
        rsi=IndicatorSeries(period=14, points=[]),
        support=[],
        resistance=[],
        source=None,
        as_of=None,
        degraded=True,
        warnings=[warning],
    )
