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

Request:

```text
position: SingleLeg | Strategy
intent: "open" | "close" | "roll"
detected_language: string
```

Response `AnalysisResult` includes:

```text
header, recommendation, probability_positive, max_profit, max_loss,
net_credit_debit, theta_daily, iv_rank, event_flags, liquidity,
scenario_1sigma, warnings[]
```

The header is deterministic. Example:
`Bull Put Spread XSP 732/729 2026-11-20`.
Every analysis includes `Educational analysis, not investment advice.` and
answers in the detected language. Calculated values come from deterministic
backend code, not the LLM.

## Contract and integration tests

- Parse a single leg without expiration and assert the exact missing-fields
  response.
- Parse bull put and bear call spreads from natural language.
- Test maximum loss for a credit spread and probability calculation from
  delta.
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
