# Market data contract

## Providers (current, non-commercial)

The application currently runs on free provider tiers for non-commercial
development. Free tiers are not commercial entitlements: obtain licensed plans
or written approval before any commercial launch.

| Data | Provider | Key | Notes |
| --- | --- | --- | --- |
| Options chain, underlying quote, VIX | CBOE delayed | none | Delayed 15 minutes |
| XSP/VIX daily candles | CBOE index history | none | EOD, OHLC, no volume |
| Other daily candles | Twelve Data Basic | `TWELVE_DATA_API_KEY` | 8 requests/min, 800/day |
| News headlines | Finnhub free | `FINNHUB_API_KEY` | Company news, general-news fallback |

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

## Finnhub news

- Company news endpoint:
  `https://finnhub.io/api/v1/company-news` with a seven-day window.
- Fall back to `https://finnhub.io/api/v1/news?category=general` when company
  news is empty.
- Authenticate with the `X-Finnhub-Token` header; never put the key in the URL.
- Normalize headlines as `{title, url, publisher, published_at}` and return at
  most three, newest first.
- Cache headlines for 300 seconds per symbol.
- If the provider is unconfigured, rate limited, or fails, return an empty
  `news` list with a warning. Do not block price, VIX, or chart data.

## Degradation and missing values

- Sections degrade independently: a news failure must not remove the quote,
  VIX, candles, or options chain.
- On CBOE HTTP 429, serve a cached chain only if it is less than ten minutes
  old. Otherwise return `degraded: true` with
  `reason: "rate_limited"`.
- On CBOE HTTP 5xx, retry once, then return a degraded response with a clear
  reason.
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
