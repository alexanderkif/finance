# Architecture

## Repository and deployment

- Angular application: repository root, under `src/`.
- FastAPI service: `api/`.
- Vercel Services and public rewrites: root `vercel.json`.
- Route `/api/*` to the API service and other public paths to the Angular
  service, as configured in `vercel.json`.
- Python version and dependencies are defined by `api/pyproject.toml` and
  `api/uv.lock`; the current project requirement is Python `>=3.14`.
- The current Vercel configuration points to `api/index:app`. The application
  may be fully rewritten; retain or replace this entry point as appropriate,
  and verify the resulting Vercel routes.
- Use `vercel dev` to verify the integrated application; `ng serve` alone
  does not exercise Vercel rewrites.

## Target API layout

```text
api/
├── index.py                 # Vercel entry point; exports the FastAPI app
├── routers/
│   ├── market.py
│   ├── options.py
│   └── analysis.py
├── core/
│   ├── cboe_provider.py
│   ├── metrics.py            # deterministic calculations only
│   └── playbooks/            # JSON playbook definitions
└── agent/
    ├── graph.py
    └── prompts.py
```

Keep HTTP routing, provider access, deterministic metrics, and LLM orchestration
in their respective modules. Use `gemini-3.1-flash-lite` for both model calls
per analysis (classification and synthesis). Prefer a direct Gemini
structured-output call; adopt LangChain/LangGraph only if the analysis flow
grows beyond one deterministic pipeline, and record that decision. The current
implementation calls Gemini directly over HTTP.

Read `GEMINI_API_KEY` only in the server process. Load it from the
repository-root `.env.local` for local development and from deployment
environment settings in production. Never expose the key in browser code or
logs.

## Angular frontend

The existing dashboard may be fully rewritten; do not preserve its layout,
components, or data services. Follow [src/AGENTS.md](src/AGENTS.md).

- Use Angular CLI, standalone APIs, signals, and typed forms.
- Screen order: market card grid, candlestick chart, AI chat, then secondary
  content.
- Include an instrument selector that defaults to SPY and persists the selected
  symbol in `localStorage`.
- Provide light and dark themes with CSS custom properties and `color-scheme`,
  persist the choice, and default to `prefers-color-scheme`. Apply the stored
  theme before hydration to avoid a flash of the wrong theme.
- Use `ng-apexcharts` for candlesticks, API-provided SMA/RSI overlays, and
  annotations. ApexCharts annotations do not support arbitrary diagonal lines,
  so user-drawn trend lines are a separate overlay synchronized to the chart;
  do not approximate them with horizontal annotations.
- ApexStock is not adopted initially. Record that decision and revisit it only
  if `ng-apexcharts` cannot meet the chart requirements.
- Chart, levels, and news data must come from the API. Render explicit
  unavailable states instead of synthetic series or placeholder values.

## Agent boundary

Analysis state contains intent, position, missing fields, playbook, market
data, metrics, result, and detected language. Natural-language extraction uses
Gemini structured output; schema validation, strategy classification, and all
financial arithmetic remain deterministic. LLM calls are limited to
classification and synthesis.

## Rewrite freedom and current implementation

The existing service still exposes Yahoo Finance-backed endpoints
(`/api/candles`, `/api/insights`, `/api/search`) and the FastAPI app is still
titled "Yahoo Finance API". The target product contract requires CBOE for
options and prohibits Yahoo Finance in production, so these endpoints and the
title must be removed as part of the frontend rewrite (Phase 4). Treat target
functionality as planned until implemented and verified; do not preserve legacy
behavior solely for compatibility.
