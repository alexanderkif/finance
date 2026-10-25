import asyncio
import unittest

import httpx
from fastapi.testclient import TestClient

from index import app


class MarketApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.http_client: httpx.AsyncClient = httpx.AsyncClient(
            transport=httpx.MockTransport(self.yahoo_response),
        )
        app.state.http_client = self.http_client
        self.client: httpx.Client = TestClient(app)

    def tearDown(self) -> None:
        asyncio.run(self.http_client.aclose())

    @staticmethod
    def yahoo_response(request: httpx.Request) -> httpx.Response:
        if "/chart/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "timestamp": [1792886400, 1792972800],
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": [250.0, 252.0],
                                            "high": [255.0, 256.0],
                                            "low": [248.0, 251.0],
                                            "close": [253.0, 254.5],
                                            "volume": [1000, 1200],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                },
            )
        if "/insights/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "finance": {
                        "result": {
                            "instrumentInfo": {
                                "technicalEvents": {
                                    "shortTerm": {"direction": "Bullish"},
                                    "provider": "Trading Central",
                                },
                                "keyTechnicals": {"support": 240.0},
                            }
                        }
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "quotes": [
                    {
                        "symbol": "MSFT",
                        "shortname": "Microsoft",
                        "exchange": "NMS",
                        "quoteType": "EQUITY",
                    }
                ],
                "news": [
                    {
                        "title": "Market update",
                        "publisher": "Finance News",
                        "link": "https://example.com/news",
                        "providerPublishTime": 1792972800,
                        "relatedTickers": ["MSFT"],
                    }
                ],
            },
        )

    def test_candles_return_typed_ohlcv_data(self) -> None:
        response = self.client.get("/api/candles/MSFT?range=1mo&interval=1d")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ticker"], "MSFT")
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["candles"][1]["close"], 254.5)
        self.assertEqual(body["candles"][1]["volume"], 1200)

    def test_insights_keep_nested_signal_values(self) -> None:
        response = self.client.get("/api/insights/MSFT")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["trends"]["short_term"]["direction"], "Bullish")
        self.assertEqual(response.json()["key_levels"]["support"], 240.0)

    def test_search_returns_quotes_and_news(self) -> None:
        response = self.client.get("/api/search?q=Microsoft")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["quotes"][0]["symbol"], "MSFT")
        self.assertEqual(body["news"][0]["tickers"], ["MSFT"])
        self.assertEqual(body["news_count"], 1)

    def test_invalid_chart_range_is_rejected(self) -> None:
        response = self.client.get("/api/candles/MSFT?range=invalid")

        self.assertEqual(response.status_code, 422)

    def test_swagger_docs_and_openapi_schema_are_available_under_api(self) -> None:
        docs_response = self.client.get("/api/docs")
        schema_response = self.client.get("/api/openapi.json")

        self.assertEqual(docs_response.status_code, 200)
        self.assertIn("/api/openapi.json", docs_response.text)
        self.assertEqual(schema_response.status_code, 200)
        self.assertIn("/api/candles/{ticker}", schema_response.json()["paths"])


if __name__ == "__main__":
    unittest.main()
