# Market data contract

## Providers (current, non-commercial)

The application currently runs on free provider tiers for non-commercial
development. Free tiers are not commercial entitlements: obtain licensed plans
or written approval before any commercial launch.

| Data                                 | Provider           | Key                   | Notes                               |
| ------------------------------------ | ------------------ | --------------------- | ----------------------------------- |
| Options chain, underlying quote, VIX | CBOE delayed       | none                  | Delayed 15 minutes                  |
| XSP/VIX daily candles                | CBOE index history | none                  | EOD, OHLC, no volume                |
| Other daily candles                  | Twelve Data Basic  | `TWELVE_DATA_API_KEY` | 8 requests/min, 800/day             |
| Dividend dates and amounts           | Twelve Data Basic  | `TWELVE_DATA_API_KEY` | `/dividends`, recent events         |
| News headlines                       | Finnhub free       | `FINNHUB_API_KEY`     | Company news, general-news fallback |
| Earnings calendar                    | Finnhub free       | `FINNHUB_API_KEY`     | `/calendar/earnings`                |

- Read provider keys only in the server process. Use `.env.local` for local
  development and deployment environment settings in production.
- Never expose or log a provider key in browser code, URLs, responses, or docs.
- Keep provider access behind adapters so a licensed provider can replace a free
  one without changing the response contracts.

## CBOE delayed options

- Options URL:
  `https://cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json`
- Quote URL:
  `https://cdn.cboe.com/api/global/delayed_quotes/quotes/{SYMBOL}.json`
- Index symbols require a leading underscore (for example, `_SPX`, `_VIX`,
  `_NDX`, `_XSP`); equity symbols do not (for example, `TSLA`, `SPY`). XSP is
  an index for CBOE and must be requested as `_XSP`.
- Index payloads echo `data.symbol` with a leading `^` (for example `^XSP`).
  Normalize `_` and `^` before comparing symbols.
- Read options from `data.options[]`. The fields used by the application are
  `option`, `bid`, `ask`, `iv`, `delta`, `gamma`, `theta`, `vega`,
  `open_interest`, and `volume`.
- The verified SPY options payload also contains `data.current_price` and
  `data.price_change_percent`; use these actual fields for the underlying
  quote and percent change.
- For expiration filtering, parse the OCC expiration encoded in the verified
  `option` symbol (for example, `SPY261120P00732000` encodes 2026-11-20).
- Use `timestamp` as `as_of` and normalize it to UTC.
- Return `source: "cboe_delayed"` and `as_of` on every CBOE-backed response.
- The UI must identify the data as **Delayed 15 min** and retain attribution.

## Exchange session and zero quotes

- Compute the regular US options session from the current clock in
  `America/New_York`: pre-market 04:00-09:30, regular 09:30-16:00,
  after-hours 16:00-20:00, closed otherwise and on weekends.
- Return the session with option-chain and quote payloads as `market_session`:
  `status`, `is_open`, `exchange_time`, `next_open`, `next_close`, and
  `timezone`. Normalize `next_open` and `next_close` to UTC for tool payloads.
- The schedule covers regular weekdays only. Exchange holidays and early closes
  are not enumerated; when the session says open but quotes are zero, report
  quotes as unavailable rather than live.
- CBOE delayed quotes can have `bid: 0` and `ask: 0` outside the regular
  session even when `open_interest`, `volume`, `iv`, `delta`, `theo`, and
  `last_trade_price` are present. Those fields are informational context, not
  executable quotes.
- When every contract in the requested expiration has a zero or missing
  bid/ask, add `quotes_unavailable_outside_session` if the regular session is
  not open, otherwise `quotes_unavailable`.
- Never compute position metrics from `theo`, `last_trade_price`, or
  `prev_day_close`, and never present them as a current executable price.

## CBOE index history (XSP, VIX)

- URL:
  `https://cdn.cboe.com/api/global/us_indices/daily_prices/{SYMBOL}_History.csv`
- Supported symbols: `XSP` and `VIX`; the file header is
  `DATE,OPEN,HIGH,LOW,CLOSE`, dates use `MM/DD/YYYY`.
- Use this source for the XSP and VIX daily chart before trying Twelve Data.
  It is end-of-day index history, not 15-minute delayed quotes, and it has no
  volume.
- Normalize candles from this source with `v: null` and return
  `source: "cboe_index_history"`. Use the last row date as `as_of`.
- Add a `volume_unavailable` warning when no candle has volume. The UI hides the
  volume pane for those symbols instead of drawing zero bars.
- Do not substitute SPY or SPX candles for XSP; they are different instruments
  and would change the price scale.

## VIX

Use the CBOE delayed quote endpoint:
`https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json`.

The verified payload contains `timestamp` and `data.current_price`; the quote
endpoint returned HTTP 200 on 2026-10-29. The options endpoint for `_VIX`
returns HTTP 403, so do not use it for the VIX level. If the quote is
unavailable, report `vix: null` with a warning.

## Twelve Data candles

- Endpoint: `https://api.twelvedata.com/time_series`.
- Parameters: `symbol`, `interval=1day`, `outputsize`, `format=JSON`.
- Authenticate with the `Authorization: apikey <key>` header; never put the key
  in the URL.
- Map chart ranges to output sizes: `1mo` 22, `3mo` 66, `6mo` 132, `1y` 260,
  `5y` 1300.
- Normalize candles as `{t, o, h, l, c, v}` in ascending time order. Use the
  last candle timestamp as `as_of`.
- Cache candles for 60 seconds per symbol and range.
- Compute SMA 20, SMA 50, RSI 14, and support/resistance on the server from the
  normalized candles. Do not call provider indicator endpoints.
- Support and resistance are clustered pivot highs and lows over the requested
  window, limited to three levels on each side of the last close.
- If the provider is unavailable, unconfigured, or rate limited, return empty
  candles and indicators with `degraded: true` and a warning. Never derive
  candles from the options chain or synthesize a series.
- Twelve Data Basic does not include some index symbols (for example, XSP and
  SPX return a plan-upgrade error). Treat that as `symbol_requires_paid_plan`
  for symbols without a CBOE history fallback; do not silently substitute a
  different instrument.

## Twelve Data dividends

- Endpoint: `https://api.twelvedata.com/dividends`.
- Parameters: `symbol`, `outputsize`, `format=JSON`.
- Authenticate with the `Authorization: apikey <key>` header; never put the key
  in the URL.
- Normalize dividends as `{ex_date, amount}` and return recent events.
- Cache dividends for 300 seconds per symbol.
- Verified on 2026-11-10: `AAPL` returned HTTP 200 with
  `{"ex_date": "2026-08-10", "amount": 0.27}`.
- If the provider is unavailable, return an empty list with a warning. Do not
  infer dividend dates from headlines.

## Finnhub news

- Company news endpoint:
  `https://finnhub.io/api/v1/company-news` with a seven-day window for the
  dashboard and a thirty-day window for analysis context.
- Dashboard behavior falls back to
  `https://finnhub.io/api/v1/news?category=general` when company news is empty.
- Analysis context is ticker-specific only: do not present general news as
  instrument news. An empty result is `news_unavailable`.
- Authenticate with the `X-Finnhub-Token` header; never put the key in the URL.
- Normalize headlines as `{title, url, publisher, published_at}` and return at
  most three for the dashboard and at most five for analysis, newest first.
- Cache headlines for 300 seconds per symbol and window; a cached result may be
  sliced to a smaller limit.
- If the provider is unconfigured, rate limited, or fails, return an empty
  `news` list with a warning. Do not block price, VIX, chart, or options
  analysis.
- News may mention dividends, earnings, or splits, but it is not a live event
  calendar. Structured calendars require separate verified endpoints and must
  not be inferred from headlines.

## Finnhub earnings

- Endpoint: `https://finnhub.io/api/v1/calendar/earnings`.
- Parameters: `symbol`, `from`, `to`.
- Authenticate with the `X-Finnhub-Token` header; never put the key in the URL.
- Read `earningsCalendar[]`; normalize `date`, `quarter`, `year`,
  `epsEstimate`, `epsActual`, `revenueEstimate`, and `revenueActual`.
- Cache earnings for 300 seconds per symbol.
- Verified on 2026-11-10: `AAPL` returned HTTP 200 with an `earningsCalendar`
  entry.
- If the provider is unavailable, return an empty list with a warning. Do not
  infer earnings dates from headlines. Finnhub dividend endpoints return HTTP
  403 on the current free tier, so dividends come from Twelve Data instead.

## Chat market snapshot

- The chat may receive the dashboard's already-loaded market and chart values
  as a client-provided snapshot. Validate and size-limit it; treat it as
  untrusted conversational context.
- The chat also receives `ui`: theme, selected symbol, chart range, and chart
  toggles. It is client state, not market data. The model may return
  `ui_actions`; the client applies them to `Preferences`.
- The snapshot is not a market-data provider and must never feed the
  deterministic analysis metrics. `compute_position` always re-fetches the
  chain, quote, candles, and news from the providers.
- Supported snapshot fields are price, change percent, VIX, up to three support
  and three resistance levels, recent candles, SMA 20/50 points, RSI 14 points,
  up to five headlines, per-section timestamps, sources, chart range and chart
  source, and degradation warnings.
- If the snapshot is missing, empty, or degraded, the chat says the value is
  unavailable. It never synthesizes candles, levels, or headlines.
- Do not present snapshot data as real-time; the delayed-data badge and
  timestamps still apply.

## Analysis volatility context

- `current_iv` comes from the CBOE chain: select the ATM IV for the position
  expiration with the same strike-closest-to-spot rule used by the 1-sigma
  scenario.
- `hv_20d` and `hv_60d` are annualized standard deviations of daily log returns
  over 20 and 60 trading days, using 252 trading days per year. Use the same
  candle providers as the chart: CBOE index history for XSP/VIX, otherwise
  Twelve Data.
- `hv_rank` is the percentile of the current 20-day HV within its trailing
  one-year rolling distribution.
- `iv_hv_ratio` is current IV divided by 60-day HV, falling back to 20-day HV
  when the longer window is unavailable.
- Do not label HV percentile as IV rank. A true IV rank needs a historical IV
  series, which the current free providers do not expose; keep `iv_rank` null.
- If candles are unavailable, return null volatility fields and the
  `hv_unavailable` warning. Never synthesize a candle series or an IV history.
  Options analysis still proceeds.

## Degradation and missing values

- Sections degrade independently: a news failure must not remove the quote,
  VIX, candles, or options chain.
- On CBOE HTTP 429, serve a cached chain only if it is less than ten minutes
  old, with a `cached_data` warning. Otherwise return `degraded: true` with
  `reason: "rate_limited"` and no contracts.
- On CBOE HTTP 5xx, retry once. If the retry fails, serve a cached chain less
  than ten minutes old with a `cached_data` warning; otherwise return
  `degraded: true` with `reason: "upstream_error"` and no contracts.
- On a network error or HTTP 5xx from Finnhub or Twelve Data, retry the same
  request once before degrading that section. Do not retry HTTP 429.
- Never fabricate values. Represent unavailable fields as `null` or `[]` and
  include a warning.
- Preserve source attribution and the real data timestamp when serving cached
  data.
- Do not use Yahoo Finance in production.

## Commercial-use note

The current free tiers are for non-commercial development only. Before a
commercial launch, license CBOE DataShop, Twelve Data, and Finnhub as required,
or replace them with commercially permitted sources. Do not treat a free quota
as a commercial-use license.
