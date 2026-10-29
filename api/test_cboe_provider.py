import unittest
from datetime import UTC, date, datetime

import httpx
from core.cboe_provider import (
    CboeOptionsProvider,
    CboePayloadError,
    normalize_cboe_symbol,
)


def cboe_payload(
    symbol: str = "SPY",
    data_symbol: str | None = None,
    options: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if options is None:
        options = [
            {
                "option": f"{symbol}261120P00732000",
                "bid": 2.45,
                "ask": 2.5,
                "iv": 0.18,
                "delta": -0.31,
                "gamma": 0.02,
                "theta": -0.04,
                "vega": 0.12,
                "open_interest": 240,
                "volume": 12,
                "provider_extra": "ignored",
            }
        ]
    return {
        "timestamp": "2026-10-28T15:48:15Z",
        "symbol": symbol,
        "data": {
            "symbol": data_symbol if data_symbol is not None else symbol,
            "current_price": 772.31,
            "price_change_percent": 0.3431,
            "options": options,
        },
    }


class CboeOptionsProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_normalizes_and_validates_a_cboe_chain(self) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                _request.url,
                "https://cdn.cboe.com/api/global/delayed_quotes/options/SPY.json",
            )
            return httpx.Response(200, json=cboe_payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            chain = await CboeOptionsProvider(client).get_chain("spy")

        self.assertEqual(chain.symbol, "SPY")
        self.assertEqual(chain.source, "cboe_delayed")
        self.assertEqual(
            chain.as_of,
            datetime(2026, 10, 28, 15, 48, 15, tzinfo=UTC),
        )
        self.assertEqual(len(chain.contracts), 1)
        self.assertEqual(chain.contracts[0].option, "SPY261120P00732000")
        self.assertEqual(chain.contracts[0].open_interest, 240)

    async def test_accepts_an_index_payload_with_a_caret_data_symbol(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url.path,
                "/api/global/delayed_quotes/options/_XSP.json",
            )
            return httpx.Response(
                200,
                json=cboe_payload(
                    symbol="_XSP",
                    data_symbol="^XSP",
                    options=[
                        {
                            "option": "XSP261120P00732000",
                            "bid": 2.45,
                            "ask": 2.5,
                            "delta": -0.31,
                            "theta": -0.04,
                            "open_interest": 240,
                        }
                    ],
                ),
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            chain = await CboeOptionsProvider(client).get_chain("XSP")

        self.assertEqual(chain.symbol, "XSP")
        self.assertEqual(chain.contracts[0].option, "XSP261120P00732000")

    async def test_reads_market_values_from_verified_payload_fields(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url.path,
                "/api/global/delayed_quotes/options/SPY.json",
            )
            return httpx.Response(200, json=cboe_payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            quote = await CboeOptionsProvider(client).get_market_quote("SPY")

        self.assertEqual(quote.symbol, "SPY")
        self.assertEqual(quote.price, 772.31)
        self.assertEqual(quote.change_pct, 0.3431)
        self.assertEqual(quote.source, "cboe_delayed")

    async def test_filters_contracts_by_occ_expiration(self) -> None:
        options: list[dict[str, object]] = [
            {
                "option": "SPY261120P00732000",
                "bid": 2.45,
                "ask": 2.5,
            },
            {
                "option": "SPY261218C00600000",
                "bid": 1.0,
                "ask": 1.1,
            },
        ]

        async def handler(_request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                _request.url.path,
                "/api/global/delayed_quotes/options/SPY.json",
            )
            return httpx.Response(200, json=cboe_payload(options=options))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            chain = await CboeOptionsProvider(client).get_chain(
                "SPY",
                date(2026, 11, 20),
            )

        self.assertEqual(chain.expiration, date(2026, 11, 20))
        self.assertEqual(len(chain.contracts), 1)
        self.assertEqual(chain.contracts[0].option, "SPY261120P00732000")

    async def test_follows_the_cboe_api_redirect(self) -> None:
        requested_hosts: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requested_hosts.append(str(request.url.host))
            if request.url.host == "cdn.cboe.com":
                return httpx.Response(
                    307,
                    headers={
                        "Location": (
                            "https://cdn-api.cboe.com/api/global/"
                            "delayed_quotes/options/SPY.json"
                        )
                    },
                )
            return httpx.Response(200, json=cboe_payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            chain = await CboeOptionsProvider(client).get_chain("SPY")

        self.assertEqual(requested_hosts, ["cdn.cboe.com", "cdn-api.cboe.com"])
        self.assertEqual(chain.source, "cboe_delayed")

    async def test_uses_the_sixty_second_per_symbol_cache(self) -> None:
        request_count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            self.assertEqual(
                request.url.path,
                "/api/global/delayed_quotes/options/SPY.json",
            )
            request_count += 1
            return httpx.Response(200, json=cboe_payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = CboeOptionsProvider(client)
            first = await provider.get_chain("SPY")
            second = await provider.get_chain("SPY")

        self.assertEqual(request_count, 1)
        self.assertEqual(first, second)

    async def test_does_not_cache_an_http_error(self) -> None:
        requests = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                _request.url.path,
                "/api/global/delayed_quotes/options/SPY.json",
            )
            nonlocal requests
            requests += 1
            return httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = CboeOptionsProvider(client)
            for _ in range(2):
                with self.assertRaises(httpx.HTTPStatusError):
                    await provider.get_chain("SPY")

        self.assertEqual(requests, 2)

    async def test_rejects_a_payload_for_a_different_symbol(self) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                _request.url.path,
                "/api/global/delayed_quotes/options/SPY.json",
            )
            return httpx.Response(200, json=cboe_payload("QQQ"))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(CboePayloadError, "unexpected symbol"):
                await CboeOptionsProvider(client).get_chain("SPY")

    async def test_rejects_a_malformed_contract(self) -> None:
        payload = cboe_payload(options=[{"bid": 1.0}])

        async def handler(_request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                _request.url.path,
                "/api/global/delayed_quotes/options/SPY.json",
            )
            return httpx.Response(200, json=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(CboePayloadError):
                await CboeOptionsProvider(client).get_chain("SPY")


class CboeSymbolTests(unittest.TestCase):
    def test_normalizes_index_symbols_with_cboe_prefix(self) -> None:
        self.assertEqual(normalize_cboe_symbol("SPX"), "_SPX")
        self.assertEqual(normalize_cboe_symbol("_VIX"), "_VIX")
        self.assertEqual(normalize_cboe_symbol("NDX"), "_NDX")
        self.assertEqual(normalize_cboe_symbol("XSP"), "_XSP")
        self.assertEqual(normalize_cboe_symbol("_RUT"), "_RUT")

    def test_keeps_equity_symbols_unprefixed(self) -> None:
        self.assertEqual(normalize_cboe_symbol(" spy "), "SPY")
        self.assertEqual(normalize_cboe_symbol("TSLA"), "TSLA")

    def test_rejects_an_empty_symbol(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            normalize_cboe_symbol("   ")


if __name__ == "__main__":
    unittest.main()
