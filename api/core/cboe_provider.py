import re
import time
from datetime import date, datetime
from typing import Final, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

CBOE_OPTIONS_URL: Final = (
    "https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
)
CBOE_CACHE_TTL_SECONDS: Final = 60.0
_INDEX_SYMBOLS: Final = frozenset({"SPX", "VIX", "NDX"})
_OCC_EXPIRATION_PATTERN: Final = re.compile(r"(?P<expiration>\d{6})[CP]\d{8}$")


class CboePayloadError(RuntimeError):
    pass


class CboeOptionQuote(BaseModel):
    model_config = ConfigDict(extra="ignore")

    option: str
    bid: float | None = None
    ask: float | None = None
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: float | None = None
    volume: float | None = None


class _CboeOptionsData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str
    options: list[CboeOptionQuote]
    current_price: float | None = None
    price_change_percent: float | None = None


class _CboeOptionsPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timestamp: datetime
    symbol: str
    data: _CboeOptionsData


class OptionChainResponse(BaseModel):
    symbol: str
    expiration: date | None = None
    contracts: list[CboeOptionQuote]
    source: Literal["cboe_delayed"] = "cboe_delayed"
    as_of: datetime
    warnings: list[str] = Field(default_factory=list)


class CboeMarketQuote(BaseModel):
    symbol: str
    price: float | None
    change_pct: float | None
    source: Literal["cboe_delayed"] = "cboe_delayed"
    as_of: datetime


def option_expiration(option_symbol: str) -> date | None:
    match = _OCC_EXPIRATION_PATTERN.search(option_symbol)
    if match is None:
        return None
    try:
        return datetime.strptime(match["expiration"], "%y%m%d").date()
    except ValueError:
        return None


def normalize_cboe_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    has_index_prefix = normalized.startswith("_")
    if has_index_prefix:
        normalized = normalized[1:]
    if not normalized:
        raise ValueError("Symbol must not be empty.")
    if has_index_prefix or normalized in _INDEX_SYMBOLS:
        return f"_{normalized}"
    return normalized


class CboeOptionsProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache_ttl_seconds: float = CBOE_CACHE_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, _CboeOptionsPayload]] = {}

    async def _get_payload(self, symbol: str) -> tuple[str, _CboeOptionsPayload]:
        normalized_symbol = normalize_cboe_symbol(symbol)
        cached = self._cache.get(normalized_symbol)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl_seconds:
            return normalized_symbol, cached[1]

        url_symbol = quote(normalized_symbol, safe="_")
        response = await self._client.get(
            CBOE_OPTIONS_URL.format(symbol=url_symbol),
            follow_redirects=True,
        )
        response.raise_for_status()

        try:
            payload = _CboeOptionsPayload.model_validate(response.json())
        except (ValidationError, ValueError) as error:
            raise CboePayloadError(
                "CBOE returned an invalid options payload."
            ) from error
        if (
            payload.symbol.upper() != normalized_symbol
            or payload.data.symbol.upper() != normalized_symbol
        ):
            raise CboePayloadError("CBOE returned data for an unexpected symbol.")

        self._cache[normalized_symbol] = (time.monotonic(), payload)
        return normalized_symbol, payload

    async def get_chain(
        self,
        symbol: str,
        expiration: date | None = None,
    ) -> OptionChainResponse:
        _, payload = await self._get_payload(symbol)
        result = OptionChainResponse(
            symbol=symbol.strip().upper().removeprefix("_"),
            contracts=payload.data.options,
            as_of=payload.timestamp,
        )
        if expiration is None:
            return result

        contracts = []
        unrecognized_symbols = 0
        for contract in result.contracts:
            contract_expiration = option_expiration(contract.option)
            if contract_expiration is None:
                unrecognized_symbols += 1
            elif contract_expiration == expiration:
                contracts.append(contract)

        warnings = (
            [
                f"Excluded {unrecognized_symbols} contracts with unrecognized "
                "option symbols from the expiration filter."
            ]
            if unrecognized_symbols
            else []
        )
        return result.model_copy(
            update={
                "expiration": expiration,
                "contracts": contracts,
                "warnings": warnings,
            }
        )

    async def get_market_quote(self, symbol: str) -> CboeMarketQuote:
        _, payload = await self._get_payload(symbol)
        return CboeMarketQuote(
            symbol=symbol.strip().upper().removeprefix("_"),
            price=payload.data.current_price,
            change_pct=payload.data.price_change_percent,
            as_of=payload.timestamp,
        )
