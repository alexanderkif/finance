# Implementation plan

Work phases in order. A gate is a stop: do not claim a phase is complete until
its acceptance evidence is available. The current application may be
substantially or completely rewritten; choose the implementation that meets
the product contract and verify the resulting deployment configuration.

## Phase 0 — Baseline and routing (GATE 0)

- Inspect the existing app and deployment configuration, then decide what to
  reuse, refactor, or replace based on the product contract.
- Configure server-side Gemini access with `GEMINI_API_KEY` and the
  `gemini-3.1-flash-lite` model. Use `.env.local` for local development and
  deployment environment settings in production.
- Keep or replace the Vercel API entry point as appropriate; verify the final
  routing and deployment configuration.
- Verify `vercel dev` serves `/` and `/api/docs`.
- **GATE 0:** record the working local URLs and attach a screenshot or
  equivalent evidence in the PR.

## Phase 1 — CBOE provider and schemas (GATE 1)

- Implement CBOE delayed quote fetching, symbol normalization, Pydantic
  schemas, and a 60-second per-symbol in-memory cache.
- Add `GET /api/market/{symbol}` and `GET /api/options/chain/{symbol}`.
- Follow [DATA_CONTRACT.md](DATA_CONTRACT.md) for allowed fields and failures.
- **GATE 1:** `GET /api/options/chain/SPY` returns at least one contract with
  delta, IV, bid, ask, and open interest; `source` and `as_of` are present.

## Phase 2 — Playbooks and parser (GATE 2)

- Add all eight JSON playbooks and the vertical-spread truth table from
  [PLAYBOOK_SPEC.md](PLAYBOOK_SPEC.md).
- Implement `POST /api/analysis/parse` with Gemini
  `gemini-3.1-flash-lite` structured output and contract tests.
- **GATE 2:** tests identify the XSP example as a two-leg `bull_put_spread`
  from both `XSP 2026-11-20` and `XSP 20.11.2026` date formats, and return
  exactly `missing_fields: ["expiration"]` for `buy call SPY 600`.

## Phase 3 — Analysis graph and metrics (GATE 3)

- Implement the LangGraph flow and deterministic calculations in
  `api/core/metrics.py`.
- Limit the analysis to two LLM calls: classification and synthesis. Use
  `gemini-3.1-flash-lite` for both.
- **GATE 3:** a valid `POST /api/analysis/run` returns an `AnalysisResult`
  with the required header, metrics, event flags, and answer language.

## Phase 4 — Angular dashboard and analysis UI (GATE 4)

Prerequisite: select a commercially permitted source for candles, news, key
levels, and market context, or decide to ship those panels with explicit
unavailable states. Record the decision before building the chart and news
panels; do not synthesize data to fill the dashboard.

- Rewrite the Angular frontend; do not preserve the legacy layout or the Yahoo
  Finance data services.
- Add the top dashboard grid: instrument selector defaulting to SPY and
  persisted in `localStorage`, current price and change, support/resistance,
  brief market context, and one to three news headline links.
- Render the candlestick chart with `ng-apexcharts`, user-added trend lines,
  and API-provided SMA/RSI indicators.
- Add light and dark themes, persisted client-side, defaulting to the OS
  preference, with the stored theme applied before hydration.
- Place the AI chat directly below the dashboard grid and chart, before
  secondary content.
- Remove the legacy Yahoo Finance endpoints and rename the FastAPI app.
- **GATE 4:** on `vercel dev`, switch the theme, select SPY, add a trend line
  and an indicator, submit a spread in the chat, and display its analysis
  card.

## Phase 5 — Degradation and end-to-end tests (GATE 5)

- Implement and test CBOE 429/5xx behavior and secondary-data degradation.
- Verify missing news/candles do not block options analysis.
- **GATE 5:** all relevant tests pass, including mocked CBOE 503 degradation.

## Phase completion

For each completed phase, update [TODO.md](TODO.md) and
`CHANGELOG_LATEST.md` in the same commit. A phase is complete only when its
gate has evidence.
