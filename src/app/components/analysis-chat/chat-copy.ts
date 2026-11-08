export const ENGLISH_GREETING =
  "Hi — I can explain the selected instrument's trend, candlestick patterns, " +
  'key levels, VIX context, and recent headlines, or help you build an option ' +
  'card. What would you like to look at?';

export const RUSSIAN_GREETING =
  'Привет — я вижу выбранный инструмент. Могу объяснить тренд, свечные паттерны, ' +
  'ключевые уровни, контекст VIX и свежие заголовки или помочь собрать опционную ' +
  'карточку. С чего начнём?';

export interface ChatCopy {
  thinking: string;
  you: string;
  assistant: string;
  position: string;
  newsCaption: string;
  optionDraft: string;
  readyToAnalyze: string;
  switchTitle: string;
  switchCopy: (current: string, target: string) => string;
  singleOption: string;
  twoLegSpread: string;
  suggestedNote: (fields: string) => string;
  stillNeeded: (fields: string) => string;
  needsValue: string;
  analysisFailed: string;
  draftCancelled: (symbol: string) => string;
  nowWatching: (symbol: string) => string;
  alreadyShowing: (symbol: string) => string;
  staying: (symbol: string) => string;
  retryChat: (milliseconds: number, attempt: string) => string;
  retryAnalysis: (milliseconds: number, attempt: string) => string;
}

export const ENGLISH_COPY: ChatCopy = {
  thinking: 'Thinking...',
  you: 'You',
  assistant: 'Assistant',
  position: 'Position',
  newsCaption: 'Recent headlines (context, not a calendar)',
  optionDraft: 'Option draft',
  readyToAnalyze: 'Ready to analyze',
  switchTitle: 'Instrument switch',
  switchCopy: (current, target) =>
    `The chart is showing ${current}. Switching will load ${target}'s price, levels, chart, and news.`,
  singleOption: 'Single option',
  twoLegSpread: 'Two-leg spread',
  suggestedNote: (fields) =>
    `Suggested from the live chain: ${fields}. Example structure, not a recommendation.`,
  stillNeeded: (fields) => `Still needed: ${fields}.`,
  needsValue: 'needs a value',
  analysisFailed: 'Analysis failed',
  draftCancelled: (symbol) =>
    `Draft cancelled. We can keep talking about ${symbol}.`,
  nowWatching: (symbol) =>
    `Now watching ${symbol}. Ask about its chart, levels, news, or an option.`,
  alreadyShowing: (symbol) => `The chart is already showing ${symbol}.`,
  staying: (symbol) => `Staying on ${symbol}.`,
  retryChat: (milliseconds, attempt) =>
    `The chat service is unavailable. Retrying in ${milliseconds / 1_000} seconds (attempt ${attempt})...`,
  retryAnalysis: (milliseconds, attempt) =>
    `The analysis service is unavailable. Retrying in ${milliseconds / 1_000} seconds (attempt ${attempt})...`,
};

export const RUSSIAN_COPY: ChatCopy = {
  thinking: 'Думаю...',
  you: 'Вы',
  assistant: 'Ассистент',
  position: 'Позиция',
  newsCaption: 'Свежие заголовки (контекст, не календарь)',
  optionDraft: 'Черновик опциона',
  readyToAnalyze: 'Готово к анализу',
  switchTitle: 'Смена инструмента',
  switchCopy: (current, target) =>
    `На графике ${current}. При переключении загрузятся цена, уровни, график и новости ${target}.`,
  singleOption: 'Одиночный опцион',
  twoLegSpread: 'Двухногий спред',
  suggestedNote: (fields) =>
    `Предложено по живой цепочке: ${fields}. Пример структуры, не рекомендация.`,
  stillNeeded: (fields) => `Ещё нужно: ${fields}.`,
  needsValue: 'нужно значение',
  analysisFailed: 'Ошибка анализа',
  draftCancelled: (symbol) =>
    `Черновик отменён. Можем продолжить разговор о ${symbol}.`,
  nowWatching: (symbol) =>
    `Теперь смотрим ${symbol}. Спросите про график, уровни, новости или опцион.`,
  alreadyShowing: (symbol) => `График уже показывает ${symbol}.`,
  staying: (symbol) => `Остаёмся на ${symbol}.`,
  retryChat: (milliseconds, attempt) =>
    `Сервис чата недоступен. Повтор через ${milliseconds / 1_000} сек. (попытка ${attempt}).`,
  retryAnalysis: (milliseconds, attempt) =>
    `Сервис анализа недоступен. Повтор через ${milliseconds / 1_000} сек. (попытка ${attempt}).`,
};

export const RUSSIAN_FIELD_LABELS: Record<string, string> = {
  side: 'покупаете вы или продаёте',
  option_type: 'это call или put',
  strike: 'страйк',
  expiration: 'дата экспирации',
  strategy_type: 'какой двухногий спред',
};

export const RUSSIAN_SUGGESTION_FIELDS: Record<string, string> = {
  expiration: 'экспирация',
  strike: 'страйк',
  long_strike: 'длинный страйк',
  width: 'ширина',
  side: 'сторона',
  option_type: 'тип опциона',
};

export const RUSSIAN_STAGE_LABELS: Record<string, string> = {
  'Loading price history for volatility context':
    'Загружаю историю цен для оценки волатильности',
  'Loading recent headlines': 'Загружаю свежие заголовки',
  'Loading the option chain': 'Загружаю опционную цепочку',
  'Loading the underlying quote': 'Загружаю котировку базового актива',
  'Calculating position metrics': 'Считаю метрики позиции',
  'Writing the assessment': 'Пишу оценку',
  'History unavailable': 'История недоступна',
  'No recent headlines': 'Свежих заголовков нет',
  'Quote unavailable': 'Котировка недоступна',
  'Assessment ready': 'Оценка готова',
};

export const RUSSIAN_STAGE_PATTERNS: ReadonlyArray<
  readonly [RegExp, string]
> = [
  [/^(\d+) daily candles$/, '$1 дневных свечей'],
  [/^(\d+) recent headlines$/, '$1 свежих заголовков'],
  [/^(\d+) contracts for (.+)$/, '$1 контрактов на $2'],
];

export const RUSSIAN_WARNINGS: Record<string, string> = {
  cached_data: 'Используются кэшированные данные.',
  rate_limited: 'Провайдер ограничил частоту запросов.',
  upstream_error: 'Провайдер временно недоступен.',
  market_data_unavailable: 'Рыночные данные недоступны.',
  not_found: 'Данные не найдены.',
  unreachable: 'Провайдер недоступен.',
  payload_error: 'Провайдер вернул некорректные данные.',
  quote_unavailable: 'Котировка недоступна.',
  price_unavailable: 'Цена недоступна.',
  change_pct_unavailable: 'Изменение цены недоступно.',
  vix_unavailable: 'VIX недоступен.',
  news_provider_not_configured: 'Провайдер новостей не настроен.',
  news_rate_limited: 'Новости: превышен лимит запросов.',
  news_unavailable: 'Новости временно недоступны.',
  hv_unavailable: 'Историческая волатильность недоступна.',
  delta_unavailable: 'Дельта недоступна, вероятность не рассчитать.',
  theta_unavailable: 'Тета недоступна.',
  scenario_1sigma_unavailable: 'Ожидаемое движение 1σ недоступно.',
  scenario_2sigma_unavailable: 'Ожидаемое движение 2σ недоступно.',
  iv_rank_unavailable: 'IV rank недоступен.',
  volume_unavailable: 'Объём недоступен.',
  symbol_requires_paid_plan: 'Для этого символа нужен платный тариф Twelve Data.',
  candles_provider_not_configured: 'Провайдер свечей не настроен.',
  candles_rate_limited: 'Провайдер свечей ограничил частоту запросов.',
  candles_unavailable: 'Свечи временно недоступны.',
};
