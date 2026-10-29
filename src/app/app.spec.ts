import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { App } from './app';
import { AnalysisResult, ChartResponse, MarketResponse } from './models/market-data';
import { MarketApi } from './services/market-data';

const chartStub: ChartResponse = {
  symbol: 'SPY',
  range: '6mo',
  interval: '1d',
  candles: [],
  sma: [],
  rsi: { period: 14, points: [] },
  support: [742.1],
  resistance: [781.5],
  source: null,
  as_of: null,
  degraded: true,
  warnings: ['candles_provider_not_configured'],
};

const marketStub: MarketResponse = {
  symbol: 'SPY',
  price: 772.31,
  change_pct: 0.34,
  vix: 17.11,
  news: [
    {
      title: 'SPY edges higher as breadth improves',
      url: 'https://example.com/spy-news',
      publisher: 'Newswire',
      published_at: '2026-10-28T16:00:00Z',
    },
  ],
  sources: { quote: 'cboe_delayed', vix: 'cboe_delayed', news: 'finnhub' },
  as_of: '2026-10-28T16:00:00Z',
  quote_as_of: '2026-10-28T15:48:15Z',
  vix_as_of: '2026-10-28T15:49:00Z',
  news_as_of: '2026-10-28T16:00:00Z',
  degraded: false,
  warnings: [],
};

const analysisStub: AnalysisResult = {
  strategy_key: 'bull_put_spread',
  header: 'Bull Put Spread XSP 732/729 2030-11-15',
  recommendation: 'This spread profits if the underlying stays above 731.79.',
  probability_positive: 0.7,
  max_profit: 150,
  max_loss: 150,
  net_credit_debit: 150,
  breakeven: 730.5,
  theta_daily: 5,
  iv_rank: null,
  event_flags: ['earnings'],
  liquidity: {
    bid_ask_spread_pct: 12.5,
    open_interest: 800,
    volume: 400,
    rating: 'fair',
  },
  scenario_1sigma: null,
  detected_language: 'English',
  disclaimer: 'Educational analysis, not investment advice.',
  source: 'cboe_delayed',
  as_of: '2026-10-28T15:48:15Z',
  degraded: true,
  warnings: ['iv_rank_unavailable'],
};

describe('App', () => {
  const marketApiStub = {
    parse: async () => ({
      position_type: 'single' as const,
      legs: [
        {
          symbol: 'SPY',
          side: 'buy' as const,
          option_type: 'call' as const,
          strike: 600,
          expiration: '2030-11-15',
        },
      ],
      missing_fields: [],
      detected_language: 'English',
    }),
    runAnalysis: async (): Promise<AnalysisResult> => analysisStub,
    getExample: async (symbol: string) => ({
      symbol,
      message:
        'Sell the 760 put and buy the 755 put on SPY expiring 2030-11-15 to open a defined-risk bull put spread.',
      description:
        'SPY is near 770.00. This 760/755 put spread expires in 40 days and caps the loss at the strike width minus the credit received.',
      legs: [
        {
          symbol,
          side: 'sell' as const,
          option_type: 'put' as const,
          strike: 760,
          expiration: '2030-11-15',
        },
        {
          symbol,
          side: 'buy' as const,
          option_type: 'put' as const,
          strike: 755,
          expiration: '2030-11-15',
        },
      ],
      current_price: 770,
      source: 'cboe_delayed' as const,
      as_of: '2030-10-06T15:48:15Z',
    }),
  };

  beforeEach(async () => {
    localStorage.clear();
    document.documentElement.dataset['theme'] = 'light';
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: MarketApi, useValue: marketApiStub },
      ],
    }).compileComponents();
  });

  async function renderDashboard(): Promise<{
    fixture: ComponentFixture<App>;
    compiled: HTMLElement;
  }> {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const httpTesting = TestBed.inject(HttpTestingController);
    httpTesting.expectOne('/api/chart/SPY?range=6mo&interval=1d').flush(chartStub);
    httpTesting.expectOne('/api/market/SPY').flush(marketStub);
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, compiled: fixture.nativeElement as HTMLElement };
  }

  it('renders the default SPY dashboard with price and news', async () => {
    const { compiled } = await renderDashboard();

    expect(compiled.querySelector('#ticker')).toHaveProperty('value', 'SPY');
    expect(compiled.querySelector('.price')?.textContent).toContain('772.31');
    expect(compiled.querySelector('.change')?.textContent).toContain('0.34');
    expect(compiled.querySelector('.vix-value')?.classList).toContain('vix-calm');
    expect(compiled.querySelector('.levels')?.textContent).toContain('742');
    expect(compiled.querySelector('.levels')?.textContent).toContain('782');
    expect(compiled.querySelector('.news-list a')?.getAttribute('href')).toBe(
      'https://example.com/spy-news',
    );
    expect(compiled.querySelector('app-analysis-chat')).not.toBeNull();
  });

  it('switches the selected instrument from a chip', async () => {
    const { fixture, compiled } = await renderDashboard();
    const httpTesting = TestBed.inject(HttpTestingController);

    const chip = Array.from(
      compiled.querySelectorAll<HTMLButtonElement>('.instrument-card .chip'),
    ).find((button) => button.textContent?.trim() === 'TSLA');

    expect(chip).toBeDefined();
    chip!.click();
    fixture.detectChanges();

    httpTesting
      .match((request) => request.url.startsWith('/api/chart/TSLA'))
      .forEach((request) => request.flush({ ...chartStub, symbol: 'TSLA' }));
    httpTesting
      .match((request) => request.url === '/api/market/TSLA')
      .forEach((request) => request.flush({ ...marketStub, symbol: 'TSLA' }));

    expect(compiled.querySelector('#ticker')).toHaveProperty('value', 'TSLA');
    expect(localStorage.getItem('osa.symbol')).toBe('TSLA');
  });

  it('toggles the theme and persists it', async () => {
    const { fixture, compiled } = await renderDashboard();
    const toggle = Array.from(compiled.querySelectorAll<HTMLButtonElement>('.topbar button')).find(
      (button) => button.textContent?.toLowerCase().includes('theme'),
    );

    expect(toggle).toBeDefined();
    toggle!.click();
    fixture.detectChanges();

    expect(document.documentElement.dataset['theme']).toBe('dark');
    expect(localStorage.getItem('osa.theme')).toBe('dark');
  });

  it('loads a dynamic and readable example into the chat', async () => {
    const { fixture, compiled } = await renderDashboard();
    const button = Array.from(
      compiled.querySelectorAll<HTMLButtonElement>('.chat-header button'),
    ).find((item) => item.textContent?.includes('Use example'));

    expect(button).toBeDefined();
    button!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    const textarea = compiled.querySelector<HTMLTextAreaElement>('.chat-form textarea');
    expect(textarea?.value).toContain('defined-risk bull put spread');
    expect(textarea?.value).toContain('2030-11-15');
    expect(textarea?.value).not.toContain('732');
  });
});
