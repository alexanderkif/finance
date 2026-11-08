import { beforeEach, describe, expect, it } from 'vitest';
import {
  DEFAULT_CHAT_HEIGHT_PX,
  DEFAULT_SYMBOL,
  MAX_CHAT_HEIGHT_PX,
  MIN_CHAT_HEIGHT_PX,
  Preferences,
} from './preferences';

describe('Preferences chart toggles', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults the instrument to AAPL', () => {
    const preferences = new Preferences();
    expect(DEFAULT_SYMBOL).toBe('AAPL');
    expect(preferences.symbol()).toBe('AAPL');
  });

  it('defaults the chart range to 6mo', () => {
    const preferences = new Preferences();
    expect(preferences.range()).toBe('6mo');
  });

  it('persists the chart range and ignores invalid values', () => {
    const preferences = new Preferences();
    preferences.setRange('1y');
    expect(new Preferences().range()).toBe('1y');

    localStorage.setItem('osa.range', '2w');
    expect(new Preferences().range()).toBe('6mo');
  });

  it('defaults indicators off and levels on', () => {
    const preferences = new Preferences();
    expect(preferences.chartToggles()).toEqual({
      sma20: false,
      sma50: false,
      rsi: false,
      levels: true,
    });
  });

  it('persists every toggle in localStorage', () => {
    const preferences = new Preferences();
    preferences.setChartToggle('sma20', true);
    preferences.setChartToggle('sma50', true);
    preferences.setChartToggle('rsi', true);
    preferences.setChartToggle('levels', false);

    expect(preferences.chartToggles()).toEqual({
      sma20: true,
      sma50: true,
      rsi: true,
      levels: false,
    });

    const restored = new Preferences();
    expect(restored.chartToggles()).toEqual({
      sma20: true,
      sma50: true,
      rsi: true,
      levels: false,
    });
  });

  it('falls back to defaults for malformed storage', () => {
    localStorage.setItem('osa.chart.toggles', 'not-json');
    const preferences = new Preferences();
    expect(preferences.chartToggles()).toEqual({
      sma20: false,
      sma50: false,
      rsi: false,
      levels: true,
    });
  });

  it('defaults the chat height and persists a clamped value', () => {
    const preferences = new Preferences();
    expect(preferences.chatHeight()).toBe(DEFAULT_CHAT_HEIGHT_PX);

    preferences.setChatHeight(500);
    expect(new Preferences().chatHeight()).toBe(500);

    preferences.setChatHeight(1);
    expect(preferences.chatHeight()).toBe(MIN_CHAT_HEIGHT_PX);

    localStorage.setItem('osa.chat.height', '9999');
    expect(new Preferences().chatHeight()).toBe(MAX_CHAT_HEIGHT_PX);

    localStorage.setItem('osa.chat.height', 'not-a-number');
    expect(new Preferences().chatHeight()).toBe(DEFAULT_CHAT_HEIGHT_PX);
  });
});
