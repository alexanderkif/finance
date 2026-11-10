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
The chat is a model-led scoped financial conversation about the selected
instrument. The model understands the turn, calls backend tools for data and
deterministic metrics, and writes the answer. It is not a general-purpose
assistant. Use Google Gemini
`gemini-3.5-flash-lite` on the free tier as the initial LLM choice. Treat the model and free-tier availability as a current implementation
choice, not a guarantee of permanent quotas or availability.

For local development, the server reads `GEMINI_API_KEY` from the repository
root `.env.local`. Production must receive the same variable through the
deployment platform's environment settings. The key is server-side only and
must never be included in frontend bundles, API responses, logs, or committed
files.

## Goals

1. Show a dashboard whose top section is a responsive card grid containing:
   - an instrument selector, defaulting to AAPL;
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
5. Hold a scoped financial conversation about the selected instrument. The
   model understands the turn, calls backend tools for data and deterministic
   calculations, and writes the answer in the user's language.
6. Accept a single option or two-leg strategy in free text. The model asks only
   for missing details and uses the live chain to propose listed contracts.
7. Compute strategy metrics deterministically and let the model explain them,
   including an educational assessment of whether the position looks favorable
   or unfavorable. The response must not be personal financial advice.
8. Keep the analysis card inline in the conversation and let the user continue
   asking follow-up questions.
9. Switch instruments after an explicit request or a confirmed switch; never
   silently substitute one instrument for another.
10. Let the chat read and change safe page state: chart toggles, theme, and chart
    range, persisted through the existing preferences.

## MVP scope

- Default symbol: AAPL.
- Popular-symbol chips, in alphabetical order: AAPL, AMZN, DIA, GOOGL, IWM,
  META, MSFT, NVDA, QQQ, SPY, TSLA, XSP. The user may still enter any
  CBOE-listed symbol with an options chain.
- Single legs: long/short call or put.
- Two-leg vertical spreads: bull put, bear call, bull call, bear put.
- Intent: open, close, or roll, inferred by the model.
- Chat tools: quote, chart, option expirations/chain, news, dividends,
  earnings, instrument switching, page state, and deterministic metrics.
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
  content. It is the primary interaction surface: a model-led conversation that
  calls backend tools and renders model text, tool steps, and an optional
  analysis card. UI changes requested in chat update the same visible controls.
- The chat example is generated from the live option chain (a future expiration
  and near-money strikes), never from hardcoded strikes or dates.
- Light and dark themes are first-class. The theme follows the OS preference
  until the user chooses one; the choice survives reloads.
- Unavailable data is shown as an explicit empty or degraded state. The UI must
  never draw synthetic candles, levels, or headlines.

## Chat behavior

The chat is a scoped financial conversation about the selected instrument and
its environment. It is not a general-purpose chatbot.

- **Model-led flow.** The model is the primary layer: it understands the
  message, decides which backend tools to call, and writes the user-facing
  answer. The backend supplies bounded provider data and deterministic metrics;
  the model never invents or recalculates a market value.
- **Tools.** The model can request the quote, chart and indicators, option
  expirations and chain, news, dividends, earnings, instrument switching, page
  state changes, and deterministic position metrics.
- **Option handling.** The model collects missing position details
  conversationally. When the position is complete, it calls `compute_position`
  and explains the computed result in the user's language.
- **UI state.** The model reads the current theme, selected symbol, chart range,
  and chart toggles. It can change chart toggles, theme, and range; safe changes
  apply immediately, and the model asks first only when the request is
  ambiguous. Changes persist through the existing `Preferences`.
- **Instrument switching.** The model switches instruments only after an
  explicit request or a confirmed switch. It never silently substitutes one
  instrument for another.
- **Grounding.** Provider data only; no fabricated values. News, dividends, and
  earnings are context, not a live calendar. If a value is unavailable, the chat
  says so.
- **Profitability.** The model may give an educational assessment of whether a
  position looks favorable or unfavorable from the computed metrics. It must not
  present that as personal financial advice or tell the user to buy or sell.
- **Answer language.** The model answers in the language of the user's question.
  Deterministic text is English-only and limited to service errors, hard safety
  blocks, validation, degradation warnings, and progress labels.
- **Limits.** A turn is limited to 20 tool calls and 60 seconds. Hard safety
  blocks run before the model. The activity timeline shows a `Thinking...`
  running step, then `done`/`failed` tool steps; failed requests show a failed
  request step with the error detail.

## Out of scope

- Authentication, accounts, database, or portfolio storage.
- Real-time streaming, WebSockets, push notifications, or alerts.
- Strategies with more than two legs (for example, iron condors or butterflies);
  these may be considered for a later phase.
- Recommendations of specific trades as financial advice.

## Intended use and abuse protection

The assistant is a scoped financial conversation about the selected instrument
and its environment, plus tool-driven option analysis and an educational
position assessment. It is not a general-purpose chatbot, a coding assistant, or
a personal-use tool.

- Allow greetings, questions about the selected instrument's price, trend,
  candlestick patterns, key levels, volatility context, and headlines, and
  requests to build or edit a single option or two-leg vertical spread.
- Soft-refuse off-topic, nonsensical, creative-generation, and
  unsupported-strategy requests in the user's language. Hard-block abuse,
  hacking, credential-probing, prompt-injection, personal use, oversized input,
  invalid symbols, and more than two legs with deterministic English control
  text and no analysis.
- Do not act as a general content generator, provide personalized financial
  advice, promise returns, execute or route orders, or produce material for
  market manipulation, spam, or personal gain outside the intended options and
  market analysis.
- Treat user text as untrusted: keep system instructions, provider keys, and
  internal prompts server-side, ignore prompt-injection attempts, and return
  only the structured chat or analysis fields.
- Enforce message-size, leg-count, symbol, and strategy limits in the API before
  any Gemini call. Apply usage limits appropriate to a no-auth, no-account
  service and the free provider tiers.
- Do not collect personal data, store portfolios, or use chat content for any
  purpose beyond producing the requested answer or analysis.
- Deterministic hard checks run before the model. Soft refusals are
  model-written. Refusals expose no secrets or internal instructions.

## Success criteria

- The input `sell 732 put and buy 729 put XSP 2030-11-15` is identified as
  `bull_put_spread`, with correct maximum profit/loss and a strategy header.
- If expiration is absent, parsing returns exactly
  `missing_fields: ["expiration"]` and analysis does not run.
- If CBOE is unreachable, the API reports `degraded: true` and a clear reason;
  it does not fabricate values.
- Outside regular US options hours, zero bid/ask is reported as unavailable
  quotes with the market session and next open. The chat does not call the
  contract illiquid, and analysis never substitutes theoretical values or
  last-trade prices for an executable quote.
- Every final analysis has the strategy identification header and does not
  define the strategy.
- "Hello" receives a greeting and a short menu of market and option topics, not
  a refusal.
- "What is the trend?" receives an answer grounded in the loaded candles,
  indicators, levels, and VIX, and it does not invent values.
- "Long call" starts a conversation about the position; the model asks for
  missing details, calls `compute_position`, and returns the card plus an
  explanation.
- Follow-up edits such as "wider by two steps" go back to the model, which
  calls the tools again against the listed chain.
- "Show MSFT chart" switches instruments; "What about MSFT?" asks for
  confirmation first.
- "Turn on both moving averages" returns UI actions that select the SMA 20 and
  SMA 50 checkboxes and persist them.
- "Use dark theme" and "show one year" update the theme and chart range.
- Off-topic and unsupported-strategy requests receive a model-written soft
  refusal. Prompt injection, hacking, abuse, oversized input, invalid symbols,
  and more than two legs receive deterministic English hard-block messages.
- A non-English request receives a model answer in that language, while service
  errors and hard-block control text stay English.
- A failed tool appears as a failed step in the activity timeline, and the model
  explains what is unavailable.

## Product response requirements

- Every analysis includes the disclaimer:
  **Educational analysis, not investment advice.**
- Chat answers about market data are educational context about the selected
  instrument, not investment advice. They identify delayed data and never
  present a headline as a cause of a price move.
- An analysis may include recent ticker headlines as context only, with their
  source and timestamp. Headlines are not a calendar. Dividend dates come from
  the Twelve Data dividend tool and earnings dates from the Finnhub earnings
  tool, and neither may supply a metric.
- Every market-data response includes its source and `as_of` timestamp.
- The strategy header is
  `{display_name} {underlying} {short_strike}/{long_strike} {expiration}` for a
  vertical spread and `{display_name} {underlying} {strike} {expiration}` for a
  single option. Example: `Bull Put Spread XSP 732/729 2030-11-15`.
