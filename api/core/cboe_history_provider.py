import csv
import io
import time
from datetime import UTC, datetime
from typing import Final

import httpx
from core.indicators import RANGE_OUTPUT_SIZES, Candle, ChartRange

CBOE_HISTORY_URL: Final = (
    "https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv"
)
CBOE_HISTORY_CACHE_TTL_SECONDS: Final = 3_600.0
SUPPORTED_SYMBOLS: Final = frozenset({"XSP", "VIX"})


class CboeHistoryError(RuntimeError):
    pass


class CboeHistoryNotSupportedError(CboeHistoryError):
    pass


class CboeHistoryNotFoundError(CboeHistoryError):
    pass


class CboeHistoryRequestError(CboeHistoryError):
    pass


class CboeHistoryPayloadError(CboeHistoryError):
    pass


class CboeHistoryProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache_ttl_seconds: float = CBOE_HISTORY_CACHE_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, list[Candle]]] = {}

    def supports(self, symbol: str) -> bool:
        return _normalize_symbol(symbol) in SUPPORTED_SYMBOLS

    async def get_index_candles(
        self,
        symbol: str,
        range_period: ChartRange,
    ) -> list[Candle]:
        normalized = _normalize_symbol(symbol)
        if normalized not in SUPPORTED_SYMBOLS:
            raise CboeHistoryNotSupportedError(
                f"CBOE history is not available for {normalized}."
            )
        output_size = RANGE_OUTPUT_SIZES[range_period]
        cached = self._cache.get(normalized)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl_seconds:
            return cached[1][-output_size:]

        try:
            response = await self._client.get(
                CBOE_HISTORY_URL.format(symbol=normalized),
                follow_redirects=True,
                timeout=20.0,
            )
        except httpx.RequestError as error:
            raise CboeHistoryRequestError(
                "The CBOE history file could not be reached."
            ) from error

        if response.status_code in (403, 404):
            raise CboeHistoryNotFoundError(
                f"No CBOE history was found for {normalized}."
            )
        if response.status_code >= 400:
            raise CboeHistoryRequestError(
                f"The CBOE history file returned HTTP {response.status_code}."
            )

        candles = _parse_history(response.content.decode("utf-8-sig"))
        if not candles:
            raise CboeHistoryPayloadError(
                f"The CBOE history file for {normalized} contained no candles."
            )
        self._cache[normalized] = (time.monotonic(), candles)
        return candles[-output_size:]


def _parse_history(text: str) -> list[Candle]:
    candles: list[Candle] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            day = datetime.strptime(row["DATE"].strip(), "%m/%d/%Y").replace(tzinfo=UTC)
            opening = float(row["OPEN"])
            high = float(row["HIGH"])
            low = float(row["LOW"])
            close = float(row["CLOSE"])
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if min(opening, high, low, close) <= 0:
            continue
        candles.append(Candle(t=day, o=opening, h=high, l=low, c=close, v=None))
    candles.sort(key=lambda candle: candle.t)
    return candles


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().removeprefix("_").removeprefix("^")
