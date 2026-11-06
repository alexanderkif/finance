import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MarketApi } from '../../services/market-data';
import { AnalysisResult, ParseResponse } from '../../models/market-data';
import { AnalysisChat } from './analysis-chat';

const missingStrike: ParseResponse = {
  position_type: 'single',
  legs: [
    {
      symbol: 'XSP',
      side: 'buy',
      option_type: 'call',
      strike: null,
      expiration: '2030-11-15',
    },
  ],
  missing_fields: ['strike'],
  detected_language: 'English',
};

const completePosition: ParseResponse = {
  position_type: 'single',
  legs: [
    {
      symbol: 'XSP',
      side: 'buy',
      option_type: 'call',
      strike: 600,
      expiration: '2030-11-15',
    },
  ],
  missing_fields: [],
  detected_language: 'English',
  header: 'Long Call XSP 600 2030-11-15',
};

const analysisStub: AnalysisResult = {
  strategy_key: 'long_call',
  intent: 'open',
  header: 'Long Call XSP 600 2030-11-15',
  recommendation: 'This long call has a defined maximum loss of the premium paid.',
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
  event_flags: ['earnings'],
  liquidity: {
    bid_ask_spread_pct: 2.5,
    open_interest: 800,
    volume: 400,
    rating: 'fair',
  },
  scenario_1sigma: {
    expected_move: 10,
    low: 590,
    high: 610,
    days_to_expiration: 30,
    atm_iv: 0.18,
  },
  scenario_2sigma: {
    expected_move: 20,
    low: 580,
    high: 620,
    days_to_expiration: 30,
    atm_iv: 0.18,
  },
  news: [],
  news_source: null,
  news_as_of: null,
  detected_language: 'English',
  disclaimer: 'Educational analysis, not investment advice.',
  source: 'cboe_delayed',
  as_of: '2030-10-28T15:48:15Z',
  degraded: true,
  warnings: [],
};

const quotaError = new HttpErrorResponse({
  status: 429,
  error: {
    detail: 'The free Gemini quota has been used up or rate limited. Wait about a minute.',
  },
});

function pendingUntilAborted(signal?: AbortSignal): Promise<ParseResponse> {
  return new Promise((_resolve, reject) => {
    signal?.addEventListener('abort', () => {
      reject(new DOMException('The request was cancelled.', 'AbortError'));
    });
  });
}

function pendingAnalysis(signal?: AbortSignal): Promise<AnalysisResult> {
  return new Promise((_resolve, reject) => {
    signal?.addEventListener('abort', () => {
      reject(new DOMException('The request was cancelled.', 'AbortError'));
    });
  });
}

describe('AnalysisChat', () => {
  async function setup(): Promise<{
    fixture: ComponentFixture<AnalysisChat>;
    compiled: HTMLElement;
    parse: ReturnType<typeof vi.fn>;
    streamAnalysis: ReturnType<typeof vi.fn>;
  }> {
    localStorage.clear();
    const parse = vi.fn(
      (_message: string, _symbol: string, signal?: AbortSignal, _context?: unknown) =>
        pendingUntilAborted(signal),
    );
    const streamAnalysis = vi.fn();
    const api = {
      parse,
      streamAnalysis,
      getExample: vi.fn(),
    };
    await TestBed.configureTestingModule({
      imports: [AnalysisChat],
      providers: [{ provide: MarketApi, useValue: api }],
    }).compileComponents();

    const fixture = TestBed.createComponent(AnalysisChat);
    fixture.componentRef.setInput('symbol', 'XSP');
    fixture.detectChanges();
    return {
      fixture,
      compiled: fixture.nativeElement as HTMLElement,
      parse,
      streamAnalysis,
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

  it('cancels the active request from the chat', async () => {
    const { fixture, compiled, parse } = await setup();
    typeMessage(compiled, 'buy call XSP 600');
    submit(fixture, compiled);

    expect(compiled.querySelector('.activity-timeline')?.textContent).toContain(
      'Interpreting your request',
    );

    button(compiled, 'Cancel')!.click();
    fixture.detectChanges();

    const signal = parse.mock.calls[0]?.[2] as AbortSignal;
    expect(signal.aborted).toBe(true);
    expect(compiled.querySelector('.activity-running')).toBeNull();
    expect(compiled.querySelector('.activity-timeline')?.textContent).toContain('Cancelled');
    expect(button(compiled, 'Cancel')).toBeUndefined();
  });

  it('cancels the previous request when a new message is sent', async () => {
    const { fixture, compiled, parse } = await setup();
    typeMessage(compiled, 'buy call XSP 600');
    submit(fixture, compiled);
    typeMessage(compiled, 'buy put XSP 500');
    submit(fixture, compiled);

    expect(parse).toHaveBeenCalledTimes(2);
    expect((parse.mock.calls[0]?.[2] as AbortSignal).aborted).toBe(true);
    expect((parse.mock.calls[1]?.[2] as AbortSignal).aborted).toBe(false);

    button(compiled, 'Cancel')!.click();
  });

  it('copies a previous user message back into the chat input', async () => {
    const { fixture, compiled } = await setup();
    typeMessage(compiled, 'buy call XSP 600');
    submit(fixture, compiled);

    const edit = compiled.querySelector<HTMLButtonElement>(
      'button[aria-label="Edit message in the chat input"]',
    );
    expect(edit).not.toBeNull();
    edit!.click();
    fixture.detectChanges();

    const textarea = compiled.querySelector<HTMLTextAreaElement>('.chat-form textarea');
    expect(textarea?.value).toBe('buy call XSP 600');

    button(compiled, 'Cancel')!.click();
  });

  it('sends on Enter and keeps Shift+Enter for a new line', async () => {
    const { fixture, compiled, parse } = await setup();
    typeMessage(compiled, 'buy call XSP 600');
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
    expect(parse).not.toHaveBeenCalled();

    textarea.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Enter',
        bubbles: true,
        cancelable: true,
      }),
    );
    fixture.detectChanges();

    expect(parse).toHaveBeenCalledTimes(1);
    expect(compiled.querySelector('.activity-timeline')).not.toBeNull();

    button(compiled, 'Cancel')!.click();
  });

  it('retries the analysis step without parsing or repeating the message', async () => {
    const { fixture, compiled, parse, streamAnalysis } = await setup();
    parse.mockResolvedValue(completePosition);
    streamAnalysis.mockRejectedValueOnce(quotaError).mockResolvedValue(analysisStub);

    typeMessage(compiled, 'buy call XSP 600 2030-11-15');
    submit(fixture, compiled);
    await settle(fixture);

    expect(parse).toHaveBeenCalledTimes(1);
    expect(streamAnalysis).toHaveBeenCalledTimes(1);
    expect(compiled.querySelectorAll('.message-user')).toHaveLength(1);
    expect(compiled.querySelector('.error')?.textContent).toContain('quota');

    button(compiled, 'Retry failed step')!.click();
    await settle(fixture);

    expect(parse).toHaveBeenCalledTimes(1);
    expect(streamAnalysis).toHaveBeenCalledTimes(2);
    expect(compiled.querySelectorAll('.message-user')).toHaveLength(1);
    expect(compiled.querySelector('.error')).toBeNull();
    const card = compiled.querySelector('.analysis-card');
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain('2σ');
    expect(card?.textContent).toContain('Playbook event sensitivity');
    expect(card?.textContent).toContain('open');
  });

  it('retries parsing when that step failed', async () => {
    const { fixture, compiled, parse, streamAnalysis } = await setup();
    parse.mockRejectedValueOnce(quotaError).mockResolvedValue(completePosition);
    streamAnalysis.mockResolvedValue(analysisStub);

    typeMessage(compiled, 'buy call XSP 600 2030-11-15');
    submit(fixture, compiled);
    await settle(fixture);

    expect(parse).toHaveBeenCalledTimes(1);
    expect(streamAnalysis).not.toHaveBeenCalled();

    button(compiled, 'Retry failed step')!.click();
    await settle(fixture);

    expect(parse).toHaveBeenCalledTimes(2);
    expect(parse.mock.calls[0]?.[0]).toBe(parse.mock.calls[1]?.[0]);
    expect(streamAnalysis).toHaveBeenCalledTimes(1);
    expect(compiled.querySelectorAll('.message-user')).toHaveLength(1);
  });

  it('shows the interpreted position before the analysis finishes', async () => {
    const { fixture, compiled, parse, streamAnalysis } = await setup();
    parse.mockResolvedValue(completePosition);
    streamAnalysis.mockImplementation((_request, _onEvent, signal) => pendingAnalysis(signal));

    typeMessage(compiled, 'buy call XSP 600 2030-11-15');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelector('.position-summary')?.textContent).toContain(
      'Long Call XSP 600 2030-11-15',
    );
    expect(compiled.querySelector('.position-legs')?.textContent).toContain('600');

    button(compiled, 'Cancel')!.click();
  });

  it('sends previous positions as context for a follow-up', async () => {
    const { fixture, compiled, parse, streamAnalysis } = await setup();
    parse.mockResolvedValue(completePosition);
    streamAnalysis.mockResolvedValue(analysisStub);

    typeMessage(compiled, 'buy call XSP 600 2030-11-15');
    submit(fixture, compiled);
    await settle(fixture);

    typeMessage(compiled, 'shift it two strikes up');
    submit(fixture, compiled);
    await settle(fixture);

    expect(parse).toHaveBeenCalledTimes(2);
    const context = parse.mock.calls[1]?.[3] as unknown[];
    expect(context).toHaveLength(1);
    expect(JSON.stringify(context[0])).toContain('600');
  });

  it('renders streamed stage updates in the activity timeline', async () => {
    const { fixture, compiled, parse, streamAnalysis } = await setup();
    parse.mockResolvedValue(completePosition);
    streamAnalysis.mockImplementation(
      async (_request: unknown, onEvent: (event: unknown) => void) => {
        onEvent({
          type: 'stage',
          id: 'chain',
          status: 'started',
          label: 'Loading the option chain',
        });
        onEvent({
          type: 'stage',
          id: 'chain',
          status: 'done',
          label: 'Loading the option chain',
          detail: '12 contracts',
        });
        return analysisStub;
      },
    );

    typeMessage(compiled, 'buy call XSP 600 2030-11-15');
    submit(fixture, compiled);
    await settle(fixture);

    const timeline = compiled.querySelector('.activity-timeline');
    expect(timeline?.textContent).toContain('Loading the option chain');
    expect(timeline?.textContent).toContain('12 contracts');
    expect(compiled.querySelector('.activity-running')).toBeNull();
  });

  it('renders recent headlines from the analysis stream', async () => {
    const { fixture, compiled, parse, streamAnalysis } = await setup();
    parse.mockResolvedValue(completePosition);
    streamAnalysis.mockImplementation(
      async (_request: unknown, onEvent: (event: unknown) => void) => {
        onEvent({
          type: 'news',
          news: [
            {
              title: 'SPY edges higher as breadth improves',
              url: 'https://example.com/spy-news',
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

    typeMessage(compiled, 'buy call XSP 600 2030-11-15');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelector('.news-context a')?.getAttribute('href')).toBe(
      'https://example.com/spy-news',
    );
    expect(compiled.querySelector('.news-context')?.textContent).toContain('not a calendar');
  });

  it('shows an unsupported parse refusal in the chat without a retry', async () => {
    const { fixture, compiled, parse } = await setup();
    parse.mockRejectedValue(
      new HttpErrorResponse({
        status: 422,
        error: {
          detail: 'I can only analyze one option or one two-leg vertical spread per message.',
        },
      }),
    );

    typeMessage(compiled, 'analyze SPY and QQQ');
    submit(fixture, compiled);
    await settle(fixture);

    expect(compiled.querySelector('.chat-log')?.textContent).toContain(
      'one two-leg vertical spread',
    );
    expect(button(compiled, 'Retry failed step')).toBeUndefined();
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
    const { fixture, compiled, parse } = await setup();
    parse.mockResolvedValue(missingStrike);
    const log = compiled.querySelector<HTMLElement>('.chat-log');
    expect(log).not.toBeNull();
    Object.defineProperty(log!, 'scrollHeight', { configurable: true, value: 1_000 });
    Object.defineProperty(log!, 'clientHeight', { configurable: true, value: 200 });

    log!.scrollTop = 0;
    log!.dispatchEvent(new Event('scroll'));
    fixture.detectChanges();

    typeMessage(compiled, 'buy call XSP 2030-11-15');
    submit(fixture, compiled);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(log!.scrollTop).toBe(0);

    log!.scrollTop = 800;
    log!.dispatchEvent(new Event('scroll'));
    fixture.detectChanges();

    expect(log!.scrollTop).toBe(1_000);

    typeMessage(compiled, 'the strike is 600');
    submit(fixture, compiled);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(log!.scrollTop).toBe(1_000);
  });

  it('scrolls to the latest message when Analyze is clicked', async () => {
    const { fixture, compiled, parse } = await setup();
    const log = compiled.querySelector<HTMLElement>('.chat-log');
    expect(log).not.toBeNull();
    Object.defineProperty(log!, 'scrollHeight', { configurable: true, value: 1_000 });
    Object.defineProperty(log!, 'clientHeight', { configurable: true, value: 200 });
    log!.scrollTop = 0;
    log!.dispatchEvent(new Event('scroll'));
    fixture.detectChanges();

    typeMessage(compiled, 'buy call XSP 600');
    fixture.detectChanges();
    button(compiled, 'Analyze')!.click();
    fixture.detectChanges();

    expect(parse).toHaveBeenCalledTimes(1);
    expect(log!.scrollTop).toBe(1_000);

    button(compiled, 'Cancel')!.click();
  });
});
