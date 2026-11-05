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
  from both `XSP 2030-11-15` and `XSP 15.11.2030` date formats, and return
  exactly `missing_fields: ["expiration"]` for `buy call SPY 600`.

## Phase 3 — Analysis pipeline and metrics (GATE 3)

- Implement the deterministic pipeline in `api/agent/graph.py` and the
  calculations in `api/core/metrics.py`.
- Classify the playbook deterministically. Make no more than two Gemini calls
  across the flow: extraction in `parse` and synthesis in `run`.
- Implement `POST /api/analysis/run` with the deterministic header, per-contract
  dollar metrics, delta-implied probability, liquidity, 1-sigma scenario,
  event flags, disclaimer, and answer language.
- Report unavailable metrics explicitly: `iv_rank` stays `null` with a warning
  until a historical IV source exists.
- **GATE 3:** a valid `POST /api/analysis/run` returns an `AnalysisResult` with
  the required header, metrics, event flags, and answer language; contract
  tests cover the 422, 429, and 502 paths.

## Phase 4 — Angular dashboard and analysis UI (GATE 4)

Data-source decision: Twelve Data Basic for daily candles, Finnhub free for
news, CBOE delayed for options, underlying quote, and VIX. These are
non-commercial tiers; a commercial launch requires licensed plans. Implemented
with independent degradation per section; no synthetic data.

- Rewrite the Angular frontend; do not preserve the legacy layout or the Yahoo
  Finance data services.
- Add the top dashboard grid: instrument selector defaulting to SPY and
  persisted in `localStorage`, current price and change, support/resistance,
  brief market context, and one to three news headline links.
- Render the candlestick chart with `ng-apexcharts`, a volume histogram, and
  API-provided SMA/RSI indicators, plus user-added trend lines.
- Add light and dark themes, persisted client-side, defaulting to the OS
  preference, with the stored theme applied before hydration.
- Place the AI chat directly below the dashboard grid and chart, before
  secondary content.
- Generate the chat example from the live chain: a future expiration and the
  nearest executable strikes around the current price, never a hardcoded
  sample.
- Remove the legacy Yahoo Finance endpoints and rename the FastAPI app.
- **GATE 4:** on `vercel dev`, switch the theme, select SPY, add a trend line
  and an indicator, submit a spread in the chat, and display its analysis
  card. Requires real Twelve Data and Finnhub keys plus a browser pass.

## Phase 5 — Degradation and end-to-end tests (GATE 5)

- Implement and test CBOE 429/5xx behavior, including stale-cache serving.
- Test Twelve Data 429/5xx and Finnhub 429/5xx behavior without blocking other
  dashboard sections.
- Verify missing news/candles do not block options analysis.
- **GATE 5:** all relevant tests pass, including mocked CBOE 503 degradation and
  provider rate-limit paths.

## Phase 6 — Chat scope and misuse guardrails (GATE 6)

- Define the allowed chat scope: a single option or two-leg vertical spread for
  an instrument with a CBOE chain, plus intent selection and missing-field
  prompts. Document that the assistant is not a general-purpose chatbot.
- Add deterministic limits and a pre-LLM scope check that rejects off-topic,
  nonsensical, abusive, oversized, or prompt-injection requests before any
  Gemini call. Return a short refusal with no analysis card.
- Keep system instructions, provider keys, and internal prompts server-side,
  never echo them, and validate every Gemini response against its schema.
- Add tests for off-topic requests, prompt injection, oversized input,
  unsupported symbols or strategies, and secret leakage. Include a test that
  refused requests make no Gemini call.
- State that the service must not be repurposed for unrelated content
  generation, personalized financial advice, trade execution, market
  manipulation, spam, or other personal use outside the intended product.
- **GATE 6:** tests show off-topic and injection requests are refused before
  Gemini, oversized/unsupported inputs are rejected, and responses never expose
  secrets or internal instructions.

## Phase 7 — Chat progress and interpreted position (GATE 7)

Decisions for this phase:

- One position per message remains the contract. A message that names unrelated
  legs is refused with a clear one-position explanation instead of being
  misread as a spread.
- Keep one market-data request. Stream real stage events from
  `POST /api/analysis/run` as NDJSON (preferred) or SSE. `parse` remains a
  separate extraction request, not a market-data request.
- The analysis card keeps the recommendation. The chat shows the interpreted
  position and progress instead of duplicating the card's recommendation.

- Replace the single `Working…` line with an ordered activity timeline that
  records each step, its state, and its timing.
- Stream only real stages: price history, option chain, underlying quote,
  news context, deterministic metrics, and synthesis. Emit `started`,
  `done`, `failed`, `retry`, `warning`, `error`, `result`, and heartbeat
  events. Do not synthesize progress from timers.
- Emit the interpreted position immediately after `parse`. For a reference
  edit, show a provisional interpretation until the chain resolves it, then
  emit `position_resolved` with the absolute legs.
- Sending a new message aborts the stream, ignores stale events by request id,
  and stops server work between stages when the client disconnects. Keep the
  existing Cancel and "Retry failed step" behavior; a run retry reuses the
  parsed position and does not repeat extraction.
- Keep auto-scroll, keyboard access, and `aria-live` behavior; announce only
  the current step rather than every heartbeat.
- **GATE 7:** a browser pass on `vercel dev` shows the activity timeline for a
  live analysis, a cancellation from a new message, and a run retry without a
  second extraction call. Streaming must be verified as unbuffered in the
  deployment environment. Backend and frontend tests pass.

## Phase 8 — Conversational context and reference edits (GATE 8)

- Store the last complete parsed positions (up to three) on the client only.
  Do not add server-side user state.
- Add an optional, size-limited `context` to `POST /api/analysis/parse`. Run
  the deterministic scope check on the new user message only; validate the
  context schema and leg limits separately.
- Let the extraction call resolve references such as "the same spread",
  "shift two strikes up", "widen by two strikes", and "change the expiration".
  It may return absolute legs and an optional operation; it is not the source
  of truth for listed contracts.
- After loading the chain, validate every leg against the listed strikes. If
  the model's strike is not listed, resolve the operation deterministically
  against the sorted strike ladder; if that is impossible, return `422` with
  the nearest available strikes.
- Keep all financial arithmetic in `api/core/metrics.py`. The model never
  supplies probabilities, sigma, breakeven, P/L, theta, or volatility values.
- Intent continues to come from the Intent selector, not from the message.
- Test multilingual reference phrasing, ambiguous or missing context, shifts
  beyond the listed ladder, width changes, and expiry changes.
- **GATE 8:** a follow-up such as "the same spread, two strikes higher"
  resolves to a listed position, an unlisted target returns actionable nearest
  strikes, and tests prove no metric value comes from the model. Backend and
  frontend tests pass.

## Phase 9 — Instrument news context (GATE 9)

- Add a ticker-specific Finnhub news context for the analysis: a 30-day
  window, a small limit, and no general-news fallback presented as instrument
  news. An empty result is an explicit warning, not a fabricated headline.
- Fetch news concurrently with the history, chain, and quote work, emit a
  `news` event as soon as it is available, and include the headlines in the
  synthesis payload only as supplied context. Instruct the model not to claim
  causation, invent dates, or give trade instructions.
- Degrade news independently: a missing key, rate limit, or outage never
  blocks the option analysis. Record the source and timestamp in the response
  and surface a warning.
- News may mention dividends, earnings, or splits, but it is not a calendar.
  Do not present it as an event calendar. Structured calendars require
  separate Finnhub endpoints, verified against the real payload and documented
  in [DATA_CONTRACT.md](DATA_CONTRACT.md) before they are shown.
- Decide whether headlines appear in the card, the chat timeline, or both
  without duplicating content or overloading the card.
- **GATE 9:** a live analysis includes recent ticker headlines when available,
  omits them with a warning when Finnhub is unavailable, and shows no headline
  or date that the provider did not return. Tests cover the degraded paths.

## Phase 10 — Example intent cleanup (GATE 10)

- Remove the opening intent from the generated `Use example` message; intent
  must come only from the Intent selector.
- Update [API_SPEC.md](API_SPEC.md) and the example, chat, and endpoint tests.
- **GATE 10:** `Use example` submits an intent-free message, and the selected
  Intent value appears on the resulting analysis card.

## Phase completion

For each completed phase, update [TODO.md](TODO.md) and
`CHANGELOG_LATEST.md` in the same commit. A phase is complete only when its
gate has evidence.
