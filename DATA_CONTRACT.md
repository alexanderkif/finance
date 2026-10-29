# Market data contract

## CBOE delayed options

- Options URL:
  `https://cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json`
- Index symbols require a leading underscore (for example, `_SPX`, `_VIX`,
  `_NDX`); equity symbols do not (for example, `TSLA`, `SPY`).
- Read options from `data.options[]`. The fields used by the application are
  `option`, `bid`, `ask`, `iv`, `delta`, `gamma`, `theta`, `vega`,
  `open_interest`, and `volume`.
- The verified SPY options payload also contains `data.current_price` and
  `data.price_change_percent`; use these actual fields for the underlying
  quote and percent change.
- For expiration filtering, parse the OCC expiration encoded in the verified
  `option` symbol (for example, `SPY261120P00732000` encodes 2026-11-20).
- Use `timestamp` as `as_of`.
- Return `source: "cboe_delayed"` and `as_of` on every market-data response.
- The UI must identify the data as **Delayed 15 min** and retain attribution.

## Secondary data

- Prefer CBOE for market data. Use a secondary source for missing fields only
  when its terms explicitly permit use in a commercial application; a free
  request quota is not a commercial-use license.
- Finnhub's published terms state that plans are for personal use unless
  otherwise authorized and prohibit redistribution without written approval.
  Do not use a personal/free Finnhub plan for this product.
- Alpha Vantage's published policy directs commercial use of US real-time or
  15-minute delayed data to its business onboarding process. Do not treat its
  free API key as commercial entitlement for those data.
- Until a commercially permitted secondary source is selected and configured,
  return unavailable candles, news, dividends, support/resistance, or VIX as
  null/empty values with `degraded: true` and explicit warnings.
- Normalize candles as `{t, o, h, l, c, v}`.
- CBOE does not provide historical candles for this use. Do not derive candles,
  SMA, or RSI from the options chain; `/api/chart/{symbol}` must report them as
  unavailable until a permitted source exists.
- Do not use Yahoo Finance in production.

Provider policy references:
[Finnhub terms](https://finnhub.io/terms-of-service),
[Alpha Vantage commercial-use policy](https://www.alphavantage.co/realtime_data_policy/),
and [Alpha Vantage free API limits](https://www.alphavantage.co/support/).

## VIX

Use the CBOE delayed quote endpoint:
`https://cdn.cboe.com/api/global/delayed_quotes/_VIX.json`.
This endpoint returned HTTP 403 during verification on 2026-10-29. Until a
valid payload is observed and its schema confirmed, report VIX as unavailable;
do not infer its response fields from the options-chain endpoint.

## Degradation and missing values

- On CBOE HTTP 429, serve a cached chain only if it is less than ten minutes
  old. Otherwise return `degraded: true` with
  `reason: "rate_limited"`.
- On CBOE HTTP 5xx, retry once, then return a degraded response with a clear
  reason.
- Never fabricate values. Represent unavailable fields as `null` and include
  a warning.
- Preserve source attribution and the real data timestamp when serving cached
  data.

## Commercial-use note

CBOE's public delayed-data endpoints are not a guarantee of rights for
systematic commercial redistribution. Evaluate a CBOE DataShop license before
production scale. Confirm the selected secondary provider's commercial-use
terms before launch.
