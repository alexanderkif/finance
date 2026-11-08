# Phase tracker

Work top-to-bottom according to [PLAN.md](PLAN.md). Keep a checkbox open until
the work is verified; record gate evidence before marking a phase complete.
Update `CHANGELOG_LATEST.md` with each completed phase.

## Phase 0 — Baseline and routing [x]

- [x] Inspect existing application and deployment; decide what to reuse,
      refactor, or replace.
- [x] Configure server-side `GEMINI_API_KEY` and
      `gemini-3.5-flash-lite` access without exposing the key to the client.
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
- [x] Add the top dashboard grid: instrument selector defaulting to SPY at the
      time (superseded by Phase 11: AAPL) and persisted in `localStorage`,
      price and change, support/resistance, brief market context, and 1–3 news
      headline links.
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

## Chat analysis cards [x]

- [x] Extract the analysis card into an `AnalysisCard` component and append one
      inline per successful answer instead of a "card updated" bubble.
- [x] Add `scenario_2sigma` and show both 1-sigma and 2-sigma ranges.
- [x] Return and display the selected intent as a card badge.
- [x] Caption the playbook event chips as event sensitivity, not a live
      calendar, with descriptive tooltips.
- [x] Add an edit-in-input icon to user messages and send on Enter while
      keeping Shift+Enter for a new line.
- [x] Add a pointer- and keyboard-accessible chat resizer with a textarea-style
      corner grip, clamped/persisted height, and double-click reset.
- [x] Submit `Use example` immediately without a separate description bubble
      and let the user edit it from the user message's edit-in-input icon.
- Evidence on 2026-11-04: backend 97 tests pass; frontend 51 tests pass;
  production build succeeds.

## Volatility context [x]

- [x] Use the CBOE ATM option IV as `current_iv`.
- [x] Compute `hv_20d` and `hv_60d` from daily candles supplied by CBOE index
      history for XSP/VIX and Twelve Data for other symbols.
- [x] Compute `hv_rank` as the current 20-day HV percentile over the trailing
      year and `iv_hv_ratio` as current IV divided by 60-day HV.
- [x] Keep `iv_rank` null because the free providers expose no historical IV
      series; do not present HV percentile as IV rank.
- [x] Show current IV, HV, HV percentile, and IV/HV in the analysis card, with
      `hv_unavailable` degradation when candles are missing.
- Evidence on 2026-11-04: live CBOE XSP history returned 260 candles with
  HV 20d 11.37%, HV 60d 10.13%, and HV percentile 46.55%; Twelve Data SPY
  returned 260 candles with HV 20d 13.25%, HV 60d 10.71%, and HV percentile
  67.67%. Backend: 97 tests pass; frontend: 47 tests pass; production build
  succeeds.

## Chat resilience and error guidance [x]

- [x] Retry transient Gemini failures and return user-facing quota/outage
      messages instead of raw upstream status text.
- [x] Retry transient chat failures in the Angular client and name the
      unavailable service between attempts.
- [x] Add a Cancel button and abort the previous request chain when a new
      message is sent.
- [x] Add a "Retry failed step" button that retries parsing when extraction
      failed, or only the analysis step with the already parsed position when
      analysis failed.
- [x] Keep the chat at the parse step and prompt for missing leg fields in
      plain language.
- [x] Auto-scroll the chat while the user is at the bottom; pause when they
      scroll up and resume at the bottom.
- [x] Add backend retry tests and frontend cancel, retry-from-failed-step, and
      auto-scroll tests. Evidence on 2026-11-04: backend 95 tests pass;
      frontend 47 tests pass; production build succeeds.

## Phase 7 — Chat progress and interpreted position [x]

- [x] Replace the single `Working…` line with an ordered activity timeline that
      records each step, its state, and its timing.
- [x] Keep one market-data request and stream real `POST /api/analysis/run`
      stage events as NDJSON (preferred) or SSE. Do not split the data fetch
      into separate requests.
- [x] Emit only real stages: price history, option chain, underlying quote,
      news context, deterministic metrics, and synthesis. Include `started`,
      `done`, `failed`, `retry`, `warning`, `error`, `result`, and heartbeat
      events; never derive progress from timers.
- [x] Emit the interpreted position immediately after `parse`. For reference
      edits, show a provisional interpretation, then the streamed `position`
      event with the absolute legs once the chain is loaded.
- [x] Abort the stream when a new message is sent, ignore stale events, and
      stop server work between stages on disconnect. Keep Cancel and "Retry
      failed step"; a run retry reuses the parsed position without repeating
      extraction.
- [x] Keep auto-scroll, keyboard access, and `aria-live` behavior, announcing
      only the current step.
- [x] Refuse a message that names unrelated legs with a clear one-position
      explanation instead of asking which spread is meant.
- [x] Keep the recommendation in the analysis card; the chat shows the
      interpreted position and progress without duplicating the card content.
- [x] Add backend streaming and frontend activity-timeline tests.
- [x] Verify through the Vercel dev proxy that the stream is not buffered.
- **GATE 7:** passed on 2026-11-05. `vercel dev` started both services; the
  NDJSON response arrived as `transfer-encoding: chunked` with
  `x-accel-buffering: no`, and a timed reader saw stages at 0.18s and 0.89s,
  a heartbeat at 10.94s, and the result at 12.81s. A headless Chrome pass
  submitted a live SPY spread, showed the activity timeline, interpreted
  position, five headlines, and the analysis card, and found no `Working…`
  text. A new message marked the first turn `Cancelled` and produced one card
  for the replacement. Chrome CDP failed the first stream request once; the
  chat retried automatically, sent two stream requests and one parse request,
  and rendered the card. Backend: 108 tests pass; frontend: 59 tests pass;
  production build succeeds. A production-deployment check remains due at
  release time.

## Phase 8 — Conversational context and reference edits [x]

- [x] Store the last complete parsed positions (up to three) on the client
      only; add no server-side user state.
- [x] Add an optional, size-limited `context` to `POST /api/analysis/parse`.
      Run the scope check on the new message only and validate the context
      schema and leg limits separately.
- [x] Let extraction resolve "the same spread", "shift two strikes up",
      "widen by two strikes", and "change the expiration". It may return
      absolute legs and an optional operation, but it is not the source of
      truth for listed contracts.
- [x] Validate every leg against the loaded chain. If a strike is not listed,
      resolve the operation deterministically against the sorted strike
      ladder; otherwise return `422` with the nearest available strikes.
- [x] Keep all financial arithmetic in `api/core/metrics.py`; the model never
      supplies probabilities, sigma, breakeven, P/L, theta, or volatility.
- [x] Keep intent sourced from the Intent selector, not from the message.
- [x] Test multilingual reference phrasing, ambiguous or missing context,
      shifts beyond the listed ladder, width changes, and expiry changes.
- **GATE 8:** passed on 2026-11-05. A "same spread, shifted two strikes up"
  request resolves to listed legs `734/732`; a reference without context
  returns `422`; an unlisted strike names the nearest listed strikes; and the
  deterministic metrics tests prove no metric value comes from the model.
  A live SPY follow-up resolved `728/727` to `730/729` and returned the
  corresponding header. Backend: 108 tests pass; frontend: 59 tests pass;
  build succeeds.

## Phase 9 — Instrument news context [x]

- [x] Add ticker-specific Finnhub news for the analysis: a 30-day window and a
      small limit, with no general-news fallback presented as instrument news.
      An empty result is an explicit warning, not a fabricated headline.
- [x] Fetch news concurrently with history, chain, and quote work; emit a
      `news` event as soon as it is available; include the headlines in the
      synthesis payload only as supplied context.
- [x] Instruct synthesis not to claim causation, invent dates, or give trade
      instructions, and keep the deterministic disclaimer and metrics.
- [x] Degrade news independently: a missing key, rate limit, or outage never
      blocks option analysis. Record the source and timestamp and surface a
      warning.
- [x] Do not present news as a dividend, earnings, or splits calendar. News may
      mention them, but structured calendars require separate Finnhub
      endpoints, verified against the real payload and documented in
      [DATA_CONTRACT.md](DATA_CONTRACT.md).
- [x] Decide whether headlines appear in the card, the chat timeline, or both
      without duplicating content or overloading the card.
- [x] Add backend and frontend tests for available news, empty news, and
      independent degradation.
- **GATE 9:** passed on 2026-11-05. A live SPY analysis streamed five ticker
  headlines with `news_source: "finnhub"` and `news_as_of`, and the synthesis
  used them only as context. A live degraded pass with an invalid Finnhub key
  returned `news: []`, `news_source: null`, and a
  `news_provider_not_configured` warning while the analysis still completed.
  Mocked tests cover empty results, rate limits, and outages. Backend: 108
  tests pass; frontend: 59 tests pass; build succeeds.

## Phase 10 — Example intent cleanup [x]

- [x] Remove the opening intent from the generated `Use example` message;
      intent must come only from the Intent selector.
- [x] Update [API_SPEC.md](API_SPEC.md) and the example, chat, and endpoint
      tests.
- **GATE 10:** passed on 2026-11-05. The example message contains no opening
  intent, and the chat test proves the selected Intent value appears on the
  resulting analysis card. Backend: 108 tests pass; frontend: 59 tests pass;
  build succeeds.

## Phase 11 - Conversational chat and guided option draft [x]

### Phase A — Contract and documentation

- [x] Define the scoped conversational chat and option-drafting contract in
      [PRD.md](PRD.md).
- [x] Add `POST /api/chat/turn` modes, request/response schemas, switch
      behavior, draft suggestions, grounding, and cost rules to
      [API_SPEC.md](API_SPEC.md).
- [x] Add the chat boundary, module layout, one-call invariant, and
      deterministic helper modules to [ARCHITECTURE.md](ARCHITECTURE.md).
- [x] Document draft suggestion defaults in
      [PLAYBOOK_SPEC.md](PLAYBOOK_SPEC.md).
- [x] Document the client market snapshot as non-authoritative context in
      [DATA_CONTRACT.md](DATA_CONTRACT.md).
- [x] Update [src/AGENTS.md](src/AGENTS.md) with the chat state machine, draft
      card, switch rules, AAPL default, and alphabetical chips.
- [x] Review and approve the Phase 11 contract before implementation.

### Phase B — Backend

- [x] Add `agent/chat.py`, `core/chat_models.py`, `core/market_digest.py`,
      `core/patterns.py`, `core/draft_suggestions.py`, `core/option_parsing.py`,
      and `routers/chat.py`.
- [x] Implement `POST /api/chat/turn` with `answer`, `draft`, `confirm`,
      `switch_symbol`, and `refused` modes.
- [x] Reuse extraction, classification, reference edits, and the listed strike
      ladder for draft suggestions.
- [x] Extend `api/core/guardrails.py` for the new scope while keeping
      deterministic refusals.
- [x] Add backend tests for modes, grounding, switch behavior, draft edits,
      red-team refusals, the one-call invariant, and snapshot isolation.

### Phase C — Frontend

- [x] Replace the parse-first flow with the chat state machine.
- [x] Add the editable draft card, confirmation, cancellation, and
      continuation-after-switch behavior.
- [x] Return to the conversational mode after every analysis card.
- [x] Default the instrument to AAPL and render the alphabetical chips.
- [x] Add frontend tests for every mode and the post-card return.

### Chat UX refinements

- [x] Remove the chat-turn interpreting activity and do not render
      cancelled/replaced stages as failed.
- [x] Remove the redundant "Card added" assistant message.
- [x] Replace the Intent selector with inferred intent (open by default).
- [x] Add backend/frontend tests for intent inference and the removed messages.

### Chat localization

- [x] Localize deterministic backend chat text for English and Russian via
      `core/chat_i18n.py`.
- [x] Localize frontend chat copy, errors, role labels, activity labels, and
      draft/switch helper text via `chat-copy.ts` and `api-error.ts`.
- [x] Add Russian localization tests for confirm, cancel, switch, refusal,
      chain failure, stage labels, and chat copy.
- Evidence on 2026-11-08: backend 139 tests pass; frontend 68 tests pass; the
  production build succeeds. A live UTF-8 Russian option request returned a
  Russian confirm.

### Phase D — Verification

- [x] Run backend and frontend suites and the production build.
- [x] Complete the `vercel dev` browser pass in GATE 11.
- [x] Record the current test/build evidence here and in
      `CHANGELOG_LATEST.md`.

- Evidence on 2026-11-08: backend 139 tests pass; frontend 68 tests pass; the
  production build succeeds. A live `uvicorn index:app` check returned an
  explicit MSFT switch, a grounded English trend answer, a Russian trend
  answer, a live `Long Call AAPL 245 2026-12-18` draft, and `intent: "close"`
  for "I want to close my long call". A fresh `vercel dev` on :3000 served
  `/api/chat/turn` and `ChatTurnResponse.intent`; headless Chrome rendered
  "Market chat" and "Instrument: AAPL" with no Intent selector; the dev logs
  showed `/api/chat/turn` and `/api/analysis/run/stream` 200 with live Gemini,
  CBOE, Twelve Data, and Finnhub calls.
- **GATE 11:** passed on 2026-11-08.
