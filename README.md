# Finance

Options Strategy Assistant: an Angular 22 SSR frontend and FastAPI backend,
deployed together as Vercel Services. The dashboard shows a selected
instrument, key levels, market context, news headlines, an ApexCharts
candlestick chart, and a scoped AI chat for market conversation and options
analysis.

The current market data comes from free, non-commercial provider tiers: CBOE
delayed options/quote/VIX, CBOE index history for XSP/VIX candles, Twelve Data
Basic candles for other symbols, and Finnhub free news. A commercial launch
requires licensed plans or replacement providers.

## Local development

Install the dependencies and create `.env.local` in the repository root:

```powershell
uv sync --project api
```

```text
GEMINI_API_KEY=...
TWELVE_DATA_API_KEY=...
FINNHUB_API_KEY=...
```

Run the whole application from the repository root:

```powershell
vercel dev
```

Open **http://localhost:3000/**. `vercel dev` starts both services and applies
the routing rules from `vercel.json`.

Without `TWELVE_DATA_API_KEY`, the chart shows an explicit unavailable state;
without `FINNHUB_API_KEY`, the news list is empty. Keys never reach the browser.

API examples:

```text
http://localhost:3000/api/market/SPY
http://localhost:3000/api/chart/SPY?range=6mo
http://localhost:3000/api/options/chain/SPY
POST /api/chat/turn
POST /api/analysis/parse
POST /api/analysis/run
POST /api/analysis/run/stream
http://localhost:3000/api/docs
```

Swagger UI: `/api/docs`, ReDoc: `/api/redoc`, OpenAPI: `/api/openapi.json`.
These are available locally and disabled in production.

If the `vercel` command is not installed yet:

```powershell
npm install -g vercel
```

The repository must be linked to the Vercel project with `vercel link`; the
project directory is the repository root, not `api`.

`npm start` / `ng serve` starts only the Angular CLI dev server on port 4200. It
does not use the Vercel rewrites and does not route `/api` to FastAPI. Use
`vercel dev` on port 3000 to verify the full integration.

## Deploying to Vercel

1. In the Vercel project settings, set the repository root as the Root Directory.
2. Keep `vercel.json` at the root: `web` builds Angular and `api` builds FastAPI;
   the rewrites send `/api/*` to the API and all other paths to Angular.
3. Add `GEMINI_API_KEY`, `TWELVE_DATA_API_KEY`, and `FINNHUB_API_KEY` to the
   project's Environment Variables.
4. Run `vercel link` if the repository is not linked yet, then:

   ```powershell
   vercel --prod
   ```

The configuration uses Vercel Services (Beta). `api/.python-version` pins the
Python version; the service dependencies are declared in `api/pyproject.toml`
and `api/uv.lock`. For a custom domain, add its hostname to
`security.allowedHosts` in `angular.json`; local addresses and `*.vercel.app`
domains are already allowed.

## Checks

```powershell
# backend tests
api\.venv\Scripts\python.exe -m unittest discover -s api\tests -t api -p "test_*.py"

# backend lint and types (from the api directory)
uv run ruff check .
uv run pyright

# frontend
npm test -- --watch=false

# production build
npm run build
```

## MCP for development

The root `opencode.json` connects the `angular-cli`, `APIs.io`, and `finance-api`
MCP servers. opencode does not read `.mcp.json` or `.vscode/mcp.json`; those are
Claude Code and VS Code configuration.

`finance-api` starts `api/mcp_dev.py`, which calls the FastAPI application
directly and does not require `vercel dev`. Tools: `get_market`, `get_chart`,
`get_option_chain`, `parse_analysis`, `run_analysis`, `get_analysis_example`.
The server is development-only and is not part of the Vercel deployment; the
`mcp` dependency is declared in the dev group of `api/pyproject.toml` and
installed with `uv sync --project api`.

## Dashboard

The dashboard opens on AAPL and is organised top to bottom:

1. A responsive card grid with the instrument selector (persisted in
   `localStorage`), current price and change, support/resistance computed from
   candles, VIX and data timestamps, and up to three news headline links.
2. A candlestick chart with a volume histogram, SMA 20/50, RSI 14,
   support/resistance annotations, and user-added trend lines. XSP/VIX candles
   come from CBOE daily history and do not include volume, so the volume pane
   is hidden for those symbols with an explanatory note.
3. The scoped AI chat. The model understands the message, calls backend tools
   for quote, chart, option chain, news, dividends, earnings, and deterministic
   metrics, and writes the answer in the question's language. It can ask for
   missing position details, call `compute_position`, and return an analysis
   card plus an explanation. It can also switch instruments and change chart
   toggles, theme, and chart range; those changes update the visible controls and
   persist through `Preferences`. A `Thinking...` step is shown while the turn is
   in flight; tool steps, including failed ones and their English error detail,
   appear in the activity timeline.
   `Use example` submits a live example message, and user messages can be copied
   back into the input for editing. Enter sends, and Shift+Enter inserts a new
   line. The conversation height can be dragged by its corner grip or adjusted
   with the keyboard and is remembered between visits.

The UI supports light and dark themes; the theme and selected instrument are
persisted in `localStorage`, and the stored theme is applied before hydration.
Market data is delayed and labelled **Delayed 15 min**. Unavailable data is
shown as an explicit empty or degraded state, never as a fabricated value.
Outside regular US options hours, CBOE can return zero bid/ask. The API reports
the US market session and the next open, and the chat explains that the quotes
are unavailable rather than calling the contract illiquid. Metrics are never
computed from zero quotes, theoretical values, or last-trade prices.

Data is fetched in the browser after hydration: the prerendered HTML ships the
dashboard shell with explicit unavailable states, because the API is not
reachable during the static build. Trend lines can be drawn with the mouse or
with the keyboard (focus the chart, move with the arrow keys, confirm with
Enter, cancel with Escape).

## Chat scope and misuse protection

The assistant is a scoped financial conversation about the selected instrument
and its environment, plus tool-driven analysis of a single option or a two-leg
vertical spread. It is not a general-purpose chatbot, a coding assistant, or a
personal-use tool. Before any Gemini call, the API applies deterministic
message-size, leg-count, symbol, and hard safety checks. Prompt injection,
abuse, hacking, credential probing, personal use, oversized input, invalid
symbols, and more than two legs are refused with English control text and no
model call. Off-topic and unsupported-strategy requests are soft refusals
written by the model. System instructions, provider keys, and internal prompts
stay server-side and are never returned.

The service must not be repurposed for unrelated content generation,
personalized financial advice, trade execution or routing, market manipulation,
spam, hacking, credential probing, or other personal use outside the intended
market and options analysis.

## Providers and licence note

- CBOE delayed: options chain, underlying quote, VIX.
- CBOE index history: XSP and VIX daily OHLC (EOD, no volume).
- Twelve Data Basic: daily candles for other symbols and dividend dates; free
  tier allows 8 requests/minute and 800/day. XSP/SPX candles require a paid
  plan, so XSP uses the CBOE history source instead.
- Finnhub free: company news with a general-market fallback and the earnings
  calendar. Finnhub dividend endpoints return HTTP 403 on the current free
  tier.

These free tiers are for non-commercial use. Before a commercial launch,
license CBOE DataShop, Twelve Data, and Finnhub as required, or replace them
with commercially permitted sources.
