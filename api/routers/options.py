from datetime import date
from typing import Annotated

import httpx
from core.cboe_provider import (
    CboeOptionsProvider,
    CboePayloadError,
    OptionChainResponse,
)
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


def get_options_provider(request: Request) -> CboeOptionsProvider:
    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise HTTPException(
            status_code=503,
            detail="Market data client is not ready.",
        )

    provider = getattr(request.app.state, "cboe_options_provider", None)
    provider_client = getattr(request.app.state, "cboe_provider_client", None)
    if not isinstance(provider, CboeOptionsProvider) or provider_client is not client:
        provider = CboeOptionsProvider(client)
        request.app.state.cboe_options_provider = provider
        request.app.state.cboe_provider_client = client
    return provider


@router.get(
    "/api/options/chain/{symbol}",
    response_model=OptionChainResponse,
)
async def get_options_chain(
    symbol: str,
    request: Request,
    expiration: Annotated[
        date | None,
        Query(description="Filter contracts by expiration date."),
    ] = None,
) -> OptionChainResponse:
    provider = get_options_provider(request)
    try:
        return await provider.get_chain(symbol, expiration)
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail="CBOE options data could not be reached.",
        ) from error
    except httpx.HTTPStatusError as error:
        status_code = 404 if error.response.status_code == 404 else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"CBOE options provider returned HTTP {error.response.status_code}.",
        ) from error
    except CboePayloadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
