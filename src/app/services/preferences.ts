import { Service, signal } from '@angular/core';
import { ChartRange } from '../models/market-data';

export type Theme = 'light' | 'dark';

export type ChartToggle = 'sma20' | 'sma50' | 'rsi' | 'levels';

export interface ChartToggles {
  sma20: boolean;
  sma50: boolean;
  rsi: boolean;
  levels: boolean;
}

const THEME_KEY = 'osa.theme';
const SYMBOL_KEY = 'osa.symbol';
const CHART_TOGGLES_KEY = 'osa.chart.toggles';
const RANGE_KEY = 'osa.range';
const CHAT_HEIGHT_KEY = 'osa.chat.height';
const SYMBOL_PATTERN = /^[A-Z0-9._-]{1,15}$/;
const CHART_RANGES: readonly ChartRange[] = ['1mo', '3mo', '6mo', '1y', '5y'];
export const DEFAULT_SYMBOL = 'AAPL';
export const DEFAULT_CHAT_HEIGHT_PX = 640;
export const MIN_CHAT_HEIGHT_PX = 240;
export const MAX_CHAT_HEIGHT_PX = 960;
const DEFAULT_CHART_TOGGLES: ChartToggles = {
  sma20: false,
  sma50: false,
  rsi: false,
  levels: true,
};

@Service()
export class Preferences {
  readonly theme = signal<Theme>('light');
  readonly symbol = signal(DEFAULT_SYMBOL);
  readonly range = signal<ChartRange>('6mo');
  readonly chartToggles = signal<ChartToggles>({
    ...DEFAULT_CHART_TOGGLES,
  });
  readonly chatHeight = signal(DEFAULT_CHAT_HEIGHT_PX);

  constructor() {
    if (typeof document === 'undefined' || typeof localStorage === 'undefined') {
      return;
    }
    const storedTheme = localStorage.getItem(THEME_KEY);
    const prefersDark =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme: Theme =
      storedTheme === 'light' || storedTheme === 'dark'
        ? storedTheme
        : prefersDark
          ? 'dark'
          : 'light';
    this.theme.set(theme);
    this.applyTheme(theme);

    const storedSymbol = localStorage.getItem(SYMBOL_KEY);
    if (storedSymbol && SYMBOL_PATTERN.test(storedSymbol)) {
      this.symbol.set(storedSymbol);
    }

    this.chartToggles.set(this.readChartToggles());
    this.range.set(this.readRange());
    this.chatHeight.set(this.readChatHeight());
  }

  setTheme(theme: Theme): void {
    this.theme.set(theme);
    if (typeof document === 'undefined' || typeof localStorage === 'undefined') {
      return;
    }
    localStorage.setItem(THEME_KEY, theme);
    this.applyTheme(theme);
  }

  toggleTheme(): void {
    this.setTheme(this.theme() === 'dark' ? 'light' : 'dark');
  }

  setSymbol(value: string): boolean {
    const normalized = value.trim().toUpperCase().replace(/^_/, '');
    if (!SYMBOL_PATTERN.test(normalized)) {
      return false;
    }
    this.symbol.set(normalized);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(SYMBOL_KEY, normalized);
    }
    return true;
  }

  setRange(range: ChartRange): void {
    this.range.set(range);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(RANGE_KEY, range);
    }
  }

  setChatHeight(value: number): void {
    const height = clampChatHeight(value);
    this.chatHeight.set(height);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(CHAT_HEIGHT_KEY, String(height));
    }
  }

  setChartToggle(key: ChartToggle, value: boolean): void {
    this.chartToggles.update((current) => ({ ...current, [key]: value }));
    if (typeof localStorage === 'undefined') {
      return;
    }
    localStorage.setItem(CHART_TOGGLES_KEY, JSON.stringify(this.chartToggles()));
  }

  private readRange(): ChartRange {
    if (typeof localStorage === 'undefined') {
      return '6mo';
    }
    const stored = localStorage.getItem(RANGE_KEY);
    return CHART_RANGES.includes(stored as ChartRange) ? (stored as ChartRange) : '6mo';
  }

  private readChatHeight(): number {
    if (typeof localStorage === 'undefined') {
      return DEFAULT_CHAT_HEIGHT_PX;
    }
    const raw = localStorage.getItem(CHAT_HEIGHT_KEY);
    if (raw === null) {
      return DEFAULT_CHAT_HEIGHT_PX;
    }
    const value = Number(raw);
    return Number.isFinite(value) ? clampChatHeight(value) : DEFAULT_CHAT_HEIGHT_PX;
  }

  private readChartToggles(): ChartToggles {
    if (typeof localStorage === 'undefined') {
      return { ...DEFAULT_CHART_TOGGLES };
    }
    const raw = localStorage.getItem(CHART_TOGGLES_KEY);
    if (!raw) {
      return { ...DEFAULT_CHART_TOGGLES };
    }
    try {
      const parsed: unknown = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') {
        return { ...DEFAULT_CHART_TOGGLES };
      }
      const source = parsed as Record<string, unknown>;
      return {
        sma20: readToggle(source, 'sma20'),
        sma50: readToggle(source, 'sma50'),
        rsi: readToggle(source, 'rsi'),
        levels: readToggle(source, 'levels'),
      };
    } catch {
      return { ...DEFAULT_CHART_TOGGLES };
    }
  }

  private applyTheme(theme: Theme): void {
    document.documentElement.dataset['theme'] = theme;
  }
}

export function clampChatHeight(value: number): number {
  return Math.min(MAX_CHAT_HEIGHT_PX, Math.max(MIN_CHAT_HEIGHT_PX, Math.round(value)));
}

function readToggle(source: Record<string, unknown>, key: ChartToggle): boolean {
  const value = source[key];
  return typeof value === 'boolean' ? value : DEFAULT_CHART_TOGGLES[key];
}
