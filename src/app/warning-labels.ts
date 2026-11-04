const WARNING_LABELS: Record<string, string> = {
  volume_unavailable: 'Volume is unavailable for this symbol.',
  symbol_requires_paid_plan: 'Candles for this symbol require a paid Twelve Data plan.',
  candles_provider_not_configured: 'The candle provider is not configured.',
  candles_rate_limited: 'The candle provider is rate limited.',
  candles_unavailable: 'Candles are temporarily unavailable.',
  quote_unavailable: 'The quote is unavailable.',
  price_unavailable: 'The price is unavailable.',
  change_pct_unavailable: 'The price change is unavailable.',
  vix_unavailable: 'VIX is unavailable.',
  news_provider_not_configured: 'The news provider is not configured.',
  news_rate_limited: 'The news provider is rate limited.',
  news_unavailable: 'News is temporarily unavailable.',
  iv_rank_unavailable: 'IV rank is unavailable.',
  hv_unavailable: 'Historical volatility is unavailable for this symbol.',
  delta_unavailable: 'Delta is unavailable, so probability cannot be computed.',
  theta_unavailable: 'Theta is unavailable for this position.',
  scenario_1sigma_unavailable: 'The 1-sigma expected move is unavailable.',
  scenario_2sigma_unavailable: 'The 2-sigma expected move is unavailable.',
};

export function warningLabel(code: string): string {
  return WARNING_LABELS[code] ?? code;
}
