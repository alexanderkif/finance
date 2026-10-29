import { describe, expect, it } from 'vitest';
import { chartPalette, contrastRatio } from './theme-palette';

const LIGHT_PANEL = '#ffffff';
const DARK_PANEL = '#111827';
const AA_TEXT = 4.5;

describe('chart palette contrast', () => {
  const light = chartPalette('light');
  const dark = chartPalette('dark');

  it('keeps level text readable on light panels', () => {
    expect(contrastRatio(light.support, LIGHT_PANEL)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(light.resistance, LIGHT_PANEL)).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it('keeps level text readable on dark panels', () => {
    expect(contrastRatio(dark.support, DARK_PANEL)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(dark.resistance, DARK_PANEL)).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it('keeps annotation labels readable on their backgrounds', () => {
    expect(contrastRatio(light.labelText, light.support)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(light.labelText, light.resistance)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(dark.labelText, dark.support)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(dark.labelText, dark.resistance)).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it('keeps axis text readable on both backgrounds', () => {
    expect(contrastRatio(light.text, LIGHT_PANEL)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(dark.text, DARK_PANEL)).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it('keeps candles and indicators above non-text contrast', () => {
    const nonText = 3;
    for (const color of [light.up, light.down, light.sma20, light.sma50, light.rsi, light.trend]) {
      expect(contrastRatio(color, LIGHT_PANEL)).toBeGreaterThanOrEqual(nonText);
    }
    for (const color of [dark.up, dark.down, dark.sma20, dark.sma50, dark.rsi, dark.trend]) {
      expect(contrastRatio(color, DARK_PANEL)).toBeGreaterThanOrEqual(nonText);
    }
  });
});
