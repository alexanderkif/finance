import json
import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
from index import app

RECOMMENDATION = (
    "This credit spread keeps its maximum profit if the underlying stays above "
    "the breakeven level at expiration."
)
NEWS_TIMESTAMP = int(datetime(2030, 10, 24, 9, 0, tzinfo=UTC).timestamp())


def twelve_data_payload(count: int = 120) -> dict[str, object]:
    values: list[dict[str, str]] = []
    closes = [100.0]
    for index in range(count - 1):
        closes.append(closes[-1] * (1.01 if index % 2 == 0 else 0.992))
    start = datetime(2026, 1, 1)
    for index, close in enumerate(closes):
        values.append(
            {
                "datetime": (start + timedelta(days=index)).strftime("%Y-%m-%d"),
                "open": f"{close:.2f}",
                "high": f"{close + 1:.2f}",
                "low": f"{close - 1:.2f}",
                "close": f"{close:.2f}",
                "volume": "1000",
            }
        )
    values.reverse()
    return {"status": "ok", "values": values}


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
        "timestamp": "2030-10-24 10:05:32",
        "symbol": "SPY",
        "data": {
            "symbol": "SPY",
            "current_price": 770.77,
            "price_change_percent": 0.42,
            "options": [
                contract(
                    "SPY301115P00732000",
                    bid=3.00,
                    ask=3.20,
                    delta=-0.30,
                    theta=-0.10,
                    open_interest=1_000,
                    volume=500,
                ),
                contract(
                    "SPY301115P00729000",
                    bid=1.50,
                    ask=1.70,
                    delta=-0.18,
                    theta=-0.05,
                    open_interest=800,
                    volume=400,
                ),
                contract(
                    "SPY301115C00732000",
                    bid=2.40,
                    ask=2.60,
                    delta=0.42,
                    theta=-0.06,
                ),
                contract(
                    "SPY301115C00729000",
                    bid=3.90,
                    ask=4.10,
                    delta=0.55,
                    theta=-0.08,
                ),
                contract(
                    "SPY301115C00600000",
                    bid=4.90,
                    ask=5.10,
                    delta=0.40,
                    theta=-0.05,
                ),
                contract(
                    "SPY301115C00734000",
                    bid=2.00,
                    ask=2.20,
                    delta=0.35,
                    theta=-0.06,
                ),
                contract(
                    "SPY301115C00736000",
                    bid=1.40,
                    ask=1.60,
                    delta=0.28,
                    theta=-0.05,
                ),
                contract(
                    "SPY301115P00734000",
                    bid=4.00,
                    ask=4.20,
                    delta=-0.35,
                    theta=-0.12,
                ),
                contract(
                    "SPY301115P00731000",
                    bid=2.50,
                    ask=2.70,
                    delta=-0.25,
                    theta=-0.08,
                ),
                contract(
                    "SPY301115P00733000",
                    bid=3.20,
                    ask=3.40,
                    delta=-0.30,
                    theta=-0.10,
                ),
                contract(
                    "SPY301115P00728000",
                    bid=2.20,
                    ask=2.40,
                    delta=-0.20,
                    theta=-0.07,
                ),
                contract(
                    "SPY270115P00732000",
                    bid=5.00,
                    ask=5.20,
                    delta=-0.25,
                    theta=-0.04,
                ),
                contract(
                    "SPY270115P00729000",
                    bid=4.40,
                    ask=4.60,
                    delta=-0.22,
                    theta=-0.04,
                ),
            ],
        },
    }


def company_news() -> list[dict[str, object]]:
    return [
        {
            "category": "company",
            "datetime": NEWS_TIMESTAMP,
            "headline": "SPY edges higher as breadth improves",
            "id": 1,
            "image": "",
            "related": "SPY",
            "source": "Newswire",
            "summary": "",
            "url": "https://example.com/spy-news",
        }
    ]


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
                    "expiration": "2030-11-15",
                },
                {
                    "symbol": "SPY",
                    "side": "buy",
                    "option_type": "put",
                    "strike": 729,
                    "expiration": "2030-11-15",
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
                    "expiration": "2030-11-15",
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
        self.twelve_data_status = 200
        self.gemini_requests: list[httpx.Request] = []
        self.cboe_requests: list[httpx.Request] = []
        self.twelve_data_requests: list[httpx.Request] = []
        self.finnhub_requests: list[httpx.Request] = []
        self.finnhub_items = company_news()
        self.environment = patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key",
                "TWELVE_DATA_API_KEY": "test-key",
                "FINNHUB_API_KEY": "test-key",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.upstream_response)
        )
        app.state.http_client = self.http_client
        app.state.cboe_options_provider = None
        app.state.cboe_provider_client = None
        app.state.twelve_data_provider = None
        app.state.twelve_data_provider_client = None
        app.state.cboe_history_provider = None
        app.state.cboe_history_provider_client = None
        app.state.finnhub_provider = None
        app.state.finnhub_provider_client = None
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
                return httpx.Response(self.gemini_status, json={"error": "redacted"})
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": json.dumps(self.model_result)}]
                            }
                        }
                    ]
                },
            )
        if request.url.host == "api.twelvedata.com":
            self.twelve_data_requests.append(request)
            if self.twelve_data_status != 200:
                return httpx.Response(self.twelve_data_status, json={"error": "x"})
            return httpx.Response(200, json=twelve_data_payload())
        if request.url.host == "finnhub.io":
            self.finnhub_requests.append(request)
            return httpx.Response(200, json=self.finnhub_items)
        return httpx.Response(404, json={"detail": "unexpected host"})

    async def test_run_endpoint_is_documented_in_openapi(self) -> None:
        response = await self.api_client.get("/api/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/analysis/run", response.json()["paths"])
        self.assertIn("/api/analysis/run/stream", response.json()["paths"])

    async def test_run_returns_deterministic_bull_put_metrics(self) -> None:
        response = await self.api_client.post("/api/analysis/run", json=spread_body())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["header"], "Bull Put Spread SPY 732/729 2030-11-15")
        self.assertEqual(body["strategy_key"], "bull_put_spread")
        self.assertEqual(body["intent"], "open")
        self.assertEqual(body["net_credit_debit"], 150.0)
        self.assertEqual(body["max_profit"], 150.0)
        self.assertEqual(body["max_loss"], 150.0)
        self.assertEqual(body["breakeven"], 730.5)
        self.assertEqual(body["probability_positive"], 0.7)
        self.assertEqual(body["theta_daily"], 5.0)
        self.assertIsNone(body["iv_rank"])
        self.assertEqual(body["current_iv"], 0.14)
        self.assertIsNotNone(body["hv_20d"])
        self.assertIsNotNone(body["hv_60d"])
        self.assertIsNotNone(body["hv_rank"])
        self.assertEqual(
            body["iv_hv_ratio"],
            round(0.14 / body["hv_60d"], 4),
        )
        self.assertEqual(body["event_flags"], ["earnings", "dividends", "macro"])
        self.assertEqual(body["liquidity"]["bid_ask_spread_pct"], 12.5)
        self.assertEqual(body["liquidity"]["open_interest"], 800)
        self.assertEqual(body["liquidity"]["rating"], "fair")
        self.assertEqual(body["scenario_1sigma"]["days_to_expiration"], 22)
        self.assertEqual(body["scenario_1sigma"]["expected_move"], 26.49)
        self.assertEqual(body["scenario_1sigma"]["atm_iv"], 0.14)
        self.assertEqual(body["scenario_2sigma"]["days_to_expiration"], 22)
        self.assertEqual(body["scenario_2sigma"]["expected_move"], 52.98)
        self.assertEqual(body["scenario_2sigma"]["atm_iv"], 0.14)
        self.assertEqual(
            body["disclaimer"], "Educational analysis, not investment advice."
        )
        self.assertEqual(body["detected_language"], "English")
        self.assertEqual(body["source"], "cboe_delayed")
        self.assertTrue(body["as_of"].startswith("2030-10-24T10:05:32"))
        self.assertFalse(body["degraded"])
        self.assertEqual(body["warnings"], [])
        self.assertEqual(body["recommendation"], RECOMMENDATION)
        self.assertEqual(body["news_source"], "finnhub")
        self.assertEqual(len(body["news"]), 1)
        self.assertEqual(
            body["news"][0]["title"],
            "SPY edges higher as breadth improves",
        )
        self.assertIsNotNone(body["news_as_of"])

    async def test_run_does_not_depend_on_chart_or_news_providers(self) -> None:
        with patch.dict(
            os.environ,
            {"TWELVE_DATA_API_KEY": "", "FINNHUB_API_KEY": ""},
        ):
            response = await self.api_client.post(
                "/api/analysis/run", json=spread_body()
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["header"],
            "Bull Put Spread SPY 732/729 2030-11-15",
        )
        self.assertEqual(len(self.gemini_requests), 1)
        self.assertIn("news_provider_not_configured", body["warnings"])
        self.assertTrue(body["degraded"])
        self.assertEqual(body["news"], [])

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
        self.assertEqual(facts["header"], "Bull Put Spread SPY 732/729 2030-11-15")
        self.assertEqual(facts["intent"], "open")
        self.assertEqual(facts["language"], "English")
        self.assertEqual(facts["metrics"]["breakeven"], 730.5)
        self.assertEqual(facts["metrics"]["max_loss"], 150.0)
        self.assertNotIn("iv_rank", facts["metrics"])
        self.assertEqual(facts["metrics"]["current_iv"], 0.14)
        self.assertIsNotNone(facts["metrics"]["hv_60d"])
        self.assertIsNotNone(facts["metrics"]["iv_hv_ratio"])
        self.assertEqual(
            facts["recent_news"][0]["title"],
            "SPY edges higher as breadth improves",
        )

    async def test_run_stream_emits_real_stages_and_result(self) -> None:
        async with self.api_client.stream(
            "POST",
            "/api/analysis/run/stream",
            json=spread_body(),
            headers={"Accept": "application/x-ndjson"},
        ) as response:
            self.assertEqual(response.status_code, 200)
            lines = [
                line async for line in response.aiter_lines() if line.strip()
            ]
        events = [json.loads(line) for line in lines]
        stages = [event for event in events if event["type"] == "stage"]
        self.assertTrue(stages)
        self.assertEqual(
            {event["id"] for event in stages},
            {"history", "news", "chain", "quote", "metrics", "synthesis"},
        )
        self.assertTrue(
            all(event["status"] in {"started", "done"} for event in stages)
        )
        self.assertEqual(events[-1]["type"], "result")
        self.assertEqual(
            events[-1]["result"]["header"],
            "Bull Put Spread SPY 732/729 2030-11-15",
        )
        news_events = [event for event in events if event["type"] == "news"]
        self.assertEqual(len(news_events), 1)

    async def test_run_resolves_a_shift_against_the_listed_ladder(self) -> None:
        base = spread_body()["position"]
        body = {
            "position": None,
            "context": [base],
            "reference": {
                "kind": "shift",
                "strikes": 2,
                "direction": "up",
                "expiration": None,
            },
            "intent": "open",
            "detected_language": "English",
        }

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["header"],
            "Bull Put Spread SPY 734/732 2030-11-15",
        )

    async def test_run_widens_a_put_spread_by_listed_strikes(self) -> None:
        base = spread_body()["position"]
        body = {
            "position": None,
            "context": [base],
            "reference": {
                "kind": "widen",
                "strikes": 1,
                "direction": None,
                "expiration": None,
            },
            "intent": "open",
            "detected_language": "English",
        }

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["header"],
            "Bull Put Spread SPY 732/728 2030-11-15",
        )

    async def test_run_rejects_a_width_change_that_removes_the_spread(self) -> None:
        base = spread_body()["position"]
        body = {
            "position": None,
            "context": [base],
            "reference": {
                "kind": "narrow",
                "strikes": 4,
                "direction": None,
                "expiration": None,
            },
            "intent": "open",
            "detected_language": "English",
        }

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 422)
        self.assertIn("remove the spread", response.json()["detail"])

    async def test_run_widens_a_call_spread_in_the_correct_direction(self) -> None:
        base = {
            "position_type": "strategy",
            "legs": [
                {
                    "symbol": "SPY",
                    "side": "sell",
                    "option_type": "call",
                    "strike": 732,
                    "expiration": "2030-11-15",
                },
                {
                    "symbol": "SPY",
                    "side": "buy",
                    "option_type": "call",
                    "strike": 734,
                    "expiration": "2030-11-15",
                },
            ],
        }
        body = {
            "position": None,
            "context": [base],
            "reference": {
                "kind": "widen",
                "strikes": 1,
                "direction": None,
                "expiration": None,
            },
            "intent": "open",
            "detected_language": "English",
        }

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["header"],
            "Bear Call Spread SPY 732/736 2030-11-15",
        )

    async def test_run_moves_a_spread_to_a_new_expiration(self) -> None:
        base = spread_body()["position"]
        body = {
            "position": None,
            "context": [base],
            "reference": {
                "kind": "expiration",
                "strikes": None,
                "direction": None,
                "expiration": "2027-01-15",
            },
            "intent": "open",
            "detected_language": "English",
        }

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["header"],
            "Bull Put Spread SPY 732/729 2027-01-15",
        )

    async def test_run_reports_nearest_strikes_for_an_unlisted_strike(self) -> None:
        body = single_body()
        body["position"]["legs"][0]["strike"] = 999

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 422)
        self.assertIn("Nearby listed strikes", response.json()["detail"])

    async def test_run_rejects_a_reference_without_previous_position(self) -> None:
        body = {
            "position": None,
            "context": [],
            "reference": {
                "kind": "same",
                "strikes": None,
                "direction": None,
                "expiration": None,
            },
            "intent": "open",
            "detected_language": "English",
        }

        response = await self.api_client.post("/api/analysis/run", json=body)

        self.assertEqual(response.status_code, 422)
        self.assertIn("previous position", response.json()["detail"])

    async def test_run_returns_an_unbounded_long_call(self) -> None:
        response = await self.api_client.post("/api/analysis/run", json=single_body())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["header"], "Long Call SPY 600 2030-11-15")
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

        response = await self.api_client.post("/api/analysis/run", json=spread_body())

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

        response = await self.api_client.post("/api/analysis/run", json=spread_body())

        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.gemini_requests, [])
        self.assertNotIn("net_credit_debit", response.json())

    async def test_run_rejects_an_invalid_recommendation_shape(self) -> None:
        self.model_result = {"recommendation": "Too short"}

        response = await self.api_client.post("/api/analysis/run", json=spread_body())

        self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
