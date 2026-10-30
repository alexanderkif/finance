import { describe, expect, it } from 'vitest';
import { chartPalette, contrastRatio } from './theme-palette';

const LIGHT_PANEL = '#ffffff';
const DARK_PANEL = '#111827';
const AA_TEXT = 4.5;

describe('chart palette contrast', () => {
  const light = chartPalette('light');
  const dark = chartPalette('dark');

  it('keeps level lines above non-text contrast', () => {
    const nonText = 3;
    expect(contrastRatio(light.support, LIGHT_PANEL)).toBeGreaterThanOrEqual(nonText);
    expect(contrastRatio(light.resistance, LIGHT_PANEL)).toBeGreaterThanOrEqual(nonText);
    expect(contrastRatio(dark.support, DARK_PANEL)).toBeGreaterThanOrEqual(nonText);
    expect(contrastRatio(dark.resistance, DARK_PANEL)).toBeGreaterThanOrEqual(nonText);
  });

  it('keeps annotation labels readable on their backgrounds', () => {
    expect(contrastRatio(light.labelText, light.supportFill)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(light.labelText, light.resistanceFill)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(dark.labelText, dark.supportFill)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(dark.labelText, dark.resistanceFill)).toBeGreaterThanOrEqual(AA_TEXT);
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
