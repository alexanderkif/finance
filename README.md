# Finance

Angular 22 SSR frontend and FastAPI backend, deployed together as Vercel
Services. The service roots and `/api` routing are configured in `vercel.json`.

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
http://localhost:3000/api/search?q=MSFT
http://localhost:3000/api/candles/MSFT?range=1mo&interval=1d
http://localhost:3000/api/docs
```

Swagger UI is available at `/api/docs`; ReDoc is at `/api/redoc`, and the
OpenAPI schema is at `/api/openapi.json`.

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

The home page starts with AAPL. Search by ticker or company name, choose a
matching result, and switch chart history from one month to five years. The
dashboard combines daily candles and volume with technical insights and
Yahoo Finance headlines.

The FastAPI routes are `/api/candles/{ticker}`, `/api/insights/{ticker}`, and
`/api/search?q=...`; their response schemas are declared in `api/index.py`.
