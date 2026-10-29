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

- The top section is a responsive grid: instrument selector (default SPY),
  price and change, support/resistance, brief market context, and one to three
  news headline links. The candlestick chart shares that section; the AI chat
  sits directly below it, before secondary content.
- Support light and dark themes with CSS custom properties and `color-scheme`.
  Persist the user choice in `localStorage`, default to
  `prefers-color-scheme`, and apply the stored theme before hydration to avoid
  a theme flash.
- Persist the selected ticker in `localStorage` and restore it on load; fall
  back to SPY when nothing valid is stored.
- Use `ng-apexcharts` for candlesticks, API-provided SMA/RSI overlays, and
  annotations. Draw user-added trend lines in a separate overlay synchronized to
  the chart: ApexCharts annotations do not support arbitrary diagonal lines.
- Render only API data for candles, levels, and news. Show explicit
  unavailable and delayed-data states; never synthesize series.
- Give the chart a text alternative: a keyboard-reachable data table or summary
  that satisfies WCAG 2.2 AA, since the chart canvas is not accessible.
- Do not introduce server-side user state.
