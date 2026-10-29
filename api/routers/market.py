from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.cboe_provider import CboeMarketQuote, CboePayloadError
from routers.options import get_options_provider

router = APIRouter()


class MarketNewsHeadline(BaseModel):
    title: str
    publisher: str | None = None
    url: str | None = None
    published_at: datetime | None = None


def empty_float_list() -> list[float]:
    return []


def empty_news_list() -> list[MarketNewsHeadline]:
    return []


class MarketResponse(BaseModel):
    symbol: str
    price: float | None
    change_pct: float | None
    support: list[float] = Field(default_factory=empty_float_list)
    resistance: list[float] = Field(default_factory=empty_float_list)
    vix: float | None = None
    news: list[MarketNewsHeadline] = Field(default_factory=empty_news_list)
    source: Literal["cboe_delayed"] = "cboe_delayed"
    as_of: datetime
    degraded: bool
    warnings: list[str] = Field(default_factory=list)


def build_market_response(quote: CboeMarketQuote) -> MarketResponse:
    warnings = [
        "support_resistance_unavailable",
        "vix_unavailable",
        "news_unavailable",
    ]
    if quote.price is None:
        warnings.append("price_unavailable")
    if quote.change_pct is None:
        warnings.append("change_pct_unavailable")

    return MarketResponse(
        symbol=quote.symbol,
        price=quote.price,
        change_pct=quote.change_pct,
        source=quote.source,
        as_of=quote.as_of,
        degraded=True,
        warnings=warnings,
    )


@router.get("/api/market/{symbol}", response_model=MarketResponse)
async def get_market(symbol: str, request: Request) -> MarketResponse:
    provider = get_options_provider(request)
    try:
        quote = await provider.get_market_quote(symbol)
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail="CBOE market data could not be reached.",
        ) from error
    except httpx.HTTPStatusError as error:
        status_code = 404 if error.response.status_code == 404 else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"CBOE market provider returned HTTP {error.response.status_code}.",
        ) from error
    except CboePayloadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return build_market_response(quote)
