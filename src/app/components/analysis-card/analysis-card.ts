import { CurrencyPipe, DecimalPipe, PercentPipe } from '@angular/common';
import { Component, input } from '@angular/core';
import { AnalysisResult } from '../../models/market-data';
import { warningLabel } from '../../warning-labels';

@Component({
  selector: 'app-analysis-card',
  imports: [CurrencyPipe, DecimalPipe, PercentPipe],
  templateUrl: './analysis-card.html',
  styleUrl: './analysis-card.css',
})
export class AnalysisCard {
  readonly result = input.required<AnalysisResult>();

  protected readonly warningLabel = warningLabel;

  protected eventFlagDescription(flag: string): string {
    switch (flag) {
      case 'earnings':
        return 'The playbook is sensitive to earnings announcements.';
      case 'dividends':
        return 'The playbook is sensitive to dividend events.';
      case 'macro':
        return 'The playbook is sensitive to macroeconomic events.';
      default:
        return 'The playbook flags sensitivity to this event type.';
    }
  }
}
