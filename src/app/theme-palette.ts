import { Theme } from './services/preferences';

export interface ChartPalette {
  support: string;
  resistance: string;
  labelText: string;
  sma20: string;
  sma50: string;
  rsi: string;
  trend: string;
  up: string;
  down: string;
  volumeUp: string;
  volumeDown: string;
  text: string;
  border: string;
  tooltip: 'light' | 'dark';
}

const LIGHT: ChartPalette = {
  support: '#2f6b4f',
  resistance: '#8a3b3b',
  labelText: '#ffffff',
  sma20: '#b45309',
  sma50: '#1d4ed8',
  rsi: '#7e22ce',
  trend: '#0f766e',
  up: '#15803d',
  down: '#b91c1c',
  volumeUp: 'rgba(21, 128, 61, 0.72)',
  volumeDown: 'rgba(185, 28, 28, 0.72)',
  text: '#334155',
  border: '#dbe3ec',
  tooltip: 'light',
};

const DARK: ChartPalette = {
  support: '#9fd6b8',
  resistance: '#f2aaaa',
  labelText: '#0b1017',
  sma20: '#fbbf24',
  sma50: '#60a5fa',
  rsi: '#c084fc',
  trend: '#2dd4bf',
  up: '#4ade80',
  down: '#f87171',
  volumeUp: 'rgba(74, 222, 128, 0.62)',
  volumeDown: 'rgba(248, 113, 113, 0.62)',
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
