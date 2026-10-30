import unittest
from datetime import UTC, date, datetime

import httpx
from core.cboe_provider import OptionChainResponse
from index import app
from pydantic import BaseModel


class OpenApiSchema(BaseModel):
    paths: dict[str, object]


def cboe_options_payload() -> dict[str, object]:
    return {
        "timestamp": "2026-10-28T15:48:15Z",
        "symbol": "SPY",
        "data": {
            "symbol": "SPY",
            "current_price": 772.31,
            "price_change_percent": 0.3431,
            "options": [
                {
                    "option": "SPY261120P00732000",
                    "bid": 2.45,
                    "ask": 2.5,
                    "iv": 0.18,
                    "delta": -0.31,
                    "gamma": 0.02,
                    "theta": -0.04,
                    "vega": 0.12,
                    "open_interest": 240,
                    "volume": 12,
                }
            ],
        },
    }


class CboeOptionsApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.status_code: int = 200
        self.requests: list[httpx.Request] = []
        self.http_client: httpx.AsyncClient = httpx.AsyncClient(
            transport=httpx.MockTransport(self.cboe_response),
        )
        app.state.http_client = self.http_client
        app.state.cboe_options_provider = None
        app.state.cboe_provider_client = None
        self.api_client: httpx.AsyncClient = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.api_client.aclose()
        await self.http_client.aclose()

    async def cboe_response(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status_code != 200:
            return httpx.Response(self.status_code)
        return httpx.Response(200, json=cboe_options_payload())

    async def test_chain_endpoint_returns_normalized_contracts_and_metadata(
        self,
    ) -> None:
        response = await self.api_client.get("/api/options/chain/SPY")

        self.assertEqual(response.status_code, 200)
        body = OptionChainResponse.model_validate(response.json())
        self.assertEqual(body.symbol, "SPY")
        self.assertIsNone(body.expiration)
        self.assertEqual(body.source, "cboe_delayed")
        self.assertEqual(
            body.as_of,
            datetime(2026, 10, 28, 15, 48, 15, tzinfo=UTC),
        )
        self.assertEqual(len(body.contracts), 1)
        self.assertEqual(body.contracts[0].delta, -0.31)
        self.assertEqual(body.contracts[0].open_interest, 240)

    async def test_chain_endpoint_filters_by_expiration(self) -> None:
        response = await self.api_client.get(
            "/api/options/chain/SPY?expiration=2026-11-20"
        )

        self.assertEqual(response.status_code, 200)
        body = OptionChainResponse.model_validate(response.json())
        self.assertEqual(body.expiration, date(2026, 11, 20))
        self.assertEqual(len(body.contracts), 1)

    async def test_chain_endpoint_rejects_an_invalid_expiration(self) -> None:
        response = await self.api_client.get(
            "/api/options/chain/SPY?expiration=invalid"
        )

        self.assertEqual(response.status_code, 422)

    async def test_chain_endpoint_degrades_after_a_retried_upstream_error(
        self,
    ) -> None:
        self.status_code = 503

        response = await self.api_client.get("/api/options/chain/SPY")

        self.assertEqual(response.status_code, 200)
        body = OptionChainResponse.model_validate(response.json())
        self.assertEqual(body.contracts, [])
        self.assertIsNone(body.as_of)
        self.assertTrue(body.degraded)
        self.assertEqual(body.reason, "upstream_error")
        self.assertEqual(body.warnings, ["upstream_error"])
        self.assertEqual(len(self.requests), 2)

    async def test_chain_endpoint_degrades_on_a_rate_limit_without_a_cache(
        self,
    ) -> None:
        self.status_code = 429

        response = await self.api_client.get("/api/options/chain/SPY")

        self.assertEqual(response.status_code, 200)
        body = OptionChainResponse.model_validate(response.json())
        self.assertEqual(body.contracts, [])
        self.assertIsNone(body.as_of)
        self.assertTrue(body.degraded)
        self.assertEqual(body.reason, "rate_limited")
        self.assertEqual(body.warnings, ["rate_limited"])
        self.assertEqual(len(self.requests), 1)

    async def test_chain_endpoint_serves_a_fresh_cache_without_upstream_call(
        self,
    ) -> None:
        await self.api_client.get("/api/options/chain/SPY")
        self.status_code = 429

        response = await self.api_client.get("/api/options/chain/SPY")

        self.assertEqual(response.status_code, 200)
        body = OptionChainResponse.model_validate(response.json())
        self.assertEqual(len(body.contracts), 1)
        self.assertFalse(body.degraded)
        self.assertEqual(body.warnings, [])
        self.assertEqual(len(self.requests), 1)

    async def test_chain_endpoint_serves_a_stale_cache_on_a_rate_limit(
        self,
    ) -> None:
        first = await self.api_client.get("/api/options/chain/SPY")
        self.assertEqual(first.status_code, 200)
        provider = app.state.cboe_options_provider
        self.assertIsNotNone(provider)
        provider._cache_ttl_seconds = 0
        self.status_code = 429

        response = await self.api_client.get("/api/options/chain/SPY")

        self.assertEqual(response.status_code, 200)
        body = OptionChainResponse.model_validate(response.json())
        self.assertEqual(len(body.contracts), 1)
        self.assertEqual(
            body.as_of,
            datetime(2026, 10, 28, 15, 48, 15, tzinfo=UTC),
        )
        self.assertTrue(body.degraded)
        self.assertEqual(body.reason, "rate_limited")
        self.assertEqual(body.warnings, ["cached_data"])
        self.assertEqual(len(self.requests), 2)

    async def test_options_endpoint_is_documented_in_openapi(self) -> None:
        response = await self.api_client.get("/api/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = OpenApiSchema.model_validate(response.json())
        self.assertIn("/api/options/chain/{symbol}", schema.paths)


if __name__ == "__main__":
    unittest.main()
