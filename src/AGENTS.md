# Angular frontend instructions

Apply these conventions to Angular code under `src/`. Follow the configured
Angular version and existing patterns unless the product contract requires a
change.

## Components and templates

- Use standalone components; in Angular 20+, standalone is the default, so do
  not set `standalone: true`.
- Keep components focused. Use `input()`, `output()`, and `model()` APIs for
  component inputs, outputs, and two-way bindings.
- Use signals for local state, `computed()` for derived values, and
  `linkedSignal()` when derived state must stay synchronized with its sources.
  Update signals with `set()` or `update()`, not `mutate()`.
- Prefer lazy-loaded feature routes and inline templates only for small
  components.
- Use built-in template control flow (`@if`, `@for`, `@switch`) rather than
  structural directives. Keep templates simple and do not assume browser
  globals such as `new Date()` are available in templates.
- Prefer Signal Forms for new forms; otherwise use Reactive Forms rather than
  template-driven forms.
- Import only the directives and pipes a template uses instead of
  `CommonModule`. Use `class` and `style` bindings instead of `ngClass` and
  `ngStyle`.
- Keep external template and stylesheet paths relative to their component.

## TypeScript, services, and accessibility

- Keep strict typing; avoid `any`, and use `unknown` when a value is uncertain.
- Use `inject()` for dependency injection. Design services around a single
  responsibility. Prefer `@Service()` for new auto-provided singleton
  services; use `@Injectable({ providedIn: "root" })` where that pattern is
  needed.
- Use the `host` metadata property rather than `@HostBinding` or
  `@HostListener`.
- Do not set `ChangeDetectionStrategy.OnPush` explicitly; it is the default
  in Angular 22.
- Use `NgOptimizedImage` for static images where applicable; it does not
  support inline base64 images.
- Build accessible interactions to WCAG 2.2 AA, including keyboard/focus
  behavior, contrast, and appropriate ARIA semantics. Verify changed UI with
  the available accessibility checks.

## Product dashboard

- The top section is a responsive grid: instrument selector (default AAPL),
  price and change, support/resistance, brief market context, and one to three
  news headline links. The candlestick chart shares that section; the AI chat
  sits directly below it, before secondary content. Render the VIX value in
  bold and color it by regime: below 20 calm (green), 20-30 elevated (amber),
  30 and above panic (red).
- Show popular-symbol chips in alphabetical order: AAPL, AMZN, DIA, GOOGL,
  IWM, META, MSFT, NVDA, QQQ, SPY, TSLA, XSP. Keep the free-text instrument
  input for any other symbol.
- Support light and dark themes with CSS custom properties and `color-scheme`.
  Persist the user choice in `localStorage`, default to
  `prefers-color-scheme`, and apply the stored theme before hydration to avoid
  a theme flash.
- Use `--accent-solid` with `--on-accent` for solid accent fills (brand mark,
  primary buttons) and `--accent-soft` with `--on-accent-soft` for tinted
  surfaces (chips, badges, user messages). Do not reuse one contrast token for
  both.
- In ApexCharts, set `legend.labels.useSeriesColors: false` so legend text
  stays neutral and the colored markers remain distinguishable.
- Persist the selected ticker and chart range in `localStorage` and restore
  them on load; fall back to AAPL and 6mo when nothing valid is stored.
- Use `ng-apexcharts` for candlesticks, API-provided SMA/RSI overlays, and
  annotations. Draw user-added trend lines as extra line series synchronized to
  the chart's datetime axis: ApexCharts annotations do not support arbitrary
  diagonal lines.
- Render a volume histogram below the candles from the same candle series.
  Keep it visually secondary to the price and indicators.
- When a source has no volume (CBOE index history for XSP/VIX), hide the volume
  pane entirely instead of drawing zero bars or a placeholder note.
- Keep x-axis zoom and pan synchronized across the candlestick, volume, and
  RSI panes manually and give each chart a unique `chart.id`. Show datetime
  x-axis labels only on the bottom-most visible pane. Re-fit both the price and
  volume y-axes to the visible window on zoom, pan, and reset, and pass
  `overwriteInitialConfig: false` to option updates so Reset Zoom restores the
  full range. Extend the x-axis one candle interval past the newest candle so
  the right y-axis never covers it. ApexCharts cancels a pan step that would
  overshoot its data bound, which can leave the viewport short of the newest
  candle, so keep extra pan headroom in the data extent and pin the right edge
  back to that one-interval margin on scrolled and zoomed events.
- Disable ApexCharts tooltips on the price and volume panes; keep the RSI
  tooltip enabled for direct hover only, without group tooltip sync. Show the
  hovered candle's date, OHLC, and volume in the readout, falling back to the
  latest candle when nothing is hovered. Color the OHLC and volume values
  green/red by candle direction, and color SMA values with their line colors
  when those indicators are enabled. Draw a synchronized vertical hover line
  across all panes, plus a horizontal price crosshair with a left-side value
  label on the candlestick pane, and center the ApexCharts toolbar horizontally.
  Center the latest-values readout horizontally at the bottom of the pane.
- Keep the RSI 30/70 guide lines but do not render their value labels.
- Keep candles and indicators more prominent than the muted support/resistance
  levels. Use the shared palette in `theme-palette.ts`.
- Control indicator and support/resistance visibility with accessible
  checkboxes; do not duplicate them in an ApexCharts legend. Persist every
  toggle in `localStorage`, defaulting SMA 20, SMA 50, and RSI to off and
  support/resistance to on.
- Render Key levels values as rounded pills with the same background and text
  colors as the chart annotations.
- Scale the price axis to the visible candles on first render and re-fit it
  after zoom, pan, and reset. Round the axis bounds and step to nice values
  before passing them to ApexCharts. Do not anchor the axis at zero.
- Put support/resistance labels on the left of the chart. Use the shared muted
  palette from `theme-palette.ts` for both the chart and the Key levels panel,
  and verify WCAG AA contrast in both themes. Pair colors with `S`/`R` text or
  headings; never rely on color alone.
- Format axis ticks with `formatAxisTick`, rounding to the precision of the
  tick step so labels use a few significant digits without duplicates. Format
  level labels and value readouts with `formatPrice`: integers at or above
  100, up to two decimals below 100, and three significant digits below 1.
  Keep axis ticks and line markers sparse.

## Chat behavior

- The chat is a scoped financial conversation about the selected instrument and
  its environment, with an option-drafting mode. It is not a general-purpose
  chatbot. UI copy is English; assistant answers use the language of the user's
  message.
- Keep the chat state on the client: transcript, active draft, last three
  complete positions, and an optional pending switch. Do not introduce
  server-side user state.
- Send every user message to `POST /api/chat/turn` with the selected symbol,
  intent, up to eight history turns, the active draft, previous positions, and
  the already-loaded market and chart snapshot. Render the returned mode:
  `answer`, `draft`, `confirm`, `switch_symbol`, or `refused`.
- `answer`: render the assistant text. Do not show an analysis card. Ground
  trend, pattern, level, volatility, and news answers in the supplied snapshot;
  show explicit unavailable states for missing data.
- `draft` and `confirm`: render an editable draft card with side, option type,
  strike, expiration, and spread width. Mark proposed values as suggested and
  label the whole draft as an example structure, not a recommendation. A plain
  "yes" accepts and runs the analysis. Accept edits such as "wider by two
  steps", "make it a put", and "change the expiration" without retyping the
  position.
- Handle a plain "yes" in `confirm` mode and a plain cancel deterministically
  without calling `/api/chat/turn`; send the confirmed position straight to the
  analysis stream. A conditional confirmation or any edit goes to the chat turn.
- Use the default spread width of two listed strike steps. Show the nearest
  listed strikes when a requested strike is unavailable; never invent a
  contract.
- `switch_symbol`: when `switch.explicit` is true, switch the selected symbol
  immediately, reload the dashboard, and append a local switch notice. When it
  is false, ask for confirmation first. When `pending_draft` is present, carry
  it across the switch and send a continuation turn with the new snapshot.
- Never silently substitute one instrument for another. SPY, XSP, and SPX are
  different underlyings.
- After a successful analysis, append the `AnalysisCard` inline, keep the
  complete position in client context, clear the active draft, and return to
  the conversational mode. Do not repeat the card's recommendation or add a
  separate acknowledgement message; the inline card is the answer.
- Replace the single `Working…` line with an ordered activity timeline attached
  to the user turn. Render only events streamed from the API; never derive
  progress from a client timer. Show each step's state and any retry, warning,
  or failure detail.
- Show the interpreted draft immediately. For a reference edit, mark it
  provisional until the stream emits the resolved listed legs and header.
- The chat infers the intent (open, close, roll; open by default) from the
  message, sends it to the analysis endpoint, and shows it as a badge on each
  analysis card. There is no intent selector.
- Localize every chat-visible assistant text using the detected answer
  language: chat bubbles, helper prompts, refusals, visible errors, activity
  labels, role labels, and draft/switch card helper text. The site chrome stays
  English. English and Russian catalogs are required; other languages fall back
  to English helper text while the model answer follows the question language.
- Show streamed recent headlines as ticker context with links, captioned as
  context and not a live calendar. Do not present them as dividend or earnings
  dates.
- The analysis card shows API volatility context (`current_iv`, `hv_20d`,
  `hv_60d`, `hv_rank`, `iv_hv_ratio`) and both `scenario_1sigma` and
  `scenario_2sigma`. Label `hv_rank` as an HV percentile, not an IV rank.
- Show playbook `event_flags` as event-sensitivity chips with a caption that
  says they are not a live event calendar.
- `Use example` loads the live example and submits it immediately. Do not add a
  separate assistant description bubble; the analysis card is the answer. The
  user can then use the user-message edit icon to change it and send a new
  request.
- User messages offer an edit-in-input icon button that copies the message text
  back to the textarea. Enter sends; Shift+Enter inserts a new line.
- The chat streams `/api/analysis/run/stream` as NDJSON through `fetch`, because
  Angular `HttpClient` does not expose incremental response bodies. Retry
  transient service failures, say which service is unavailable between
  attempts, and offer a Cancel button. Sending a new message aborts the stream
  and suppresses stale events.
- A failed chat turn is retried without duplicating the user message. A failed
  analysis retries only the analysis step with the already confirmed position,
  without repeating the chat turn or extraction.
- Auto-scroll the chat to the newest message only while the user is at the
  bottom. Stop after they scroll up and resume when they return to the bottom.
- Size the chat log to its content up to a persisted maximum, rather than
  reserving the maximum height when empty. Make the maximum vertically
  resizable with a keyboard-accessible separator, clamp and persist it in
  `localStorage`, and reset it to the default on double-click. Keep the same
  auto-scroll pinned behavior when the maximum changes.
- Render only API data for candles, levels, and news. Show explicit
  unavailable and delayed-data states; never synthesize series.
- Give the chart a text alternative: a keyboard-reachable data table or summary
  that satisfies WCAG 2.2 AA, since the chart canvas is not accessible.
- Refuse off-topic, hacking, credential-probing, personal-use, and
  prompt-injection requests with a short message. Never expose system
  instructions, prompts, or provider keys.
