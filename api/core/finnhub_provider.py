import asyncio
import time
from datetime import UTC, date, datetime, timedelta
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict
from settings import require_finnhub_api_key

FINNHUB_BASE_URL: Final = "https://finnhub.io/api/v1"
FINNHUB_CACHE_TTL_SECONDS: Final = 300.0
FINNHUB_NEWS_WINDOW_DAYS: Final = 7
FINNHUB_ANALYSIS_NEWS_WINDOW_DAYS: Final = 30
FINNHUB_RETRY_DELAY_SECONDS: Final = 0.25
FINNHUB_MAX_CACHED_HEADLINES: Final = 20


class FinnhubError(RuntimeError):
    pass


class FinnhubConfigurationError(FinnhubError):
    pass


class FinnhubRateLimitError(FinnhubError):
    pass


class FinnhubRequestError(FinnhubError):
    pass


class NewsHeadline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    publisher: str | None = None
    published_at: datetime | None = None


class EarningsEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    quarter: int | None = None
    year: int | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None


class FinnhubProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache_ttl_seconds: float = FINNHUB_CACHE_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[
            tuple[str, int, bool],
            tuple[float, list[NewsHeadline]],
        ] = {}
        self._earnings_cache: dict[str, tuple[float, list[EarningsEvent]]] = {}

    async def get_headlines(
        self,
        symbol: str,
        limit: int = 3,
        today: date | None = None,
        *,
        window_days: int = FINNHUB_NEWS_WINDOW_DAYS,
        allow_general_fallback: bool = True,
    ) -> list[NewsHeadline]:
        normalized_symbol = symbol.strip().upper().removeprefix("_").removeprefix("^")
        if not normalized_symbol:
            raise ValueError("Symbol must not be empty.")
        if window_days < 1:
            raise ValueError("The news window must be at least one day.")
        cache_key = (normalized_symbol, window_days, allow_general_fallback)
        cached = self._cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl_seconds:
            return cached[1][:limit]

        try:
            api_key = require_finnhub_api_key()
        except RuntimeError as error:
            raise FinnhubConfigurationError(str(error)) from error

        current_day = today or datetime.now(UTC).date()
        start_day = current_day - timedelta(days=window_days)
        headers = {"X-Finnhub-Token": api_key}

        try:
            items = await self._get_items(
                "company-news",
                {
                    "symbol": normalized_symbol,
                    "from": start_day.isoformat(),
                    "to": current_day.isoformat(),
                },
                headers,
            )
        except FinnhubRequestError:
            items = []
        if not items and allow_general_fallback:
            items = await self._get_items(
                "news",
                {"category": "general"},
                headers,
            )

        headlines = _normalize_headlines(
            items,
            limit=FINNHUB_MAX_CACHED_HEADLINES,
        )
        self._cache[cache_key] = (time.monotonic(), headlines)
        return headlines[:limit]

    async def get_analysis_headlines(
        self,
        symbol: str,
        limit: int = 5,
    ) -> list[NewsHeadline]:
        return await self.get_headlines(
            symbol,
            limit=limit,
            window_days=FINNHUB_ANALYSIS_NEWS_WINDOW_DAYS,
            allow_general_fallback=False,
        )

    async def get_earnings(
        self,
        symbol: str,
        limit: int = 4,
        today: date | None = None,
        *,
        past_days: int = 30,
        future_days: int = 90,
    ) -> list[EarningsEvent]:
        normalized_symbol = symbol.strip().upper().removeprefix("_").removeprefix("^")
        if not normalized_symbol:
            raise ValueError("Symbol must not be empty.")
        if limit < 1 or limit > 20:
            raise ValueError("The earnings limit must be between 1 and 20.")
        cached = self._earnings_cache.get(normalized_symbol)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl_seconds:
            return cached[1][:limit]

        try:
            api_key = require_finnhub_api_key()
        except RuntimeError as error:
            raise FinnhubConfigurationError(str(error)) from error

        current_day = today or datetime.now(UTC).date()
        data = await self._get_json(
            "calendar/earnings",
            {
                "symbol": normalized_symbol,
                "from": (current_day - timedelta(days=past_days)).isoformat(),
                "to": (current_day + timedelta(days=future_days)).isoformat(),
            },
            {"X-Finnhub-Token": api_key},
        )
        if data is None:
            return []
        if not isinstance(data, dict):
            raise FinnhubRequestError(
                "The earnings provider returned an invalid payload."
            )
        items = data.get("earningsCalendar")
        if not isinstance(items, list):
            raise FinnhubRequestError(
                "The earnings provider returned an invalid payload."
            )

        events: list[EarningsEvent] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("date")
            if not isinstance(raw_date, str):
                continue
            try:
                event_date = date.fromisoformat(raw_date)
            except ValueError:
                continue
            events.append(
                EarningsEvent(
                    date=event_date,
                    quarter=_optional_int(item.get("quarter")),
                    year=_optional_int(item.get("year")),
                    eps_estimate=_optional_float(item.get("epsEstimate")),
                    eps_actual=_optional_float(item.get("epsActual")),
                    revenue_estimate=_optional_float(item.get("revenueEstimate")),
                    revenue_actual=_optional_float(item.get("revenueActual")),
                )
            )
        events.sort(key=lambda event: event.date)
        self._earnings_cache[normalized_symbol] = (time.monotonic(), events)
        return events[:limit]

    async def _get_json(
        self,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> object | None:
        attempts = 2
        response: httpx.Response | None = None
        for attempt in range(attempts):
            try:
                response = await self._client.get(
                    f"{FINNHUB_BASE_URL}/{path}",
                    params=params,
                    headers=headers,
                    timeout=15.0,
                )
            except httpx.RequestError as error:
                if attempt < attempts - 1:
                    await asyncio.sleep(FINNHUB_RETRY_DELAY_SECONDS)
                    continue
                raise FinnhubRequestError(
                    "The news provider could not be reached."
                ) from error
            if 500 <= response.status_code < 600 and attempt < attempts - 1:
                await asyncio.sleep(FINNHUB_RETRY_DELAY_SECONDS)
                continue
            break

        if response is None:
            raise FinnhubRequestError("The news provider did not respond.")
        if response.status_code == 429:
            raise FinnhubRateLimitError("The news provider rate limit was reached.")
        if response.status_code in (401, 403):
            raise FinnhubConfigurationError("The news provider key was rejected.")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise FinnhubRequestError(
                f"The news provider returned HTTP {response.status_code}."
            )
        try:
            return response.json()
        except ValueError as error:
            raise FinnhubRequestError(
                "The news provider returned an invalid payload."
            ) from error

    async def _get_items(
        self,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> list[object]:
        data = await self._get_json(path, params, headers)
        if data is None:
            return []
        if not isinstance(data, list):
            raise FinnhubRequestError("The news provider returned an invalid payload.")
        return list(data)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _normalize_headlines(
    items: list[object],
    *,
    limit: int,
) -> list[NewsHeadline]:
    candidates: list[tuple[int, str, str, str | None, datetime]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("headline")
        url = item.get("url")
        timestamp = item.get("datetime")
        if not isinstance(title, str) or not isinstance(url, str):
            continue
        if not isinstance(timestamp, int) or timestamp <= 0:
            continue
        publisher = item.get("source")
        candidates.append(
            (
                timestamp,
                title,
                url,
                publisher if isinstance(publisher, str) else None,
                datetime.fromtimestamp(timestamp, tz=UTC),
            )
        )
    candidates.sort(key=lambda entry: entry[0], reverse=True)
    return [
        NewsHeadline(
            title=title,
            url=url,
            publisher=publisher,
            published_at=published_at,
        )
        for _, title, url, publisher, published_at in candidates[:limit]
    ]
