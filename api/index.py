import os
import re
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from routers.analysis import router as analysis_router
from routers.chart import router as chart_router
from routers.chat import router as chat_router
from routers.market import router as market_router
from routers.options import router as options_router

_IS_PRODUCTION: Final = os.getenv("VERCEL_ENV") == "production"
_RATE_LIMIT_ENABLED: Final = _IS_PRODUCTION or os.getenv("RATE_LIMIT_ENABLED") == "1"
_RATE_LIMITS: Final = (
    (re.compile(r"^/api/chat/turn$"), 20, 60.0),
    (re.compile(r"^/api/analysis/"), 30, 60.0),
    (re.compile(r"^/api/"), 120, 60.0),
)
_RATE_HITS: dict[tuple[str, str], list[float]] = {}


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
    docs_url=None if _IS_PRODUCTION else "/api/docs",
    redoc_url=None if _IS_PRODUCTION else "/api/redoc",
    openapi_url=None if _IS_PRODUCTION else "/api/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if not _RATE_LIMIT_ENABLED or not request.url.path.startswith("/api/"):
        return await call_next(request)
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    now = time.monotonic()
    for pattern, limit, window in _RATE_LIMITS:
        if not pattern.search(request.url.path):
            continue
        key = (pattern.pattern, ip)
        hits = [hit for hit in _RATE_HITS.get(key, []) if now - hit < window]
        if len(hits) >= limit:
            retry_after = max(1, int(window - (now - hits[0])) + 1)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        "Too many requests. "
                        f"Try again in {retry_after} seconds."
                    )
                },
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
        _RATE_HITS[key] = hits
        break
    if len(_RATE_HITS) > 5_000:
        _RATE_HITS.clear()
    return await call_next(request)


app.include_router(options_router)
app.include_router(market_router)
app.include_router(chart_router)
app.include_router(chat_router)
app.include_router(analysis_router)
