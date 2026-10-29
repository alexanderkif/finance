import time
from datetime import UTC, date, datetime, timedelta
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict
from settings import require_finnhub_api_key

FINNHUB_BASE_URL: Final = "https://finnhub.io/api/v1"
FINNHUB_CACHE_TTL_SECONDS: Final = 300.0
FINNHUB_NEWS_WINDOW_DAYS: Final = 7


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


class FinnhubProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache_ttl_seconds: float = FINNHUB_CACHE_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, list[NewsHeadline]]] = {}

    async def get_headlines(
        self,
        symbol: str,
        limit: int = 3,
        today: date | None = None,
    ) -> list[NewsHeadline]:
        normalized_symbol = symbol.strip().upper().removeprefix("_").removeprefix("^")
        if not normalized_symbol:
            raise ValueError("Symbol must not be empty.")
        cached = self._cache.get(normalized_symbol)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl_seconds:
            return cached[1][:limit]

        try:
            api_key = require_finnhub_api_key()
        except RuntimeError as error:
            raise FinnhubConfigurationError(str(error)) from error

        current_day = today or datetime.now(UTC).date()
        start_day = current_day - timedelta(days=FINNHUB_NEWS_WINDOW_DAYS)
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
        if not items:
            items = await self._get_items(
                "news",
                {"category": "general"},
                headers,
            )

        headlines = _normalize_headlines(items, limit=limit)
        self._cache[normalized_symbol] = (time.monotonic(), headlines)
        return headlines

    async def _get_items(
        self,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> list[object]:
        try:
            response = await self._client.get(
                f"{FINNHUB_BASE_URL}/{path}",
                params=params,
                headers=headers,
                timeout=15.0,
            )
        except httpx.RequestError as error:
            raise FinnhubRequestError(
                "The news provider could not be reached."
            ) from error

        if response.status_code == 429:
            raise FinnhubRateLimitError("The news provider rate limit was reached.")
        if response.status_code in (401, 403):
            raise FinnhubConfigurationError("The news provider key was rejected.")
        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            raise FinnhubRequestError(
                f"The news provider returned HTTP {response.status_code}."
            )
        try:
            data = response.json()
        except ValueError as error:
            raise FinnhubRequestError(
                "The news provider returned an invalid payload."
            ) from error
        if not isinstance(data, list):
            raise FinnhubRequestError("The news provider returned an invalid payload.")
        return list(data)


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
