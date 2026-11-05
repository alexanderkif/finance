export interface Candle {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number | null;
}

export interface IndicatorPoint {
  t: string;
  value: number;
}

export interface IndicatorSeries {
  period: number;
  points: IndicatorPoint[];
}

export type ChartRange = '1mo' | '3mo' | '6mo' | '1y' | '5y';

export interface ChartResponse {
  symbol: string;
  range: ChartRange;
  interval: '1d';
  candles: Candle[];
  sma: IndicatorSeries[];
  rsi: IndicatorSeries;
  support: number[];
  resistance: number[];
  source: 'twelve_data' | 'cboe_index_history' | null;
  as_of: string | null;
  degraded: boolean;
  warnings: string[];
}

export interface NewsHeadline {
  title: string;
  url: string;
  publisher: string | null;
  published_at: string | null;
}

export interface MarketSources {
  quote: 'cboe_delayed' | null;
  vix: 'cboe_delayed' | null;
  news: 'finnhub' | null;
}

export interface MarketResponse {
  symbol: string;
  price: number | null;
  change_pct: number | null;
  vix: number | null;
  news: NewsHeadline[];
  sources: MarketSources;
  as_of: string | null;
  quote_as_of: string | null;
  vix_as_of: string | null;
  news_as_of: string | null;
  degraded: boolean;
  warnings: string[];
}

export type OptionSide = 'buy' | 'sell';
export type OptionType = 'call' | 'put';
export type Intent = 'open' | 'close' | 'roll';

export interface PositionLeg {
  symbol: string;
  side: OptionSide;
  option_type: OptionType;
  strike: number;
  expiration: string;
}

export interface AnalysisPosition {
  position_type: 'single' | 'strategy';
  legs: PositionLeg[];
}

export type ReferenceKind = 'same' | 'shift' | 'widen' | 'narrow' | 'expiration';

export interface ReferenceEdit {
  kind: ReferenceKind;
  strikes: number | null;
  direction: 'up' | 'down' | null;
  expiration: string | null;
}

export interface ParsedLeg {
  symbol: string;
  side: OptionSide | null;
  option_type: OptionType | null;
  strike: number | null;
  expiration: string | null;
}

export interface ParseResponse {
  position_type: 'single' | 'strategy';
  legs: ParsedLeg[];
  missing_fields: string[];
  detected_language: string;
  strategy_key?: string;
  header?: string | null;
  reference?: ReferenceEdit | null;
}

export interface AnalysisRequest {
  position?: AnalysisPosition | null;
  context?: AnalysisPosition[];
  reference?: ReferenceEdit | null;
  intent: Intent;
  detected_language: string;
}

export interface AnalysisStageEvent {
  type: 'stage';
  id: string;
  status: 'started' | 'done' | 'failed';
  label: string;
  detail?: string;
}

export interface AnalysisPositionEvent {
  type: 'position';
  position: AnalysisPosition;
  header: string;
}

export interface AnalysisNewsEvent {
  type: 'news';
  news: NewsHeadline[];
  source: 'finnhub' | null;
  as_of: string | null;
}

export interface AnalysisWarningEvent {
  type: 'warning';
  code: string;
  message?: string;
}

export interface AnalysisResultEvent {
  type: 'result';
  result: AnalysisResult;
}

export interface AnalysisErrorEvent {
  type: 'error';
  status: number;
  detail: string;
}

export interface AnalysisHeartbeatEvent {
  type: 'heartbeat';
}

export type AnalysisStreamEvent =
  | AnalysisStageEvent
  | AnalysisPositionEvent
  | AnalysisNewsEvent
  | AnalysisWarningEvent
  | AnalysisResultEvent
  | AnalysisErrorEvent
  | AnalysisHeartbeatEvent;

export interface ExampleResponse {
  symbol: string;
  message: string;
  description: string;
  legs: PositionLeg[];
  current_price: number;
  source: 'cboe_delayed';
  as_of: string;
}

export interface Liquidity {
  bid_ask_spread_pct: number | null;
  open_interest: number | null;
  volume: number | null;
  rating: 'good' | 'fair' | 'poor' | 'unknown';
}

export interface Scenario {
  expected_move: number;
  low: number;
  high: number;
  days_to_expiration: number;
  atm_iv: number;
}

export interface AnalysisResult {
  strategy_key: string;
  intent: Intent;
  header: string;
  recommendation: string;
  probability_positive: number | null;
  max_profit: number | null;
  max_loss: number | null;
  net_credit_debit: number;
  breakeven: number | null;
  theta_daily: number | null;
  iv_rank: number | null;
  current_iv: number | null;
  hv_20d: number | null;
  hv_60d: number | null;
  hv_rank: number | null;
  iv_hv_ratio: number | null;
  event_flags: string[];
  liquidity: Liquidity;
  scenario_1sigma: Scenario | null;
  scenario_2sigma: Scenario | null;
  news: NewsHeadline[];
  news_source: 'finnhub' | null;
  news_as_of: string | null;
  detected_language: string;
  disclaimer: string;
  source: 'cboe_delayed';
  as_of: string;
  degraded: boolean;
  warnings: string[];
}
