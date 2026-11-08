import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  ElementRef,
  afterRenderEffect,
  computed,
  effect,
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
  ChatConfirm,
  ChatDraft,
  ChatDraftSuggestions,
  ChatHistoryTurn,
  ChatMarketSnapshot,
  ChatSwitch,
  ChatTurnResponse,
  Intent,
  NewsHeadline,
  PositionLeg,
} from '../../models/market-data';
import { MarketApi, isAbortError, requestAbortedError } from '../../services/market-data';
import {
  DEFAULT_CHAT_HEIGHT_PX,
  MAX_CHAT_HEIGHT_PX,
  MIN_CHAT_HEIGHT_PX,
  Preferences,
  clampChatHeight,
} from '../../services/preferences';
import { formatPrice } from '../../price-format';
import { warningLabel } from '../../warning-labels';
import { AnalysisCard } from '../analysis-card/analysis-card';
import {
  ChatCopy,
  ENGLISH_COPY,
  ENGLISH_GREETING,
  RUSSIAN_GREETING,
  RUSSIAN_COPY,
  RUSSIAN_FIELD_LABELS,
  RUSSIAN_STAGE_LABELS,
  RUSSIAN_STAGE_PATTERNS,
  RUSSIAN_SUGGESTION_FIELDS,
  RUSSIAN_WARNINGS,
} from './chat-copy';

type ActivityState = 'running' | 'done' | 'failed';
type ChatMode = 'explore' | 'draft' | 'confirm' | 'switch';

interface ChatActivity {
  id: string;
  label: string;
  state: ActivityState;
  detail?: string;
}

interface PositionSummary {
  header: string;
  legs: PositionLeg[];
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

type RetryAction =
  | { kind: 'example' }
  | { kind: 'chat'; text: string; continuation: boolean }
  | { kind: 'analysis'; position: AnalysisPosition; turnId: number };

const RETRY_DELAYS_MS = [1_200, 3_000] as const;
const YES_PATTERN =
  /^(?:yes|y|yeah|yep|ok|okay|sure|go\s+ahead|use\s+these|use\s+it|do\s+it|analy[sz]e|да|ок|хорошо|верно|давай|подходит)[.!]?$/i;
const CANCEL_PATTERN =
  /^(?:cancel|start\s+over|reset|never\s*mind|not\s+now|forget\s+it|drop\s+it|отмена|начать\s+заново|сброс|не\s+сейчас|забудь)[.!]?$/i;
const INITIAL_MESSAGE =
  "Hi — I can explain the selected instrument's trend, candlestick patterns, " +
  'key levels, VIX context, and recent headlines, or help you build an option ' +
  'card. What would you like to look at?';
const STRATEGY_LABELS: Record<string, string> = {
  bull_put_spread: 'Bull Put Spread',
  bear_call_spread: 'Bear Call Spread',
  bull_call_spread: 'Bull Call Spread',
  bear_put_spread: 'Bear Put Spread',
  long_call: 'Long Call',
  long_put: 'Long Put',
  short_call: 'Short Call',
  short_put: 'Short Put',
};
const FIELD_LABELS: Record<string, string> = {
  side: 'whether the option is a buy or a sell',
  option_type: 'whether it is a call or a put',
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
  private history: ChatHistoryTurn[] = [];
  private resizeStart: { y: number; height: number } | null = null;
  private activeRequest: AbortController | null = null;
  private exampleRequest: AbortController | null = null;
  private activeTurnId: number | null = null;
  private nextMessageId = 1;
  private retrySequence = 0;
  private continuationInFlight = false;
  private previousSymbol: string | null = null;
  private readonly detectedLanguage = signal('English');
  private analysisIntent: Intent = 'open';

  readonly symbol = input.required<string>();
  readonly snapshot = input<ChatMarketSnapshot | null>(null);

  protected readonly chatHeight = this.preferences.chatHeight;
  protected readonly minChatHeight = MIN_CHAT_HEIGHT_PX;
  protected readonly maxChatHeight = MAX_CHAT_HEIGHT_PX;
  protected readonly resizing = signal(false);
  protected readonly formatPrice = formatPrice;

  protected readonly messages = signal<ChatMessage[]>([
    { id: 0, role: 'assistant', text: ENGLISH_GREETING },
  ]);
  protected readonly draftText = signal('');
  protected readonly busy = signal(false);
  protected readonly exampleBusy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly retryable = signal<RetryAction | null>(null);
  protected readonly mode = signal<ChatMode>('explore');
  protected readonly draft = signal<ChatDraft | null>(null);
  protected readonly suggestions = signal<ChatDraftSuggestions | null>(null);
  protected readonly missing = signal<string[]>([]);
  protected readonly draftWarnings = signal<string[]>([]);
  protected readonly confirm = signal<ChatConfirm | null>(null);
  protected readonly switchProposal = signal<ChatSwitch | null>(null);
  protected readonly pendingDraftAfterSwitch = signal<ChatDraft | null>(null);
  protected readonly isRussian = computed(() =>
    this.detectedLanguage().toLowerCase().startsWith('russ'),
  );
  protected readonly copy = computed<ChatCopy>(() =>
    this.isRussian() ? RUSSIAN_COPY : ENGLISH_COPY,
  );
  protected readonly canSend = computed(() => this.draftText().trim().length > 0);
  protected readonly isSpread = computed(() => (this.draft()?.legs.length ?? 0) === 2);
  protected readonly canNarrow = computed(() => {
    if (!this.isSpread()) {
      return false;
    }
    const width = this.suggestions()?.width;
    return width === null || width === undefined || width > 1;
  });
  protected readonly hasSuggestions = computed(() => (this.suggestions()?.fields.length ?? 0) > 0);
  protected readonly draftTitle = computed(() => {
    const active = this.draft();
    if (!active) {
      return 'Option draft';
    }
    if (active.strategy_key && STRATEGY_LABELS[active.strategy_key]) {
      return STRATEGY_LABELS[active.strategy_key];
    }
    return active.legs.length === 1
      ? this.copy().singleOption
      : this.copy().twoLegSpread;
  });
  protected readonly suggestedLabel = computed(() => {
    const fields = this.suggestions()?.fields ?? [];
    const localized = this.isRussian() ? RUSSIAN_SUGGESTION_FIELDS : null;
    return fields
      .map(
        (field) =>
          localized?.[field] ??
          (field === 'long_strike'
            ? 'long strike'
            : field === 'option_type'
              ? 'option type'
              : field),
      )
      .join(', ');
  });
  protected readonly missingLabel = computed(() => {
    const missing = this.missing();
    if (missing.length === 0) {
      return '';
    }
    const labels = this.isRussian() ? RUSSIAN_FIELD_LABELS : FIELD_LABELS;
    return missing.map((field) => labels[field] ?? field).join(', ');
  });
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

    effect(() => {
      const pending = this.pendingDraftAfterSwitch();
      const snapshot = this.snapshot();
      if (!pending || !snapshot || this.continuationInFlight || this.busy()) {
        return;
      }
      const symbol = pending.legs[0]?.symbol;
      if (!symbol || snapshot.symbol !== symbol) {
        return;
      }
      this.continuationInFlight = true;
      this.pendingDraftAfterSwitch.set(null);
      this.draft.set(pending);
      this.mode.set('draft');
      void this.sendTurn('continue', { continuation: true, recordUser: false }).finally(() => {
        this.continuationInFlight = false;
      });
    });

    effect(() => {
      const symbol = this.symbol();
      if (this.previousSymbol !== null && this.previousSymbol !== symbol) {
        this.history = [];
        this.cancelRunningActivities();
        this.activeRequest?.abort();
        this.activeRequest = null;
        this.busy.set(false);
        this.error.set(null);
        this.retryable.set(null);
        this.switchProposal.set(null);
        if (!this.pendingDraftAfterSwitch()) {
          this.draft.set(null);
          this.suggestions.set(null);
          this.missing.set([]);
          this.draftWarnings.set([]);
          this.confirm.set(null);
          this.mode.set('explore');
        }
        this.addAssistantMessage(this.copy().nowWatching(symbol));
      }
      this.previousSymbol = symbol;
    });
  }

  protected updateDraft(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLTextAreaElement) {
      this.draftText.set(target.value);
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
    this.draftText.set(text);
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

  protected scrollToLatestOnAnalyze(): void {
    this.scrollPinned.set(true);
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
    if (action.kind === 'chat') {
      this.retryable.set(null);
      await this.sendTurn(action.text, {
        continuation: action.continuation,
        recordUser: false,
      });
      return;
    }
    this.retryable.set(null);
    await this.runAnalysis(action.position, action.turnId);
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
      this.draft.set(null);
      this.suggestions.set(null);
      this.missing.set([]);
      this.draftWarnings.set([]);
      this.confirm.set(null);
      this.switchProposal.set(null);
      this.pendingDraftAfterSwitch.set(null);
      this.mode.set('explore');
      this.draftText.set(example.message);
      await this.send();
    } catch (error) {
      if (!controller.signal.aborted && !isAbortError(error)) {
        this.error.set(this.errorMessage(error, this.detectedLanguage()));
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
    const text = this.draftText().trim();
    if (this.mode() === 'confirm' && this.confirm() && this.isYes(text)) {
      const turnId = this.addUserMessage('Yes');
      this.pushHistory({ role: 'user', text: 'Yes' });
      this.draftText.set('');
      await this.runConfirmed(turnId);
      return;
    }
    if (!text) {
      return;
    }
    if (this.isCancel(text) && this.mode() !== 'explore') {
      this.addUserMessage(text);
      this.pushHistory({ role: 'user', text });
      this.draftText.set('');
      this.clearDraftWithMessage();
      return;
    }
    this.draftText.set('');
    await this.sendTurn(text);
  }

  protected acceptDraft(): void {
    if (this.confirm()) {
      void this.runConfirmed();
      return;
    }
    void this.sendTurn('use these values');
  }

  protected widenDraft(): void {
    void this.sendTurn('wider by 2');
  }

  protected narrowDraft(): void {
    void this.sendTurn('narrow by 1');
  }

  protected changeDraft(): void {
    this.chatInput()?.nativeElement.focus();
  }

  protected startOver(): void {
    if (this.busy()) {
      return;
    }
    this.clearDraftWithMessage();
  }

  protected switchNow(): void {
    const proposal = this.switchProposal();
    if (proposal) {
      this.performSwitch(proposal.symbol);
    }
  }

  protected stayOnSymbol(): void {
    const proposal = this.switchProposal();
    this.switchProposal.set(null);
    this.pendingDraftAfterSwitch.set(null);
    this.mode.set('explore');
    if (proposal) {
      this.addAssistantMessage(this.copy().staying(this.symbol()));
    }
  }

  protected legText(leg: PositionLeg | ChatDraft['legs'][number]): string {
    const strike = leg.strike === null ? '—' : this.formatPrice(leg.strike);
    return `${leg.side ?? '—'} ${leg.option_type ?? '—'} ${strike} ${leg.expiration ?? '—'}`;
  }

  private isYes(text: string): boolean {
    return YES_PATTERN.test(text);
  }

  private isCancel(text: string): boolean {
    return CANCEL_PATTERN.test(text);
  }

  private clearDraftWithMessage(): void {
    this.draft.set(null);
    this.suggestions.set(null);
    this.missing.set([]);
    this.draftWarnings.set([]);
    this.confirm.set(null);
    this.switchProposal.set(null);
    this.pendingDraftAfterSwitch.set(null);
    this.mode.set('explore');
    this.addAssistantMessage(this.copy().draftCancelled(this.symbol()));
  }

  private async sendTurn(
    text: string,
    options: { continuation?: boolean; recordUser?: boolean } = {},
  ): Promise<void> {
    const continuation = options.continuation ?? false;
    const recordUser = options.recordUser ?? true;
    const turnId = recordUser ? this.addUserMessage(text) : this.nextMessageId++;
    this.busy.set(true);
    this.error.set(null);
    this.retryable.set(null);
    const controller = this.startChatRequest();
    this.activeTurnId = turnId;
    try {
      const response = await this.withRetry(
        (signal) => this.api.chatTurn(this.buildChatRequest(text, continuation), signal),
        controller.signal,
        'The chat service',
        (message) => this.addRetryActivity(turnId, message),
      );
      if (controller.signal.aborted) {
        return;
      }
      this.completeRunningActivities(turnId);
      this.handleTurn(response, text, turnId, continuation);
    } catch (error) {
      this.markRunningActivitiesFailed(turnId);
      this.handleChatFailure(controller, error, {
        kind: 'chat',
        text,
        continuation,
      });
    } finally {
      this.finishChat(controller);
    }
  }

  private buildChatRequest(
    text: string,
    continuation: boolean,
  ): Parameters<MarketApi['chatTurn']>[0] {
    return {
      symbol: this.symbol(),
      message: text,
      intent: this.draft()?.intent ?? 'open',
      language: this.detectedLanguage(),
      history: this.history.slice(-8),
      draft: this.draft(),
      context: [...this.contextStack],
      continuation,
      market: this.snapshot() ?? this.emptySnapshot(),
    };
  }

  private handleTurn(
    response: ChatTurnResponse,
    userText: string,
    turnId: number,
    continuation: boolean,
  ): void {
    if (!continuation) {
      this.pushHistory({ role: 'user', text: userText });
    }
    this.detectedLanguage.set(response.language || this.detectedLanguage());
    this.analysisIntent = response.intent || this.analysisIntent || 'open';
    this.localizeGreeting();
    if (response.text.trim() && !(response.mode === 'switch_symbol' && response.switch?.explicit)) {
      this.addAssistantMessage(response.text);
    }
    switch (response.mode) {
      case 'answer':
        if (response.draft) {
          this.draft.set(response.draft);
        }
        break;
      case 'draft':
        this.draft.set(response.draft);
        this.suggestions.set(response.suggestions);
        this.missing.set(response.missing);
        this.draftWarnings.set(response.warnings);
        this.confirm.set(null);
        this.mode.set('draft');
        break;
      case 'confirm':
        this.draft.set(response.draft);
        this.suggestions.set(response.suggestions);
        this.missing.set([]);
        this.draftWarnings.set(response.warnings);
        this.confirm.set(response.confirm);
        this.mode.set('confirm');
        break;
      case 'switch_symbol':
        if (response.switch) {
          this.pendingDraftAfterSwitch.set(response.pending_draft);
          if (response.switch.explicit) {
            this.performSwitch(response.switch.symbol);
          } else {
            this.switchProposal.set(response.switch);
            this.mode.set('switch');
          }
        }
        break;
      case 'refused':
        break;
    }
    this.updateTurn(turnId, (message) => ({ ...message }));
  }

  private async runConfirmed(turnId?: number): Promise<void> {
    const confirmed = this.confirm();
    if (!confirmed) {
      return;
    }
    const id = turnId ?? this.addUserMessage('Analyze');
    if (turnId === undefined) {
      this.pushHistory({ role: 'user', text: 'Analyze' });
    }
    await this.runAnalysis(confirmed.position, id);
  }

  private async runAnalysis(position: AnalysisPosition, turnId: number): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    this.retryable.set(null);
    const controller = this.startChatRequest();
    this.activeTurnId = turnId;
    try {
      const result = await this.withRetry(
        (signal) =>
          this.api.streamAnalysis(
            {
              position,
              context: [...this.contextStack],
              reference: null,
              intent: this.analysisIntent,
              detected_language: this.detectedLanguage(),
            },
            (event) => this.handleStreamEvent(turnId, event),
            signal,
          ),
        controller.signal,
        'The analysis service',
        (message) => this.addRetryActivity(turnId, message),
      );
      if (controller.signal.aborted) {
        return;
      }
      this.completeRunningActivities(turnId);
      this.retryable.set(null);
      this.addContext(position);
      this.messages.update((messages) => [
        ...messages,
        { id: this.nextMessageId++, role: 'assistant', analysis: result },
      ]);
      this.draft.set(null);
      this.suggestions.set(null);
      this.missing.set([]);
      this.draftWarnings.set([]);
      this.confirm.set(null);
      this.switchProposal.set(null);
      this.pendingDraftAfterSwitch.set(null);
      this.mode.set('explore');
    } catch (error) {
      this.markRunningActivitiesFailed(turnId);
      this.handleChatFailure(controller, error, {
        kind: 'analysis',
        position,
        turnId,
      });
    } finally {
      this.finishChat(controller);
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
          this.localizeStageLabel(event.label),
          event.status === 'started' ? 'running' : event.status === 'done' ? 'done' : 'failed',
          this.localizeStageDetail(event.detail),
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
        this.upsertActivity(turnId, `warning-${event.code}`, this.chatWarningLabel(event.code), 'done');
        break;
      case 'error':
        this.upsertActivity(turnId, 'stream-error', this.copy().analysisFailed, 'failed', event.detail);
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
      this.addAssistantMessage(this.errorMessage(error, this.detectedLanguage()));
    }
    this.error.set(this.errorMessage(error, this.detectedLanguage()));
    this.retryable.set(this.canRetryAfter(error) ? action : null);
  }

  private canRetryAfter(error: unknown): boolean {
    if (error instanceof HttpErrorResponse) {
      return error.status !== 404 && error.status !== 422;
    }
    return true;
  }

  protected chatWarningLabel(code: string): string {
    if (!this.isRussian()) {
      return this.warningLabel(code);
    }
    return RUSSIAN_WARNINGS[code] ?? code;
  }

  private localizeStageLabel(label: string): string {
    if (!this.isRussian()) {
      return label;
    }
    const mapped = RUSSIAN_STAGE_LABELS[label];
    if (mapped) {
      return mapped;
    }
    for (const [pattern, template] of RUSSIAN_STAGE_PATTERNS) {
      const match = pattern.exec(label);
      if (match) {
        return template.replace('$1', match[1] ?? '').replace('$2', match[2] ?? '');
      }
    }
    return label;
  }

  private localizeStageDetail(detail?: string): string | undefined {
    if (!detail || !this.isRussian()) {
      return detail;
    }
    return this.localizeStageLabel(detail);
  }

  private retryMessage(label: string, delay: number, attempt: number): string {
    const attemptText = `${attempt + 2}/${RETRY_DELAYS_MS.length + 1}`;
    const retry = label.toLowerCase().includes('chat')
      ? this.copy().retryChat
      : this.copy().retryAnalysis;
    return retry(delay, attemptText);
  }

  private localizeGreeting(): void {
    const greeting = this.isRussian() ? RUSSIAN_GREETING : ENGLISH_GREETING;
    this.messages.update((messages) =>
      messages.map((message) =>
        message.id === 0 && message.role === 'assistant'
          ? { ...message, text: greeting }
          : message,
      ),
    );
  }

  private addUserMessage(text: string, activities?: ChatActivity[]): number {
    const id = this.nextMessageId++;
    this.messages.update((messages) => [
      ...messages,
      { id, role: 'user', text, activities: activities ?? [] },
    ]);
    return id;
  }

  private addAssistantMessage(text: string): number {
    const id = this.nextMessageId++;
    this.messages.update((messages) => [...messages, { id, role: 'assistant', text }]);
    this.pushHistory({ role: 'assistant', text });
    return id;
  }

  private pushHistory(turn: ChatHistoryTurn): void {
    this.history.push(turn);
    if (this.history.length > 8) {
      this.history = this.history.slice(-8);
    }
  }

  private performSwitch(symbol: string): void {
    this.switchProposal.set(null);
    if (symbol === this.symbol()) {
      this.mode.set('explore');
      this.addAssistantMessage(this.copy().alreadyShowing(symbol));
      return;
    }
    this.preferences.setSymbol(symbol);
    this.mode.set(this.pendingDraftAfterSwitch() ? 'draft' : 'explore');
  }

  private emptySnapshot(): ChatMarketSnapshot {
    return {
      symbol: this.symbol(),
      price: null,
      change_pct: null,
      vix: null,
      support: [],
      resistance: [],
      candles: [],
      sma: [],
      rsi: { period: 14, points: [] },
      news: [],
      range: '6mo',
      chart_source: null,
      chart_as_of: null,
      as_of: null,
      quote_as_of: null,
      vix_as_of: null,
      news_as_of: null,
      sources: { quote: null, vix: null, news: null },
      degraded: true,
      warnings: ['snapshot_unavailable'],
    };
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
        const message = this.retryMessage(label, delay, attempt);
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

  private scrollToLatest(): void {
    const element = this.chatLog()?.nativeElement;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
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
          activities: message.activities.filter((activity) => activity.state !== 'running'),
        };
      }),
    );
  }
}
