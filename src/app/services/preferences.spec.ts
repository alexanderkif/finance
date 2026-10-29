import { beforeEach, describe, expect, it } from 'vitest';
import { Preferences } from './preferences';

describe('Preferences chart toggles', () => {
  beforeEach(() => {
    localStorage.clear();
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
});
