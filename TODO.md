# Phase tracker

Work top-to-bottom according to [PLAN.md](PLAN.md). Keep a checkbox open until
the work is verified; record gate evidence before marking a phase complete.
Update `CHANGELOG_LATEST.md` with each completed phase.

## Phase 0 — Baseline and routing [x]

- [x] Inspect existing application and deployment; decide what to reuse,
      refactor, or replace.
- [x] Configure server-side `GEMINI_API_KEY` and
      `gemini-3.1-flash-lite` access without exposing the key to the client.
- [x] Verify local `.env.local` is ignored by Git.
- [x] Keep the current Vercel service entry points for the initial
      implementation; verify the routing configuration.
- [x] Confirm `vercel dev` serves `/` and `/api/docs` with HTTP 200.
- [x] Record routing evidence: on 2026-10-29, `vercel dev --listen 3000`
      served `http://localhost:3000/` and
      `http://localhost:3000/api/docs`; browser screenshots were captured.
- **GATE 0:** passed locally. Configure the production `GEMINI_API_KEY` in
  Vercel project settings before production deployment.

## Phase 1 — CBOE provider and schemas [x]

- [x] Implement the CBOE options provider, redirect handling, payload
      validation, and documented index-symbol prefix handling.
- [x] Define and validate the normalized option and chain schemas.
- [x] Implement `GET /api/options/chain/{symbol}` with optional expiration
      filtering.
- [x] Implement `GET /api/market/{symbol}` with available CBOE quote fields
      and explicit degraded metadata for unavailable data.
- [x] Add 60-second in-memory per-symbol chain cache.
- [x] Verify a live SPY chain returns delta, IV, bid, ask, open interest,
      `source`, and `as_of`.
- **GATE 1:** passed on 2026-10-29. Live
  `GET /api/options/chain/SPY` returned 12,374 contracts with the required
  quote fields, `source: "cboe_delayed"`, and `as_of: "2026-10-29T01:31:27"`.
  Live `GET /api/market/SPY` returned the available CBOE quote and explicitly
  reported unavailable support/resistance, VIX, and news.

## Phase 2 — Playbooks and parser [x]

- [x] Add all eight playbook JSON files.
- [x] Document and test the vertical-spread identification truth table.
- [x] Implement structured parsing for `POST /api/analysis/parse`.
- [x] Test bull put parsing with ISO and `DD.MM.YYYY` dates, bear call parsing,
      and missing expiration.
- **GATE 2:** passed on 2026-10-29. All four vertical spreads, all four single
  legs, and the differing-expiration case pass; `sell 732 put and buy 729 put
  XSP 2026-11-20` resolves to `bull_put_spread`; `buy call SPY 600` returns
  exactly `missing_fields: ["expiration"]`. Backend suite: 37 tests, 0 failures
  (`python -m unittest discover -s api -p "test_*.py"`). Gemini calls are
  covered by mocked contract tests; no live model call was recorded.

## Phase 3 — Analysis graph and metrics [ ]

- [ ] Implement classify, completeness, playbook, fetch, metrics, synthesize,
      and format nodes.
- [ ] Implement deterministic calculations in `api/core/metrics.py`.
- [ ] Verify no more than two LLM calls per analysis.
- [ ] Test `POST /api/analysis/run`, output header, disclaimer, and language.
- **GATE 3:** end-to-end analysis acceptance criteria pass.

## Phase 4 — Angular dashboard and analysis UI [ ]

- [ ] Decide the data source for candles, news, key levels, and market context,
      or commit to explicit unavailable states for those panels.
- [ ] Rewrite the Angular frontend; remove the legacy AAPL dashboard and Yahoo
      Finance data services.
- [ ] Add the top dashboard grid: instrument selector defaulting to SPY and
      persisted in `localStorage`, price and change, support/resistance, brief
      market context, and 1–3 news headline links.
- [ ] Add light and dark themes, persisted client-side, defaulting to the OS
      preference, applied before hydration.
- [ ] Install `ng-apexcharts` and render candlesticks with API-provided SMA/RSI
      indicators.
- [ ] Implement user-added trend lines as an overlay synchronized to the
      ApexCharts canvas.
- [ ] Place the AI chat directly below the market grid and chart.
- [ ] Add the accessible chart fallback (keyboard-reachable summary or table).
- [ ] Remove the legacy Yahoo Finance endpoints and rename the FastAPI app.
- [ ] Verify the complete browser flow on `vercel dev`.
- **GATE 4:** theme switch, SPY selection, trend line, indicator, chat spread
  submission, and analysis card all work on `vercel dev`.

## Phase 5 — Degradation and tests [ ]

- [ ] Test CBOE 429 with fresh-cache behavior and stale-cache degradation.
- [ ] Test CBOE 5xx retry and degraded response with no fabricated values.
- [ ] Verify unavailable news/candles do not block options analysis.
- [ ] Run all relevant backend and frontend tests.
- [ ] Update `CHANGELOG_LATEST.md` with verified results.
- **GATE 5:** all tests pass and mocked CBOE 503 degradation is demonstrated.
