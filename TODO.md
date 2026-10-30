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

## Phase 3 — Analysis graph and metrics [x]

- [x] Implement the deterministic pipeline in `api/agent/graph.py`.
- [x] Implement deterministic calculations in `api/core/metrics.py`.
- [x] Verify no more than two LLM calls per analysis: one extraction call in
      `parse` and one synthesis call in `run`.
- [x] Test `POST /api/analysis/run`, output header, disclaimer, and language.
- **GATE 3:** passed on 2026-10-29. A mocked chain with a bull put spread
  returns `header: "Bull Put Spread SPY 732/729 2026-11-20"`,
  `net_credit_debit: 150.0`, `max_profit: 150.0`, `max_loss: 150.0`,
  `breakeven: 730.5`, `probability_positive: 0.7`, `theta_daily: 5.0`, the
  playbook event flags, a 1-sigma scenario, and the disclaimer. `run` makes
  exactly one Gemini call. Error paths covered: `422` missing contract or
  invalid spread, `429` Gemini quota, `502` CBOE outage, `503` missing key.
  Backend suite: 57 tests, 0 failures
  (`python -m unittest discover -p "test_*.py"`). `iv_rank` is `null` with an
  `iv_rank_unavailable` warning by design. Live deterministic check of the PRD
  example on `XSP 732/729 2026-11-20`: net credit 21.00, max loss 279.00,
  breakeven 731.79, probability 0.8758, theta 0.72/day. That check exposed and
  fixed CBOE index handling: `XSP` maps to `_XSP`, and index payloads echo
  `^XSP` in `data.symbol`. Gemini synthesis is mocked; no live model call was
  recorded.

## Phase 4 — Angular dashboard and analysis UI [x]

- [x] Select data sources: Twelve Data Basic for candles, Finnhub free for
      news, CBOE delayed for quote/VIX. Non-commercial tiers; licensed plans
      are required before a commercial launch.
- [x] Add `GET /api/chart/{symbol}` with Twelve Data candles, SMA 20/50,
      RSI 14, and deterministic pivot support/resistance.
- [x] Rework `GET /api/market/{symbol}` to combine CBOE quote, CBOE VIX, and
      Finnhub news with independent degradation and per-section sources.
- [x] Rewrite the Angular frontend; remove the legacy AAPL dashboard and Yahoo
      Finance data services.
- [x] Add the top dashboard grid: instrument selector defaulting to SPY and
      persisted in `localStorage`, price and change, support/resistance, brief
      market context, and 1–3 news headline links.
- [x] Add light and dark themes, persisted client-side, defaulting to the OS
      preference, applied before hydration.
- [x] Install `ng-apexcharts` and render candlesticks with API-provided SMA/RSI
      indicators.
- [x] Scale the chart price axis to the visible candles and re-fit it after
      zoom, pan, and reset.
- [x] Move support/resistance labels to the left, share the muted accessible
      palette with the Key levels panel, reduce tick/marker density, and
      shorten axis level labels.
- [x] Brighten candles and indicators relative to support/resistance, add a
      volume histogram under the candles, and render Key levels as matching
      rounded colored pills.
- [x] Implement user-added trend lines as extra line series synchronized to the
      chart's datetime axis.
- [x] Place the AI chat directly below the market grid and chart, with an
      intent selector and missing-field prompts.
- [x] Generate the chat example from the live chain: a future expiration and
      near-money strikes from the current CBOE chain, with a readable
      explanation.
- [x] Keep the assistant chat message short instead of repeating the analysis
      card content.
- [x] Add the accessible chart fallback (keyboard-reachable data table).
- [x] Load XSP and VIX candles from CBOE daily index history without a paid
      Twelve Data plan; hide the volume pane when the source has no volume.
- [x] Remove the legacy Yahoo Finance endpoints and rename the FastAPI app.
- [x] Configure real `TWELVE_DATA_API_KEY` and `FINNHUB_API_KEY` values and
      verify the live market, chart, parse, and run endpoints.
- [x] Verify the chart interaction, theme switch, and chat analysis card in a
      browser on `vercel dev`.
- **GATE 4:** passed on 2026-10-30. A headless Chrome pass against
  `vercel dev` on `http://localhost:3000/` verified the SPY dashboard with live
  CBOE price 761.69 (-0.98%), VIX 18.50, three Finnhub headlines, three support
  and one resistance level, two chart panes, the 12-row accessible chart table,
  and the **Delayed 15 min** badge. The theme switched from light to dark and
  persisted as `osa.theme=dark`; SMA 20 turned on and appeared in the readout;
  a keyboard-drawn trend line enabled Clear; `Use example` produced
  `Sell the 750 put and buy the 745 put on SPY expiring 2026-12-11`; and
  `Analyze` rendered `Bull Put Spread SPY 750/745 2026-12-11` with the
  disclaimer. Earlier on 2026-10-29, `vercel dev` served `/` (200, title
  "Options Strategy Assistant"), `/api/docs` (200), live `/api/market/SPY`,
  132-candle `/api/chart/SPY?range=6mo`, XSP candles from
  `cboe_index_history`, and the PRD analysis flow. Backend: 75 tests passed at
  that point; frontend: 28 tests passed and the production build succeeded.

## Phase 5 — Degradation and tests [x]

- [x] Test CBOE 429 with fresh-cache behavior and stale-cache degradation.
- [x] Test CBOE 5xx retry and degraded response with no fabricated values.
- [x] Verify unavailable news/candles do not block options analysis.
- [x] Run all relevant backend and frontend tests.
- [x] Update `CHANGELOG_LATEST.md` with verified results.
- **GATE 5:** passed on 2026-10-30. CBOE now retries a 5xx once; without a
  cache it returns `degraded: true`, `reason: "upstream_error"`, empty
  contracts, and `as_of: null`. On 429 it serves a cache less than ten minutes
  old with `warnings: ["cached_data"]` and `reason: "rate_limited"` or returns
  `warnings: ["rate_limited"]` with no contracts. Twelve Data 429/5xx and
  Finnhub 429/5xx degrade independently, a missing news/candle key does not
  block `/api/analysis/run`, and mocks prove no fabricated values. Backend: 93
  tests pass; frontend: 43 tests pass; production build succeeds.

## Phase 6 — Chat scope and misuse guardrails [x]

- [x] Document the allowed chat scope and state that the assistant is not a
      general-purpose chatbot.
- [x] Add message-size, leg-count, symbol, and strategy validation before any
      Gemini call.
- [x] Add a deterministic pre-LLM scope check that refuses off-topic,
      nonsensical, abusive, and prompt-injection requests with a short message
      and no analysis card.
- [x] Keep system instructions, provider keys, and internal prompts server-side,
      never echo them, and validate Gemini output against the schema.
- [x] Add tests for off-topic requests, prompt injection, oversized input,
      unsupported symbols or strategies, secret leakage, and no Gemini call on
      refused requests.
- [x] Document that the service must not be repurposed for unrelated content
      generation, personalized financial advice, trade execution, market
      manipulation, spam, or other personal use outside the intended product.
- **GATE 6:** passed on 2026-10-30. `api/core/guardrails.py` runs before
  extraction and enforces the 2,000-character message limit, default-symbol
  format, a two-buy/sell-leg limit, and short refusals for off-topic,
  nonsensical, abusive, creative-generation, prompt-injection,
  secret-probing, and unsupported-strategy requests. Refused requests return
  `422` with no analysis fields and make zero Gemini calls. Tests cover
  off-topic, injection, abusive, oversized, unsupported-strategy, unsupported
  symbol, and three-leg inputs, and assert that refusals expose no key or
  internal instruction text. Backend: 93 tests pass; frontend: 42 tests pass;
  production build succeeds.
