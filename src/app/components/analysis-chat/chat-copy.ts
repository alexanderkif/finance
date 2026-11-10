export const ENGLISH_GREETING =
  "Hi — I can explain the selected instrument's trend, candlestick patterns, " +
  'key levels, VIX context, and recent headlines, or help you build an option ' +
  'card. What would you like to look at?';

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
