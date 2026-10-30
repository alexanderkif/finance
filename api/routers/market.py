from datetime import datetime
from typing import Literal

import httpx
from core.cboe_provider import (
    CboePayloadError,
    CboeRateLimitedError,
    CboeUnavailableError,
)
from core.finnhub_provider import (
    FinnhubConfigurationError,
    FinnhubProvider,
    FinnhubRateLimitError,
    FinnhubRequestError,
    NewsHeadline,
)
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from routers.options import get_options_provider

router = APIRouter()


class MarketSources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: Literal["cboe_delayed"] | None = None
    vix: Literal["cboe_delayed"] | None = None
    news: Literal["finnhub"] | None = None


class MarketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    price: float | None
    change_pct: float | None
    vix: float | None
    news: list[NewsHeadline]
    sources: MarketSources
    as_of: datetime | None
    quote_as_of: datetime | None
    vix_as_of: datetime | None
    news_as_of: datetime | None
    degraded: bool
    warnings: list[str]


def get_finnhub_provider(request: Request) -> FinnhubProvider:
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise TypeError("Market data client is not ready.")
    provider = getattr(request.app.state, "finnhub_provider", None)
    provider_client = getattr(request.app.state, "finnhub_provider_client", None)
    if not isinstance(provider, FinnhubProvider) or provider_client is not client:
        provider = FinnhubProvider(client)
        request.app.state.finnhub_provider = provider
        request.app.state.finnhub_provider_client = client
    return provider


@router.get("/api/market/{symbol}", response_model=MarketResponse)
async def get_market(symbol: str, request: Request) -> MarketResponse:
    normalized_symbol = symbol.strip().upper().removeprefix("_")
    if not normalized_symbol:
        normalized_symbol = symbol.strip().upper()

    provider = get_options_provider(request)
    warnings: list[str] = []
    quote = None
    vix_quote = None
    news: list[NewsHeadline] = []

    try:
        quote = await provider.get_market_quote(normalized_symbol)
    except (
        httpx.HTTPStatusError,
        httpx.RequestError,
        CboePayloadError,
        CboeRateLimitedError,
        CboeUnavailableError,
        ValueError,
    ):
        warnings.append("quote_unavailable")
    if quote is not None:
        if quote.price is None:
            warnings.append("price_unavailable")
        if quote.change_pct is None:
            warnings.append("change_pct_unavailable")

    try:
        vix_quote = await provider.get_index_quote("VIX")
    except (
        httpx.HTTPStatusError,
        httpx.RequestError,
        CboePayloadError,
        CboeRateLimitedError,
        CboeUnavailableError,
        ValueError,
    ):
        warnings.append("vix_unavailable")
    if vix_quote is not None and vix_quote.price is None:
        warnings.append("vix_unavailable")

    try:
        news = await get_finnhub_provider(request).get_headlines(normalized_symbol)
    except FinnhubConfigurationError:
        warnings.append("news_provider_not_configured")
    except FinnhubRateLimitError:
        warnings.append("news_rate_limited")
    except (FinnhubRequestError, ValueError):
        warnings.append("news_unavailable")
    if not news and "news_provider_not_configured" not in warnings:
        warnings.append("news_unavailable")

    quote_as_of = quote.as_of if quote is not None else None
    vix_as_of = vix_quote.as_of if vix_quote is not None else None
    news_as_of = max(
        (
            headline.published_at
            for headline in news
            if headline.published_at is not None
        ),
        default=None,
    )
    timestamps = [
        timestamp
        for timestamp in (quote_as_of, vix_as_of, news_as_of)
        if timestamp is not None
    ]

    return MarketResponse(
        symbol=normalized_symbol,
        price=quote.price if quote is not None else None,
        change_pct=quote.change_pct if quote is not None else None,
        vix=vix_quote.price if vix_quote is not None else None,
        news=news,
        sources=MarketSources(
            quote="cboe_delayed" if quote is not None else None,
            vix="cboe_delayed" if vix_quote is not None else None,
            news="finnhub" if news else None,
        ),
        as_of=max(timestamps) if timestamps else None,
        quote_as_of=quote_as_of,
        vix_as_of=vix_as_of,
        news_as_of=news_as_of,
        degraded=bool(warnings),
        warnings=warnings,
    )
