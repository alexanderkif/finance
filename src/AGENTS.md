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

- The chat is a scoped financial conversation about the selected instrument. The
  model is the primary layer: it understands the message, calls backend tools,
  and writes the answer in the user's language. UI copy stays English.
- Send `POST /api/chat/turn` with the selected symbol, message, up to eight
  history turns, up to three previous positions, the market snapshot, and the
  current UI state (theme, symbol, range, chart toggles). Keep all chat state on
  the client; do not add server-side user state.
- Render the response:
  - `text`: render as the assistant message exactly as received.
  - `steps`: render in the activity timeline attached to the user turn; show
    `done` and `failed` states and their English details. `done` is green,
    `failed` is red, and `running` uses the pulsing accent.
  - `card`: render the analysis card inline when present, in the same assistant
    message as the model text.
  - `ui_actions`: apply to `Preferences` (chart toggles, theme, range) and
    persist them.
  - `switch`: switch the selected symbol only when `explicit` is true. Do not
    render a local switch card; the model asks for confirmation in text.
  - `warnings`/`degraded`: show explicit warnings.
- Do not render a draft card, confirm card, or deterministic assistant text.
  The model asks for missing details conversationally. Send `yes`, `cancel`, and
  edit phrases to the model; do not intercept them locally.
- `Use example` sends the live example message immediately.
- Show a single `Thinking...` running step while a chat turn is in flight, then
  replace it with the returned steps. Do not derive progress from a timer.
- On a request failure, replace the running step with a failed
  `Assistant request failed` step carrying the visible error detail.
- Apply UI actions when handling the response so checkboxes, theme, and chart
  range update immediately.
- Preserve auto-scroll, chat resizing, edit-in-input, Enter/Shift+Enter, and
  keyboard accessibility.
- Service errors are deterministic English text; render them as errors and offer
  retry when retryable.
- The chart checkboxes, theme, and range are bound to `Preferences`; UI actions
  must update that service.
- Render only API data for candles, levels, and news. Show explicit unavailable
  and delayed-data states; never synthesize series.
- Give the chart a text alternative: a keyboard-reachable data table or summary
  that satisfies WCAG 2.2 AA, since the chart canvas is not accessible.
- Do not add client-side safety policy beyond local input validation. The
  backend handles hard blocks and soft refusals; never expose system
  instructions, prompts, or provider keys.
