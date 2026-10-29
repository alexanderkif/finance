import unittest
from datetime import date, datetime, timezone

import httpx
from pydantic import BaseModel

from core.cboe_provider import CboeMarketQuote, OptionChainResponse
from index import app
from routers.market import MarketResponse, build_market_response


class OpenApiSchema(BaseModel):
    paths: dict[str, object]


class ProviderErrorResponse(BaseModel):
    detail: str


class CboeOptionsApiTests(unittest.IsolatedAsyncioTestCase):
    def test_market_response_warns_when_cboe_omits_quote_fields(self) -> None:
        response = build_market_response(
            CboeMarketQuote(
                symbol="SPY",
                price=None,
                change_pct=None,
                as_of=datetime(2026, 10, 28, 15, 48, 15, tzinfo=timezone.utc),
            )
        )

        self.assertIn("price_unavailable", response.warnings)
        self.assertIn("change_pct_unavailable", response.warnings)

    async def asyncSetUp(self) -> None:
        self.status_code: int = 200
        self.requests: list[httpx.Request] = []
        self.http_client: httpx.AsyncClient = httpx.AsyncClient(
            transport=httpx.MockTransport(self.cboe_response),
        )
        app.state.http_client = self.http_client
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
        return httpx.Response(
            200,
            json={
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
            },
        )

    async def test_market_endpoint_reports_cboe_quote_and_degraded_fields(
        self,
    ) -> None:
        response = await self.api_client.get("/api/market/SPY")

        self.assertEqual(response.status_code, 200)
        body = MarketResponse.model_validate(response.json())
        self.assertEqual(body.symbol, "SPY")
        self.assertEqual(body.price, 772.31)
        self.assertEqual(body.change_pct, 0.3431)
        self.assertEqual(body.source, "cboe_delayed")
        self.assertEqual(
            body.as_of,
            datetime(2026, 10, 28, 15, 48, 15, tzinfo=timezone.utc),
        )
        self.assertTrue(body.degraded)
        self.assertIsNone(body.vix)
        self.assertEqual(body.support, [])
        self.assertEqual(body.resistance, [])
        self.assertEqual(body.news, [])
        self.assertIn("vix_unavailable", body.warnings)

    async def test_chain_endpoint_returns_normalized_contracts_and_metadata(self) -> None:
        response = await self.api_client.get("/api/options/chain/SPY")

        self.assertEqual(response.status_code, 200)
        body = OptionChainResponse.model_validate(response.json())
        self.assertEqual(body.symbol, "SPY")
        self.assertIsNone(body.expiration)
        self.assertEqual(body.source, "cboe_delayed")
        self.assertEqual(
            body.as_of,
            datetime(2026, 10, 28, 15, 48, 15, tzinfo=timezone.utc),
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

    async def test_chain_endpoint_reports_upstream_errors_without_market_values(
        self,
    ) -> None:
        self.status_code = 503

        response = await self.api_client.get("/api/options/chain/SPY")

        self.assertEqual(response.status_code, 502)
        error = ProviderErrorResponse.model_validate(response.json())
        self.assertIn("HTTP 503", error.detail)
        self.assertEqual(len(self.requests), 1)

    async def test_market_and_chain_endpoints_are_documented_in_openapi(self) -> None:
        response = await self.api_client.get("/api/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = OpenApiSchema.model_validate(response.json())
        self.assertIn("/api/options/chain/{symbol}", schema.paths)
        self.assertIn("/api/market/{symbol}", schema.paths)


if __name__ == "__main__":
    unittest.main()
