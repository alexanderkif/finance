# API specification

All market-data responses identify their source and `as_of` timestamp.
Unavailable values are explicit; see [DATA_CONTRACT.md](DATA_CONTRACT.md).

## LLM configuration

- Use Google Gemini model `gemini-3.5-flash-lite` on the free tier for now.
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

## Transient failures and user-facing errors

- Gemini requests retry transient failures (network errors and HTTP
  `408`, `425`, `500`, `502`, `503`, `504`) twice with a short backoff. HTTP
  `429` is not retried.
- An exhausted free-tier quota returns `429` with a message to wait about a
  minute. A Gemini outage that persists through retries returns `502` with a
  "temporarily unavailable" message.
- CBOE rate limits and outages return `429` and `502` with retry guidance
  instead of raw upstream status text.
- The Angular chat retries `502`, `503`, `504`, and network (`0`) responses up
  to two more times, names the unavailable service between attempts, and offers
  a Cancel button. It reads `/api/analysis/run/stream` incrementally and treats
  `error` events as the HTTP-equivalent failure. Sending a new message aborts
  the stream and ignores stale events.
- The chat retries a failed `/api/chat/turn` request without duplicating the
  user turn. A confirmed analysis retries only the analysis stream with the
  already confirmed position; it does not repeat extraction or the chat turn.
- A `draft` or `confirm` response keeps the draft on the client. Missing fields
  are collected across turns; `/api/analysis/run` is called only after the
  user confirms a complete position. A failed chat turn never discards the
  draft.
- The chat scrolls to the newest message while the user is at the bottom. It
  stops auto-scrolling after the user scrolls up and resumes when they return
  to the bottom.
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

## `POST /api/chat/turn`

The primary chat endpoint. It holds a scoped financial conversation about the
selected instrument, drafts an option position, or proposes an instrument
switch. It is not a general-purpose chat endpoint. The frontend sends every
message here; the server decides whether the turn is a market answer, an option
draft, a switch, or a refusal.

Request fields:

```text
symbol: string
message: string (required unless continuation is true)
intent: "open" | "close" | "roll" (default hint; the chat infers from the message)
language: string (default "English"; the last detected answer language)
history: { role: "user" | "assistant", text: string }[] (max 8 turns)
draft: ChatDraft | null
context: AnalysisPosition[] (max 3 complete previous positions)
continuation: boolean (default false; used after a switch)
market: ChatMarketSnapshot
```

`ChatDraft`:

```text
position_type: "single" | "strategy"
legs: {
  symbol: string,
  side: "buy" | "sell" | null,
  option_type: "call" | "put" | null,
  strike: number | null,
  expiration: "YYYY-MM-DD" | null
}[]
strategy_key: string | null
reference: { kind, strikes, direction, expiration } | null
intent: "open" | "close" | "roll" | null
```

`ChatMarketSnapshot` is the dashboard data the user already sees. It is
client-provided conversational context, not a provider response:

```text
symbol, price, change_pct, vix,
support[], resistance[],
candles: { t, o, h, l, c, v | null }[],
sma: { period, points: { t, value }[] }[],
rsi: { period, points: { t, value }[] },
news: { title, url, publisher, published_at }[],
range, chart_source, chart_as_of,
as_of, quote_as_of, vix_as_of, news_as_of,
sources: { quote, vix, news },
degraded, warnings[]
```

Size limits: `message` 2,000 characters; each history text 2,000 characters;
at most 120 candles, 120 SMA points, and 120 RSI points; at most five
headlines; at most three support and three resistance levels; at most two
draft legs and three context positions.

Response fields:

```text
mode: "answer" | "draft" | "confirm" | "switch_symbol" | "refused"
text: string
language: string
intent: "open" | "close" | "roll"
draft: ChatDraft | null
missing: string[]
suggestions: ChatDraftSuggestions | null
confirm: { summary: string, position: AnalysisPosition } | null
switch: { symbol: string, explicit: boolean, reason: string } | null
pending_draft: ChatDraft | null
as_of: string | null
degraded: boolean
warnings: string[]
```

`ChatDraftSuggestions` names the fields the server proposed from the live
chain:

```text
fields: string[]
expiration: string | null
strike: number | null
long_strike: number | null
width: number | null
```

For a single option, `strike` is the proposed strike. For a spread, `strike` is
the short leg and `long_strike` is the long leg.

### Modes

- `answer`: a grounded answer about the selected instrument using only the
  supplied snapshot and a deterministic market digest. It is used for
  greetings, trend and pattern questions, key levels, volatility context, and
  headlines. It contains no analysis card and no metric fields.
- `draft`: the option draft still has missing fields. `draft` carries the known
  values, and `suggestions` may propose some of the missing ones. The frontend
  renders an editable draft card.
- `confirm`: every leg field has a concrete value after applying suggestions.
  `confirm.position` is ready for `/api/analysis/run`. `suggestions` identifies
  which values were proposed, so the UI can label them as example values. A
  plain "yes" accepts and runs the analysis.
- `switch_symbol`: the user asked about another instrument. `switch.explicit`
  is `true` for an imperative command and `false` for an exploratory question.
  An option request for another symbol returns `explicit: false` and carries
  `pending_draft`.
- `refused`: the request is outside the allowed scope. It returns a short
  refusal, no analysis fields, and no draft.

### Language

The chat returns `language` and uses it for deterministic text. English and
Russian catalogs cover helper prompts, refusals, visible errors, and the chat
copy; other languages receive the model answer in the question language with
English helper templates. The UI chrome remains English. The Angular client
localizes the analysis activity timeline and common visible errors for English
and Russian; the API stage labels stay stable English for other clients.

### Intent inference

The chat infers the intent from the message: `open` when the user describes a
position to establish (including buy or sell), `close` when they say close,
exit, or take profit, and `roll` when they say roll or roll out. The default is
`open`. The inferred value is stored on `ChatDraft.intent`, returned as
`ChatTurnResponse.intent`, and sent unchanged to `/api/analysis/run`. There is
no intent selector in the UI.

### Instrument switching

- Explicit commands such as "show MSFT chart", "switch to MSFT", "покажи график
  MSFT", and "переключи на MSFT" return `explicit: true`. The frontend switches
  the selected symbol immediately, reloads the dashboard, and appends a local
  switch notice.
- Exploratory questions such as "what about MSFT?", "XSP?", and "а что там у
  MSFT?" return `explicit: false`. The frontend asks for confirmation first.
- An option request for a different symbol returns `explicit: false` with the
  extracted `pending_draft`. After the user confirms the switch, the frontend
  selects the new symbol, waits for the dashboard snapshot, and sends a
  continuation turn with `continuation: true` and the pending draft.
- The server validates the symbol format and never silently substitutes one
  instrument for another. SPY, XSP, and SPX are different underlyings.

### Draft suggestions

Suggestions are deterministic and come from the live chain; see
[PLAYBOOK_SPEC.md](PLAYBOOK_SPEC.md) for the strategy-specific strike rules.

- Expiration: the listed expiration closest to 40 days, preferring 21-60 days.
- Width: two listed strike steps, meaning the long leg is the second next
  listed strike from the short leg. If the ladder has fewer steps, use the
  widest available and say so.
- Every suggestion is labelled as an example structure, not a recommendation.
- When the request leaves the side or option type ambiguous, the server may
  propose the common case and label it as assumed. The user can change it.
- If no listed candidate exists, return the nearest listed strikes or a
  `draft` response with an explicit warning instead of inventing a contract.

### Deterministic confirmation and cancellation

- A short confirmation ("yes", "y", "ok", "sure", "use these", "да", "ок") in
  `confirm` mode is handled by the client without a chat turn. The client sends
  the confirmed `confirm.position` directly to
  `/api/analysis/run/stream`.
- A short cancel ("cancel", "start over", "never mind", "отмена", "начать
  заново") with an active draft clears the draft locally and returns to
  `explore` without a chat turn.
- "Use these values" completes the active draft from the live chain
  deterministically, without a chat model call.
- A continuation turn after a switch completes the pending draft from the new
  symbol's live chain deterministically, without a chat model call.
- Any other message, including a conditional confirmation or an edit, goes to
  `/api/chat/turn`.
- This keeps the happy path "option request -> yes -> card" at one chat call
  plus one synthesis call, and the switch-continuation path at one synthesis
  call.

### Grounding and cost

- The server builds a deterministic `MarketDigest` from the snapshot. The model
  may describe trend, candlestick patterns, levels, volatility context,
  market sentiment derived from the supplied volatility/trend/headline context,
  and headlines. It must not calculate new financial values, invent data, or
  present sentiment as a forecast.
- The snapshot is never used for deterministic analysis metrics. A confirmed
  analysis re-fetches the chain, quote, candles, and news from the providers.
- Each chat turn makes at most one Gemini call. A deterministic refusal makes
  zero. A confirmed analysis adds exactly one synthesis call in
  `/api/analysis/run` or `/api/analysis/run/stream`. A single option request
  followed by a plain confirmation therefore makes at most two Gemini calls in
  total: one chat call and one synthesis call. A further edit is a new turn and
  may add one chat call for that edit.

## `POST /api/analysis/parse`

Structured extraction endpoint. The chat frontend uses `/api/chat/turn`;
this endpoint remains for clients that only need parsed legs and for internal
reuse. Its request and response contract is unchanged.

Request:

```json
{
  "message": "sell 732 put and buy 729 put XSP 2030-11-15",
  "default_symbol": "AAPL",
  "context": []
}
```

Response:

```text
position_type: "single" | "strategy"
legs: { symbol, side, option_type, strike, expiration }[]
missing_fields: string[]
detected_language: string
strategy_key?: string
header?: string
reference?: { kind, strikes, direction, expiration }
```

`default_symbol` is optional and defaults to `AAPL`; the frontend should pass
its selected ticker so an omitted symbol can be resolved without guessing.
Return structured fields only; do not include an LLM explanation. Normalize
dates to `YYYY-MM-DD` and classify a vertical spread only when its legs satisfy
the truth table in [PLAYBOOK_SPEC.md](PLAYBOOK_SPEC.md). When expiration is the
only missing leg field, return exactly `missing_fields: ["expiration"]`; do
not start analysis.

`context` is an optional, client-owned list of up to three complete previous
positions. The extraction call may use it to resolve references such as "the
same spread", "shift two strikes up", "widen by two strikes", or "change the
expiration". It returns absolute legs and an optional `reference` operation.
Context is validated separately; the deterministic scope check runs only on
the new message. Return `header` for a complete, non-reference position. When
two legs do not form a supported vertical spread, return `422` with a
one-position explanation instead of asking which spread is meant.

## Chat scope and misuse guardrails

The assistant is a scoped financial conversation about the selected instrument
and its environment, plus drafting and evaluating a single option or a two-leg
vertical spread. It is not a general-purpose chatbot, a coding assistant, or a
personal-use tool.

- Allow greetings, questions about the selected instrument's price, trend,
  candlestick patterns, key levels, volatility context, and headlines, and
  requests to build or edit a supported option position.
- Before any Gemini call, `POST /api/chat/turn` and
  `POST /api/analysis/parse` enforce the message size, symbol format, a
  deterministic two-leg limit, and a scope check.
- Off-topic, nonsensical, abusive, creative-generation, hacking,
  credential-probing, prompt-injection, personal-use, and unsupported-strategy
  requests are refused with a short message. A deterministic refusal makes no
  Gemini call, returns no analysis fields, and never echoes system
  instructions, prompts, or provider keys.
- The structured chat router may also return `mode: "refused"`. It is not the
  only protection: deterministic checks run first, and every model response is
  validated against its schema.
- Oversized messages and invalid symbols are rejected by request validation
  before the handler runs.
- The same deterministic limits apply to messages merged from missing-field
  follow-ups; a message with more than two buy/sell legs is refused.
- Allowed strategies are a single long/short call or put and the four two-leg
  vertical spreads. Multi-leg strategies such as iron condors, butterflies,
  straddles, strangles, calendars, and diagonals are out of scope.
- The service must not be repurposed for unrelated content generation,
  personalized financial advice, trade execution or routing, market
  manipulation, spam, hacking, credential probing, or other personal use
  outside the intended market and options analysis.
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
- `message` is a verbose sentence containing every parser field and no
  intent. Intent is inferred by `/api/chat/turn` from the message, defaulting to
  open. `description` explains
  the mechanics in plain language. The chat submits `message` immediately
  instead of rendering `description` as a separate assistant bubble.
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
  "context": [],
  "reference": null,
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
  for a leg. The error names the nearest listed strikes when they exist.
- `position` is optional when `reference` is supplied. `reference` describes a
  client-approved edit against the most recent item in `context` (`same`,
  `shift`, `widen`, `narrow`, `expiration`). The server resolves it against
  the real listed strike ladder before validating or calculating anything.
  A reference without context returns `422`.
- The chat client sends the intent inferred by `/api/chat/turn`; this endpoint
  echoes it and does not infer intent itself.

Response `AnalysisResult`:

```text
strategy_key, intent, header, recommendation, probability_positive, max_profit,
max_loss, net_credit_debit, breakeven, theta_daily, iv_rank, current_iv,
hv_20d, hv_60d, hv_rank, iv_hv_ratio, event_flags, liquidity, scenario_1sigma,
scenario_2sigma, news[], news_source, news_as_of, detected_language,
disclaimer, source, as_of, degraded, warnings[]
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
- `iv_rank` stays `null` until a historical IV series is available; it is never
  estimated from HV or presented as a true IV rank.
- `current_iv` is the ATM implied volatility selected from the CBOE chain for
  the position expiration.
- `hv_20d` and `hv_60d` are annualized historical volatility from daily log
  returns over 20 and 60 trading days (252 trading days per year). Candles come
  from CBOE index history for XSP/VIX and from Twelve Data otherwise.
- `hv_rank` is the percentile of the current 20-day HV within its trailing
  one-year rolling distribution.
- `iv_hv_ratio` is `current_iv / hv_60d`, falling back to `hv_20d` when the
  60-day window is unavailable.
- If candles are unavailable, the volatility fields are `null` and the response
  includes an `hv_unavailable` warning; options analysis still returns.
- `intent` echoes the requested `open`, `close`, or `roll` intent. It shapes the
  written assessment and is shown on every analysis card so results can be
  compared.
- `event_flags` lists the playbook's own event sensitivity (`earnings`,
  `dividends`, `macro`). It describes which event types the strategy is exposed
  to; it is not a live event calendar and does not claim an event is scheduled.
- `news` contains up to five ticker-specific Finnhub headlines from the last
  30 days. They are supplied to synthesis only as context: they never supply a
  metric, and they are not a dividend, earnings, or splits calendar. A missing
  key, rate limit, outage, or empty result yields
  `news_provider_not_configured`, `news_rate_limited`, or `news_unavailable`
  with `news: []`, `news_source: null`, and a non-blocking warning.
  `news_as_of` is the newest headline timestamp when one exists. No
  general-news fallback is presented as instrument news.
- `liquidity` reports the worst-leg bid/ask spread percent, the minimum open
  interest and volume across legs, and a `good`/`fair`/`poor`/`unknown` rating.
- `scenario_1sigma` is the expected move over the option's days to expiration:
  `underlying_price * atm_iv * sqrt(days_to_expiration / 365)`, where `atm_iv`
  is selected from the chain at the strike closest to the underlying price.
- `scenario_2sigma` uses the same formula multiplied by two, giving the wider
  two-standard-deviation range.
- `header` is deterministic and ordered short leg / long leg:
  `Bull Put Spread XSP 732/729 2030-11-15`. A single-leg header is
  `Long Call SPY 600 2030-11-15`.
- `degraded` is true when any warning is present.
- `recommendation` comes from one Gemini synthesis call and must use only the
  supplied facts. It must not define the strategy or give trade instructions.
  The disclaimer is added deterministically, not by the model.
- A chat-driven analysis makes at most two Gemini calls: one structured chat
  call in `/api/chat/turn` (routing and extraction) and one synthesis call in
  `run`. Clients that use the standalone `parse` endpoint instead make one
  extraction call there and one synthesis call in `run`.

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

## `POST /api/analysis/run/stream`

The same request body and analysis as `/api/analysis/run`, returned as
newline-delimited JSON (`application/x-ndjson`). This is one market-data
request; stages are progress events, not separate data fetches. The client
sends `Accept: application/x-ndjson`.

Event shapes, one JSON object per line:

```text
{ "type": "stage", "id": "history|news|chain|quote|metrics|synthesis",
  "status": "started|done|failed", "label": string, "detail"?: string }
{ "type": "position", "position": AnalysisPosition, "header": string }
{ "type": "news", "news": NewsHeadline[], "source": "finnhub"|null,
  "as_of": string|null }
{ "type": "warning", "code": string }
{ "type": "heartbeat" }
{ "type": "result", "result": AnalysisResult }
{ "type": "error", "status": number, "detail": string }
```

- Only real stages are emitted. Never emit progress from a client timer.
- `position` follows the chain load and carries the resolved, listed legs and
  deterministic header. For a reference edit it replaces the provisional
  interpretation shown after parsing.
- `news` is emitted as soon as ticker headlines are available, so the user can
  read them while metrics and synthesis run.
- `heartbeat` keeps a proxy from closing a long synthesis call. Clients ignore
  it except for liveness.
- Once streaming starts, errors are `error` events with an HTTP-equivalent
  status; the stream then ends without a `result`.
- The server stops between stages when the client disconnects. The client aborts
  the request when the user cancels or sends a new message.

## Contract and integration tests

- Parse a single leg without expiration and assert the exact missing-fields
  response.
- Parse bull put and bear call spreads from natural language.
- Test maximum loss for a credit spread and probability calculation from
  delta.
- Run analysis against a mocked chain and mocked Gemini, and assert the header,
  credit/debit metrics, breakeven, probability, theta, liquidity, 1-sigma and
  2-sigma scenarios, event flags, intent, disclaimer, and answer language.
- Assert that `run` makes exactly one Gemini synthesis call and passes the
  computed metrics as facts.
- Assert `422` for a missing contract and for legs that do not form a supported
  spread, `429` for Gemini quota exhaustion, and `502` for a CBOE outage.
- Assert a transient Gemini `503` is retried, and a persistent outage returns a
  friendly `502` after the retry budget is spent.
- Assert `iv_rank` is `null`, and that `current_iv`, `hv_20d`, `hv_60d`,
  `hv_rank`, and `iv_hv_ratio` are populated from mocked candles. Assert an
  `hv_unavailable` warning when candles are not configured.
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
  and the next lower strike, and returns a verbose message without an intent.
  Verify `Use example` submits that message immediately and that the user can
  edit it from the message's edit-in-input icon.
- Verify `POST /api/chat/turn` returns `answer` for a greeting and for a
  trend/pattern question, grounded in the supplied snapshot, with no analysis
  card and no invented values.
- Verify an option request returns `confirm` with a suggested expiration and
  near-money strike, and that a plain "yes" runs the analysis. Verify the
  default spread width is two listed strike steps.
- Verify "wider by two steps", "make it a put", and "change the expiration"
  update the draft against the listed ladder.
- Verify an explicit switch command returns `switch.explicit: true`, an
  exploratory question returns `false`, and an option request for another
  symbol returns `pending_draft` with `explicit: false`.
- Verify a chat turn makes at most one Gemini call, a deterministic refusal
  makes zero, and a confirmed analysis adds exactly one synthesis call.
- Verify the chat snapshot is validated and size-limited and is never used for
  analysis metrics.
- Verify off-topic, hacking, credential-probing, personal-use, and
  prompt-injection messages return `mode: "refused"` with no analysis fields.
- Verify close or roll wording changes the draft and response intent, and the
  analysis request uses that inferred intent.
- Verify the chat UI has no intent selector and no redundant "card added"
  acknowledgement.
- Verify a busy chat turn shows a neutral "Thinking…" status, and a cancelled
  or replaced chat turn leaves no failed activity step or "Cancelled" text.
- Verify the stream endpoint emits only real stages, an early `position`, a
  `news` event when headlines exist, and a final `result`; verify an `error`
  event ends the stream with the expected status.
- Verify parse context reaches the extraction call, reference wording is
  accepted only with context, and a two-leg unrelated request returns the
  one-position `422`.
- Verify a reference shift resolves against the listed strike ladder, a
  reference without context returns `422`, and an unlisted strike names the
  nearest listed strikes.
- Verify analysis includes ticker news when available and degrades with a
  warning when Finnhub is missing, rate limited, or empty; no general-news
  fallback is presented as instrument news.
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
  `localStorage`, defaults the ticker to AAPL, and applies the OS theme when no
  choice is stored. Verify the popular-symbol chips are alphabetical and
  include the documented list.
- Verify the dashboard renders the market grid, the candlestick chart with a
  trend line and an indicator, and the news headline links.
- Verify the AI chat is rendered directly below the market grid and chart,
  greets the user, answers market questions, enters an option draft on an
  option request, and returns to the conversation after an analysis card.
- Verify Cancel aborts the active request, a new message cancels the previous
  request, and auto-scroll pauses while the user is reading older messages and
  resumes at the bottom.
- Verify a failed chat turn is retried without duplicating the user message, and
  a failed analysis retries only the analysis call with the already confirmed
  position, without repeating the chat turn or extraction.
- Verify every successful answer appends its analysis card inline in the chat,
  so multiple cards remain comparable, and that the card shows the intent badge,
  the 1-sigma and 2-sigma ranges, and the playbook event-sensitivity caption.
- Verify a user message offers an edit-in-input button that copies its text back
  to the textarea, and that Enter sends while Shift+Enter inserts a new line.
- Verify the chat log resizes by pointer drag and keyboard arrows, clamps to its
  minimum and maximum, persists the height, and resets on double-click.
- Verify degraded chart and news responses render an unavailable state instead
  of synthetic data.

## Phase rule

A phase is complete only after its gate passes and `CHANGELOG_LATEST.md` is
updated; see [PLAN.md](PLAN.md).
