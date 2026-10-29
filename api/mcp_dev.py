"""Dev-only MCP bridge for the local FastAPI app.

Run it from the repository root with
``uv run --project api python api/mcp_dev.py``. The bridge forwards tool calls
to the FastAPI app in-process, so no API server has to be running, and it is
never deployed to Vercel.
"""

from datetime import date
from typing import Annotated, Literal
from urllib.parse import quote

import anyio
import httpx
from index import app, lifespan
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

API_BASE_URL = "http://finance-api.local"
REQUEST_TIMEOUT_SECONDS = 60.0

ChartRange = Literal["1mo", "3mo", "6mo", "1y", "5y"]
Intent = Literal["open", "close", "roll"]

INSTRUCTIONS = (
    "Tools for the Options Strategy Assistant API. Quotes are delayed by "
    "15 minutes and analysis is educational, not investment advice."
)


class Leg(BaseModel):
    """One option leg of a position."""

    symbol: str = Field(description="Underlying or OCC symbol, for example XSP.")
    side: Literal["buy", "sell"]
    option_type: Literal["call", "put"]
    strike: float = Field(gt=0, description="Strike price in dollars.")
    expiration: date = Field(description="Expiration date in ISO format.")


def _symbol(value: str) -> str:
    """Normalize a ticker symbol for use in a URL path."""
    symbol = value.strip().upper().removeprefix("_")
    if not symbol:
        message = "Symbol must not be empty."
        raise ToolError(message)
    return quote(symbol, safe="")


def _read(response: httpx.Response) -> object:
    """Return the JSON body, or raise a tool error for HTTP failures."""
    if response.is_error:
        message = f"API returned HTTP {response.status_code}: {response.text}"
        raise ToolError(message)
    return response.json()


def build_server(client: httpx.AsyncClient) -> MCPServer:
    """Create the MCP server bound to an in-process API client."""
    server = MCPServer("finance-api", instructions=INSTRUCTIONS)

    async def get(path: str, params: dict[str, str] | None = None) -> object:
        try:
            response = await client.get(path, params=params)
        except httpx.HTTPError as error:
            message = f"API request failed: {error}"
            raise ToolError(message) from error
        return _read(response)

    async def post(path: str, body: dict[str, object]) -> object:
        try:
            response = await client.post(path, json=body)
        except httpx.HTTPError as error:
            message = f"API request failed: {error}"
            raise ToolError(message) from error
        return _read(response)

    @server.tool()
    async def get_market(
        symbol: Annotated[
            str,
            Field(description="Ticker symbol, for example SPY."),
        ],
    ) -> object:
        """Return the delayed quote, VIX, and news headlines for a symbol."""
        return await get(f"/api/market/{_symbol(symbol)}")

    @server.tool()
    async def get_chart(
        symbol: Annotated[
            str,
            Field(description="Ticker symbol, for example SPY."),
        ],
        range_: Annotated[
            ChartRange,
            Field(description="History period for the chart."),
        ] = "6mo",
    ) -> object:
        """Return daily candles, SMA, RSI, and support/resistance levels."""
        return await get(
            f"/api/chart/{_symbol(symbol)}",
            {"range": range_, "interval": "1d"},
        )

    @server.tool()
    async def get_option_chain(
        symbol: Annotated[
            str,
            Field(description="Underlying symbol, for example SPY."),
        ],
        expiration: Annotated[
            date | None,
            Field(description="Optional expiration date filter."),
        ] = None,
    ) -> object:
        """Return the delayed CBOE option chain for a symbol."""
        params = (
            {"expiration": expiration.isoformat()} if expiration is not None else None
        )
        return await get(f"/api/options/chain/{_symbol(symbol)}", params)

    @server.tool()
    async def parse_analysis(
        message: Annotated[
            str,
            Field(description="Natural-language description of the position."),
        ],
        default_symbol: Annotated[
            str,
            Field(description="Symbol used when the message omits one."),
        ] = "SPY",
    ) -> object:
        """Extract option legs from a message and report missing fields."""
        return await post(
            "/api/analysis/parse",
            {"message": message, "default_symbol": default_symbol},
        )

    @server.tool()
    async def run_analysis(
        legs: Annotated[
            list[Leg],
            Field(description="One option or a two-leg vertical spread."),
        ],
        intent: Annotated[Intent, Field(description="Analysis intent.")] = "open",
        position_type: Annotated[
            Literal["single", "strategy"] | None,
            Field(description="Inferred from the leg count when omitted."),
        ] = None,
        detected_language: Annotated[
            str,
            Field(description="Language code for the response."),
        ] = "en",
    ) -> object:
        """Run the deterministic strategy analysis for a position."""
        resolved_type = position_type or ("single" if len(legs) == 1 else "strategy")
        return await post(
            "/api/analysis/run",
            {
                "position": {
                    "position_type": resolved_type,
                    "legs": [leg.model_dump(mode="json") for leg in legs],
                },
                "intent": intent,
                "detected_language": detected_language,
            },
        )

    @server.tool()
    async def get_analysis_example(
        symbol: Annotated[
            str,
            Field(description="Underlying symbol, for example XSP."),
        ],
    ) -> object:
        """Build an example vertical spread for a symbol from the live chain."""
        return await get(f"/api/analysis/example/{_symbol(symbol)}")

    return server


async def main() -> None:
    """Serve the API bridge over stdio."""
    async with (
        lifespan(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=API_BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client,
    ):
        await build_server(client).run_stdio_async()


if __name__ == "__main__":
    anyio.run(main)
