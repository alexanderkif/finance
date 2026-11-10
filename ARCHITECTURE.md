# Architecture

## Repository and deployment

- Angular application: repository root, under `src/`.
- FastAPI service: `api/`.
- Vercel Services and public rewrites: root `vercel.json`.
- Route `/api/*` to the API service and other public paths to the Angular
  service, as configured in `vercel.json`.
- Python version and dependencies are defined by `api/pyproject.toml` and
  `api/uv.lock`; the current project requirement is Python `>=3.14`.
- The Vercel configuration points to `api/index:app`.
- Use `vercel dev` to verify the integrated application; `ng serve` alone
  does not exercise Vercel rewrites.

## API layout

```text
api/
├── index.py                 # Vercel entry point; exports the FastAPI app
├── routers/
│   ├── market.py            # quote, VIX, news
│   ├── chart.py             # candles, indicators, key levels
│   ├── options.py
│   └── analysis.py
├── core/
│   ├── cboe_provider.py
│   ├── cboe_history_provider.py  # XSP/VIX daily OHLC history
│   ├── twelvedata_provider.py    # candles and dividends
│   ├── finnhub_provider.py       # news and earnings
│   ├── chat_models.py            # chat request/response and UI state
│   ├── chat_text.py              # English service and control text
│   ├── indicators.py             # deterministic SMA/RSI and pivot levels
│   ├── metrics.py                # deterministic calculations only
│   └── playbooks/                # JSON playbook definitions
├── agent/
│   ├── chat.py                   # tool-calling chat loop
│   ├── tools.py                  # tool declarations and executors
│   ├── graph.py
│   └── prompts.py
└── tests/                        # unittest suite; `api/` is the import root
```

The conversational flow uses `routers/chat.py` for `POST /api/chat/turn`,
`agent/chat.py` for the Gemini tool loop, `agent/tools.py` for the bounded data
and metric tools, `core/chat_models.py` for the request/response and UI-state
schemas, and `core/chat_text.py` for English service and control text. The
Angular chat renders model text, tool steps, the analysis card, and UI actions.

Keep HTTP routing, provider access, deterministic metrics, and LLM orchestration
in their respective modules. Providers are isolated behind adapters so the
free-tier sources can be replaced without changing response contracts.

Use `gemini-3.5-flash-lite` for the chat tool loop and for standalone
extraction/synthesis calls. Prefer direct Gemini function calling; adopt
LangChain/LangGraph only if the flow outgrows the deterministic tool loop, and
record that decision. The current implementation calls Gemini directly over
HTTP.

## Provider configuration

- `GEMINI_API_KEY` enables the chat tool loop, extraction, and synthesis.
- `TWELVE_DATA_API_KEY` enables daily candles for non-index symbols and dividend
  dates.
- CBOE index history provides XSP and VIX daily OHLC without a key.
- `FINNHUB_API_KEY` enables news headlines and the earnings calendar.
- CBOE delayed endpoints require no key.
- Read keys only in the server process. Load them from the repository-root
  `.env.local` for local development and from deployment environment settings
  in production. Never expose or log a key.
- The current free tiers are non-commercial. A commercial launch requires
  licensed CBOE, Twelve Data, and Finnhub plans or replacement providers.

## Angular frontend

The legacy dashboard has been replaced. Follow [src/AGENTS.md](src/AGENTS.md).

- Use Angular CLI, standalone APIs, signals, and typed forms.
- Screen order: market card grid, candlestick chart, AI chat, then secondary
  content.
- The instrument selector defaults to AAPL and persists the selected symbol in
  `localStorage`. Popular-symbol chips are alphabetical: AAPL, AMZN, DIA,
  GOOGL, IWM, META, MSFT, NVDA, QQQ, SPY, TSLA, XSP.
- The chat is model-led. It sends the market snapshot, history, previous
  positions, and current UI state to `POST /api/chat/turn`. The response contains
  model-written text, tool `steps`, an optional analysis `card`, and
  `ui_actions`. The client shows a `Thinking...` running step while the turn is
  in flight, then renders the text and card, replaces it with the returned
  `done`/`failed` steps, applies UI actions to `Preferences`, and switches the
  symbol only when `switch.explicit` is true. A failed request becomes a failed
  `Assistant request failed` step.
- Exploratory switch questions are answered conversationally; the model asks for
  confirmation in text instead of rendering a local switch card.
- Provide light and dark themes with CSS custom properties and `color-scheme`,
  persist the choice, and default to `prefers-color-scheme`. Apply the stored
  theme before hydration to avoid a flash of the wrong theme.
- Use `ng-apexcharts` for candlesticks, API-provided SMA/RSI overlays, and
  annotations. ApexCharts annotations do not support arbitrary diagonal lines,
  so user-drawn trend lines are added as extra line series synchronized to the
  chart's datetime axis; do not approximate them with horizontal annotations.
- ApexStock is not adopted. Revisit it only if `ng-apexcharts` cannot meet the
  chart requirements.
- Chart, levels, and news data must come from the API. Render explicit
  unavailable states instead of synthetic series or placeholder values.
- The model infers the intent (open, close, roll; open by default) and passes it
  to `compute_position`. There is no intent selector.
- Do not render a chat-turn "interpreting" step. When a request is cancelled or
  replaced, remove its in-progress stages instead of showing a failure. Do not
  add a separate "card added" acknowledgement; the inline card is the answer.
- The chat does not call `POST /api/analysis/run/stream`; the analysis card comes
  from the chat tool result. The analysis endpoints remain available for other
  clients.
- The client keeps the last three complete positions and sends them as
  `context`; no user state is stored server-side. Reference edits are resolved
  inside `compute_position` against the listed strike ladder.

## Agent boundary

Chat state is client-owned: transcript, previous positions, dashboard snapshot,
and current UI state. The server is stateless.

The model is the primary conversational layer. It receives the message, history,
snapshot, previous positions, and UI state, then calls tools for fresh provider
data and deterministic calculations. `agent/tools.py` bounds every result:
quotes, chart summaries, option expirations and chain slices, news, dividends,
earnings, instrument switching, UI actions, and computed metrics. The model
writes the final text; it never invents or recalculates a market value.

The tool loop is capped at 20 tool calls and 60 seconds per turn. Each tool call
is one model step, so a turn can make several Gemini calls. A hard safety block
makes zero model calls. Tool failures are returned to the model as error
payloads and appear as failed steps; the model may explain them.

`compute_position` runs the deterministic metrics pipeline without a synthesis
call. The card is the deterministic result; the model writes the explanation.
Standalone `POST /api/analysis/parse` and `/api/analysis/run` remain available
for clients that do not use the chat.

Deterministic limits and a hard safety check run before the model. Prompt
injection, abuse, hacking, credential probing, personal use, oversized input,
invalid symbols, and more than two legs are refused deterministically. Off-topic
and unsupported-strategy requests are soft refusals written by the model.

## Guardrails

`api/core/guardrails.py` runs synchronously before the chat tool loop. It
enforces the message size and symbol format, a deterministic two-leg limit, and
refuses prompt injection, abuse, hacking, credential probing, personal use, and
unsafe input with English control text. These hard blocks make no Gemini call
and never echo secrets or internal instructions. Off-topic, nonsensical,
creative-generation, and unsupported-strategy requests are left to the model as
soft refusals.

## Current implementation

The API is `Options Strategy Assistant API` and exposes market, chart, options,
chat, parse, and analysis routes. `POST /api/chat/turn` is a Gemini tool loop:
`agent/chat.py` runs the loop and `agent/tools.py` executes bounded provider and
metric tools. Deterministic metrics live in `core/metrics.py`. Twelve Data
supplies dividends and Finnhub supplies earnings. CBOE 429/5xx responses serve a
cache less than ten minutes old or an explicit degraded response, and unavailable
news or candle providers do not block options analysis.

In production, per-IP rate limits protect the API and Swagger/ReDoc/OpenAPI are
disabled. Locally, the docs remain available and rate limiting is off unless
`RATE_LIMIT_ENABLED=1` is set.
