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

## Phase completion

For each completed phase, update [TODO.md](TODO.md) and
`CHANGELOG_LATEST.md` in the same commit. A phase is complete only when its
gate has evidence.
