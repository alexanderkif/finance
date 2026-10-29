import os
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
from index import app
from routers.market import MarketResponse

NEWS_TIMESTAMP = int(datetime(2026, 10, 28, 16, 0, tzinfo=UTC).timestamp())
OLDER_NEWS_TIMESTAMP = int(datetime(2026, 10, 28, 15, 0, tzinfo=UTC).timestamp())


def cboe_quote_payload() -> dict[str, object]:
    return {
        "timestamp": "2026-10-28T15:48:15Z",
        "symbol": "SPY",
        "data": {
            "symbol": "SPY",
            "current_price": 772.31,
            "price_change_percent": 0.3431,
            "options": [],
        },
    }


def vix_quote_payload() -> dict[str, object]:
    return {
        "timestamp": "2026-10-28T15:49:00Z",
        "symbol": "_VIX",
        "data": {
            "symbol": "^VIX",
            "current_price": 17.11,
            "price_change_percent": 1.1827,
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
        },
        {
            "category": "company",
            "datetime": OLDER_NEWS_TIMESTAMP,
            "headline": "Older headline",
            "id": 2,
            "image": "",
            "related": "SPY",
            "source": "Newswire",
            "summary": "",
            "url": "https://example.com/older",
        },
    ]


def general_news() -> list[dict[str, object]]:
    return [
        {
            "category": "general",
            "datetime": NEWS_TIMESTAMP,
            "headline": "Market-wide headline",
            "id": 3,
            "image": "",
            "related": "",
            "source": "Marketwire",
            "summary": "",
            "url": "https://example.com/market",
        }
    ]


class MarketApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.cboe_status = 200
        self.finnhub_status = 200
        self.finnhub_company_items: list[dict[str, object]] = company_news()
        self.finnhub_general_items: list[dict[str, object]] = general_news()
        self.environment = patch.dict(os.environ, {"FINNHUB_API_KEY": "test-key"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.requests: list[httpx.Request] = []
        self.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.upstream_response)
        )
        app.state.http_client = self.http_client
        app.state.cboe_options_provider = None
        app.state.cboe_provider_client = None
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
        self.requests.append(request)
        if request.url.host == "cdn.cboe.com":
            if self.cboe_status != 200:
                return httpx.Response(self.cboe_status)
            if request.url.path.endswith("/_VIX.json"):
                return httpx.Response(200, json=vix_quote_payload())
            return httpx.Response(200, json=cboe_quote_payload())
        if request.url.host == "finnhub.io":
            self.assertNotIn("token", request.url.params)
            if self.finnhub_status != 200:
                return httpx.Response(self.finnhub_status, json={"error": "x"})
            if request.url.path.endswith("/company-news"):
                return httpx.Response(200, json=self.finnhub_company_items)
            return httpx.Response(200, json=self.finnhub_general_items)
        return httpx.Response(404, json={"detail": "unexpected host"})

    async def test_market_combines_quote_vix_and_news(self) -> None:
        response = await self.api_client.get("/api/market/SPY")

        self.assertEqual(response.status_code, 200)
        body = MarketResponse.model_validate(response.json())
        self.assertEqual(body.symbol, "SPY")
        self.assertEqual(body.price, 772.31)
        self.assertEqual(body.change_pct, 0.3431)
        self.assertEqual(body.vix, 17.11)
        self.assertEqual(len(body.news), 2)
        self.assertEqual(body.news[0].title, "SPY edges higher as breadth improves")
        self.assertEqual(body.news[0].url, "https://example.com/spy-news")
        self.assertEqual(body.sources.quote, "cboe_delayed")
        self.assertEqual(body.sources.vix, "cboe_delayed")
        self.assertEqual(body.sources.news, "finnhub")
        self.assertEqual(
            body.as_of,
            datetime.fromtimestamp(NEWS_TIMESTAMP, tz=UTC),
        )
        self.assertFalse(body.degraded)
        self.assertEqual(body.warnings, [])

    async def test_market_falls_back_to_general_news(self) -> None:
        self.finnhub_company_items = []

        response = await self.api_client.get("/api/market/SPY")

        body = MarketResponse.model_validate(response.json())
        self.assertEqual(len(body.news), 1)
        self.assertEqual(body.news[0].title, "Market-wide headline")
        self.assertEqual(body.sources.news, "finnhub")

    async def test_market_reports_missing_news_key_without_fabricating(self) -> None:
        with patch.dict(os.environ, {"FINNHUB_API_KEY": ""}):
            response = await self.api_client.get("/api/market/SPY")

        self.assertEqual(response.status_code, 200)
        body = MarketResponse.model_validate(response.json())
        self.assertEqual(body.news, [])
        self.assertIsNone(body.sources.news)
        self.assertIn("news_provider_not_configured", body.warnings)
        self.assertTrue(body.degraded)
        self.assertEqual(body.price, 772.31)
        self.assertEqual(body.vix, 17.11)

    async def test_market_reports_cboe_outage_but_keeps_news(self) -> None:
        self.cboe_status = 503

        response = await self.api_client.get("/api/market/SPY")

        self.assertEqual(response.status_code, 200)
        body = MarketResponse.model_validate(response.json())
        self.assertIsNone(body.price)
        self.assertIsNone(body.vix)
        self.assertEqual(len(body.news), 2)
        self.assertIsNone(body.sources.quote)
        self.assertIsNone(body.sources.vix)
        self.assertIn("quote_unavailable", body.warnings)
        self.assertIn("vix_unavailable", body.warnings)
        self.assertTrue(body.degraded)

    async def test_market_reports_news_rate_limit(self) -> None:
        self.finnhub_status = 429

        response = await self.api_client.get("/api/market/SPY")

        body = MarketResponse.model_validate(response.json())
        self.assertEqual(body.news, [])
        self.assertIn("news_rate_limited", body.warnings)
        self.assertEqual(body.price, 772.31)

    async def test_market_requests_do_not_leak_the_news_key(self) -> None:
        await self.api_client.get("/api/market/SPY")

        finnhub_requests = [
            request for request in self.requests if request.url.host == "finnhub.io"
        ]
        self.assertTrue(finnhub_requests)
        self.assertEqual(finnhub_requests[0].headers["x-finnhub-token"], "test-key")


if __name__ == "__main__":
    unittest.main()
