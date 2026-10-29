import json
import os
import unittest
from unittest.mock import patch

import httpx

from index import app

RECOMMENDATION = (
    "This credit spread keeps its maximum profit if the underlying stays above "
    "the breakeven level at expiration."
)


def contract(
    option: str,
    *,
    bid: float,
    ask: float,
    delta: float,
    theta: float,
    iv: float = 0.14,
    open_interest: float = 1_000,
    volume: float = 500,
) -> dict[str, object]:
    return {
        "option": option,
        "bid": bid,
        "ask": ask,
        "iv": iv,
        "delta": delta,
        "gamma": 0.01,
        "theta": theta,
        "vega": 0.1,
        "open_interest": open_interest,
        "volume": volume,
    }


def cboe_payload() -> dict[str, object]:
    return {
        "timestamp": "2026-10-29 10:05:32",
        "symbol": "SPY",
        "data": {
            "symbol": "SPY",
            "current_price": 770.77,
            "price_change_percent": 0.42,
            "options": [
                contract(
                    "SPY261120P00732000",
                    bid=3.00,
                    ask=3.20,
                    delta=-0.30,
                    theta=-0.10,
                    open_interest=1_000,
                    volume=500,
                ),
                contract(
                    "SPY261120P00729000",
                    bid=1.50,
                    ask=1.70,
                    delta=-0.18,
                    theta=-0.05,
                    open_interest=800,
                    volume=400,
                ),
                contract(
                    "SPY261120C00732000",
                    bid=2.40,
                    ask=2.60,
                    delta=0.42,
                    theta=-0.06,
                ),
                contract(
                    "SPY261120C00729000",
                    bid=3.90,
                    ask=4.10,
                    delta=0.55,
                    theta=-0.08,
                ),
                contract(
                    "SPY261120C00600000",
                    bid=4.90,
                    ask=5.10,
                    delta=0.40,
                    theta=-0.05,
                ),
            ],
        },
    }


def spread_body() -> dict[str, object]:
    return {
        "position": {
            "position_type": "strategy",
            "legs": [
                {
                    "symbol": "SPY",
                    "side": "sell",
                    "option_type": "put",
                    "strike": 732,
                    "expiration": "2026-11-20",
                },
                {
                    "symbol": "SPY",
                    "side": "buy",
                    "option_type": "put",
                    "strike": 729,
                    "expiration": "2026-11-20",
                },
            ],
        },
        "intent": "open",
        "detected_language": "English",
    }


def single_body() -> dict[str, object]:
    return {
        "position": {
            "position_type": "single",
            "legs": [
                {
                    "symbol": "SPY",
                    "side": "buy",
                    "option_type": "call",
                    "strike": 600,
                    "expiration": "2026-11-20",
                }
            ],
        },
        "intent": "open",
        "detected_language": "English",
    }


class AnalysisRunApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.model_result: dict[str, object] = {"recommendation": RECOMMENDATION}
        self.gemini_status = 200
        self.cboe_status = 200
        self.gemini_requests: list[httpx.Request] = []
        self.cboe_requests: list[httpx.Request] = []
        self.environment = patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
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
        if request.url.host == "cdn.cboe.com":
            self.cboe_requests.append(request)
            if self.cboe_status != 200:
                return httpx.Response(self.cboe_status, json={})
            return httpx.Response(200, json=cboe_payload())
        if request.url.host == "generativelanguage.googleapis.com":
            self.gemini_requests.append(request)
            if self.gemini_status != 200:
                return httpx.Response(
                    self.gemini_status, json={"error": "redacted"}
                )
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": json.dumps(self.model_result)}
                                ]
                            }
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"detail": "unexpected host"})

    async def test_run_endpoint_is_documented_in_openapi(self) -> None:
        response = await self.api_client.get("/api/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/analysis/run", response.json()["paths"])

    async def test_run_returns_deterministic_bull_put_metrics(self) -> None:
        response = await self.api_client.post(
            "/api/analysis/run", json=spread_body()
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["header"], "Bull Put Spread SPY 732/729 2026-11-20"
        )
        self.assertEqual(body["strategy_key"], "bull_put_spread")
        self.assertEqual(body["net_credit_debit"], 150.0)
        self.assertEqual(body["max_profit"], 150.0)
        self.assertEqual(body["max_loss"], 150.0)
        self.assertEqual(body["breakeven"], 730.5)
        self.assertEqual(body["probability_positive"], 0.7)
        self.assertEqual(body["theta_daily"], 5.0)
        self.assertIsNone(body["iv_rank"])
        self.assertEqual(
            body["event_flags"], ["earnings", "dividends", "macro"]
        )
        self.assertEqual(body["liquidity"]["bid_ask_spread_pct"], 12.5)
        self.assertEqual(body["liquidity"]["open_interest"], 800)
        self.assertEqual(body["liquidity"]["rating"], "fair")
        self.assertEqual(body["scenario_1sigma"]["days_to_expiration"], 22)
        self.assertEqual(body["scenario_1sigma"]["atm_iv"], 0.14)
        self.assertEqual(
            body["disclaimer"], "Educational analysis, not investment advice."
        )
        self.assertEqual(body["detected_language"], "English")
        self.assertEqual(body["source"], "cboe_delayed")
        self.assertTrue(body["as_of"].startswith("2026-10-29T10:05:32"))
        self.assertTrue(body["degraded"])
        self.assertIn("iv_rank_unavailable", body["warnings"])
        self.assertEqual(body["recommendation"], RECOMMENDATION)

    async def test_run_uses_one_gemini_call_with_computed_facts(self) -> None:
        await self.api_client.post("/api/analysis/run", json=spread_body())

        self.assertEqual(len(self.gemini_requests), 1)
        request = self.gemini_requests[0]
        self.assertNotIn("test-key", str(request.url))
        self.assertEqual(request.headers["x-goog-api-key"], "test-key")
        payload = json.loads(request.content)
        self.assertEqual(payload["generationConfig"]["temperature"], 0.2)
        self.assertIn(
            "never calculate new values",
            payload["systemInstruction"]["parts"][0]["text"],
        )
        facts = json.loads(payload["contents"][0]["parts"][0]["text"])
        self.assertEqual(facts["header"], "Bull Put Spread SPY 732/729 2026-11-20")
        self.assertEqual(facts["intent"], "open")
        self.assertEqual(facts["language"], "English")
        self.assertEqual(facts["metrics"]["breakeven"], 730.5)
        self.assertEqual(facts["metrics"]["max_loss"], 150.0)
        self.assertIsNone(facts["metrics"]["iv_rank"])

    async def test_run_returns_an_unbounded_long_call(self) -> None:
        response = await self.api_client.post(
            "/api/analysis/run", json=single_body()
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["header"], "Long Call SPY 600 2026-11-20")
        self.assertIsNone(body["max_profit"])
        self.assertEqual(body["max_loss"], 500.0)
        self.assertEqual(body["breakeven"], 605.0)
        self.assertEqual(body["probability_positive"], 0.4)
        self.assertEqual(body["strategy_key"], "long_call")

    async def test_run_rejects_a_leg_without_a_listed_contract(self) -> None:
        body = single_body()
        body["position"]["legs"][0]["strike"] = 999

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 422)
        self.assertIn("No listed contract", response.json()["detail"])
        self.assertEqual(self.gemini_requests, [])

    async def test_run_rejects_legs_that_are_not_a_spread(self) -> None:
        body = spread_body()
        body["position"]["legs"][1]["side"] = "sell"

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.gemini_requests, [])
        self.assertEqual(self.cboe_requests, [])

    async def test_run_rejects_a_single_position_with_two_legs(self) -> None:
        body = spread_body()
        body["position"]["position_type"] = "single"

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.cboe_requests, [])

    async def test_run_reports_gemini_quota_exhaustion(self) -> None:
        self.gemini_status = 429

        response = await self.api_client.post(
            "/api/analysis/run", json=spread_body()
        )

        self.assertEqual(response.status_code, 429)
        self.assertIn("quota", response.json()["detail"])
        self.assertEqual(len(self.gemini_requests), 1)

    async def test_run_reports_missing_gemini_key_without_calling_gemini(
        self,
    ) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            response = await self.api_client.post(
                "/api/analysis/run", json=spread_body()
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])
        self.assertEqual(self.gemini_requests, [])

    async def test_run_reports_cboe_outage_without_fabricating_metrics(
        self,
    ) -> None:
        self.cboe_status = 503

        response = await self.api_client.post(
            "/api/analysis/run", json=spread_body()
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.gemini_requests, [])
        self.assertNotIn("net_credit_debit", response.json())

    async def test_run_rejects_an_invalid_recommendation_shape(self) -> None:
        self.model_result = {"recommendation": "Too short"}

        response = await self.api_client.post(
            "/api/analysis/run", json=spread_body()
        )

        self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
