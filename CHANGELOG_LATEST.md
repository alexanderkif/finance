# Phase log

## Phase 4 — Dashboard and providers

- Selected free, non-commercial providers: Twelve Data Basic for daily candles,
  Finnhub free for news, CBOE delayed for options, quote, and VIX.
- Added `GET /api/chart/{symbol}` with normalized candles, SMA 20/50, RSI 14,
  deterministic support/resistance, and 60-second caching.
- Reworked `GET /api/market/{symbol}` to combine quote, VIX, and news with
  per-section sources/timestamps and independent degradation.
- Removed the Yahoo Finance endpoints and renamed the app to
  "Options Strategy Assistant API".
- Rewrote the Angular dashboard with a market card grid, instrument selector
  defaulting to SPY, light/dark themes, ApexCharts candlesticks with SMA/RSI,
  trend-line drawing, news links, an accessible chart table, and the AI chat
  below the chart.
- Verified 75 backend tests and 28 frontend tests pass; the production build
  succeeds.
- Live `vercel dev` verification on 2026-10-29: `/` 200 with the new title,
  `/api/docs` 200, `/api/market/SPY` returned the CBOE quote and three Finnhub
  headlines, `/api/chart/SPY?range=6mo` returned 132 Twelve Data candles with
  SMA/RSI and three support levels, and the PRD example parsed to
  `bull_put_spread` and produced `Bull Put Spread XSP 732/729 2026-11-20` with
  probability 0.8624, max loss 276.00, and breakeven 731.76.
- Chart price axis now fits the visible candles on first render and re-fits on
  zoom, pan, and reset. The assistant announces a card update instead of
  repeating the card recommendation.
- Support/resistance labels moved to the left of the chart. The chart and Key
  levels panel now share a muted, WCAG AA-checked palette; axis ticks and line
  markers are sparser, and level labels use short rounded values.
- Candles and indicators now use a brighter, higher-contrast palette than the
  muted support/resistance levels. Added a volume histogram under the candles
  and rendered Key levels as the same rounded colored pills used on the chart.
- Added `GET /api/analysis/example/{symbol}` and wired the chat's
  `Use example` button to it. The example uses the live chain's nearest future
  expiration and near-money put strikes instead of a hardcoded ticker, strike,
  or date, and returns a readable explanation. Test fixtures now use a
  synthetic 2030 expiration instead of the stale 2026 sample.
- XSP and VIX charts now use CBOE daily index history, so XSP loads without a
  paid Twelve Data plan. Those sources have no volume; the chart shows an
  explanatory note instead of an empty histogram. Twelve Data plan errors for
  other symbols degrade with `symbol_requires_paid_plan`.
- ApexCharts toolbar and menu now follow the dark theme (`chart.theme.mode`),
  with matching panel colors and focus styling. Added a multi-size
  three-candle favicon.
- The chart price axis now rounds its bounds and tick step to nice values
  (for example 720, 740, 760), and the label formatter survives zoom/pan
  updates instead of reverting to raw decimals.
- Chart panes keep zoom/pan aligned manually, and datetime labels appear only
  on the bottom-most visible pane. Price and volume tooltips are disabled;
  hovering any pane draws a synchronized vertical line and updates the readout
  with the hovered candle's date, OHLC, and volume (or the latest candle).
  OHLC and volume values follow the candle color, enabled SMA values use their
  line colors, the RSI tooltip responds only to direct hover, and the RSI 30/70
  guide lines no longer show value labels. The candlestick pane also shows a
  horizontal price crosshair with the value labeled at its left end.
- Chart indicator and level toggles persist in `localStorage`; SMA 20, SMA 50,
  and RSI start off while support/resistance starts on. Volume bars use a more
  opaque fill.
- The selected chart range persists in `localStorage`. Zoom, pan, and Reset
  Zoom now re-fit both the price and volume y-axes to the visible window, and
  Reset Zoom restores the full range again.
- The VIX value is bold and colored by regime: green below 20, amber from 20
  to 30, and red at 30 or above.
- Split accent contrast tokens: solid accent fills use `--accent-solid` /
  `--on-accent`, tinted surfaces use `--accent-soft` / `--on-accent-soft`.
  This fixes the brand mark, Apply/Analyze buttons, chips, badges, and user
  messages.
- Removed the ApexCharts legend (Price/SMA entries) and added a
  Support/Resistance visibility checkbox alongside the SMA and RSI toggles.
- Live verification on 2026-10-29: XSP returned 132 CBOE history candles with
  `source: "cboe_index_history"` and `volume_unavailable`, while SPY returned
  132 Twelve Data candles with volume.
- GATE 4 passed on 2026-10-30 with a headless Chrome pass against `vercel dev`:
  the SPY dashboard showed live CBOE price 761.69 (-0.98%), VIX 18.50, three
  Finnhub headlines, three support and one resistance level, two chart panes,
  the accessible table, and the Delayed 15 min badge. The theme switched to
  dark and persisted; SMA 20 turned on and appeared in the readout; a
  keyboard-drawn trend line enabled Clear; `Use example` loaded a live
  2026-12-11 SPY 750/745 bull put spread; and `Analyze` rendered the analysis
  card with the disclaimer.
- The price and headline cards now show explicit loading placeholders instead
  of stale or empty values while data loads, with a matching component test.
  Also fixed mojibake punctuation in the dashboard template and ticker error.

## Phase 5 — Degradation and end-to-end tests

- CBOE options requests now retry a 5xx once. Without a cache the chain
  endpoint returns `degraded: true`, `reason: "upstream_error"`, empty
  contracts, and `as_of: null`; with a cache less than ten minutes old it serves
  the cached chain with `cached_data`.
- CBOE 429 responses serve a cache less than ten minutes old with
  `warnings: ["cached_data"]` and `reason: "rate_limited"`; otherwise the
  response is empty and degraded. Fresh cache entries are served without an
  upstream call.
- Analysis maps CBOE rate limits to `429` and upstream failures to `502` instead
  of fabricating metrics. Twelve Data 429/5xx and Finnhub 429/5xx degrade only
  their own dashboard sections, and missing news/candle keys do not block
  `/api/analysis/run`.
- New backend tests cover the retry, stale-cache, no-cache, chain 429/5xx,
  chart 5xx, market news 5xx, and provider-independence paths.
- GATE 5 passed on 2026-10-30: 93 backend tests pass, 43 frontend tests pass,
  and the production build succeeds.

## Phase 6 — Chat scope and misuse guardrails

- Added `api/core/guardrails.py`, a deterministic pre-LLM check that enforces
  the message-size limit, default-symbol format, a two-leg limit, and refuses
  off-topic, nonsensical, abusive, creative-generation, prompt-injection,
  secret-probing, and unsupported-strategy requests with a short `422` message.
- Refused requests make no Gemini call, return no analysis fields, and never
  echo provider keys or internal instructions. Existing schema validation still
  checks every Gemini response.
- Documented the allowed scope and the prohibition on unrelated content
  generation, personalized advice, trade execution, market manipulation, spam,
  and other out-of-scope use in `API_SPEC.md`, `README.md`, and
  `ARCHITECTURE.md`.
- Added nine guardrail tests covering off-topic, injection with secret-leakage
  assertions, abusive, oversized, unsupported-strategy, unsupported-symbol,
  two three-leg phrasings, and missing-field acceptance paths.
- GATE 6 passed on 2026-10-30: all guardrail tests pass, refused requests make
  zero Gemini calls, and responses expose no secrets or internal instructions.
  Backend: 93 tests pass; frontend: 43 tests pass; build succeeds.

## Phase 3 — Analysis pipeline and metrics

- Added `POST /api/analysis/run` with request validation for a single option or
  a two-leg vertical spread, rejecting unsupported legs with `422`.
- Added deterministic calculations in `api/core/metrics.py`: signed net
  credit/debit, bounded and unbounded outcomes, breakeven, delta-implied
  probability, daily theta, worst-leg liquidity, event flags, and the 1-sigma
  expected move. Dollar values are per one contract per leg.
- Added the deterministic header (short/long order for spreads), the fixed
  disclaimer, and the answer language.
- Added one Gemini synthesis call in `api/agent/graph.py`; `iv_rank` is `null`
  with a warning until a historical IV source exists.
- Fixed CBOE index handling found during live verification: `XSP` now maps to
  `_XSP`, and index payloads that echo `^XSP` in `data.symbol` are accepted.
- Verified 57 backend tests pass
  (`python -m unittest discover -p "test_*.py"`) and 2 Angular tests pass
  (`npm test`).
- Acceptance evidence for 2026-10-29: the mocked bull put spread analysis
  returns `Bull Put Spread SPY 732/729 2026-11-20`, net credit 150.00, max
  profit 150.00, max loss 150.00, breakeven 730.50, probability 0.70, theta
  5.00/day, and exactly one Gemini call. `422`, `429`, `502`, and `503` paths
  are covered. A live deterministic check of `XSP 732/729 2026-11-20` returned
  net credit 21.00, max loss 279.00, breakeven 731.79, probability 0.8758, and
  theta 0.72/day. Gemini synthesis is mocked; no live model call was recorded.

## Previous

- Phase 2 — Playbooks and parser: eight playbooks, deterministic vertical
  classification, and Gemini structured parsing with mocked contract tests.
- Phase 1 — CBOE provider and schemas: live SPY chain with delta, IV, bid, ask,
  open interest, `source: "cboe_delayed"`, and `as_of`.
