import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MarketApi } from '../../services/market-data';
import { Preferences } from '../../services/preferences';
import {
  AnalysisResult,
  ChatMarketSnapshot,
  ChatTurnRequest,
  ChatTurnResponse,
} from '../../models/market-data';
import { AnalysisChat } from './analysis-chat';

const snapshotStub: ChatMarketSnapshot = {
  symbol: 'AAPL',
  price: 245,
  change_pct: 1.2,
  vix: 18.5,
  support: [240],
  resistance: [250],
  candles: [],
  sma: [],
  rsi: { period: 14, points: [] },
  news: [],
  range: '6mo',
  chart_source: null,
  chart_as_of: null,
  as_of: '2026-11-08T15:00:00Z',
  quote_as_of: '2026-11-08T15:00:00Z',
  vix_as_of: '2026-11-08T15:00:00Z',
  news_as_of: null,
  sources: { quote: 'cboe_delayed', vix: 'cboe_delayed', news: null },
  degraded: false,
  warnings: [],
};

const longCallDraft = {
  position_type: 'single' as const,
  legs: [
    {
      symbol: 'AAPL',
      side: 'buy' as const,
      option_type: 'call' as const,
      strike: 245,
      expiration: '2026-12-18',
    },
  ],
  strategy_key: 'long_call',
  reference: null,
};

const spreadDraft = {
  position_type: 'strategy' as const,
  legs: [
    {
      symbol: 'AAPL',
      side: 'sell' as const,
      option_type: 'put' as const,
      strike: 240,
      expiration: '2026-12-18',
    },
    {
      symbol: 'AAPL',
      side: 'buy' as const,
      option_type: 'put' as const,
      strike: 230,
      expiration: '2026-12-18',
    },
  ],
  strategy_key: 'bull_put_spread',
  reference: null,
};

const confirmResponse: ChatTurnResponse = {
  mode: 'confirm',
  text: 'AAPL is near 245.00. I can use Long Call AAPL 245 2026-12-18. Use these, or tell me what to change.',
  language: 'English',
  intent: 'open',
  draft: longCallDraft,
  missing: [],
  suggestions: {
    fields: ['expiration', 'side', 'strike'],
    expiration: '2026-12-18',
    strike: 245,
    long_strike: null,
    width: null,
  },
  confirm: {
    summary: 'Long Call AAPL 245 2026-12-18',
    position: {
      position_type: 'single',
      legs: [
        {
          symbol: 'AAPL',
          side: 'buy',
          option_type: 'call',
          strike: 245,
          expiration: '2026-12-18',
        },
      ],
    },
  },
  switch: null,
  pending_draft: null,
  as_of: '2026-11-08T15:00:00Z',
  degraded: false,
  warnings: [],
};

const spreadConfirmResponse: ChatTurnResponse = {
  ...confirmResponse,
  text: 'AAPL is near 245.00. I can use Bull Put Spread AAPL 240/230 2026-12-18.',
  draft: spreadDraft,
  suggestions: {
    fields: ['expiration', 'long_strike', 'side', 'strike'],
    expiration: '2026-12-18',
    strike: 240,
    long_strike: 230,
    width: 2,
  },
  confirm: {
    summary: 'Bull Put Spread AAPL 240/230 2026-12-18',
    position: {
      position_type: 'strategy',
      legs: spreadDraft.legs,
    },
  },
};

const answerResponse: ChatTurnResponse = {
  mode: 'answer',
  text: 'AAPL is above SMA 20 and SMA 50, RSI is 58, and VIX 18.5 is calm.',
  language: 'English',
  intent: 'open',
  draft: null,
  missing: [],
  suggestions: null,
  confirm: null,
  switch: null,
  pending_draft: null,
  as_of: '2026-11-08T15:00:00Z',
  degraded: false,
  warnings: [],
};

const refusedResponse: ChatTurnResponse = {
  ...answerResponse,
  mode: 'refused',
  text: "I can help with this instrument's chart, market context, news, and option positions.",
};

const switchResponse: ChatTurnResponse = {
  ...answerResponse,
  mode: 'switch_symbol',
  text: 'You are asking about MSFT, while the chart shows AAPL. Switch to MSFT?',
  switch: {
    symbol: 'MSFT',
    explicit: false,
    reason: 'The user asked about another instrument.',
  },
};

const explicitSwitchResponse: ChatTurnResponse = {
  ...switchResponse,
  text: 'Switching to MSFT.',
  switch: {
    symbol: 'MSFT',
    explicit: true,
    reason: 'Explicit instrument command.',
  },
};

const analysisStub: AnalysisResult = {
  strategy_key: 'long_call',
  intent: 'open',
  header: 'Long Call AAPL 245 2026-12-18',
  recommendation: 'This long call has a defined maximum loss of the premium paid.',
  probability_positive: 0.4,
  max_profit: null,
  max_loss: 500,
  net_credit_debit: -500,
  breakeven: 250,
  theta_daily: -1,
  iv_rank: null,
  current_iv: 0.18,
  hv_20d: 0.16,
  hv_60d: 0.17,
  hv_rank: 0.55,
  iv_hv_ratio: 1.06,
  event_flags: ['earnings'],
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
  as_of: '2026-10-28T15:48:15Z',
  degraded: true,
  warnings: [],
};

const quotaError = new HttpErrorResponse({
  status: 429,
  error: {
    detail: 'The free Gemini quota has been used up or rate limited. Wait about a minute.',
  },
});

describe('AnalysisChat', () => {
  async function setup(): Promise<{
    fixture: ComponentFixture<AnalysisChat>;
    compiled: HTMLElement;
    chatTurn: ReturnType<typeof vi.fn>;
    streamAnalysis: ReturnType<typeof vi.fn>;
    preferences: Preferences;
  }> {
    localStorage.clear();
    const chatTurn = vi.fn(async (_request: ChatTurnRequest) => confirmResponse);
    const streamAnalysis = vi.fn(async () => analysisStub);
    const api = {
      chatTurn,
      streamAnalysis,
      getExample: vi.fn(),
    };
    await TestBed.configureTestingModule({
      imports: [AnalysisChat],
      providers: [{ provide: MarketApi, useValue: api }],
    }).compileComponents();

    const fixture = TestBed.createComponent(AnalysisChat);
    fixture.componentRef.setInput('symbol', 'AAPL');
    fixture.componentRef.setInput('snapshot', snapshotStub);
    fixture.detectChanges();
    return {
      fixture,
      compiled: fixture.nativeElement as HTMLElement,
      chatTurn,
      streamAnalysis,
      preferences: TestBed.inject(Preferences),
    };
  }

  function typeMessage(compiled: HTMLElement, text: string): void {
    const textarea = compiled.querySelector<HTMLTextAreaElement>('.chat-form textarea');
    expect(textarea).not.toBeNull();
    textarea!.value = text;
    textarea!.dispatchEvent(new Event('input'));
  }

  function submit(fixture: ComponentFixture<AnalysisChat>, compiled: HTMLElement): void {
    const form = compiled.querySelector<HTMLFormElement>('.chat-form');
    expect(form).not.toBeNull();
    form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
  }

  function button(compiled: HTMLElement, label: string): HTMLButtonElement | undefined {
    return Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (item) => item.textContent?.trim() === label,
    );
  }

  async function settle(fixture: ComponentFixture<AnalysisChat>): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();
  }

  it('greets the user and answers a market question', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    chatTurn.mockResolvedValue(answerResponse);

    expect(compiled.querySelector('.chat-header h2')?.textContent).toContain('Market chat');
    expect(compiled.querySelector('.chat-log')?.textContent).toContain('I can explain');

    typeMessage(compiled, 'what is the trend?');
    submit(fixture, compiled);
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(1);
    expect(compiled.querySelector('.chat-log')?.textContent).toContain('above SMA 20');
    expect(compiled.querySelector('.draft-card')).toBeNull();
  });

  it('renders a draft and runs the analysis from Analyze', async () => {
    const { fixture, compiled, chatTurn, streamAnalysis } = await setup();

    typeMessage(compiled, 'long call');
    submit(fixture, compiled);
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(1);
    const draftCard = compiled.querySelector('.draft-card');
    expect(draftCard?.textContent).toContain('Long Call AAPL 245 2026-12-18');
    expect(draftCard?.textContent).toContain('Suggested from the live chain');
    expect(draftCard?.textContent).toContain('not a recommendation');

    button(compiled, 'Analyze')!.click();
    await settle(fixture);

    expect(streamAnalysis).toHaveBeenCalledTimes(1);
    const request = streamAnalysis.mock.calls[0]?.[0] as {
      position: { legs: unknown[] };
    };
    expect(request.position.legs).toHaveLength(1);
    expect(compiled.querySelector('.analysis-card')).not.toBeNull();
    expect(compiled.querySelector('.draft-card')).toBeNull();
  });

  it('runs a plain yes without another chat turn', async () => {
    const { fixture, compiled, chatTurn, streamAnalysis } = await setup();

    typeMessage(compiled, 'long call');
    submit(fixture, compiled);
    await settle(fixture);

    typeMessage(compiled, 'yes');
    submit(fixture, compiled);
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(1);
    expect(streamAnalysis).toHaveBeenCalledTimes(1);
    expect(compiled.querySelectorAll('.message-user')).toHaveLength(2);
    expect(compiled.querySelector('.analysis-card')).not.toBeNull();
  });

  it('uses the detected language for the analysis request', async () => {
    const { fixture, compiled, chatTurn, streamAnalysis } = await setup();
    chatTurn.mockResolvedValue({ ...confirmResponse, language: 'Russian' });

    typeMessage(compiled, 'лонг колл');
    submit(fixture, compiled);
    await settle(fixture);

    button(compiled, 'Analyze')!.click();
    await settle(fixture);

    const request = streamAnalysis.mock.calls[0]?.[0] as {
      detected_language: string;
    };
    expect(request.detected_language).toBe('Russian');
  });

  it('localizes chat copy and analysis stages for a Russian response', async () => {
    const { fixture, compiled, chatTurn, streamAnalysis } = await setup();
    chatTurn.mockResolvedValue({
      ...confirmResponse,
      language: 'Russian',
      text: 'Могу использовать Long Call AAPL 245 2026-12-18.',
    });
    streamAnalysis.mockImplementation(
      async (_request: unknown, onEvent: (event: unknown) => void) => {
        onEvent({
          type: 'stage',
          id: 'history',
          status: 'done',
          label: '260 daily candles',
        });
        onEvent({
          type: 'news',
          news: [
            {
              title: 'AAPL edges higher',
              url: 'https://example.com/aapl',
              publisher: 'Newswire',
              published_at: null,
            },
          ],
          source: 'finnhub',
          as_of: null,
        });
        return analysisStub;
      },
    );

    typeMessage(compiled, 'лонг колл');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelector('.message-role')?.textContent).toContain('Ассистент');
    expect(compiled.querySelector('.message-user .message-role')?.textContent).toContain(
      'Вы',
    );
    expect(compiled.querySelector('.draft-card')?.textContent).toContain(
      'Готово к анализу',
    );
    expect(compiled.querySelector('.draft-card')?.textContent).toContain(
      'Предложено по живой цепочке',
    );

    button(compiled, 'Analyze')!.click();
    await settle(fixture);

    expect(compiled.querySelector('.activity-timeline')?.textContent).toContain(
      '260 дневных свечей',
    );
    expect(compiled.querySelector('.news-context')?.textContent).toContain(
      'Свежие заголовки',
    );
  });

  it('uses the inferred intent for the analysis request', async () => {
    const { fixture, compiled, chatTurn, streamAnalysis } = await setup();
    chatTurn.mockResolvedValue({ ...confirmResponse, intent: 'close' });

    typeMessage(compiled, 'close my long call');
    submit(fixture, compiled);
    await settle(fixture);

    button(compiled, 'Analyze')!.click();
    await settle(fixture);

    const request = streamAnalysis.mock.calls[0]?.[0] as { intent: string };
    expect(request.intent).toBe('close');
  });

  it('sends a wider-by-two edit through the chat turn', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    chatTurn.mockResolvedValue(spreadConfirmResponse);

    typeMessage(compiled, 'bull put spread');
    submit(fixture, compiled);
    await settle(fixture);

    button(compiled, 'Wider by 2')!.click();
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(2);
    const secondRequest = chatTurn.mock.calls[1]?.[0] as ChatTurnRequest;
    expect(secondRequest.message).toBe('wider by 2');
    expect(secondRequest.draft?.legs).toHaveLength(2);
  });

  it('clears the draft on a plain cancel without a chat turn', async () => {
    const { fixture, compiled, chatTurn } = await setup();

    typeMessage(compiled, 'long call');
    submit(fixture, compiled);
    await settle(fixture);

    typeMessage(compiled, 'cancel');
    submit(fixture, compiled);
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(1);
    expect(compiled.querySelector('.draft-card')).toBeNull();
    expect(compiled.querySelector('.chat-log')?.textContent).toContain('Draft cancelled');
  });

  it('switches immediately for an explicit command response', async () => {
    const { fixture, compiled, chatTurn, preferences } = await setup();
    chatTurn.mockResolvedValue(explicitSwitchResponse);

    typeMessage(compiled, 'show MSFT chart');
    submit(fixture, compiled);
    await settle(fixture);

    expect(preferences.symbol()).toBe('MSFT');
    expect(compiled.querySelector('.switch-card')).toBeNull();
  });

  it('asks before switching for an exploratory question', async () => {
    const { fixture, compiled, chatTurn, preferences } = await setup();
    chatTurn.mockResolvedValue(switchResponse);

    typeMessage(compiled, 'what about MSFT?');
    submit(fixture, compiled);
    await settle(fixture);

    expect(preferences.symbol()).toBe('AAPL');
    expect(compiled.querySelector('.switch-card')?.textContent).toContain('Switch to MSFT');

    button(compiled, 'Switch to MSFT')!.click();
    await settle(fixture);

    expect(preferences.symbol()).toBe('MSFT');
  });

  it('shows a refusal without offering a retry', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    chatTurn.mockResolvedValue(refusedResponse);

    typeMessage(compiled, 'write a poem');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelector('.chat-log')?.textContent).toContain(
      "I can help with this instrument's chart",
    );
    expect(button(compiled, 'Retry failed step')).toBeUndefined();
  });

  it('retries a failed chat turn without duplicating the user message', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    chatTurn.mockRejectedValueOnce(quotaError).mockResolvedValue(answerResponse);

    typeMessage(compiled, 'hello');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelectorAll('.message-user')).toHaveLength(1);
    expect(compiled.querySelector('.error')?.textContent).toContain('quota');

    button(compiled, 'Retry failed step')!.click();
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(2);
    expect(compiled.querySelectorAll('.message-user')).toHaveLength(1);
    expect(compiled.querySelector('.error')).toBeNull();
  });

  it('retries only the analysis after an analysis failure', async () => {
    const { fixture, compiled, chatTurn, streamAnalysis } = await setup();
    streamAnalysis.mockRejectedValueOnce(quotaError).mockResolvedValue(analysisStub);

    typeMessage(compiled, 'long call');
    submit(fixture, compiled);
    await settle(fixture);
    button(compiled, 'Analyze')!.click();
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(1);
    expect(streamAnalysis).toHaveBeenCalledTimes(1);
    expect(compiled.querySelector('.error')?.textContent).toContain('quota');

    button(compiled, 'Retry failed step')!.click();
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(1);
    expect(streamAnalysis).toHaveBeenCalledTimes(2);
    expect(compiled.querySelector('.analysis-card')).not.toBeNull();
    expect(compiled.querySelectorAll('.message-user')).toHaveLength(2);
  });

  it('copies a previous user message back into the chat input', async () => {
    const { fixture, compiled, chatTurn } = await setup();

    typeMessage(compiled, 'hello');
    submit(fixture, compiled);
    await settle(fixture);

    const edit = compiled.querySelector<HTMLButtonElement>(
      'button[aria-label="Edit message in the chat input"]',
    );
    expect(edit).not.toBeNull();
    edit!.click();
    fixture.detectChanges();

    const textarea = compiled.querySelector<HTMLTextAreaElement>('.chat-form textarea');
    expect(textarea?.value).toBe('hello');
    expect(chatTurn).toHaveBeenCalledTimes(1);
  });

  it('sends on Enter and keeps Shift+Enter for a new line', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    typeMessage(compiled, 'hello');
    const textarea = compiled.querySelector<HTMLTextAreaElement>('.chat-form textarea')!;

    textarea.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Enter',
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      }),
    );
    fixture.detectChanges();
    expect(chatTurn).not.toHaveBeenCalled();

    textarea.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Enter',
        bubbles: true,
        cancelable: true,
      }),
    );
    fixture.detectChanges();

    expect(chatTurn).toHaveBeenCalledTimes(1);
  });

  it('sizes the conversation to its content up to the saved maximum', async () => {
    const { compiled } = await setup();
    const frame = compiled.querySelector<HTMLElement>('.chat-log-frame');
    const log = compiled.querySelector<HTMLElement>('.chat-log');
    expect(frame?.style.height).toBe('');
    expect(log?.style.maxHeight).toBe('640px');
  });

  it('resizes the conversation with the keyboard and persists the height', async () => {
    const { fixture, compiled } = await setup();
    const resizer = compiled.querySelector<HTMLElement>('.chat-resizer');
    const log = compiled.querySelector<HTMLElement>('.chat-log');
    expect(resizer).not.toBeNull();
    expect(resizer!.getAttribute('aria-valuenow')).toBe('640');

    resizer!.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true }),
    );
    fixture.detectChanges();

    expect(resizer!.getAttribute('aria-valuenow')).toBe('664');
    expect(log?.style.maxHeight).toBe('664px');
    expect(localStorage.getItem('osa.chat.height')).toBe('664');

    resizer!.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    fixture.detectChanges();

    expect(resizer!.getAttribute('aria-valuenow')).toBe('640');
    expect(log?.style.maxHeight).toBe('640px');
    expect(localStorage.getItem('osa.chat.height')).toBe('640');
  });

  it('keeps the latest message in view unless the user scrolled away', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    chatTurn.mockResolvedValue(answerResponse);
    const log = compiled.querySelector<HTMLElement>('.chat-log');
    expect(log).not.toBeNull();
    Object.defineProperty(log!, 'scrollHeight', { configurable: true, value: 1_000 });
    Object.defineProperty(log!, 'clientHeight', { configurable: true, value: 200 });

    log!.scrollTop = 0;
    log!.dispatchEvent(new Event('scroll'));
    fixture.detectChanges();

    typeMessage(compiled, 'hello');
    submit(fixture, compiled);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(log!.scrollTop).toBe(0);

    log!.scrollTop = 800;
    log!.dispatchEvent(new Event('scroll'));
    fixture.detectChanges();

    expect(log!.scrollTop).toBe(1_000);
  });
});
