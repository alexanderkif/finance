# API specification

All market-data responses identify their source and `as_of` timestamp.
Unavailable values are explicit; see [DATA_CONTRACT.md](DATA_CONTRACT.md).

## LLM configuration

- Use Google Gemini model `gemini-3.1-flash-lite` on the free tier for now.
- The server reads `GEMINI_API_KEY` from its environment. Local development
  uses the repository-root `.env.local`; production uses deployment
  environment settings.
- Missing credentials, quota exhaustion, and provider failures must be
  reported explicitly; do not silently substitute another model.
- Never return, log, or expose the API key to the browser.

## Provider configuration

- `TWELVE_DATA_API_KEY` enables daily candles, indicators, and chart levels.
- `FINNHUB_API_KEY` enables news headlines.
- `GEMINI_API_KEY` enables parsing and synthesis.
- All keys are server-side only. Local development reads them from the
  repository-root `.env.local`; production reads deployment environment
  settings.
- Free tiers are used for non-commercial development. Do not launch
  commercially without licensed plans.

## `GET /api/market/{symbol}`

Response fields:

```text
symbol, price, change_pct, vix, news[], sources, as_of,
quote_as_of, vix_as_of, news_as_of, degraded, warnings[]
```

- `price` and `change_pct` come from the CBOE delayed quote.
- `vix` comes from the CBOE delayed `_VIX` quote.
- `news` contains up to three Finnhub headlines, newest first:
  `{title, url, publisher, published_at}`.
- `sources` is `{quote, vix, news}` with the provider name or `null` for each
  section.
- `as_of` is the newest available section timestamp; per-section timestamps are
  returned separately.
- Sections degrade independently. Missing quote, VIX, or news never blocks the
  others; the response is `200` with `degraded: true` and warnings.

## `GET /api/chart/{symbol}?range=6mo&interval=1d`

Returns the data needed by the dashboard candlestick chart.

Response fields:

```text
symbol, range, interval, candles: {t, o, h, l, c, v}[],
sma: {period, points[]}[], rsi: {period, points[]},
support[], resistance[], source, as_of, degraded, warnings[]
```

- XSP and VIX candles come from CBOE daily index history
  (`source: "cboe_index_history"`). Other symbols come from Twelve Data Basic
  (`source: "twelve_data"`). Candles are returned in ascending time order.
- CBOE index history is end-of-day and has no volume. Those responses carry
  `v: null` and a `volume_unavailable` warning; the UI hides the volume pane.
- `sma` contains periods 20 and 50; `rsi` is a single series with period 14.
- `support` and `resistance` are deterministic clustered pivot levels from the
  candles, at most three each.
- `source` is `"twelve_data"`, `"cboe_index_history"`, or `null` when no
  candles are available.
- `as_of` is the last candle timestamp.
- If the provider is unconfigured, rate limited, or unavailable, the endpoint
  returns empty candles and indicators with `degraded: true` and a warning.
  A Twelve Data plan restriction returns `symbol_requires_paid_plan` with `200`
  and empty candles. Never derive candles from the options chain, substitute a
  different instrument, or synthesize a series.

## `GET /api/options/chain/{symbol}?expiration=YYYY-MM-DD`

The `expiration` query parameter is optional. When provided, return only
contracts expiring on that date. Without it, return the available chain.

Response fields:

```text
symbol, expiration|null, contracts: OptionQuote[], source, as_of,
degraded, reason|null, warnings[]
```

`OptionQuote` includes the normalized fields defined in
[DATA_CONTRACT.md](DATA_CONTRACT.md).

- `as_of` is `null` only when no usable chain is available.
- On CBOE HTTP 429, serve a cached chain up to ten minutes old with
  `warnings: ["cached_data"]`, `degraded: true`, and
  `reason: "rate_limited"`. Without a cache, return empty contracts with
  `warnings: ["rate_limited"]`.
- On CBOE HTTP 5xx, retry once. If the retry fails, serve a cached chain up to
  ten minutes old with `warnings: ["cached_data"]` and
  `reason: "upstream_error"`. Without a cache, return empty contracts with
  `warnings: ["upstream_error"]`.
- Degraded chain responses keep the real cached `as_of` timestamp and never
  fabricate contracts or values.

## `POST /api/analysis/parse`

Request:

```json
{
  "message": "sell 732 put and buy 729 put XSP 2030-11-15",
  "default_symbol": "SPY"
}
```

Response:

```text
position_type: "single" | "strategy"
legs: { symbol, side, option_type, strike, expiration }[]
missing_fields: string[]
detected_language: string
strategy_key?: string
```

`default_symbol` is optional and defaults to `SPY`; the frontend should pass
its selected ticker so an omitted symbol can be resolved without guessing.
Return structured fields only; do not include an LLM explanation. Normalize
dates to `YYYY-MM-DD` and classify a vertical spread only when its legs satisfy
the truth table in [PLAYBOOK_SPEC.md](PLAYBOOK_SPEC.md). When expiration is the
only missing leg field, return exactly `missing_fields: ["expiration"]`; do
not start analysis.

## Chat scope and misuse guardrails

The assistant is limited to parsing and evaluating a single option or a two-leg
vertical spread for the selected instrument, plus questions about that analysis.
It is not a general-purpose chatbot.

- Before any Gemini call, `POST /api/analysis/parse` enforces the message size,
  default-symbol format, a deterministic two-leg limit, and a scope check.
- Off-topic, nonsensical, abusive, creative-generation, prompt-injection,
  secret-probing, and unsupported-strategy requests are refused with HTTP `422`
  and a short `detail` message. Refusals make no Gemini call, return no analysis
  fields, and never echo system instructions, prompts, or provider keys.
- Oversized messages and invalid default symbols are rejected by request
  validation before the handler runs.
- The same deterministic limits apply to messages merged from missing-field
  follow-ups; a message with more than two buy/sell legs is refused.
- Allowed strategies are a single long/short call or put and the four two-leg
  vertical spreads. Multi-leg strategies such as iron condors, butterflies,
  straddles, strangles, calendars, and diagonals are out of scope.
- The service must not be repurposed for unrelated content generation,
  personalized financial advice, trade execution or routing, market
  manipulation, spam, or other personal use outside the intended options
  analysis.
- System instructions, provider keys, and internal prompts stay server-side and
  are never returned. Every Gemini response is validated against its schema.

## `GET /api/analysis/example/{symbol}`

Returns a ready-to-send example built from the live CBOE chain. The example is
not a recommendation.

Response fields:

```text
symbol, message, description, legs[], current_price, source, as_of
```

- Pick the listed put expiration closest to 40 days, preferring 21–60 days.
- Pick the highest executable put strike at or below 99% of the underlying
  price; fall back to the nearest executable strike below the price.
- Pick the next lower executable put strike as the long leg.
- `message` is a verbose sentence containing every parser field.
  `description` explains the mechanics in plain language.
- Both are regenerated per request, so the expiration and strikes follow the
  live chain instead of a hardcoded sample.
- Return `422` when the chain has no executable puts or no lower strike.

The dashboard `Use example` button loads this response into the chat instead of
using a hardcoded ticker, strike, or expiration.

## `POST /api/analysis/run`

Runs a deterministic analysis for a complete position. Call `parse` first and do
not call this endpoint while `missing_fields` is non-empty.

Request:

```json
{
  "position": {
    "position_type": "strategy",
    "legs": [
      {
        "symbol": "XSP",
        "side": "sell",
        "option_type": "put",
        "strike": 732,
        "expiration": "2030-11-15"
      },
      {
        "symbol": "XSP",
        "side": "buy",
        "option_type": "put",
        "strike": 729,
        "expiration": "2030-11-15"
      }
    ]
  },
  "intent": "open",
  "detected_language": "English"
}
```

- `position_type` must match the leg count: one leg for `single`, two for
  `strategy`.
- The legs must satisfy the vertical-spread truth table; otherwise the endpoint
  returns `422`.
- Every leg field is required. Incomplete input is rejected with `422` instead
  of being guessed.
- Return `422` when the chain has no matching contract or no executable bid/ask
  for a leg.

Response `AnalysisResult`:

```text
strategy_key, header, recommendation, probability_positive, max_profit,
max_loss, net_credit_debit, breakeven, theta_daily, iv_rank, event_flags,
liquidity, scenario_1sigma, detected_language, disclaimer, source, as_of,
degraded, warnings[]
```

Conventions:

- Dollar values are per one contract per leg. `net_credit_debit` is signed:
  positive is a credit, negative is a debit.
- `max_profit` and `max_loss` are `null` only when theoretically unbounded: a
  long call's profit and a short call's loss.
- `probability_positive` is a delta-implied approximation, not a forecast: the
  absolute delta of the deciding long leg for debit structures, and one minus
  the absolute delta of the deciding short leg for credit structures.
- `theta_daily` is the position theta for one contract per leg, built from
  CBOE's per-share theta.
- `iv_rank` is `null` with an `iv_rank_unavailable` warning until a historical
  IV source exists.
- `event_flags` lists the playbook's sensitive events (`earnings`, `dividends`,
  `macro`). It is not an event calendar.
- `liquidity` reports the worst-leg bid/ask spread percent, the minimum open
  interest and volume across legs, and a `good`/`fair`/`poor`/`unknown` rating.
- `scenario_1sigma` is the expected move over the option's days to expiration:
  `underlying_price * atm_iv * sqrt(days_to_expiration / 365)`, where `atm_iv`
  is selected from the chain at the strike closest to the underlying price.
- `header` is deterministic and ordered short leg / long leg:
  `Bull Put Spread XSP 732/729 2030-11-15`. A single-leg header is
  `Long Call SPY 600 2030-11-15`.
- `degraded` is true when any warning is present.
- `recommendation` comes from one Gemini synthesis call and must use only the
  supplied facts. It must not define the strategy or give trade instructions.
  The disclaimer is added deterministically, not by the model.
- The whole flow makes at most two Gemini calls: one extraction call in `parse`
  and one synthesis call in `run`.

Example response values for the request above, given executable quotes and a
chain with a matching contract:

```text
header: "Bull Put Spread XSP 732/729 2030-11-15"
net_credit_debit: 150.0
max_profit: 150.0
max_loss: 150.0
breakeven: 730.5
disclaimer: "Educational analysis, not investment advice."
```

## Contract and integration tests

- Parse a single leg without expiration and assert the exact missing-fields
  response.
- Parse bull put and bear call spreads from natural language.
- Test maximum loss for a credit spread and probability calculation from
  delta.
- Run analysis against a mocked chain and mocked Gemini, and assert the header,
  credit/debit metrics, breakeven, probability, theta, liquidity, 1-sigma
  scenario, event flags, disclaimer, and answer language.
- Assert that `run` makes exactly one Gemini synthesis call and passes the
  computed metrics as facts.
- Assert `422` for a missing contract and for legs that do not form a supported
  spread, `429` for Gemini quota exhaustion, and `502` for a CBOE outage.
- Assert `iv_rank` is `null` with an `iv_rank_unavailable` warning.
- Mock CBOE 200 and verify the normalized chain, `source`, and `as_of`.
- Mock CBOE quote, `_VIX`, and Finnhub news; verify the combined market
  response, per-section sources and timestamps, and the general-news fallback.
- Verify market sections degrade independently: a CBOE outage keeps news, and
  a missing news key keeps price and VIX.
- Mock Twelve Data and verify candle normalization, SMA 20/50, RSI 14, support
  and resistance, the 60-second cache, and the key staying out of the URL.
- Mock CBOE index history and verify XSP candles load without a Twelve Data
  key, with `source: "cboe_index_history"` and `volume_unavailable`.
- Verify chart degradation for a missing key, a rate limit, a paid-plan
  restriction, and an unknown symbol.
- Verify the example endpoint picks a future expiration, a near-money strike,
  and the next lower strike, and returns a verbose message.
- Mock CBOE 503 and verify the single retry, then a degraded response with no
  fabricated values.
- Mock CBOE 429 with a fresh cache and verify no upstream call is made; with a
  stale cache under ten minutes, verify the cached chain, `cached_data`, and
  `reason: "rate_limited"`; with no cache, verify empty degraded output.
- Verify unavailable Twelve Data and Finnhub sections do not block options
  analysis.
- Verify off-topic, abusive, unsupported-strategy, oversized, and
  prompt-injection requests are refused before Gemini, and that refusals expose
  no secrets or internal instructions.
- Verify the frontend restores the selected ticker and theme from
  `localStorage`, defaults the ticker to SPY, and applies the OS theme when no
  choice is stored.
- Verify the dashboard renders the market grid, the candlestick chart with a
  trend line and an indicator, and the news headline links.
- Verify the AI chat is rendered directly below the market grid and chart, and
  prompts for missing fields before analysis.
- Verify degraded chart and news responses render an unavailable state instead
  of synthetic data.

## Phase rule

A phase is complete only after its gate passes and `CHANGELOG_LATEST.md` is
updated; see [PLAN.md](PLAN.md).
