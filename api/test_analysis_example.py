import unittest
from datetime import UTC, datetime

import httpx
from index import app
from routers.analysis import ExampleResponse

TIMESTAMP = "2026-10-29T15:00:00Z"


def contract(
    option: str,
    *,
    bid: float,
    ask: float,
) -> dict[str, object]:
    return {
        "option": option,
        "bid": bid,
        "ask": ask,
        "iv": 0.14,
        "delta": -0.25,
        "gamma": 0.01,
        "theta": -0.05,
        "vega": 0.1,
        "open_interest": 1_000,
        "volume": 100,
    }


def cboe_payload(options: list[dict[str, object]]) -> dict[str, object]:
    return {
        "timestamp": TIMESTAMP,
        "symbol": "SPY",
        "data": {
            "symbol": "SPY",
            "current_price": 770.0,
            "price_change_percent": 0.2,
            "options": options,
        },
    }


def default_options() -> list[dict[str, object]]:
    return [
        contract("SPY261120P00755000", bid=1.0, ask=1.1),
        contract("SPY261120P00760000", bid=1.5, ask=1.6),
        contract("SPY261218P00755000", bid=4.4, ask=4.5),
        contract("SPY261218P00760000", bid=4.9, ask=5.0),
        contract("SPY261218P00765000", bid=5.5, ask=5.6),
        contract("SPY261218P00770000", bid=6.2, ask=6.3),
        contract("SPY261218C00760000", bid=8.0, ask=8.1),
        contract("SPY261001P00760000", bid=1.0, ask=1.1),
        contract("SPY261218P00750000", bid=0.0, ask=0.05),
    ]


class AnalysisExampleApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.status_code = 200
        self.options = default_options()
        self.requests: list[httpx.Request] = []
        self.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.upstream_response)
        )
        app.state.http_client = self.http_client
        app.state.cboe_options_provider = None
        app.state.cboe_provider_client = None
        self.api_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.api_client.aclose()
        await self.http_client.aclose()

    async def upstream_response(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status_code != 200:
            return httpx.Response(self.status_code)
        return httpx.Response(200, json=cboe_payload(self.options))

    async def test_example_uses_a_near_current_expiration_and_strikes(self) -> None:
        response = await self.api_client.get("/api/analysis/example/SPY")

        self.assertEqual(response.status_code, 200)
        body = ExampleResponse.model_validate(response.json())
        self.assertEqual(body.symbol, "SPY")
        self.assertEqual(body.current_price, 770.0)
        self.assertEqual(body.legs[0].side, "sell")
        self.assertEqual(body.legs[0].option_type, "put")
        self.assertEqual(body.legs[0].strike, 760)
        self.assertEqual(body.legs[1].side, "buy")
        self.assertEqual(body.legs[1].strike, 755)
        self.assertEqual(body.legs[0].expiration.isoformat(), "2026-12-18")
        self.assertIn("Sell the 760 put", body.message)
        self.assertIn("buy the 755 put", body.message)
        self.assertIn("defined-risk bull put spread", body.message)
        self.assertIn("760/755", body.description)
        self.assertEqual(
            body.as_of,
            datetime(2026, 10, 29, 15, 0, tzinfo=UTC),
        )
        self.assertLessEqual(
            abs(body.current_price - body.legs[0].strike),
            body.current_price * 0.02,
        )

    async def test_example_rejects_a_chain_without_puts(self) -> None:
        self.options = [contract("SPY261218C00760000", bid=8.0, ask=8.1)]

        response = await self.api_client.get("/api/analysis/example/SPY")

        self.assertEqual(response.status_code, 422)
        self.assertIn("put", response.json()["detail"])

    async def test_example_reports_a_cboe_outage(self) -> None:
        self.status_code = 503

        response = await self.api_client.get("/api/analysis/example/SPY")

        self.assertEqual(response.status_code, 502)

    async def test_example_is_documented_in_openapi(self) -> None:
        response = await self.api_client.get("/api/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "/api/analysis/example/{symbol}",
            response.json()["paths"],
        )


if __name__ == "__main__":
    unittest.main()
