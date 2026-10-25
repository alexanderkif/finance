from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Final, Literal, TypeAlias, cast
from urllib.parse import quote as url_quote

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, JsonValue

YAHOO_BASE_URL_Q1: Final = "https://query1.finance.yahoo.com"
YAHOO_BASE_URL_Q2: Final = "https://query2.finance.yahoo.com"

ChartRange: TypeAlias = Literal[
    "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"
]
ChartInterval: TypeAlias = Literal["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]


class Candle(BaseModel):
    timestamp: int
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class CandlesResponse(BaseModel):
    ticker: str
    range: str
    interval: str
    count: int
    candles: list[Candle]


class SearchQuote(BaseModel):
    symbol: str | None
    shortname: str | None
    longname: str | None
    exchange: str | None
    type: str | None


class SearchNews(BaseModel):
    title: str | None
    publisher: str | None
    link: str | None
    pubtime: int | None
    tickers: list[str]


class SearchResponse(BaseModel):
    query: str
    quotes_count: int
    quotes: list[SearchQuote]
    news_count: int
    news: list[SearchNews]


class InsightsResponse(BaseModel):
    ticker: str
    trends: dict[str, JsonValue]
    key_levels: dict[str, JsonValue]
    provider: str | None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(headers=headers, http2=True, timeout=10.0) as client:
        app.state.http_client = client
        yield


app: Final = FastAPI(
    title="Yahoo Finance API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


def get_http_client(request: Request) -> httpx.AsyncClient:
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise HTTPException(status_code=503, detail="Market data client is not ready.")
    return client


def as_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, object] = {}
    entries = cast(Mapping[object, object], value)
    for key, item in entries.items():
        if isinstance(key, str):
            result[key] = item
    return result


def as_objects(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def as_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def as_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def as_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        items = cast(list[object], value)
        return [as_json_value(item) for item in items]
    if isinstance(value, Mapping):
        entries = cast(Mapping[object, object], value)
        return {
            key: as_json_value(item)
            for key, item in entries.items()
            if isinstance(key, str)
        }
    return str(value)


async def fetch_yahoo_json(
    client: httpx.AsyncClient,
    url: str,
    params: Mapping[str, str],
) -> Mapping[str, object]:
    try:
        response = await client.get(url, params=params)
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail="Market data provider could not be reached.",
        ) from error

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="No market data was found for this request.",
            ) from error
        raise HTTPException(
            status_code=502,
            detail="Market data provider returned an error.",
        ) from error

    try:
        return as_mapping(response.json())
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="Market data provider returned an invalid response.",
        ) from error


@app.get("/api/candles/{ticker}", response_model=CandlesResponse)
async def get_candles(
    ticker: str,
    request: Request,
    range_period: Annotated[
        ChartRange,
        Query(alias="range", description="History period for the chart."),
    ] = "6mo",
    interval: Annotated[
        ChartInterval,
        Query(description="Candle interval."),
    ] = "1d",
) -> CandlesResponse:
    symbol = ticker.upper()
    data = await fetch_yahoo_json(
        get_http_client(request),
        f"{YAHOO_BASE_URL_Q1}/v8/finance/chart/{url_quote(symbol, safe='')}",
        {"range": range_period, "interval": interval},
    )

    chart = as_mapping(data.get("chart"))
    result_list = as_objects(chart.get("result"))
    if not result_list:
        raise HTTPException(status_code=404, detail=f"Ticker {symbol} was not found.")

    result = as_mapping(result_list[0])
    timestamps = [as_number(value) for value in as_objects(result.get("timestamp"))]
    indicators = as_mapping(result.get("indicators"))
    quotes = as_objects(indicators.get("quote"))
    quote = as_mapping(quotes[0]) if quotes else {}
    opens = [as_number(value) for value in as_objects(quote.get("open"))]
    highs = [as_number(value) for value in as_objects(quote.get("high"))]
    lows = [as_number(value) for value in as_objects(quote.get("low"))]
    closes = [as_number(value) for value in as_objects(quote.get("close"))]
    volumes = [as_number(value) for value in as_objects(quote.get("volume"))]

    candles: list[Candle] = []
    for index, timestamp in enumerate(timestamps):
        if (
            timestamp is None
            or index >= len(opens)
            or index >= len(closes)
            or opens[index] is None
            or closes[index] is None
        ):
            continue

        opening = opens[index]
        closing = closes[index]
        if opening is None or closing is None:
            continue
        high = highs[index] if index < len(highs) else None
        low = lows[index] if index < len(lows) else None
        volume = volumes[index] if index < len(volumes) else None
        timestamp_seconds = int(timestamp)

        candles.append(
            Candle(
                timestamp=timestamp_seconds,
                date=datetime.fromtimestamp(
                    timestamp_seconds,
                    tz=timezone.utc,
                ).strftime("%Y-%m-%d %H:%M:%S"),
                open=round(opening, 2),
                high=round(high, 2) if high is not None else round(opening, 2),
                low=round(low, 2) if low is not None else round(opening, 2),
                close=round(closing, 2),
                volume=int(volume) if volume is not None else 0,
            )
        )

    return CandlesResponse(
        ticker=symbol,
        range=range_period,
        interval=interval,
        count=len(candles),
        candles=candles,
    )


@app.get("/api/insights/{ticker}", response_model=InsightsResponse)
async def get_technical_insights(ticker: str, request: Request) -> InsightsResponse:
    symbol = ticker.upper()
    data = await fetch_yahoo_json(
        get_http_client(request),
        f"{YAHOO_BASE_URL_Q1}/ws/insights/v1/finance/insights",
        {"symbol": symbol},
    )

    finance = as_mapping(data.get("finance"))
    result = as_mapping(finance.get("result"))
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No technical insights were found for {symbol}.",
        )

    instrument = as_mapping(result.get("instrumentInfo"))
    events = as_mapping(instrument.get("technicalEvents"))
    technicals = as_mapping(instrument.get("keyTechnicals"))
    trend_keys = {
        "short_term": "shortTerm",
        "mid_term": "midTerm",
        "long_term": "longTerm",
    }
    level_keys = {
        "support": "support",
        "resistance": "resistance",
        "stop_loss": "stopLoss",
    }

    return InsightsResponse(
        ticker=symbol,
        trends={
            key: as_json_value(events.get(source))
            for key, source in trend_keys.items()
        },
        key_levels={
            key: as_json_value(technicals.get(source))
            for key, source in level_keys.items()
        },
        provider=as_string(events.get("provider")),
    )


@app.get("/api/search", response_model=SearchResponse)
async def search_symbols_and_news(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> SearchResponse:
    data = await fetch_yahoo_json(
        get_http_client(request),
        f"{YAHOO_BASE_URL_Q2}/v1/finance/search",
        {"q": q},
    )

    quotes = [
        SearchQuote(
            symbol=as_string(item.get("symbol")),
            shortname=as_string(item.get("shortname")),
            longname=as_string(item.get("longname")),
            exchange=as_string(item.get("exchange")),
            type=as_string(item.get("quoteType")),
        )
        for item in map(as_mapping, as_objects(data.get("quotes")))
    ]
    news = [
        SearchNews(
            title=as_string(item.get("title")),
            publisher=as_string(item.get("publisher")),
            link=as_string(item.get("link")),
            pubtime=(
                int(timestamp)
                if (timestamp := as_number(item.get("providerPublishTime"))) is not None
                else None
            ),
            tickers=[
                ticker
                for ticker in as_objects(item.get("relatedTickers"))
                if isinstance(ticker, str)
            ],
        )
        for item in map(as_mapping, as_objects(data.get("news")))
    ]

    return SearchResponse(
        query=q,
        quotes_count=len(quotes),
        quotes=quotes,
        news_count=len(news),
        news=news,
    )
