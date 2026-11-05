import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  ElementRef,
  afterRenderEffect,
  computed,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { errorMessage, isRetryable } from '../../api-error';
import {
  AnalysisPosition,
  AnalysisResult,
  AnalysisStreamEvent,
  Intent,
  NewsHeadline,
  ParseResponse,
  ParsedLeg,
  PositionLeg,
  ReferenceEdit,
} from '../../models/market-data';
import { MarketApi, isAbortError, requestAbortedError } from '../../services/market-data';
import {
  DEFAULT_CHAT_HEIGHT_PX,
  MAX_CHAT_HEIGHT_PX,
  MIN_CHAT_HEIGHT_PX,
  Preferences,
  clampChatHeight,
} from '../../services/preferences';
import { warningLabel } from '../../warning-labels';
import { AnalysisCard } from '../analysis-card/analysis-card';

type ActivityState = 'running' | 'done' | 'failed';

interface ChatActivity {
  id: string;
  label: string;
  state: ActivityState;
  detail?: string;
}

interface PositionSummary {
  header: string;
  legs: ParsedLeg[];
  provisional: boolean;
}

interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  text?: string;
  analysis?: AnalysisResult;
  activities?: ChatActivity[];
  position?: PositionSummary;
  news?: NewsHeadline[];
}

type RunAction = {
  kind: 'run';
  turnId: number;
  parsed: ParseResponse;
  position: AnalysisPosition | null;
  context: AnalysisPosition[];
  reference: ReferenceEdit | null;
  intent: Intent;
};

type RetryAction =
  { kind: 'example' } | { kind: 'parse'; combined: string; turnId: number } | RunAction;

const RETRY_DELAYS_MS = [1_200, 3_000] as const;
const FIELD_PROMPTS: Record<string, string> = {
  side: 'whether each leg is a buy or sell',
  option_type: 'whether each leg is a call or a put',
  strike: 'the strike price',
  expiration: 'the expiration date',
  strategy_type: 'which two-leg spread you mean',
};

@Component({
  selector: 'app-analysis-chat',
  imports: [AnalysisCard],
  templateUrl: './analysis-chat.html',
  styleUrl: './analysis-chat.css',
})
export class AnalysisChat {
  private readonly api = inject(MarketApi);
  private readonly preferences = inject(Preferences);
  private readonly chatLog = viewChild<ElementRef<HTMLElement>>('chatLog');
  private readonly chatInput = viewChild<ElementRef<HTMLTextAreaElement>>('chatInput');
  private readonly scrollPinned = signal(true);
  private readonly contextStack: AnalysisPosition[] = [];
  private resizeStart: { y: number; height: number } | null = null;
  private activeRequest: AbortController | null = null;
  private exampleRequest: AbortController | null = null;
  private activeTurnId: number | null = null;
  private nextMessageId = 1;
  private retrySequence = 0;

  protected readonly chatHeight = this.preferences.chatHeight;
  protected readonly minChatHeight = MIN_CHAT_HEIGHT_PX;
  protected readonly maxChatHeight = MAX_CHAT_HEIGHT_PX;
  protected readonly resizing = signal(false);

  readonly symbol = input.required<string>();

  protected readonly messages = signal<ChatMessage[]>([
    {
      id: 0,
      role: 'assistant',
      text:
        'Describe a single option or a two-leg vertical spread. I will ask only ' +
        'for the fields that are missing.',
    },
  ]);
  protected readonly draft = signal('');
  protected readonly intent = signal<Intent>('open');
  protected readonly busy = signal(false);
  protected readonly exampleBusy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly pending = signal<{ text: string; missing: string[] } | null>(null);
  protected readonly retryable = signal<RetryAction | null>(null);
  protected readonly canSend = computed(() => this.draft().trim().length > 0);
  protected readonly errorMessage = errorMessage;
  protected readonly warningLabel = warningLabel;

  constructor() {
    afterRenderEffect({
      mixedReadWrite: () => {
        this.messages();
        this.busy();
        this.chatHeight();
        if (this.scrollPinned()) {
          this.scrollToLatest();
        }
      },
    });
  }

  protected updateDraft(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLTextAreaElement) {
      this.draft.set(target.value);
    }
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing) {
      return;
    }
    event.preventDefault();
    void this.send();
  }

  protected editMessage(text?: string): void {
    if (!text) {
      return;
    }
    this.draft.set(text);
    this.pending.set(null);
    this.error.set(null);
    this.retryable.set(null);
    this.chatInput()?.nativeElement.focus();
  }

  protected onScroll(event: Event): void {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const distanceFromBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    this.scrollPinned.set(distanceFromBottom <= 32);
  }

  protected startResize(event: PointerEvent): void {
    if (event.button !== 0) {
      return;
    }
    this.resizeStart = { y: event.clientY, height: this.chatHeight() };
    this.resizing.set(true);
    const target = event.currentTarget;
    if (target instanceof HTMLElement) {
      target.setPointerCapture(event.pointerId);
    }
  }

  protected resizeWithPointer(event: PointerEvent): void {
    const start = this.resizeStart;
    if (!start) {
      return;
    }
    event.preventDefault();
    this.chatHeight.set(clampChatHeight(start.height + event.clientY - start.y));
  }

  protected endResize(event: PointerEvent): void {
    if (!this.resizeStart) {
      return;
    }
    this.resizeStart = null;
    this.resizing.set(false);
    const target = event.currentTarget;
    if (target instanceof HTMLElement && target.hasPointerCapture(event.pointerId)) {
      target.releasePointerCapture(event.pointerId);
    }
    this.preferences.setChatHeight(this.chatHeight());
  }

  protected resizeWithKeyboard(event: KeyboardEvent): void {
    const step = event.shiftKey ? 80 : 24;
    let next: number;
    switch (event.key) {
      case 'ArrowUp':
        next = this.chatHeight() + step;
        break;
      case 'ArrowDown':
        next = this.chatHeight() - step;
        break;
      case 'Home':
        next = MIN_CHAT_HEIGHT_PX;
        break;
      case 'End':
        next = MAX_CHAT_HEIGHT_PX;
        break;
      default:
        return;
    }
    event.preventDefault();
    this.preferences.setChatHeight(clampChatHeight(next));
  }

  protected resetChatHeight(): void {
    this.preferences.setChatHeight(DEFAULT_CHAT_HEIGHT_PX);
  }

  protected setIntent(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLSelectElement) {
      const value = target.value;
      if (value === 'open' || value === 'close' || value === 'roll') {
        this.intent.set(value);
      }
    }
  }

  protected cancel(): void {
    this.cancelRunningActivities();
    this.activeRequest?.abort();
    this.exampleRequest?.abort();
    this.activeRequest = null;
    this.exampleRequest = null;
    this.activeTurnId = null;
    this.busy.set(false);
    this.exampleBusy.set(false);
    this.error.set(null);
    this.retryable.set(null);
  }

  protected async retry(): Promise<void> {
    const action = this.retryable();
    if (!action || this.busy() || this.exampleBusy()) {
      return;
    }
    if (action.kind === 'example') {
      this.retryable.set(null);
      await this.useExample();
      return;
    }

    const controller = this.startChatRequest();
    this.activeTurnId = action.turnId;
    this.busy.set(true);
    try {
      if (action.kind === 'parse') {
        await this.parseAndAnalyze(controller, action.combined, action.turnId);
      } else {
        this.resetActivities(action.turnId);
        await this.runAnalysisStage(controller, action);
      }
    } finally {
      this.finishChat(controller);
    }
  }

  protected async useExample(): Promise<void> {
    if (this.exampleBusy()) {
      return;
    }
    this.cancelRunningActivities();
    this.activeRequest?.abort();
    this.activeRequest = null;
    this.busy.set(false);
    const controller = new AbortController();
    this.exampleRequest?.abort();
    this.exampleRequest = controller;
    this.exampleBusy.set(true);
    this.error.set(null);
    this.retryable.set(null);
    try {
      const example = await this.withRetry(
        (signal) => this.api.getExample(this.symbol(), signal),
        controller.signal,
        'The market-data service',
      );
      if (controller.signal.aborted) {
        return;
      }
      this.draft.set(example.message);
      await this.send();
    } catch (error) {
      if (!controller.signal.aborted && !isAbortError(error)) {
        this.error.set(this.errorMessage(error));
        this.retryable.set(this.canRetryAfter(error) ? { kind: 'example' } : null);
      }
    } finally {
      if (this.exampleRequest === controller) {
        this.exampleRequest = null;
        this.exampleBusy.set(false);
      }
    }
  }

  protected async send(event?: Event): Promise<void> {
    event?.preventDefault();
    const text = this.draft().trim();
    if (!text) {
      return;
    }
    const combined = this.pending() ? `${this.pending()!.text} ${text}` : text;
    const turnId = this.nextMessageId++;
    const controller = this.startChatRequest();
    this.activeTurnId = turnId;
    this.draft.set('');
    this.messages.update((messages) => [
      ...messages,
      { id: turnId, role: 'user', text, activities: [] },
    ]);
    this.busy.set(true);
    try {
      await this.parseAndAnalyze(controller, combined, turnId);
    } finally {
      this.finishChat(controller);
    }
  }

  private startChatRequest(): AbortController {
    const controller = new AbortController();
    this.cancelRunningActivities();
    this.activeRequest?.abort();
    this.exampleRequest?.abort();
    this.activeRequest = controller;
    this.error.set(null);
    this.retryable.set(null);
    return controller;
  }

  private finishChat(controller: AbortController): void {
    if (this.activeRequest === controller) {
      this.activeRequest = null;
      this.activeTurnId = null;
      this.busy.set(false);
    }
  }

  private async parseAndAnalyze(
    controller: AbortController,
    combined: string,
    turnId: number,
  ): Promise<void> {
    this.upsertActivity(turnId, 'parse', 'Interpreting your request', 'running');
    let parsed: ParseResponse;
    try {
      parsed = await this.withRetry(
        (signal) => this.api.parse(combined, this.symbol(), signal, [...this.contextStack]),
        controller.signal,
        'The analysis service',
        (message) => this.addRetryActivity(turnId, message),
      );
    } catch (error) {
      this.markRunningActivitiesFailed(turnId);
      this.handleChatFailure(controller, error, { kind: 'parse', combined, turnId });
      return;
    }
    if (controller.signal.aborted) {
      return;
    }
    this.upsertActivity(
      turnId,
      'parse',
      'Interpreting your request',
      'done',
      parsed.header ?? undefined,
    );
    this.updateTurn(turnId, (message) => ({
      ...message,
      position: this.positionSummary(parsed),
    }));
    if (parsed.missing_fields.length > 0) {
      this.pending.set({ text: combined, missing: parsed.missing_fields });
      this.messages.update((messages) => [
        ...messages,
        {
          id: this.nextMessageId++,
          role: 'assistant',
          text: this.missingFieldsPrompt(parsed.missing_fields),
        },
      ]);
      return;
    }
    this.pending.set(null);
    const position = this.toPosition(parsed);
    const reference = parsed.reference ?? null;
    if (!position && !reference) {
      this.messages.update((messages) => [
        ...messages,
        {
          id: this.nextMessageId++,
          role: 'assistant',
          text:
            'I could not build a complete position from that message. ' +
            'Please include the side, call or put, strike, and expiration.',
        },
      ]);
      return;
    }
    const context = [...this.contextStack];
    if (reference && context.length === 0) {
      this.messages.update((messages) => [
        ...messages,
        {
          id: this.nextMessageId++,
          role: 'assistant',
          text:
            'I need the previous position before I can apply that change. ' +
            'Please describe the full position.',
        },
      ]);
      return;
    }
    if (!reference && position) {
      this.addContext(position);
    }
    await this.runAnalysisStage(controller, {
      kind: 'run',
      turnId,
      parsed,
      position,
      context,
      reference,
      intent: this.intent(),
    });
  }

  private async runAnalysisStage(controller: AbortController, action: RunAction): Promise<void> {
    this.upsertActivity(action.turnId, 'request', 'Contacting the analysis service', 'running');
    try {
      const result = await this.withRetry(
        (signal) =>
          this.api.streamAnalysis(
            {
              position: action.reference ? null : action.position,
              context: action.context,
              reference: action.reference,
              intent: action.intent,
              detected_language: action.parsed.detected_language,
            },
            (event) => this.handleStreamEvent(action.turnId, event),
            signal,
          ),
        controller.signal,
        'The analysis service',
        (message) => this.addRetryActivity(action.turnId, message),
      );
      if (controller.signal.aborted) {
        return;
      }
      this.completeRunningActivities(action.turnId);
      this.retryable.set(null);
      this.messages.update((messages) => [
        ...messages,
        { id: this.nextMessageId++, role: 'assistant', analysis: result },
      ]);
    } catch (error) {
      this.markRunningActivitiesFailed(action.turnId);
      this.handleChatFailure(controller, error, action);
    }
  }

  private handleStreamEvent(turnId: number, event: AnalysisStreamEvent): void {
    if (turnId !== this.activeTurnId) {
      return;
    }
    switch (event.type) {
      case 'stage':
        this.upsertActivity(
          turnId,
          event.id,
          event.label,
          event.status === 'started' ? 'running' : event.status === 'done' ? 'done' : 'failed',
          event.detail,
        );
        break;
      case 'position':
        this.addContext(event.position);
        this.updateTurn(turnId, (message) => ({
          ...message,
          position: {
            header: event.header,
            legs: event.position.legs,
            provisional: false,
          },
        }));
        break;
      case 'news':
        this.updateTurn(turnId, (message) => ({ ...message, news: event.news }));
        break;
      case 'warning':
        this.upsertActivity(turnId, `warning-${event.code}`, this.warningLabel(event.code), 'done');
        break;
      case 'error':
        this.upsertActivity(turnId, 'stream-error', 'Analysis failed', 'failed', event.detail);
        break;
      case 'heartbeat':
      case 'result':
        break;
    }
  }

  private handleChatFailure(
    controller: AbortController,
    error: unknown,
    action: RetryAction,
  ): void {
    if (controller.signal.aborted || isAbortError(error)) {
      return;
    }
    if (error instanceof HttpErrorResponse && error.status === 422) {
      if (action.kind === 'run') {
        this.messages.update((messages) => [
          ...messages,
          {
            id: this.nextMessageId++,
            role: 'assistant',
            text:
              'I need a complete, listed position before I can analyse it. ' +
              'Please check the side, strike, and expiration, then send the ' +
              'corrected description.',
          },
        ]);
      } else if (action.kind === 'parse') {
        this.messages.update((messages) => [
          ...messages,
          {
            id: this.nextMessageId++,
            role: 'assistant',
            text: this.errorMessage(error),
          },
        ]);
      }
    }
    this.error.set(this.errorMessage(error));
    this.retryable.set(this.canRetryAfter(error) ? action : null);
  }

  private canRetryAfter(error: unknown): boolean {
    if (error instanceof HttpErrorResponse) {
      return error.status !== 404 && error.status !== 422;
    }
    return true;
  }

  private missingFieldsPrompt(missing: string[]): string {
    const requested = missing.map((field) => FIELD_PROMPTS[field] ?? field);
    return `I still need ${this.joinWithAnd(requested)} before I can run the analysis.`;
  }

  private joinWithAnd(items: string[]): string {
    if (items.length <= 1) {
      return items[0] ?? 'one more detail';
    }
    return `${items.slice(0, -1).join(', ')}, and ${items.at(-1)}`;
  }

  private async withRetry<T>(
    request: (signal: AbortSignal) => Promise<T>,
    signal: AbortSignal,
    label: string,
    onRetry?: (message: string) => void,
  ): Promise<T> {
    for (let attempt = 0; ; attempt += 1) {
      try {
        return await request(signal);
      } catch (error) {
        if (signal.aborted || !isRetryable(error) || attempt >= RETRY_DELAYS_MS.length) {
          throw error;
        }
        const delay = RETRY_DELAYS_MS[attempt];
        const message =
          `${label} is unavailable. Retrying in ${this.formatSeconds(delay)} ` +
          `(attempt ${attempt + 2} of ${RETRY_DELAYS_MS.length + 1})…`;
        onRetry?.(message);
        await this.wait(delay, signal);
      }
    }
  }

  private wait(milliseconds: number, signal: AbortSignal): Promise<void> {
    if (signal.aborted) {
      return Promise.reject(requestAbortedError());
    }
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        signal.removeEventListener('abort', onAbort);
        resolve();
      }, milliseconds);
      const onAbort = (): void => {
        clearTimeout(timer);
        reject(requestAbortedError());
      };
      signal.addEventListener('abort', onAbort, { once: true });
    });
  }

  private formatSeconds(milliseconds: number): string {
    const seconds = milliseconds / 1_000;
    return seconds === 1 ? '1 second' : `${seconds} seconds`;
  }

  private scrollToLatest(): void {
    const element = this.chatLog()?.nativeElement;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }

  private toPosition(parsed: ParseResponse): AnalysisPosition | null {
    const legs: PositionLeg[] = [];
    for (const leg of parsed.legs) {
      if (!leg.symbol || !leg.side || !leg.option_type || leg.strike === null || !leg.expiration) {
        return null;
      }
      legs.push({
        symbol: leg.symbol,
        side: leg.side,
        option_type: leg.option_type,
        strike: leg.strike,
        expiration: leg.expiration,
      });
    }
    return { position_type: parsed.position_type, legs };
  }

  private addContext(position: AnalysisPosition): void {
    const key = JSON.stringify(position.legs);
    if (this.contextStack.some((item) => JSON.stringify(item.legs) === key)) {
      return;
    }
    this.contextStack.push(position);
    if (this.contextStack.length > 3) {
      this.contextStack.shift();
    }
  }

  private positionSummary(parsed: ParseResponse): PositionSummary {
    if (parsed.reference) {
      return {
        header: this.referenceLabel(parsed.reference),
        legs: parsed.legs,
        provisional: true,
      };
    }
    return {
      header: parsed.header ?? this.fallbackHeader(parsed),
      legs: parsed.legs,
      provisional: false,
    };
  }

  private fallbackHeader(parsed: ParseResponse): string {
    if (parsed.strategy_key) {
      return parsed.strategy_key
        .split('_')
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
    }
    return parsed.position_type === 'single' ? 'Single option' : 'Two-leg position';
  }

  private referenceLabel(reference: ReferenceEdit): string {
    const count = reference.strikes ?? 0;
    const strikes = `${count} strike${count === 1 ? '' : 's'}`;
    switch (reference.kind) {
      case 'same':
        return 'Same position as the previous request';
      case 'shift':
        return `Same position, shifted ${strikes} ${reference.direction ?? 'up'}`;
      case 'widen':
        return `Same position, widened by ${strikes}`;
      case 'narrow':
        return `Same position, narrowed by ${strikes}`;
      case 'expiration':
        return `Same position, expiring ${reference.expiration ?? 'later'}`;
      default:
        return 'Same position as the previous request';
    }
  }

  private updateTurn(turnId: number, update: (message: ChatMessage) => ChatMessage): void {
    this.messages.update((messages) =>
      messages.map((message) => (message.id === turnId ? update(message) : message)),
    );
  }

  private upsertActivity(
    turnId: number,
    id: string,
    label: string,
    state: ActivityState,
    detail?: string,
  ): void {
    this.updateTurn(turnId, (message) => {
      const activities = [...(message.activities ?? [])];
      const index = activities.findIndex((activity) => activity.id === id);
      const activity: ChatActivity = { id, label, state, detail };
      if (index >= 0) {
        activities[index] = activity;
      } else {
        activities.push(activity);
      }
      return { ...message, activities };
    });
  }

  private addRetryActivity(turnId: number, label: string): void {
    this.retrySequence += 1;
    this.upsertActivity(turnId, `retry-${this.retrySequence}`, label, 'running');
  }

  private completeRunningActivities(turnId: number): void {
    this.updateTurn(turnId, (message) => ({
      ...message,
      activities: message.activities?.map((activity) =>
        activity.state === 'running' ? { ...activity, state: 'done' } : activity,
      ),
    }));
  }

  private markRunningActivitiesFailed(turnId: number): void {
    this.updateTurn(turnId, (message) => ({
      ...message,
      activities: message.activities?.map((activity) =>
        activity.state === 'running'
          ? { ...activity, state: 'failed', detail: activity.detail ?? 'Failed' }
          : activity,
      ),
    }));
  }

  private cancelRunningActivities(): void {
    this.messages.update((messages) =>
      messages.map((message) => {
        if (!message.activities?.some((activity) => activity.state === 'running')) {
          return message;
        }
        return {
          ...message,
          activities: message.activities.map((activity) =>
            activity.state === 'running'
              ? { ...activity, state: 'failed', detail: 'Cancelled' }
              : activity,
          ),
        };
      }),
    );
  }

  private resetActivities(turnId: number): void {
    this.updateTurn(turnId, (message) => ({
      ...message,
      activities: [],
      news: undefined,
    }));
  }
}
