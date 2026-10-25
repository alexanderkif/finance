export interface Candle {
  timestamp: number;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlesResponse {
  ticker: string;
  range: string;
  interval: string;
  count: number;
  candles: Candle[];
}

export interface SearchQuote {
  symbol: string | null;
  shortname: string | null;
  longname: string | null;
  exchange: string | null;
  type: string | null;
}

export interface SearchNews {
  title: string | null;
  publisher: string | null;
  link: string | null;
  pubtime: number | null;
  tickers: string[];
}

export interface SearchResponse {
  query: string;
  quotes_count: number;
  quotes: SearchQuote[];
  news_count: number;
  news: SearchNews[];
}

export type InsightValue =
  string | number | boolean | null | InsightValue[] | { [key: string]: InsightValue };

export interface InsightsResponse {
  ticker: string;
  trends: {
    short_term: InsightValue;
    mid_term: InsightValue;
    long_term: InsightValue;
  };
  key_levels: {
    support: InsightValue;
    resistance: InsightValue;
    stop_loss: InsightValue;
  };
  provider: string | null;
}

export type ChartRange = '1mo' | '3mo' | '6mo' | '1y' | '5y';
