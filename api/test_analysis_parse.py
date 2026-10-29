import json
import os
import unittest
from datetime import date
from typing import Literal
from unittest.mock import patch

import httpx
from core.playbook_registry import PlaybookKey
from index import app
from routers.analysis import ParsedLeg, classify_strategy, classify_vertical

Side = Literal["buy", "sell"]
OptionType = Literal["call", "put"]


def extracted_position(
    legs: list[dict[str, object]],
    detected_language: str = "English",
) -> dict[str, object]:
    return {"legs": legs, "detected_language": detected_language}


class AnalysisParseApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.model_result = extracted_position([])
        self.upstream_status = 200
        self.requests: list[httpx.Request] = []
        self.environment = patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.gemini_response)
        )
        app.state.http_client = self.http_client
        self.api_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.api_client.aclose()
        await self.http_client.aclose()

    async def gemini_response(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.upstream_status != 200:
            return httpx.Response(self.upstream_status, json={"error": "redacted"})
        response_text = json.dumps(self.model_result)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": response_text}]}}]},
        )

    def assert_gemini_request_is_structured(self) -> None:
        request = self.requests[-1]
        self.assertEqual(request.url.host, "generativelanguage.googleapis.com")
        self.assertNotIn("test-key", str(request.url))
        self.assertEqual(request.headers["x-goog-api-key"], "test-key")
        body = json.loads(request.content)
        self.assertEqual(
            body["generationConfig"]["responseMimeType"],
            "application/json",
        )
        self.assertIn("responseSchema", body["generationConfig"])

    async def test_parses_bull_put_spread_with_iso_expiration(self) -> None:
        self.model_result = extracted_position(
            [
                {
                    "symbol": "XSP",
                    "side": "sell",
                    "option_type": "put",
                    "strike": 732,
                    "expiration": "2030-11-15",
                },
                {
                    "symbol": "XSP",
                    "side": "buy",
                    "option_type": "put",
                    "strike": 729,
                    "expiration": "2030-11-15",
                },
            ]
        )

        response = await self.api_client.post(
            "/api/analysis/parse",
            json={
                "message": "sell 732 put and buy 729 put XSP 2030-11-15",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["position_type"], "strategy")
        self.assertEqual(body["strategy_key"], "bull_put_spread")
        self.assertEqual(body["missing_fields"], [])
        self.assertEqual(body["legs"][0]["expiration"], "2030-11-15")
        self.assert_gemini_request_is_structured()

    async def test_parses_bear_call_spread_with_dotted_expiration(self) -> None:
        self.model_result = extracted_position(
            [
                {
                    "symbol": "XSP",
                    "side": "sell",
                    "option_type": "call",
                    "strike": 732,
                    "expiration": "15.11.2030",
                },
                {
                    "symbol": "XSP",
                    "side": "buy",
                    "option_type": "call",
                    "strike": 735,
                    "expiration": "15.11.2030",
                },
            ]
        )

        response = await self.api_client.post(
            "/api/analysis/parse",
            json={"message": "sell 732 call and buy 735 call XSP 15.11.2030"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["strategy_key"], "bear_call_spread")
        self.assertEqual(body["legs"][1]["expiration"], "2030-11-15")
        self.assertEqual(body["missing_fields"], [])

    async def test_single_leg_without_expiration_has_only_that_missing_field(
        self,
    ) -> None:
        self.model_result = extracted_position(
            [
                {
                    "symbol": "SPY",
                    "side": "buy",
                    "option_type": "call",
                    "strike": 600,
                    "expiration": None,
                }
            ]
        )

        response = await self.api_client.post(
            "/api/analysis/parse",
            json={"message": "buy call SPY 600"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["missing_fields"], ["expiration"])
        self.assertEqual(response.json()["strategy_key"], "long_call")
        self.assertIsNone(response.json()["legs"][0]["expiration"])

    async def test_uses_the_selected_ticker_when_message_omits_symbol(self) -> None:
        self.model_result = extracted_position(
            [
                {
                    "symbol": None,
                    "side": "buy",
                    "option_type": "call",
                    "strike": 600,
                    "expiration": "2030-11-15",
                }
            ]
        )

        response = await self.api_client.post(
            "/api/analysis/parse",
            json={
                "message": "buy 600 call 2030-11-15",
                "default_symbol": " xsp ",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["legs"][0]["symbol"], "XSP")

    async def test_missing_gemini_key_is_reported_without_request(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            response = await self.api_client.post(
                "/api/analysis/parse",
                json={"message": "buy call SPY 600"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])
        self.assertEqual(self.requests, [])

    async def test_gemini_quota_exhaustion_is_reported_as_rate_limit(self) -> None:
        self.upstream_status = 429

        response = await self.api_client.post(
            "/api/analysis/parse",
            json={"message": "buy call SPY 600"},
        )

        self.assertEqual(response.status_code, 429)
        self.assertIn("quota", response.json()["detail"])
        self.assertNotIn("redacted", response.text)

    async def test_rejects_strategies_with_more_than_two_legs(self) -> None:
        self.model_result = extracted_position(
            [
                {
                    "symbol": "SPY",
                    "side": "buy",
                    "option_type": "call",
                    "strike": strike,
                    "expiration": "2030-11-15",
                }
                for strike in (600, 610, 620)
            ]
        )

        response = await self.api_client.post(
            "/api/analysis/parse",
            json={"message": "three-leg option strategy"},
        )

        self.assertEqual(response.status_code, 422)


class VerticalClassificationTests(unittest.TestCase):
    def test_identifies_each_vertical_from_the_lower_strike_leg(self) -> None:
        cases: tuple[tuple[Side, OptionType, PlaybookKey], ...] = (
            ("buy", "call", "bull_call_spread"),
            ("sell", "call", "bear_call_spread"),
            ("buy", "put", "bull_put_spread"),
            ("sell", "put", "bear_put_spread"),
        )
        expiration = date(2026, 11, 20)
        for lower_side, option_type, expected in cases:
            with self.subTest(expected=expected):
                legs = [
                    ParsedLeg(
                        symbol="SPY",
                        side=lower_side,
                        option_type=option_type,
                        strike=100,
                        expiration=expiration,
                    ),
                    ParsedLeg(
                        symbol="SPY",
                        side="sell" if lower_side == "buy" else "buy",
                        option_type=option_type,
                        strike=105,
                        expiration=expiration,
                    ),
                ]
                self.assertEqual(classify_vertical(legs), expected)

    def test_does_not_classify_legs_with_different_expirations(self) -> None:
        legs = [
            ParsedLeg(
                symbol="SPY",
                side="sell",
                option_type="put",
                strike=105,
                expiration=date(2026, 11, 20),
            ),
            ParsedLeg(
                symbol="SPY",
                side="buy",
                option_type="put",
                strike=100,
                expiration=date(2026, 12, 18),
            ),
        ]

        self.assertIsNone(classify_vertical(legs))

    def test_classifies_single_leg_playbooks(self) -> None:
        cases: tuple[tuple[Side, OptionType, PlaybookKey], ...] = (
            ("buy", "call", "long_call"),
            ("buy", "put", "long_put"),
            ("sell", "call", "short_call"),
            ("sell", "put", "short_put"),
        )
        for side, option_type, expected in cases:
            with self.subTest(expected=expected):
                leg = ParsedLeg(
                    symbol="SPY",
                    side=side,
                    option_type=option_type,
                    strike=100,
                    expiration=date(2026, 11, 20),
                )
                self.assertEqual(classify_strategy([leg]), expected)
