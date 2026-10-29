import time
from datetime import UTC, datetime
from typing import Final

import httpx
from core.indicators import RANGE_OUTPUT_SIZES, Candle, ChartRange
from pydantic import BaseModel, ConfigDict, ValidationError
from settings import require_twelve_data_api_key

TWELVE_DATA_URL: Final = "https://api.twelvedata.com/time_series"
TWELVE_DATA_CACHE_TTL_SECONDS: Final = 60.0


class TwelveDataError(RuntimeError):
    pass


class TwelveDataConfigurationError(TwelveDataError):
    pass


class TwelveDataRateLimitError(TwelveDataError):
    pass


class TwelveDataNotFoundError(TwelveDataError):
    pass


class TwelveDataPlanError(TwelveDataError):
    pass


class TwelveDataRequestError(TwelveDataError):
    pass


class TwelveDataPayloadError(TwelveDataError):
    pass


class _TimeSeriesValue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    datetime: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class _TimeSeriesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str | None = None
    values: list[_TimeSeriesValue] = []
    code: int | None = None
    message: str | None = None


class TwelveDataProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache_ttl_seconds: float = TWELVE_DATA_CACHE_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[tuple[str, ChartRange], tuple[float, list[Candle]]] = {}

    async def get_daily_candles(
        self,
        symbol: str,
        range_period: ChartRange,
    ) -> list[Candle]:
        normalized_symbol = symbol.strip().upper().removeprefix("_").removeprefix("^")
        if not normalized_symbol:
            raise ValueError("Symbol must not be empty.")
        output_size = RANGE_OUTPUT_SIZES[range_period]
        key = (normalized_symbol, range_period)
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl_seconds:
            return cached[1]

        try:
            api_key = require_twelve_data_api_key()
        except RuntimeError as error:
            raise TwelveDataConfigurationError(str(error)) from error

        try:
            response = await self._client.get(
                TWELVE_DATA_URL,
                params={
                    "symbol": normalized_symbol,
                    "interval": "1day",
                    "outputsize": str(output_size),
                    "format": "JSON",
                },
                headers={"Authorization": f"apikey {api_key}"},
                timeout=20.0,
            )
        except httpx.RequestError as error:
            raise TwelveDataRequestError(
                "The candle provider could not be reached."
            ) from error

        try:
            data = response.json()
        except ValueError:
            data = None

        if response.status_code >= 400:
            api_code = data.get("code") if isinstance(data, dict) else None
            api_message = data.get("message") if isinstance(data, dict) else None
            self._raise_for_api_error(
                api_code if isinstance(api_code, int) else response.status_code,
                api_message if isinstance(api_message, str) else None,
            )

        try:
            payload = _TimeSeriesResponse.model_validate(data)
        except (ValidationError, ValueError) as error:
            raise TwelveDataPayloadError(
                "The candle provider returned an invalid payload."
            ) from error
        if payload.status == "error":
            self._raise_for_api_error(payload.code, payload.message)
        if not payload.values:
            raise TwelveDataPayloadError(
                "The candle provider returned no data for this symbol."
            )

        candles = sorted(
            (
                Candle(
                    t=_parse_datetime(value.datetime),
                    o=value.open,
                    h=value.high,
                    l=value.low,
                    c=value.close,
                    v=value.volume,
                )
                for value in payload.values
            ),
            key=lambda candle: candle.t,
        )
        self._cache[key] = (time.monotonic(), candles)
        return candles

    def _raise_for_api_error(
        self,
        code: int | None,
        message: str | None,
    ) -> None:
        detail = message or "The candle provider returned an error."
        if code == 429:
            raise TwelveDataRateLimitError(detail)
        if code in (401, 403):
            raise TwelveDataConfigurationError(detail)
        if code == 404:
            lowered = detail.lower()
            if "plan" in lowered or "upgrade" in lowered:
                raise TwelveDataPlanError(detail)
            raise TwelveDataNotFoundError(detail)
        raise TwelveDataRequestError(detail)


def _parse_datetime(value: str) -> datetime:
    for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise TwelveDataPayloadError(
        f"The candle provider returned an invalid date: {value}."
    )
