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
The chat is a scoped financial conversation about the selected instrument and
its environment, with an option-drafting mode that feeds the deterministic
analysis card. It is not a general-purpose assistant. Use Google Gemini
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
5. Hold a scoped financial conversation about the selected instrument using the
   already-loaded price, VIX, support/resistance, candles, indicators, and
   headlines.
6. Accept a single option or two-leg strategy in free text or through a guided
   draft, asking only for missing fields and proposing a complete example from
   live data.
7. Identify the strategy and provide a probabilistic assessment with
   explanations based on the playbook, without teaching the user what the
   strategy is.
8. Return to the conversational mode after every analysis card.
9. Allow explicit instrument switching and confirmed switching when the user
   only asks about another instrument.

## MVP scope

- Default symbol: AAPL.
- Popular-symbol chips, in alphabetical order: AAPL, AMZN, DIA, GOOGL, IWM,
  META, MSFT, NVDA, QQQ, SPY, TSLA, XSP. The user may still enter any
  CBOE-listed symbol with an options chain.
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
  content. It is the primary interaction surface: a scoped financial
  conversation about the selected instrument and its environment, with an
  option-drafting mode. After a successful analysis it returns to the
  conversation; the inline card is the answer, so it does not repeat the card
  content or add a redundant acknowledgement.
- The chat example is generated from the live option chain (a future expiration
  and near-money strikes), never from hardcoded strikes or dates.
- Light and dark themes are first-class. The theme follows the OS preference
  until the user chooses one; the choice survives reloads.
- Unavailable data is shown as an explicit empty or degraded state. The UI must
  never draw synthetic candles, levels, or headlines.

## Chat behavior

The chat is a scoped financial conversation about the selected instrument and
its environment. It is not a general-purpose chatbot.

- **Explore mode is the default.** The chat sees the already-loaded dashboard
  snapshot: price and change, VIX, support/resistance, recent candles, SMA 20
  and 50, RSI, and recent headlines, each with its timestamp and degradation
  state. It answers questions about trend, candlestick patterns, key levels,
  volatility context, and headlines using only that supplied data.
- **Option-drafting mode is entered only when the user asks about an option or
  a vertical spread.** The chat keeps known fields, proposes the missing fields
  from the live chain, and asks the user to confirm. A plain "yes" accepts the
  proposal. Edits such as "wider by two steps", "make it a put", or "change the
  expiration" update the draft without retyping the position.
- **Intent inference.** The chat infers open, close, or roll from the message,
  defaulting to open. The interface has no intent selector.
- **Draft defaults.** The suggested expiration is the listed expiration closest
  to 40 days, preferring 21-60 days. The suggested strike is near the money:
  ATM for long calls and long puts, the first out-of-the-money strike for short
  calls and short puts, and the strategy-appropriate short/long pair for a
  vertical spread. The default spread width is two listed strike steps (the
  second next listed strike). Suggestions are labelled as an example structure,
  not a recommendation.
- **Confirmation.** When every field is known, the chat shows a summary and an
  Analyze action. It runs the existing deterministic analysis only after the
  user confirms.
- **Return to conversation.** After a successful analysis, the card is appended
  inline, the complete position is kept in client-side context, the active
  draft is cleared, and the chat returns to explore mode without repeating the
  card content.
- **Instrument switching.** An explicit command such as "show MSFT chart" or
  "switch to MSFT" switches the selected instrument immediately. An exploratory
  question such as "what about MSFT?" asks for confirmation first. An option
  request for a different symbol first offers to switch to that symbol and
  carries the pending draft across the switch. The chat never silently
  substitutes one instrument for another.
- **Cancellation.** The user can cancel the draft, start over, or return to the
  chart conversation at any time.
- **Grounding.** The chat must not calculate new financial values. Trend,
  pattern, and sentiment language must be based on the supplied snapshot and a
  deterministic market digest. If a value is unavailable, the chat says so. It
  never presents delayed data as real-time and never presents headlines as a
  calendar.
- **Answer language.** The interface chrome is English; the chat answers in
  the language of the user's question. Deterministic helper prompts, refusals,
  visible errors, activity labels, and role labels are localized for English
  and Russian. Other languages keep the English helper templates while the
  model answer follows the question language.

## Out of scope

- Authentication, accounts, database, or portfolio storage.
- Real-time streaming, WebSockets, push notifications, or alerts.
- Strategies with more than two legs (for example, iron condors or butterflies);
  these may be considered for a later phase.
- Recommendations of specific trades as financial advice.

## Intended use and abuse protection

The assistant is a scoped financial conversation about the selected instrument
and its environment, plus option-position drafting and analysis. It is not a
general-purpose chatbot, a coding assistant, or a personal-use tool.

- Allow greetings, questions about the selected instrument's price, trend,
  candlestick patterns, key levels, volatility context, and headlines, and
  requests to build or edit a single option or two-leg vertical spread.
- Reject off-topic, nonsensical, abusive, creative-generation, hacking,
  credential-probing, prompt-injection, personal-use, and unrelated requests
  with a short refusal and no analysis. Do not use them as free-form generation
  prompts.
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
- Deterministic checks run before the model. The structured chat router may also
  refuse a request, but it is not the only protection. Refusals expose no
  secrets or internal instructions.

## Success criteria

- The input `sell 732 put and buy 729 put XSP 2030-11-15` is identified as
  `bull_put_spread`, with correct maximum profit/loss and a strategy header.
- If expiration is absent, parsing returns exactly
  `missing_fields: ["expiration"]` and analysis does not run.
- If CBOE is unreachable, the API reports `degraded: true` and a clear reason;
  it does not fabricate values.
- Every final analysis has the strategy identification header and does not
  define the strategy.
- "Hello" receives a greeting and a short menu of market and option topics, not
  a refusal.
- "What is the trend?" receives an answer grounded in the loaded candles,
  indicators, levels, and VIX, and it does not invent values.
- "Long call" opens a draft with a suggested strike and expiration, and a plain
  "yes" runs the analysis.
- "Wider by two steps" updates the spread width against the listed strike
  ladder. Closing or rolling wording changes the inferred intent shown on the
  card.
- "Show MSFT chart" switches instruments immediately; "What about MSFT?" asks
  for confirmation first.
- After the analysis card, the chat returns to the conversational mode.
- Off-topic, hacking, credential-probing, and prompt-injection requests are
  refused without an analysis card.
- A Russian option request receives Russian helper text, and a Russian refusal
  or visible error is shown in Russian.

## Product response requirements

- Every analysis includes the disclaimer:
  **Educational analysis, not investment advice.**
- Chat answers about market data are educational context about the selected
  instrument, not investment advice. They identify delayed data and never
  present a headline as a cause of a price move.
- An analysis may include recent ticker headlines as context only, with their
  source and timestamp. Headlines are not a dividend, earnings, or splits
  calendar, and must never supply a metric.
- Every market-data response includes its source and `as_of` timestamp.
- The strategy header is
  `{display_name} {underlying} {short_strike}/{long_strike} {expiration}` for a
  vertical spread and `{display_name} {underlying} {strike} {expiration}` for a
  single option. Example: `Bull Put Spread XSP 732/729 2030-11-15`.
