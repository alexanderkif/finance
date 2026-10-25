import {
  afterNextRender,
  Component,
  computed,
  effect,
  ElementRef,
  inject,
  OnDestroy,
  resource,
  signal,
  viewChild,
} from '@angular/core';
import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import type { CandlestickData, IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import {
  Candle,
  CandlesResponse,
  ChartRange,
  InsightsResponse,
  InsightValue,
  SearchResponse,
  SearchQuote,
} from './models/market-data';
import { MarketData } from './services/market-data';

@Component({
  imports: [CurrencyPipe, DatePipe, DecimalPipe],
  selector: 'app-root',
  templateUrl: './app.html',
})
export class App implements OnDestroy {
  private readonly marketData = inject(MarketData);
  private readonly chartElement = viewChild<ElementRef<HTMLDivElement>>('chart');
  private chart?: IChartApi;
  private candleSeries?: ISeriesApi<'Candlestick'>;
  private volumeSeries?: ISeriesApi<'Histogram'>;
  private resizeObserver?: ResizeObserver;

  protected readonly chartError = signal<string | null>(null);
  protected readonly ticker = signal('AAPL');
  protected readonly searchInput = signal('AAPL');
  protected readonly searchQuery = signal('AAPL');
  protected readonly range = signal<ChartRange>('6mo');
  protected readonly showSearchResults = signal(false);
  protected readonly browserReady = signal(false);
  protected readonly ranges: readonly ChartRange[] = ['1mo', '3mo', '6mo', '1y', '5y'];
  protected readonly popularTickers = ['NVDA', 'MSFT', 'TSLA'];

  protected readonly candles = resource<
    CandlesResponse,
    { ticker: string; range: ChartRange } | undefined
  >({
    params: () =>
      this.browserReady() ? { ticker: this.ticker(), range: this.range() } : undefined,
    loader: ({ params, abortSignal }) => {
      if (!params) return Promise.reject(new Error('Choose a ticker to load market data.'));
      return this.marketData.getCandles(params.ticker, params.range, abortSignal);
    },
  });

  protected readonly insights = resource<InsightsResponse, string | undefined>({
    params: () => (this.browserReady() ? this.ticker() : undefined),
    loader: ({ params, abortSignal }) => {
      if (!params) return Promise.reject(new Error('Choose a ticker to load market data.'));
      return this.marketData.getInsights(params, abortSignal);
    },
  });

  protected readonly searchResults = resource<SearchResponse, string | undefined>({
    params: () => (this.browserReady() ? this.searchQuery() : undefined),
    loader: ({ params, abortSignal }) => {
      if (!params) return Promise.reject(new Error('Enter a symbol to search market data.'));
      return this.marketData.search(params, abortSignal);
    },
  });

  protected readonly latestCandle = computed(() => {
    const data = this.candles.value();
    return data?.candles.at(-1);
  });

  protected readonly priceChange = computed(() => {
    const data = this.candles.value()?.candles ?? [];
    if (data.length < 2) return null;
    return data[data.length - 1].close - data[0].close;
  });

  protected readonly priceChangePercent = computed(() => {
    const data = this.candles.value()?.candles ?? [];
    if (data.length < 2 || data[0].close === 0) return null;
    return ((data[data.length - 1].close - data[0].close) / data[0].close) * 100;
  });

  protected readonly searchQuotes = computed(() => this.searchResults.value()?.quotes ?? []);
  protected readonly news = computed(() => this.searchResults.value()?.news ?? []);

  constructor() {
    afterNextRender(() => {
      this.browserReady.set(true);
      void this.initializeChart().catch((error: unknown) => {
        this.chartError.set(this.errorMessage(error));
      });
    });

    effect(() => {
      const data = this.candles.value();
      if (!data) return;
      this.setChartData(data.candles);
      this.setVolumeData(data.candles);
    });
  }

  protected submitSearch(event: SubmitEvent): void {
    event.preventDefault();
    const query = this.searchInput().trim();
    if (!query) return;

    const symbol = query.toUpperCase();
    this.ticker.set(symbol);
    this.searchQuery.set(query);
    this.showSearchResults.set(true);
  }

  protected selectQuote(quote: SearchQuote): void {
    if (!quote.symbol) return;
    const symbol = quote.symbol.toUpperCase();
    this.ticker.set(symbol);
    this.searchInput.set(symbol);
    this.searchQuery.set(symbol);
    this.showSearchResults.set(false);
  }

  protected selectTicker(symbol: string): void {
    const normalizedSymbol = symbol.toUpperCase();
    this.ticker.set(normalizedSymbol);
    this.searchInput.set(normalizedSymbol);
    this.searchQuery.set(normalizedSymbol);
    this.showSearchResults.set(false);
  }

  protected updateSearchInput(event: Event): void {
    this.searchInput.set((event.target as HTMLInputElement).value);
  }

  protected selectRange(range: ChartRange): void {
    this.range.set(range);
  }

  protected onRefresh(): void {
    this.candles.reload();
    this.insights.reload();
    this.searchResults.reload();
  }

  protected formatInsight(value: InsightValue | undefined): string {
    if (value === null || value === undefined) return '—';
    if (typeof value !== 'object') return String(value);
    if (Array.isArray(value)) return value.map((item) => this.formatInsight(item)).join(' · ');
    return (
      Object.entries(value)
        .filter(([, item]) => item !== null)
        .map(([key, item]) => `${this.humanize(key)} ${this.formatInsight(item)}`)
        .join(' · ') || '—'
    );
  }

  protected humanize(value: string): string {
    return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  protected errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : 'Please try again in a moment.';
  }

  protected trackQuote(_index: number, quote: SearchQuote): string {
    return quote.symbol ?? String(_index);
  }

  protected trackNews(_index: number, item: { title: string | null }): string {
    return item.title ?? String(_index);
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.chart?.remove();
  }

  private async initializeChart(): Promise<void> {
    const element = this.chartElement()?.nativeElement;
    if (!element) return;
    if (typeof ResizeObserver === 'undefined') {
      this.chartError.set('Interactive charts require ResizeObserver support in this browser.');
      return;
    }

    const { CandlestickSeries, ColorType, createChart, HistogramSeries } =
      await import('lightweight-charts');

    this.chart = createChart(element, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: '#101310' },
        textColor: '#8e9990',
        fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: '#1c211d' },
        horzLines: { color: '#1c211d' },
      },
      rightPriceScale: { borderColor: '#292e29' },
      timeScale: {
        borderColor: '#292e29',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { color: '#62746a', labelBackgroundColor: '#29332c' },
        horzLine: { color: '#62746a', labelBackgroundColor: '#29332c' },
      },
    });

    this.candleSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: '#b9f36a',
      downColor: '#f07868',
      borderUpColor: '#b9f36a',
      borderDownColor: '#f07868',
      wickUpColor: '#b9f36a',
      wickDownColor: '#f07868',
    });

    this.volumeSeries = this.chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      lastValueVisible: false,
      priceLineVisible: false,
    });
    this.volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    this.resizeObserver = new ResizeObserver(() => this.chart?.timeScale().fitContent());
    this.resizeObserver.observe(element);
    const data = this.candles.value()?.candles;
    if (data) {
      this.setChartData(data);
      this.setVolumeData(data);
    }
  }

  private setChartData(candles: Candle[]): void {
    if (!this.candleSeries) return;
    const points: CandlestickData<Time>[] = candles.map((item) => ({
      time: this.chartTime(item),
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }));
    this.candleSeries.setData(points);
    this.chart?.timeScale().fitContent();
  }

  private setVolumeData(candles: Candle[]): void {
    this.volumeSeries?.setData(
      candles.map((item) => ({
        time: this.chartTime(item),
        value: item.volume,
        color: item.close >= item.open ? '#b9f36a45' : '#f0786845',
      })),
    );
  }

  private chartTime(candle: Candle): Time {
    return new Date(candle.timestamp * 1000).toISOString().slice(0, 10) as Time;
  }
}
