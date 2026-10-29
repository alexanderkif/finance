import unittest

import httpx
from index import app


class ApiDocumentationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(404))
        )
        app.state.http_client = self.http_client
        self.api_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.api_client.aclose()
        await self.http_client.aclose()

    async def test_docs_and_openapi_are_available_under_api(self) -> None:
        for path in ("/api/docs", "/api/redoc", "/api/openapi.json"):
            response = await self.api_client.get(path)
            self.assertEqual(response.status_code, 200, path)

    async def test_openapi_documents_the_product_endpoints(self) -> None:
        response = await self.api_client.get("/api/openapi.json")

        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        for path in (
            "/api/market/{symbol}",
            "/api/chart/{symbol}",
            "/api/options/chain/{symbol}",
            "/api/analysis/parse",
            "/api/analysis/run",
        ):
            self.assertIn(path, paths)

    async def test_legacy_yahoo_endpoints_are_removed(self) -> None:
        response = await self.api_client.get("/api/openapi.json")

        paths = response.json()["paths"]
        for path in (
            "/api/candles/{ticker}",
            "/api/insights/{ticker}",
            "/api/search",
        ):
            self.assertNotIn(path, paths)

    def test_app_is_renamed(self) -> None:
        self.assertEqual(app.title, "Options Strategy Assistant API")


if __name__ == "__main__":
    unittest.main()
