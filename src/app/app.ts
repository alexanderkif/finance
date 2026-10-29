import { DatePipe, DecimalPipe } from '@angular/common';
import { httpResource } from '@angular/common/http';
import { Component, afterNextRender, computed, inject, signal } from '@angular/core';
import { errorMessage } from './api-error';
import { AnalysisChat } from './components/analysis-chat/analysis-chat';
import { PriceChart } from './components/price-chart/price-chart';
import { ChartRange, ChartResponse, MarketResponse, NewsHeadline } from './models/market-data';
import { formatPrice } from './price-format';
import { Preferences } from './services/preferences';
import { chartPalette } from './theme-palette';

@Component({
  selector: 'app-root',
  imports: [AnalysisChat, PriceChart, DatePipe, DecimalPipe],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly preferences = inject(Preferences);

  protected readonly browserReady = signal(false);
  protected readonly range = this.preferences.range;
  protected readonly tickerInput = signal('SPY');
  protected readonly tickerError = signal<string | null>(null);
  protected readonly ranges: readonly ChartRange[] = ['1mo', '3mo', '6mo', '1y', '5y'];
  protected readonly popularSymbols = ['SPY', 'QQQ', 'AAPL', 'TSLA', 'XSP'];

  protected readonly theme = this.preferences.theme;
  protected readonly symbol = this.preferences.symbol;
  protected readonly levelColors = computed(() => chartPalette(this.theme()));

  protected readonly chart = httpResource<ChartResponse>(() =>
    this.browserReady()
      ? `/api/chart/${encodeURIComponent(this.symbol())}?range=${this.range()}&interval=1d`
      : undefined,
  );

  protected readonly market = httpResource<MarketResponse>(() =>
    this.browserReady() ? `/api/market/${encodeURIComponent(this.symbol())}` : undefined,
  );

  protected readonly chartData = computed(() =>
    this.chart.hasValue() ? this.chart.value() : undefined,
  );
  private readonly marketData = computed(() =>
    this.market.hasValue() ? this.market.value() : undefined,
  );

  protected readonly support = computed(() => this.chartData()?.support ?? []);
  protected readonly resistance = computed(() => this.chartData()?.resistance ?? []);
  protected readonly news = computed((): NewsHeadline[] => this.marketData()?.news ?? []);
  protected readonly vix = computed(() => this.marketData()?.vix ?? null);
  protected readonly vixSeverity = computed<'calm' | 'elevated' | 'panic' | null>(() => {
    const value = this.vix();
    if (value === null) {
      return null;
    }
    if (value < 20) {
      return 'calm';
    }
    if (value < 30) {
      return 'elevated';
    }
    return 'panic';
  });
  protected readonly hasCandles = computed(() => (this.chartData()?.candles.length ?? 0) > 0);

  protected readonly price = computed<number | null>(() => {
    const marketPrice = this.marketData()?.price;
    if (marketPrice !== null && marketPrice !== undefined) {
      return marketPrice;
    }
    const candles = this.chartData()?.candles ?? [];
    return candles.at(-1)?.c ?? null;
  });

  protected readonly changePct = computed<number | null>(() => {
    const marketChange = this.marketData()?.change_pct;
    if (marketChange !== null && marketChange !== undefined) {
      return marketChange;
    }
    const candles = this.chartData()?.candles ?? [];
    if (candles.length < 2) {
      return null;
    }
    const previous = candles.at(-2)?.c;
    const latest = candles.at(-1)?.c;
    if (!previous || latest === undefined) {
      return null;
    }
    return ((latest - previous) / previous) * 100;
  });

  protected readonly asOf = computed(
    () => this.marketData()?.as_of ?? this.chartData()?.as_of ?? null,
  );

  protected readonly sourceLabels = computed<string[]>(() => {
    const labels: string[] = [];
    const sources = this.marketData()?.sources;
    if (sources?.quote) {
      labels.push('CBOE delayed');
    }
    const chartSource = this.chartData()?.source;
    if (chartSource === 'twelve_data') {
      labels.push('Twelve Data');
    } else if (chartSource === 'cboe_index_history') {
      labels.push('CBOE daily history');
    }
    if (sources?.news) {
      labels.push('Finnhub');
    }
    return labels;
  });

  protected readonly warnings = computed<string[]>(() => {
    const chartWarnings = this.chartData()?.warnings ?? [];
    const marketWarnings = this.marketData()?.warnings ?? [];
    return [...new Set([...marketWarnings, ...chartWarnings])];
  });

  protected readonly degraded = computed(
    () => Boolean(this.chartData()?.degraded) || Boolean(this.marketData()?.degraded),
  );

  protected readonly errorMessage = errorMessage;

  constructor() {
    afterNextRender(() => {
      this.browserReady.set(true);
      this.tickerInput.set(this.symbol());
    });
  }

  protected submitTicker(event: SubmitEvent): void {
    event.preventDefault();
    if (this.preferences.setSymbol(this.tickerInput())) {
      this.tickerInput.set(this.symbol());
      this.tickerError.set(null);
      return;
    }
    this.tickerError.set('Use 1вЂ“15 characters: letters, digits, dot, dash, or underscore.');
  }

  protected selectSymbol(symbol: string): void {
    if (this.preferences.setSymbol(symbol)) {
      this.tickerInput.set(this.symbol());
      this.tickerError.set(null);
    }
  }

  protected updateTickerInput(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLInputElement) {
      this.tickerInput.set(target.value);
    }
  }

  protected selectRange(range: ChartRange): void {
    this.preferences.setRange(range);
  }

  protected toggleTheme(): void {
    this.preferences.toggleTheme();
  }

  protected reload(): void {
    this.chart.reload();
    this.market.reload();
  }

  protected warningLabel(code: string): string {
    switch (code) {
      case 'volume_unavailable':
        return 'Volume is unavailable for this symbol.';
      case 'symbol_requires_paid_plan':
        return 'Candles for this symbol require a paid Twelve Data plan.';
      case 'candles_provider_not_configured':
        return 'The candle provider is not configured.';
      case 'candles_rate_limited':
        return 'The candle provider is rate limited.';
      case 'candles_unavailable':
        return 'Candles are temporarily unavailable.';
      case 'quote_unavailable':
        return 'The quote is unavailable.';
      case 'price_unavailable':
        return 'The price is unavailable.';
      case 'change_pct_unavailable':
        return 'The price change is unavailable.';
      case 'vix_unavailable':
        return 'VIX is unavailable.';
      case 'news_provider_not_configured':
        return 'The news provider is not configured.';
      case 'news_rate_limited':
        return 'The news provider is rate limited.';
      case 'news_unavailable':
        return 'News is temporarily unavailable.';
      case 'iv_rank_unavailable':
        return 'IV rank is unavailable.';
      default:
        return code;
    }
  }

  protected formatLevel(value: number): string {
    return formatPrice(value);
  }
}
