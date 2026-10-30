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
└── agent/
    ├── graph.py
    └── prompts.py
```

Keep HTTP routing, provider access, deterministic metrics, and LLM orchestration
in their respective modules. Providers are isolated behind adapters so the
free-tier sources can be replaced without changing response contracts.

Use `gemini-3.1-flash-lite` for both model calls per analysis: extraction and
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
- The instrument selector defaults to SPY and persists the selected symbol in
  `localStorage`.
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
- The chat collects the intent (open, close, roll) separately because parsing
  currently returns position legs and language only.

## Agent boundary

Analysis state contains intent, position, missing fields, playbook, market
data, metrics, result, and detected language. Natural-language extraction uses
Gemini structured output; schema validation, strategy classification, and all
financial arithmetic remain deterministic in `api/core/metrics.py`. LLM calls
are limited to extraction and synthesis: one extraction call in
`POST /api/analysis/parse` and at most one synthesis call in
`POST /api/analysis/run`. The synthesis prompt receives computed facts and must
not perform arithmetic. Deterministic limits and a scope check run before
extraction: off-topic, oversized, abusive, or prompt-injection input is refused
without a Gemini call and without an analysis card.

## Guardrails

`api/core/guardrails.py` runs synchronously before extraction. It enforces the
message size and default-symbol format, a deterministic two-leg limit, and
refuses off-topic, nonsensical, abusive, creative-generation,
prompt-injection, secret-probing, and unsupported-strategy requests. Refused
requests return a short message with no analysis fields and make no Gemini
call. These limits apply to any merged missing-field follow-up text.

## Current implementation

The Yahoo Finance endpoints and the "Yahoo Finance API" title have been removed.
The API is now `Options Strategy Assistant API` and exposes market, chart,
options, parse, and analysis routes. CBOE 429/5xx responses now serve a cache
less than ten minutes old or an explicit degraded response, and unavailable
news or candle providers do not block options analysis. Phase 4 frontend
verification is still pending a real-browser pass; the integrated `vercel dev`
routes, CBOE quote/VIX, and the Twelve Data chart endpoint have been verified
with the Twelve Data demo key.
