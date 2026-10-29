from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final

import httpx
from fastapi import FastAPI
from routers.analysis import router as analysis_router
from routers.chart import router as chart_router
from routers.market import router as market_router
from routers.options import router as options_router


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
    title="Options Strategy Assistant API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.include_router(options_router)
app.include_router(market_router)
app.include_router(chart_router)
app.include_router(analysis_router)
