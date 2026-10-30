import re
import time
from datetime import UTC, date, datetime
from typing import Final, Literal, NamedTuple
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CBOE_OPTIONS_URL: Final = (
    "https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
)
CBOE_QUOTE_URL: Final = (
    "https://cdn.cboe.com/api/global/delayed_quotes/quotes/{symbol}.json"
)
CBOE_CACHE_TTL_SECONDS: Final = 60.0
CBOE_STALE_CACHE_SECONDS: Final = 600.0
_INDEX_SYMBOLS: Final = frozenset({"SPX", "VIX", "NDX", "XSP"})
_OCC_SYMBOL_PATTERN: Final = re.compile(
    r"^(?P<root>[A-Z0-9.]+?)(?P<expiration>\d{6})(?P<option_type>[CP])"
    r"(?P<strike>\d{8})$"
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class CboeProviderError(RuntimeError):
    pass


class CboePayloadError(CboeProviderError):
    pass


class CboeRateLimitedError(CboeProviderError):
    pass


class CboeUnavailableError(CboeProviderError):
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

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _utc(value)


class _CboeQuoteData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str
    current_price: float | None = None
    price_change_percent: float | None = None


class _CboeQuotePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timestamp: datetime
    symbol: str
    data: _CboeQuoteData

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _utc(value)


class OptionChainResponse(BaseModel):
    symbol: str
    expiration: date | None = None
    contracts: list[CboeOptionQuote]
    source: Literal["cboe_delayed"] = "cboe_delayed"
    as_of: datetime | None = None
    degraded: bool = False
    reason: Literal["rate_limited", "upstream_error"] | None = None
    warnings: list[str] = Field(default_factory=list)


class CboeMarketQuote(BaseModel):
    symbol: str
    price: float | None
    change_pct: float | None
    source: Literal["cboe_delayed"] = "cboe_delayed"
    as_of: datetime


class CboeIndexQuote(BaseModel):
    symbol: str
    price: float | None
    change_pct: float | None
    source: Literal["cboe_delayed"] = "cboe_delayed"
    as_of: datetime


class OccSymbol(NamedTuple):
    root: str
    expiration: date
    option_type: Literal["call", "put"]
    strike: float


def parse_occ_symbol(option_symbol: str) -> OccSymbol | None:
    match = _OCC_SYMBOL_PATTERN.fullmatch(option_symbol.strip().upper())
    if match is None:
        return None
    try:
        expiration = datetime.strptime(match["expiration"], "%y%m%d").date()
    except ValueError:
        return None
    option_type: Literal["call", "put"] = (
        "call" if match["option_type"] == "C" else "put"
    )
    return OccSymbol(
        root=match["root"],
        expiration=expiration,
        option_type=option_type,
        strike=int(match["strike"]) / 1000,
    )


def option_expiration(option_symbol: str) -> date | None:
    parsed = parse_occ_symbol(option_symbol)
    return parsed.expiration if parsed is not None else None


def select_atm_iv(
    contracts: list[CboeOptionQuote],
    underlying_price: float | None,
    expiration: date,
) -> float | None:
    if underlying_price is None or underlying_price <= 0:
        return None
    best_distance: float | None = None
    values: list[float] = []
    for contract in contracts:
        parsed = parse_occ_symbol(contract.option)
        if parsed is None or parsed.expiration != expiration:
            continue
        if contract.iv is None or contract.iv <= 0:
            continue
        distance = abs(parsed.strike - underlying_price)
        if best_distance is None or distance < best_distance - 1e-9:
            best_distance = distance
            values = [contract.iv]
        elif abs(distance - best_distance) <= 1e-9:
            values.append(contract.iv)
    if not values:
        return None
    return sum(values) / len(values)


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


def _bare_symbol(value: str) -> str:
    return value.strip().upper().removeprefix("_").removeprefix("^")


class CboeOptionsProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache_ttl_seconds: float = CBOE_CACHE_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, _CboeOptionsPayload]] = {}
        self._quote_cache: dict[str, tuple[float, _CboeQuotePayload]] = {}

    async def _request(self, url: str) -> httpx.Response:
        response = await self._client.get(url, follow_redirects=True)
        if 500 <= response.status_code < 600:
            response = await self._client.get(url, follow_redirects=True)
        return response

    def _stale_cached(
        self,
        cached: tuple[float, _CboeOptionsPayload] | None,
    ) -> _CboeOptionsPayload | None:
        if cached is None:
            return None
        if time.monotonic() - cached[0] >= CBOE_STALE_CACHE_SECONDS:
            return None
        return cached[1]

    async def _get_payload(
        self,
        symbol: str,
    ) -> tuple[
        str,
        _CboeOptionsPayload,
        list[str],
        Literal["rate_limited", "upstream_error"] | None,
    ]:
        normalized_symbol = normalize_cboe_symbol(symbol)
        cached = self._cache.get(normalized_symbol)
        if (
            cached is not None
            and time.monotonic() - cached[0] < self._cache_ttl_seconds
        ):
            return normalized_symbol, cached[1], [], None

        url_symbol = quote(normalized_symbol, safe="_")
        response = await self._request(
            CBOE_OPTIONS_URL.format(symbol=url_symbol),
        )

        if response.status_code == 429:
            stale = self._stale_cached(cached)
            if stale is not None:
                return normalized_symbol, stale, ["cached_data"], "rate_limited"
            raise CboeRateLimitedError("CBOE rate limit was reached.")
        if 500 <= response.status_code < 600:
            stale = self._stale_cached(cached)
            if stale is not None:
                return normalized_symbol, stale, ["cached_data"], "upstream_error"
            raise CboeUnavailableError(
                f"CBOE returned HTTP {response.status_code}."
            )

        response.raise_for_status()

        try:
            payload = _CboeOptionsPayload.model_validate(response.json())
        except (ValidationError, ValueError) as error:
            raise CboePayloadError(
                "CBOE returned an invalid options payload."
            ) from error
        if _bare_symbol(payload.symbol) != _bare_symbol(
            normalized_symbol
        ) or _bare_symbol(payload.data.symbol) != _bare_symbol(normalized_symbol):
            raise CboePayloadError("CBOE returned data for an unexpected symbol.")

        self._cache[normalized_symbol] = (time.monotonic(), payload)
        return normalized_symbol, payload, [], None

    async def get_chain(
        self,
        symbol: str,
        expiration: date | None = None,
    ) -> OptionChainResponse:
        _, payload, cache_warnings, reason = await self._get_payload(symbol)
        result = OptionChainResponse(
            symbol=_bare_symbol(symbol),
            contracts=payload.data.options,
            as_of=payload.timestamp,
            degraded=bool(cache_warnings),
            reason=reason,
            warnings=list(cache_warnings),
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

        warnings = list(cache_warnings)
        if unrecognized_symbols:
            warnings.append(
                f"Excluded {unrecognized_symbols} contracts with unrecognized "
                "option symbols from the expiration filter."
            )
        return result.model_copy(
            update={
                "expiration": expiration,
                "contracts": contracts,
                "warnings": warnings,
                "degraded": bool(warnings),
            }
        )

    async def get_market_quote(self, symbol: str) -> CboeMarketQuote:
        _, payload, _, _ = await self._get_payload(symbol)
        return CboeMarketQuote(
            symbol=_bare_symbol(symbol),
            price=payload.data.current_price,
            change_pct=payload.data.price_change_percent,
            as_of=payload.timestamp,
        )

    async def get_index_quote(self, symbol: str) -> CboeIndexQuote:
        normalized_symbol = normalize_cboe_symbol(symbol)
        cached = self._quote_cache.get(normalized_symbol)
        if (
            cached is not None
            and time.monotonic() - cached[0] < self._cache_ttl_seconds
        ):
            payload = cached[1]
        else:
            url_symbol = quote(normalized_symbol, safe="_")
            response = await self._request(
                CBOE_QUOTE_URL.format(symbol=url_symbol),
            )
            if response.status_code == 429:
                raise CboeRateLimitedError("CBOE rate limit was reached.")
            if 500 <= response.status_code < 600:
                raise CboeUnavailableError(
                    f"CBOE returned HTTP {response.status_code}."
                )
            response.raise_for_status()
            try:
                payload = _CboeQuotePayload.model_validate(response.json())
            except (ValidationError, ValueError) as error:
                raise CboePayloadError(
                    "CBOE returned an invalid quote payload."
                ) from error
            if _bare_symbol(payload.symbol) != _bare_symbol(
                normalized_symbol
            ) or _bare_symbol(payload.data.symbol) != _bare_symbol(normalized_symbol):
                raise CboePayloadError("CBOE returned data for an unexpected symbol.")
            self._quote_cache[normalized_symbol] = (time.monotonic(), payload)

        return CboeIndexQuote(
            symbol=_bare_symbol(normalized_symbol),
            price=payload.data.current_price,
            change_pct=payload.data.price_change_percent,
            as_of=payload.timestamp,
        )
