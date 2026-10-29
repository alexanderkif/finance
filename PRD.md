# Product requirements

## Product

Build a commercial Options Strategy Assistant: an Angular application with a
FastAPI service deployed as Vercel Services. It helps users identify an
options position and evaluates it against delayed market data.

The current development deployment uses free provider tiers and is
non-commercial. CBOE delayed data provides options, the underlying quote, and
VIX; Twelve Data Basic provides daily candles; Finnhub provides news. Free tiers
are not commercial entitlements: obtain licensed plans or replace providers
before a commercial launch.

The existing application may be substantially or completely rewritten to meet
this contract; its current implementation is not a compatibility constraint.
Use Google Gemini `gemini-3.1-flash-lite` on the free tier as the initial LLM
choice. Treat the model and free-tier availability as a current implementation
choice, not a guarantee of permanent quotas or availability.

For local development, the server reads `GEMINI_API_KEY` from the repository
root `.env.local`. Production must receive the same variable through the
deployment platform's environment settings. The key is server-side only and
must never be included in frontend bundles, API responses, logs, or committed
files.

## Goals

1. Show a dashboard whose top section is a responsive card grid containing:
   - an instrument selector, defaulting to SPY;
   - the current price and change;
   - key levels: support and resistance when available;
   - brief market context, such as VIX, when available;
   - one to three top news headlines as links when available.
2. Render a candlestick chart in the same top section, with volume below the
   candles, user-added trend lines, and indicators (SMA and RSI).
3. Place the AI chat directly below the market grid and chart, before any other
   content.
4. Provide light and dark themes, persisted client-side and defaulting to the
   operating-system preference.
5. Accept a single option or two-leg strategy in free text.
6. Ask only for missing fields: side, call/put, strike, expiration, or intent.
7. Identify the strategy and provide a probabilistic assessment with
   explanations based on the playbook, without teaching the user what the
   strategy is.

## MVP scope

- Symbols: SPY, XSP, and any CBOE-listed symbol with an options chain.
- Single legs: long/short call or put.
- Two-leg vertical spreads: bull put, bear call, bull call, bear put.
- Intent: open, close, or roll.
- UI language: English. Answer in the language of the user's question.
- Show the data-freshness badge: **Delayed 15 min**.
- Chart library: `ng-apexcharts` (ApexCharts). It is preferred over ApexStock
  for integration and control; revisit that choice only if `ng-apexcharts`
  cannot meet the trend-line and indicator requirements.

## Dashboard layout

- The first screen is a dashboard, not a landing page. Its top section is a
  responsive grid of compact cards: instrument selector, price, key levels,
  market context, and news headlines. The chart occupies the remaining space
  of that section.
- The chart price axis fits the visible candles and re-fits after zoom, pan,
  and reset instead of anchoring at zero.
- The AI chat follows the market grid and chart directly, above any secondary
  content. It announces card updates instead of repeating the card content.
- The chat example is generated from the live option chain (a future expiration
  and near-money strikes), never from hardcoded strikes or dates.
- Light and dark themes are first-class. The theme follows the OS preference
  until the user chooses one; the choice survives reloads.
- Unavailable data is shown as an explicit empty or degraded state. The UI must
  never draw synthetic candles, levels, or headlines.

## Out of scope

- Authentication, accounts, database, or portfolio storage.
- Real-time streaming, WebSockets, push notifications, or alerts.
- Strategies with more than two legs (for example, iron condors or butterflies);
  these may be considered for a later phase.
- Recommendations of specific trades as financial advice.

## Intended use and abuse protection

The assistant is limited to parsing and evaluating a single option or a two-leg
vertical spread for the selected instrument, and to answering questions about
that analysis. It is not a general-purpose chatbot.

- Reject off-topic, nonsensical, abusive, or unrelated requests with a short
  refusal and no analysis. Do not use them as free-form generation prompts.
- Do not act as a general content generator, provide personalized financial
  advice, promise returns, execute or route orders, or produce material for
  market manipulation, spam, or personal gain outside the intended options
  analysis.
- Treat user text as untrusted: keep system instructions, provider keys, and
  internal prompts server-side, ignore prompt-injection attempts, and return
  only the structured analysis fields.
- Enforce message-size, leg-count, symbol, and strategy limits in the API before
  any Gemini call. Apply usage limits appropriate to a no-auth, no-account
  service and the free provider tiers.
- Do not collect personal data, store portfolios, or use chat content for any
  purpose beyond producing the requested analysis.

## Success criteria

- The input `sell 732 put and buy 729 put XSP 2030-11-15` is identified as
  `bull_put_spread`, with correct maximum profit/loss and a strategy header.
- If expiration is absent, parsing returns exactly
  `missing_fields: ["expiration"]` and analysis does not run.
- If CBOE is unreachable, the API reports `degraded: true` and a clear reason;
  it does not fabricate values.
- Every final analysis has the strategy identification header and does not
  define the strategy.

## Product response requirements

- Every analysis includes the disclaimer:
  **Educational analysis, not investment advice.**
- Every market-data response includes its source and `as_of` timestamp.
- The strategy header is
  `{display_name} {underlying} {short_strike}/{long_strike} {expiration}` for a
  vertical spread and `{display_name} {underlying} {strike} {expiration}` for a
  single option. Example: `Bull Put Spread XSP 732/729 2030-11-15`.
