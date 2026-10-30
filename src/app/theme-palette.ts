import { Theme } from './services/preferences';

export interface ChartPalette {
  support: string;
  resistance: string;
  supportFill: string;
  resistanceFill: string;
  labelText: string;
  sma20: string;
  sma50: string;
  rsi: string;
  trend: string;
  up: string;
  down: string;
  volumeUp: string;
  volumeDown: string;
  volumeOpacity: number;
  text: string;
  border: string;
  tooltip: 'light' | 'dark';
}

const LIGHT: ChartPalette = {
  support: '#0aa55f',
  resistance: '#e06a6a',
  supportFill: '#bfe8d2',
  resistanceFill: '#f6cece',
  labelText: '#0b1017',
  sma20: '#d77c00',
  sma50: '#457bdc',
  rsi: '#8f63dd',
  trend: '#b86acb',
  up: '#00a85c',
  down: '#ef4444',
  volumeUp: '#0aa55f',
  volumeDown: '#e06a6a',
  volumeOpacity: 1,
  text: '#475569',
  border: '#dbe3ec',
  tooltip: 'light',
};

const DARK: ChartPalette = {
  support: '#9fd6b8',
  resistance: '#f2aaaa',
  supportFill: '#9fd6b8',
  resistanceFill: '#f2aaaa',
  labelText: '#0b1017',
  sma20: '#fbbf24',
  sma50: '#60a5fa',
  rsi: '#c084fc',
  trend: '#e6b8f2',
  up: '#4ade80',
  down: '#f87171',
  volumeUp: '#4ade80',
  volumeDown: '#f87171',
  volumeOpacity: 0.62,
  text: '#c3ccd9',
  border: '#2a3544',
  tooltip: 'dark',
};

export function chartPalette(theme: Theme): ChartPalette {
  return theme === 'dark' ? DARK : LIGHT;
}

export function contrastRatio(foreground: string, background: string): number {
  const first = _luminance(foreground);
  const second = _luminance(background);
  const lighter = Math.max(first, second);
  const darker = Math.min(first, second);
  return (lighter + 0.05) / (darker + 0.05);
}

function _luminance(hex: string): number {
  const normalized = hex.replace('#', '');
  const channels = [0, 2, 4].map((offset) =>
    _linearize(Number.parseInt(normalized.slice(offset, offset + 2), 16) / 255),
  );
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function _linearize(channel: number): number {
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
}
