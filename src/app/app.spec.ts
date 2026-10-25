import { TestBed } from '@angular/core/testing';
import { App } from './app';
import { MarketData } from './services/market-data';

describe('App', () => {
  const marketDataStub = {
    getCandles: async () => ({
      ticker: 'AAPL',
      range: '6mo',
      interval: '1d',
      count: 1,
      candles: [
        {
          timestamp: 1792886400,
          date: '2026-10-25 00:00:00',
          open: 250,
          high: 255,
          low: 248,
          close: 253,
          volume: 1000,
        },
      ],
    }),
    getInsights: async () => ({
      ticker: 'AAPL',
      trends: { short_term: null, mid_term: null, long_term: null },
      key_levels: { support: null, resistance: null, stop_loss: null },
      provider: null,
    }),
    search: async (query: string) => ({
      query,
      quotes_count: 1,
      quotes: [
        {
          symbol: 'MSFT',
          shortname: 'Microsoft Corporation',
          longname: 'Microsoft Corporation',
          exchange: 'NMS',
          type: 'EQUITY',
        },
      ],
      news_count: 0,
      news: [],
    }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: MarketData, useValue: marketDataStub }],
    }).compileComponents();
  });

  it('renders the dashboard and the selected ticker', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Your market');
    expect(compiled.querySelector('.summary-price')?.textContent).toContain('$253.00');
    expect(compiled.querySelector('.price-chart')?.getAttribute('aria-label')).toContain('AAPL');
  });

  it('searches for a ticker and updates the selected market', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const input = compiled.querySelector<HTMLInputElement>('#ticker-search');
    const form = compiled.querySelector<HTMLFormElement>('.search-form');
    expect(input).not.toBeNull();
    expect(form).not.toBeNull();

    input!.value = 'MSFT';
    input!.dispatchEvent(new Event('input', { bubbles: true }));
    form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.querySelector('.asset-row h2')?.textContent).toContain('MSFT');
  });
});
