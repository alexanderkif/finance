import { CurrencyPipe, DecimalPipe, PercentPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { errorMessage } from '../../api-error';
import { AnalysisResult, Intent, ParseResponse, PositionLeg } from '../../models/market-data';
import { MarketApi } from '../../services/market-data';

interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
}

@Component({
  selector: 'app-analysis-chat',
  imports: [CurrencyPipe, DecimalPipe, PercentPipe],
  templateUrl: './analysis-chat.html',
  styleUrl: './analysis-chat.css',
})
export class AnalysisChat {
  private readonly api = inject(MarketApi);

  readonly symbol = input.required<string>();

  protected readonly messages = signal<ChatMessage[]>([
    {
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
  protected readonly analysis = signal<AnalysisResult | null>(null);
  protected readonly pending = signal<{ text: string; missing: string[] } | null>(null);
  protected readonly canSend = computed(() => this.draft().trim().length > 0 && !this.busy());
  protected readonly errorMessage = errorMessage;

  protected updateDraft(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLTextAreaElement) {
      this.draft.set(target.value);
    }
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

  protected async useExample(): Promise<void> {
    if (this.exampleBusy()) {
      return;
    }
    this.exampleBusy.set(true);
    this.error.set(null);
    try {
      const example = await this.api.getExample(this.symbol());
      this.draft.set(example.message);
      this.messages.update((messages) => [
        ...messages,
        { role: 'assistant', text: example.description },
      ]);
    } catch (error) {
      this.error.set(this.errorMessage(error));
    } finally {
      this.exampleBusy.set(false);
    }
  }

  protected async send(event?: Event): Promise<void> {
    event?.preventDefault();
    const text = this.draft().trim();
    if (!text || this.busy()) {
      return;
    }
    this.draft.set('');
    this.error.set(null);
    this.messages.update((messages) => [...messages, { role: 'user', text }]);
    const combined = this.pending() ? `${this.pending()!.text} ${text}` : text;
    this.busy.set(true);
    try {
      const parsed = await this.api.parse(combined, this.symbol());
      if (parsed.missing_fields.length > 0) {
        this.pending.set({ text: combined, missing: parsed.missing_fields });
        this.messages.update((messages) => [
          ...messages,
          {
            role: 'assistant',
            text: `I still need: ${parsed.missing_fields.join(', ')}.`,
          },
        ]);
        return;
      }
      this.pending.set(null);
      const position = this.toPosition(parsed);
      if (!position) {
        this.messages.update((messages) => [
          ...messages,
          {
            role: 'assistant',
            text: 'The position is missing a required leg field.',
          },
        ]);
        return;
      }
      const result = await this.api.runAnalysis({
        position,
        intent: this.intent(),
        detected_language: parsed.detected_language,
      });
      this.analysis.set(result);
      this.messages.update((messages) => [
        ...messages,
        {
          role: 'assistant',
          text: 'Analysis card updated with the latest metrics.',
        },
      ]);
    } catch (error) {
      this.error.set(this.errorMessage(error));
    } finally {
      this.busy.set(false);
    }
  }

  private toPosition(
    parsed: ParseResponse,
  ): { position_type: 'single' | 'strategy'; legs: PositionLeg[] } | null {
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
}
