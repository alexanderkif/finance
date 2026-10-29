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

## `GET /api/market/{symbol}`

Response fields:

```text
symbol, price, change_pct, support[], resistance[], vix, news[],
source, as_of, degraded, warnings[]
```

The endpoint returns CBOE-backed price/change data when available. Missing
support/resistance, VIX, and news are represented as empty or null values with
`degraded: true` and explicit warnings; they are never synthesized.

## `GET /api/chart/{symbol}?range=6mo&interval=1d`

Returns the data needed by the dashboard candlestick chart.

Response fields:

```text
symbol, range, interval, candles: {t, o, h, l, c, v}[],
sma: {period, points[]}[], rsi: {period, points[]}[],
support[], resistance[], source, as_of, degraded, warnings[]
```

When no commercially permitted source is configured for historical prices, the
endpoint returns empty `candles`, `sma`, and `rsi` with `degraded: true` and an
explicit warning. `source` must never claim CBOE for historical candles. The UI
renders an unavailable state rather than a synthetic series.

## `GET /api/options/chain/{symbol}?expiration=YYYY-MM-DD`

The `expiration` query parameter is optional. When provided, return only
contracts expiring on that date. Without it, return the available chain.

Response fields:

```text
symbol, expiration|null, contracts: OptionQuote[], source, as_of, warnings[]
```

`OptionQuote` includes the normalized fields defined in
[DATA_CONTRACT.md](DATA_CONTRACT.md).

## `POST /api/analysis/parse`

Request:

```json
{
  "message": "sell 732 put and buy 729 put XSP 2026-11-20",
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
        "expiration": "2026-11-20"
      },
      {
        "symbol": "XSP",
        "side": "buy",
        "option_type": "put",
        "strike": 729,
        "expiration": "2026-11-20"
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
  `Bull Put Spread XSP 732/729 2026-11-20`. A single-leg header is
  `Long Call SPY 600 2026-11-20`.
- `degraded` is true when any warning is present.
- `recommendation` comes from one Gemini synthesis call and must use only the
  supplied facts. It must not define the strategy or give trade instructions.
  The disclaimer is added deterministically, not by the model.
- The whole flow makes at most two Gemini calls: one extraction call in `parse`
  and one synthesis call in `run`.

Example response values for the request above, given executable quotes and a
chain with a matching contract:

```text
header: "Bull Put Spread XSP 732/729 2026-11-20"
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
- Mock CBOE 200 and verify normalized chain, `source`, and `as_of`.
- Mock CBOE 503 and verify degraded output without fabricated values.
- Mock CBOE 429 with a fresh cache and verify the cached chain is served.
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
