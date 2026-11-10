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

const analysisStub: AnalysisResult = {
  strategy_key: 'long_call',
  intent: 'open',
  header: 'Long Call AAPL 245 2026-12-18',
  recommendation: '',
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
  card: null,
  steps: [],
  as_of: '2026-11-08T15:00:00Z',
  degraded: false,
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
    preferences: Preferences;
  }> {
    localStorage.clear();
    const chatTurn = vi.fn(async (_request: ChatTurnRequest) => answerResponse);
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

    typeMessage(compiled, 'what is the trend?');
    submit(fixture, compiled);
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(1);
    expect(compiled.querySelectorAll('.message-user')).toHaveLength(1);
    expect(compiled.querySelector('.chat-log')?.textContent).toContain(
      'AAPL is above SMA 20',
    );
  });

  it('shows a thinking step before the chat response arrives', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    let resolveChat!: (value: ChatTurnResponse) => void;
    chatTurn.mockImplementation(
      () =>
        new Promise<ChatTurnResponse>((resolve) => {
          resolveChat = resolve;
        }),
    );

    typeMessage(compiled, 'what is the trend?');
    submit(fixture, compiled);
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();

    expect(compiled.querySelector('.chat-thinking')).toBeNull();
    expect(compiled.querySelector('.activity-running')?.textContent).toContain(
      'Thinking...',
    );
    expect(compiled.querySelector('.chat-log .activity-running')).not.toBeNull();

    resolveChat(answerResponse);
    await settle(fixture);

    expect(compiled.querySelector('.activity-running')).toBeNull();
  });

  it('renders model text with an analysis card and tool steps', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    chatTurn.mockResolvedValue({
      ...answerResponse,
      text: 'The long call has a defined maximum loss.',
      card: analysisStub,
      steps: [
        {
          id: 'metrics-0',
          label: 'Computing metrics',
          status: 'done',
          detail: 'Long Call AAPL 245 2026-12-18',
        },
      ],
    });

    typeMessage(compiled, 'buy the 245 call');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelector('.chat-log')?.textContent).toContain(
      'The long call has a defined maximum loss.',
    );
    expect(compiled.querySelector('.analysis-card')).not.toBeNull();
    expect(compiled.querySelector('.analysis-card')?.textContent).toContain(
      'Long Call AAPL 245 2026-12-18',
    );
    expect(compiled.querySelector('.activity-timeline')?.textContent).toContain(
      'Computing metrics',
    );
  });

  it('renders failed tool steps', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    chatTurn.mockResolvedValue({
      ...answerResponse,
      text: 'The quote is unavailable right now.',
      steps: [
        {
          id: 'quote-0',
          label: 'Loading quote',
          status: 'failed',
          detail: 'The quote provider is unavailable.',
        },
      ],
    });

    typeMessage(compiled, 'what is the price?');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelector('.activity-failed')?.textContent).toContain(
      'Loading quote',
    );
    expect(compiled.querySelector('.chat-log')?.textContent).toContain(
      'The quote is unavailable right now.',
    );
  });

  it('sends a confirmation to the model instead of handling it locally', async () => {
    const { fixture, compiled, chatTurn } = await setup();

    typeMessage(compiled, 'yes');
    submit(fixture, compiled);
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(1);
    const request = chatTurn.mock.calls[0]?.[0] as ChatTurnRequest;
    expect(request.message).toBe('yes');
  });

  it('applies UI actions from the chat response', async () => {
    const { fixture, compiled, chatTurn, preferences } = await setup();
    chatTurn.mockResolvedValue({
      ...answerResponse,
      text: 'Enabled both moving averages and switched the theme.',
      ui_actions: [
        { type: 'chart_toggle', key: 'sma20', value: true },
        { type: 'chart_toggle', key: 'sma50', value: true },
        { type: 'theme', value: 'dark' },
        { type: 'chart_range', value: '1y' },
      ],
    });

    typeMessage(compiled, 'turn on both moving averages');
    submit(fixture, compiled);
    await settle(fixture);

    expect(preferences.chartToggles().sma20).toBe(true);
    expect(preferences.chartToggles().sma50).toBe(true);
    expect(preferences.theme()).toBe('dark');
    expect(preferences.range()).toBe('1y');
    const request = chatTurn.mock.calls[0]?.[0] as ChatTurnRequest;
    expect(request.ui?.chart_toggles.levels).toBe(true);
    expect(request.ui?.range).toBe('6mo');
  });

  it('does not render a draft card for a normal answer', async () => {
    const { fixture, compiled } = await setup();

    typeMessage(compiled, 'what is the trend?');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelector('.draft-card')).toBeNull();
  });

  it('switches immediately for an explicit switch response', async () => {
    const { fixture, compiled, chatTurn, preferences } = await setup();
    chatTurn.mockResolvedValue({
      ...answerResponse,
      text: 'Switching to MSFT.',
      switch: { symbol: 'MSFT', explicit: true, reason: 'Explicit command.' },
    });

    typeMessage(compiled, 'switch to MSFT');
    submit(fixture, compiled);
    await settle(fixture);

    expect(preferences.symbol()).toBe('MSFT');
    expect(compiled.querySelector('.chat-log')?.textContent).toContain('Switching to MSFT.');
  });

  it('does not switch for an exploratory switch response', async () => {
    const { fixture, compiled, chatTurn, preferences } = await setup();
    chatTurn.mockResolvedValue({
      ...answerResponse,
      text: 'Do you want me to switch to MSFT?',
      switch: { symbol: 'MSFT', explicit: false, reason: 'Exploratory question.' },
    });

    typeMessage(compiled, 'what about MSFT?');
    submit(fixture, compiled);
    await settle(fixture);

    expect(preferences.symbol()).toBe('AAPL');
    expect(compiled.querySelector('.switch-card')).toBeNull();
  });

  it('shows a model refusal without offering a retry', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    chatTurn.mockResolvedValue({
      ...answerResponse,
      text: "I can help with this instrument's market and options, but not with that request.",
    });

    typeMessage(compiled, 'write a poem');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelector('.chat-log')?.textContent).toContain(
      "I can help with this instrument's market",
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

  it('copies a previous user message back into the chat input', async () => {
    const { fixture, compiled } = await setup();

    typeMessage(compiled, 'hello');
    submit(fixture, compiled);
    await settle(fixture);

    const edit = compiled.querySelector<HTMLButtonElement>('.message-edit');
    expect(edit).not.toBeNull();
    edit!.click();
    fixture.detectChanges();

    expect(compiled.querySelector<HTMLTextAreaElement>('.chat-form textarea')?.value).toBe(
      'hello',
    );
  });

  it('sends on Enter and keeps Shift+Enter for a new line', async () => {
    const { fixture, compiled, chatTurn } = await setup();
    const textarea = compiled.querySelector<HTMLTextAreaElement>('.chat-form textarea')!;

    textarea.value = 'first line';
    textarea.dispatchEvent(new Event('input'));
    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true }));
    fixture.detectChanges();
    expect(chatTurn).not.toHaveBeenCalled();

    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await settle(fixture);

    expect(chatTurn).toHaveBeenCalledTimes(1);
  });

  it('sizes the conversation to its content up to the saved maximum', async () => {
    const { fixture, compiled } = await setup();
    const log = compiled.querySelector<HTMLElement>('.chat-log');
    expect(log?.style.maxHeight).not.toBe('');
    expect(fixture.componentInstance).toBeDefined();
  });

  it('resizes the conversation with the keyboard and persists the height', async () => {
    const { fixture, compiled, preferences } = await setup();
    const grip = compiled.querySelector<HTMLElement>('.chat-resizer');
    expect(grip).not.toBeNull();

    const before = preferences.chatHeight();
    grip!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }));
    fixture.detectChanges();

    expect(preferences.chatHeight()).not.toBe(before);
  });

  it('keeps the latest message in view unless the user scrolled away', async () => {
    const { fixture, compiled } = await setup();
    const log = compiled.querySelector<HTMLElement>('.chat-log');
    expect(log).not.toBeNull();
    expect(fixture.componentInstance).toBeDefined();
  });
});
