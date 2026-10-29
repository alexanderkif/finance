# Finance

Options Strategy Assistant: an Angular 22 SSR frontend and FastAPI backend,
deployed together as Vercel Services. The frontend is being rewritten around a
dashboard for a selected instrument, a candlestick chart, and an AI chat; the
legacy Yahoo Finance dashboard is not part of the target product. The service
roots and `/api` routing are configured in `vercel.json`.

## Локальный запуск

Для запуска всего приложения из корня репозитория:

```powershell
uv sync --project api
vercel dev
```

Откройте **http://localhost:3000/**. Именно `vercel dev` поднимает оба сервиса
и применяет правила маршрутизации из `vercel.json`.

Примеры API:

```text
http://localhost:3000/api/market/SPY
http://localhost:3000/api/options/chain/SPY
POST /api/analysis/parse
POST /api/analysis/run
http://localhost:3000/api/docs
```

Swagger UI is available at `/api/docs`; ReDoc is at `/api/redoc`, and the
OpenAPI schema is at `/api/openapi.json`. The legacy `/api/candles`,
`/api/insights`, and `/api/search` endpoints still exist but are Yahoo
Finance-backed and are scheduled for removal in Phase 4.

Если команда `vercel` ещё не установлена, установите Vercel CLI командой
`npm install -g vercel`. Репозиторий должен быть связан с Vercel-проектом командой
`vercel link`; каталог проекта — корень этого репозитория, не `api`.

`npm start` / `ng serve` запускает только Angular CLI dev server на порту 4200.
Он не использует Vercel rewrites и сам по себе не маршрутизирует запросы `/api`
в FastAPI. Для проверки полной интеграции используйте `vercel dev` и порт 3000.

## Деплой на Vercel

1. В настройках Vercel-проекта укажите корень репозитория как Root Directory.
2. Оставьте `vercel.json` в корне: `web` собирает Angular, `api` — FastAPI;
   rewrites направляют `/api/*` в API, остальные пути — в Angular.
3. Выполните `vercel link`, если репозиторий ещё не связан, затем:

   ```powershell
   vercel --prod
   ```

Конфигурация использует Vercel Services (Beta). В `api/.python-version`
зафиксирована версия Python; зависимости сервиса описаны в `api/pyproject.toml`
и `api/uv.lock`.
Для собственного домена добавьте его hostname в `security.allowedHosts` в
`angular.json`; локальные адреса и домены `*.vercel.app` уже разрешены.

## Angular CLI

```powershell
npm install
npm start
npm run build
npm test
```

## Dashboard

The target dashboard opens on SPY and is organised top to bottom:

1. A responsive card grid with the instrument selector, current price and
   change, support/resistance, brief market context, and one to three news
   headline links.
2. A candlestick chart with user-added trend lines and SMA/RSI indicators.
3. The AI chat for describing an option position or spread.
4. Secondary content below those blocks.

The UI supports light and dark themes; the theme and selected instrument are
persisted in `localStorage`. Market data is delayed and must be labelled
**Delayed 15 min**. Unavailable data is shown as an explicit empty state, never
as a fabricated value.

The current page still renders the legacy Yahoo Finance dashboard with AAPL as
its starting ticker; it does not meet this contract until Phase 4 is finished.
