import os
import unittest
from datetime import UTC, datetime, timedelta
from math import sin
from unittest.mock import patch

import httpx
from index import app
from routers.chart import ChartResponse

START = datetime(2026, 1, 1, tzinfo=UTC)
CANDLE_COUNT = 60


def twelve_data_payload() -> dict[str, object]:
    values: list[dict[str, str]] = []
    for index in range(CANDLE_COUNT):
        close = 100 + 5 * sin(index / 5)
        day = START + timedelta(days=index)
        values.append(
            {
                "datetime": day.strftime("%Y-%m-%d"),
                "open": f"{close:.2f}",
                "high": f"{close + 1:.2f}",
                "low": f"{close - 1:.2f}",
                "close": f"{close:.2f}",
                "volume": "1000",
            }
        )
    values.reverse()
    return {"status": "ok", "values": values}


def cboe_history_csv() -> str:
    lines = ["DATE,OPEN,HIGH,LOW,CLOSE"]
    for index in range(CANDLE_COUNT):
        close = 100 + 5 * sin(index / 5)
        day = START + timedelta(days=index)
        lines.append(
            f"{day.strftime('%m/%d/%Y')},{close:.2f},"
            f"{close + 1:.2f},{close - 1:.2f},{close:.2f}"
        )
    return "\n".join(lines)


class ChartApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.status_code = 200
        self.plan_error = False
        self.payload: dict[str, object] = twelve_data_payload()
        self.requests: list[httpx.Request] = []
        self.environment = patch.dict(os.environ, {"TWELVE_DATA_API_KEY": "test-key"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.upstream_response)
        )
        app.state.http_client = self.http_client
        app.state.twelve_data_provider = None
        app.state.twelve_data_provider_client = None
        app.state.cboe_history_provider = None
        app.state.cboe_history_provider_client = None
        self.api_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.api_client.aclose()
        await self.http_client.aclose()

    async def upstream_response(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "cdn.cboe.com":
            return httpx.Response(200, text=cboe_history_csv())
        if request.url.host != "api.twelvedata.com":
            return httpx.Response(404, json={"detail": "unexpected host"})
        if self.status_code != 200:
            if self.status_code == 404 and self.plan_error:
                return httpx.Response(
                    404,
                    json={
                        "code": 404,
                        "message": (
                            "This symbol is available starting with the Grow "
                            "or Venture plan. Consider upgrading now."
                        ),
                    },
                )
            return httpx.Response(self.status_code, json={"error": "x"})
        return httpx.Response(200, json=self.payload)

    async def test_chart_returns_candles_indicators_and_levels(self) -> None:
        response = await self.api_client.get("/api/chart/SPY?range=6mo")

        self.assertEqual(response.status_code, 200)
        body = ChartResponse.model_validate(response.json())
        self.assertEqual(body.symbol, "SPY")
        self.assertEqual(body.range, "6mo")
        self.assertEqual(body.interval, "1d")
        self.assertEqual(len(body.candles), CANDLE_COUNT)
        self.assertEqual(body.candles[0].t, START)
        self.assertEqual(body.candles[-1].t, START + timedelta(days=CANDLE_COUNT - 1))
        self.assertEqual([series.period for series in body.sma], [20, 50])
        self.assertEqual(len(body.sma[0].points), CANDLE_COUNT - 20 + 1)
        self.assertEqual(len(body.sma[1].points), CANDLE_COUNT - 50 + 1)
        self.assertEqual(body.rsi.period, 14)
        self.assertEqual(len(body.rsi.points), CANDLE_COUNT - 14)
        self.assertEqual(body.source, "twelve_data")
        self.assertEqual(body.as_of, body.candles[-1].t)
        self.assertFalse(body.degraded)
        self.assertTrue(body.support)
        self.assertTrue(body.resistance)

    async def test_chart_does_not_leak_the_key(self) -> None:
        await self.api_client.get("/api/chart/SPY")

        self.assertTrue(self.requests)
        request = self.requests[0]
        self.assertNotIn("test-key", str(request.url))
        self.assertEqual(request.headers["authorization"], "apikey test-key")
        self.assertEqual(request.url.params["interval"], "1day")

    async def test_chart_is_cached_per_symbol_and_range(self) -> None:
        await self.api_client.get("/api/chart/SPY?range=1mo")
        await self.api_client.get("/api/chart/SPY?range=1mo")

        self.assertEqual(len(self.requests), 1)

    async def test_chart_degrades_without_a_provider_key(self) -> None:
        with patch.dict(os.environ, {"TWELVE_DATA_API_KEY": ""}):
            response = await self.api_client.get("/api/chart/SPY")

        self.assertEqual(response.status_code, 200)
        body = ChartResponse.model_validate(response.json())
        self.assertEqual(body.candles, [])
        self.assertIsNone(body.source)
        self.assertIsNone(body.as_of)
        self.assertEqual(body.warnings, ["candles_provider_not_configured"])
        self.assertTrue(body.degraded)
        self.assertEqual(self.requests, [])

    async def test_chart_degrades_on_rate_limit(self) -> None:
        self.status_code = 429

        response = await self.api_client.get("/api/chart/SPY")

        self.assertEqual(response.status_code, 200)
        body = ChartResponse.model_validate(response.json())
        self.assertEqual(body.warnings, ["candles_rate_limited"])
        self.assertTrue(body.degraded)

    async def test_chart_degrades_on_upstream_5xx(self) -> None:
        self.status_code = 503

        response = await self.api_client.get("/api/chart/SPY")

        self.assertEqual(response.status_code, 200)
        body = ChartResponse.model_validate(response.json())
        self.assertEqual(body.candles, [])
        self.assertEqual(body.warnings, ["candles_unavailable"])
        self.assertTrue(body.degraded)

    async def test_chart_returns_404_for_an_unknown_symbol(self) -> None:
        self.status_code = 404

        response = await self.api_client.get("/api/chart/UNKNOWN")

        self.assertEqual(response.status_code, 404)

    async def test_chart_uses_cboe_history_for_xsp_without_a_key(self) -> None:
        with patch.dict(os.environ, {"TWELVE_DATA_API_KEY": ""}):
            response = await self.api_client.get("/api/chart/XSP?range=6mo")

        self.assertEqual(response.status_code, 200)
        body = ChartResponse.model_validate(response.json())
        self.assertEqual(body.symbol, "XSP")
        self.assertEqual(body.source, "cboe_index_history")
        self.assertEqual(len(body.candles), CANDLE_COUNT)
        self.assertEqual(body.candles[-1].t, START + timedelta(days=CANDLE_COUNT - 1))
        self.assertIsNone(body.candles[0].v)
        self.assertEqual(body.warnings, ["volume_unavailable"])
        self.assertTrue(body.degraded)
        self.assertFalse(
            any(request.url.host == "api.twelvedata.com" for request in self.requests)
        )

    async def test_chart_degrades_when_symbol_requires_a_paid_plan(self) -> None:
        self.status_code = 404
        self.plan_error = True

        response = await self.api_client.get("/api/chart/SPY")

        self.assertEqual(response.status_code, 200)
        body = ChartResponse.model_validate(response.json())
        self.assertEqual(body.candles, [])
        self.assertEqual(body.warnings, ["symbol_requires_paid_plan"])
        self.assertIsNone(body.source)
        self.assertTrue(body.degraded)

    async def test_chart_rejects_an_invalid_range(self) -> None:
        response = await self.api_client.get("/api/chart/SPY?range=10y")

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
