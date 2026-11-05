import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AnalysisStreamEvent } from '../models/market-data';
import { MarketApi } from './market-data';

const result = {
  strategy_key: 'long_call',
  intent: 'open',
  header: 'Long Call XSP 600 2030-11-15',
  recommendation: 'This long call has a defined maximum loss.',
  probability_positive: 0.4,
  max_profit: null,
  max_loss: 500,
  net_credit_debit: -500,
  breakeven: 605,
  theta_daily: -1,
  iv_rank: null,
  current_iv: 0.18,
  hv_20d: 0.16,
  hv_60d: 0.17,
  hv_rank: 0.55,
  iv_hv_ratio: 1.06,
  event_flags: [],
  liquidity: {
    bid_ask_spread_pct: 2.5,
    open_interest: 800,
    volume: 400,
    rating: 'fair',
  },
  scenario_1sigma: null,
  scenario_2sigma: null,
  news: [],
  news_source: null,
  news_as_of: null,
  detected_language: 'English',
  disclaimer: 'Educational analysis, not investment advice.',
  source: 'cboe_delayed',
  as_of: '2030-10-28T15:48:15Z',
  degraded: false,
  warnings: [],
};

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

describe('MarketApi.streamAnalysis', () => {
  let api: MarketApi;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(MarketApi);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('parses NDJSON across chunk boundaries and returns the result', async () => {
    const first = JSON.stringify({
      type: 'stage',
      id: 'chain',
      status: 'started',
      label: 'Loading the option chain',
    });
    const second = JSON.stringify({ type: 'result', result });
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(streamOf(`${first}\n${second.slice(0, 12)}`, `${second.slice(12)}\n`), {
            status: 200,
          }),
      ),
    );
    const events: AnalysisStreamEvent[] = [];

    const analysis = await api.streamAnalysis(
      { intent: 'open', detected_language: 'English' },
      (event) => events.push(event),
    );

    expect(analysis.header).toBe('Long Call XSP 600 2030-11-15');
    expect(events.map((event) => event.type)).toEqual(['stage', 'result']);
  });

  it('maps a network failure to a retryable HTTP-shaped error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );

    await expect(
      api.streamAnalysis({ intent: 'open', detected_language: 'English' }, () => undefined),
    ).rejects.toMatchObject({
      status: 0,
      error: {
        detail: 'The analysis service could not be reached. Check the connection and try again.',
      },
    });
  });

  it('throws an HTTP-shaped error for an error event', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            streamOf(
              `${JSON.stringify({
                type: 'error',
                status: 429,
                detail: 'The free Gemini quota has been used up.',
              })}\n`,
            ),
            { status: 200 },
          ),
      ),
    );

    await expect(
      api.streamAnalysis({ intent: 'open', detected_language: 'English' }, () => undefined),
    ).rejects.toMatchObject({
      status: 429,
      error: { detail: 'The free Gemini quota has been used up.' },
    });
  });
});
