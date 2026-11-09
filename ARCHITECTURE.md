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
│   ├── twelvedata_provider.py
│   ├── finnhub_provider.py
│   ├── indicators.py        # deterministic SMA/RSI and pivot levels
│   ├── metrics.py           # deterministic calculations only
│   └── playbooks/           # JSON playbook definitions
├── agent/
│   ├── graph.py
│   └── prompts.py
└── tests/                   # unittest suite; `api/` is the import root
```

The conversational flow adds `routers/chat.py` for `POST /api/chat/turn`,
`agent/chat.py` for the structured router and answer prompt,
`core/chat_i18n.py` for English/Russian deterministic chat text,
`core/market_digest.py` for deterministic trend/level/volatility facts, and
`core/patterns.py` for candlestick-pattern detection. The Angular chat copy
catalog is `src/app/components/analysis-chat/chat-copy.ts`.

Keep HTTP routing, provider access, deterministic metrics, and LLM orchestration
in their respective modules. Providers are isolated behind adapters so the
free-tier sources can be replaced without changing response contracts.

Use `gemini-3.5-flash-lite` for both model calls per analysis: extraction and
synthesis. Prefer a direct Gemini structured-output call; adopt
LangChain/LangGraph only if the analysis flow grows beyond one deterministic
pipeline, and record that decision. The current implementation calls Gemini
directly over HTTP and runs the pipeline in `api/agent/graph.py`.

## Provider configuration

- `GEMINI_API_KEY` enables extraction and synthesis.
- `TWELVE_DATA_API_KEY` enables daily candles for non-index symbols.
- CBOE index history provides XSP and VIX daily OHLC without a key.
- `FINNHUB_API_KEY` enables news headlines.
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
- The chat is a scoped financial conversation about the selected instrument,
  with an option-drafting mode. It sends the already-loaded market and chart
  snapshot to `POST /api/chat/turn`, keeps the transcript, draft, and previous
  positions on the client, and returns to the conversation after every analysis
  card.
- Explicit switch commands switch the selected symbol immediately; exploratory
  questions ask for confirmation. An option request for another symbol carries
  a pending draft across the switch.
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
- The chat infers the intent (open, close, roll; open by default) from the
  message and sends it to the analysis endpoint. There is no intent selector.
- Do not render a chat-turn "interpreting" step. When a request is cancelled or
  replaced, remove its in-progress stages instead of showing a failure. Do not
  add a separate "card added" acknowledgement; the inline card is the answer.
- The chat streams `POST /api/analysis/run/stream` as NDJSON through `fetch` to
  show real stage progress, the interpreted position, and recent headlines
  before the analysis card. `POST /api/analysis/run` remains the JSON endpoint
  for other clients.
- The client keeps the last three complete positions and sends them as
  `context` to the chat turn and analysis; no user state is stored server-side.
  Reference edits are applied against the listed strike ladder before any
  metric is computed.

## Agent boundary

Chat state contains the mode, the active draft, client-owned history and
previous positions, the last detected answer language, an optional pending
switch, and the dashboard market snapshot. The transcript, draft, and context live on the client; the server is
stateless.

Natural-language routing and extraction use Gemini structured output. Schema
validation, strategy classification, market-digest construction, candlestick
pattern detection, and all financial arithmetic remain deterministic. The
market snapshot is conversational context only; it must never supply a metric
to the analysis pipeline, which always re-fetches the chain, quote, candles,
and news from the providers.

LLM calls are limited to one structured chat call per turn and one synthesis
call per confirmed analysis. `POST /api/chat/turn` performs routing, extraction,
and the grounded market answer in one call. A deterministic refusal makes zero
calls. A plain "yes" in confirm mode and a plain cancel are handled on the
client without a chat turn; the confirmed position goes straight to the
analysis stream. A confirmed analysis then calls `POST /api/analysis/run` or
its streaming variant, which makes exactly one synthesis call. A single option
request followed by a plain confirmation therefore makes at most two Gemini
calls in total. A further edit is a new turn and may add one chat call for that
edit. `POST /api/analysis/parse` remains available for structured extraction
clients and internal reuse.

The synthesis prompt receives computed facts and optional ticker headlines as
context, and must not perform arithmetic or present news as a calendar. The
chat prompt receives the deterministic digest, recent candles, and headlines;
it must not calculate new values, invent data, or claim causation. The
extraction call may receive client-owned previous positions to resolve
references, but every resulting leg is validated against the real listed chain
before metrics run.

Deterministic limits and a scope check run before the model. Off-topic,
hacking, credential-probing, personal-use, oversized, abusive, and
prompt-injection input is refused without an analysis card. When a deterministic
check passes, the structured router may still return a refusal; it is not the
only protection.

## Guardrails

`api/core/guardrails.py` runs synchronously before the chat router or
extraction. It enforces the message size and symbol format, a deterministic
two-leg limit, and refuses off-topic, nonsensical, abusive, creative-generation,
hacking, credential-probing, prompt-injection, personal-use, and
unsupported-strategy requests. Refused requests return a short message with no
analysis fields and never echo secrets or internal instructions. Deterministic
refusals make no Gemini call. These limits apply to any merged missing-field
follow-up text and to the chat snapshot validation.

## Current implementation

The Yahoo Finance endpoints and the "Yahoo Finance API" title have been removed.
The API is now `Options Strategy Assistant API` and exposes market, chart,
options, chat, parse, and analysis routes. The Phase 11 conversational chat
contract (`POST /api/chat/turn`) is documented in [API_SPEC.md](API_SPEC.md)
and implemented by `routers/chat.py`, `agent/chat.py`, and the deterministic
helpers in `core/`. CBOE 429/5xx responses now serve a cache
less than ten minutes old or an explicit degraded response, and unavailable
news or candle providers do not block options analysis. Phase 4 frontend
verification is still pending a real-browser pass; the integrated `vercel dev`
routes, CBOE quote/VIX, and the Twelve Data chart endpoint have been verified
with the Twelve Data demo key.
