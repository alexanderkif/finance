# Finance

Options Strategy Assistant: an Angular 22 SSR frontend and FastAPI backend,
deployed together as Vercel Services. The dashboard shows a selected
instrument, key levels, market context, news headlines, an ApexCharts
candlestick chart, and an AI chat for options analysis.

The current market data comes from free, non-commercial provider tiers: CBOE
delayed options/quote/VIX, CBOE index history for XSP/VIX candles, Twelve Data
Basic candles for other symbols, and Finnhub free news. A commercial launch
requires licensed plans or replacement providers.

## Локальный запуск

Установите зависимости и создайте `.env.local` в корне репозитория:

```powershell
uv sync --project api
```

```text
GEMINI_API_KEY=...
TWELVE_DATA_API_KEY=...
FINNHUB_API_KEY=...
```

Запустите всё приложение из корня репозитория:

```powershell
vercel dev
```

Откройте **http://localhost:3000/**. Именно `vercel dev` поднимает оба сервиса
и применяет правила маршрутизации из `vercel.json`.

Без `TWELVE_DATA_API_KEY` график показывает явное состояние недоступности, без
`FINNHUB_API_KEY` — пустой список новостей. Ключи не попадают в браузер.

Примеры API:

```text
http://localhost:3000/api/market/SPY
http://localhost:3000/api/chart/SPY?range=6mo
http://localhost:3000/api/options/chain/SPY
POST /api/analysis/parse
POST /api/analysis/run
http://localhost:3000/api/docs
```

Swagger UI: `/api/docs`, ReDoc: `/api/redoc`, OpenAPI: `/api/openapi.json`.

Если команда `vercel` ещё не установлена:

```powershell
npm install -g vercel
```

Репозиторий должен быть связан с Vercel-проектом командой `vercel link`;
каталог проекта — корень этого репозитория, не `api`.

`npm start` / `ng serve` запускает только Angular CLI dev server на порту 4200.
Он не использует Vercel rewrites и не маршрутизирует `/api` в FastAPI. Для
проверки полной интеграции используйте `vercel dev` и порт 3000.

## Деплой на Vercel

1. В настройках Vercel-проекта укажите корень репозитория как Root Directory.
2. Оставьте `vercel.json` в корне: `web` собирает Angular, `api` — FastAPI;
   rewrites направляют `/api/*` в API, остальные пути — в Angular.
3. Добавьте `GEMINI_API_KEY`, `TWELVE_DATA_API_KEY` и `FINNHUB_API_KEY` в
   Environment Variables проекта.
4. Выполните `vercel link`, если репозиторий ещё не связан, затем:

   ```powershell
   vercel --prod
   ```

Конфигурация использует Vercel Services (Beta). В `api/.python-version`
зафиксирована версия Python; зависимости сервиса описаны в `api/pyproject.toml`
и `api/uv.lock`. Для собственного домена добавьте его hostname в
`security.allowedHosts` в `angular.json`; локальные адреса и домены
`*.vercel.app` уже разрешены.

## Проверки

```powershell
# backend
api\.venv\Scripts\python.exe -m unittest discover -s api -p "test_*.py"

# frontend
npm test -- --watch=false

# production build
npm run build
```

## MCP для разработки

`opencode.json` в корне подключает MCP-серверы `angular-cli`, `APIs.io` и
`finance-api`. opencode не читает `.mcp.json` и `.vscode/mcp.json` — это
конфигурация Claude Code и VS Code.

`finance-api` запускает `api/mcp_dev.py`, который вызывает FastAPI-приложение
напрямую и не требует `vercel dev`. Инструменты: `get_market`, `get_chart`,
`get_option_chain`, `parse_analysis`, `run_analysis`, `get_analysis_example`.
Сервер только для разработки и не входит в деплой Vercel; зависимость `mcp`
объявлена в dev-группе `api/pyproject.toml` и ставится через
`uv sync --project api`.

## Dashboard

The dashboard opens on SPY and is organised top to bottom:

1. A responsive card grid with the instrument selector (persisted in
   `localStorage`), current price and change, support/resistance computed from
   candles, VIX and data timestamps, and up to three news headline links.
2. A candlestick chart with a volume histogram, SMA 20/50, RSI 14,
   support/resistance annotations, and user-added trend lines. XSP/VIX candles
   come from CBOE daily history and do not include volume, so the volume pane
   is hidden for those symbols with an explanatory note.
3. The AI chat for describing an option position or spread, with missing-field
   prompts, an intent selector, and a deterministic analysis card.

The UI supports light and dark themes; the theme and selected instrument are
persisted in `localStorage`, and the stored theme is applied before hydration.
Market data is delayed and labelled **Delayed 15 min**. Unavailable data is
shown as an explicit empty or degraded state, never as a fabricated value.

Data is fetched in the browser after hydration: the prerendered HTML ships the
dashboard shell with explicit unavailable states, because the API is not
reachable during the static build. Trend lines can be drawn with the mouse or
with the keyboard (focus the chart, move with the arrow keys, confirm with
Enter, cancel with Escape).

## Chat scope and misuse protection

The assistant is limited to a single option or a two-leg vertical spread for the
selected instrument and to questions about that analysis. It is not a
general-purpose chatbot. Before any Gemini call, the API applies deterministic
message-size, leg-count, symbol, and strategy checks and refuses off-topic,
nonsensical, abusive, creative-generation, prompt-injection, secret-probing, and
unsupported-strategy requests with a short message and no analysis. Refusals
make no Gemini call. System instructions, provider keys, and internal prompts
stay server-side and are never returned.

The service must not be repurposed for unrelated content generation,
personalized financial advice, trade execution or routing, market manipulation,
spam, or other personal use outside the intended options analysis.

## Providers and licence note

- CBOE delayed: options chain, underlying quote, VIX.
- CBOE index history: XSP and VIX daily OHLC (EOD, no volume).
- Twelve Data Basic: daily candles for other symbols; free tier allows
  8 requests/minute and 800/day. XSP/SPX candles require a paid plan, so XSP
  uses the CBOE history source instead.
- Finnhub free: company news with a general-market fallback.

These free tiers are for non-commercial use. Before a commercial launch,
license CBOE DataShop, Twelve Data, and Finnhub as required, or replace them
with commercially permitted sources.
