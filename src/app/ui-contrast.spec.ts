import { describe, expect, it } from 'vitest';
import { contrastRatio } from './theme-palette';

const AA_TEXT = 4.5;

const LIGHT = {
  accentSolid: '#1d4ed8',
  onAccent: '#ffffff',
  accentSoft: '#dbeafe',
  onAccentSoft: '#0b2a6b',
  textPrimary: '#101828',
  panel: '#ffffff',
};

const DARK = {
  accentSolid: '#2563eb',
  onAccent: '#ffffff',
  accentSoft: '#1b2f4d',
  onAccentSoft: '#eaf2ff',
  textPrimary: '#e8eef7',
  panel: '#111827',
};

describe('UI token contrast', () => {
  it('keeps primary button and brand text readable in both themes', () => {
    expect(contrastRatio(LIGHT.onAccent, LIGHT.accentSolid)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(DARK.onAccent, DARK.accentSolid)).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it('keeps soft chip, badge, and user-message text readable', () => {
    expect(contrastRatio(LIGHT.onAccentSoft, LIGHT.accentSoft)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(DARK.onAccentSoft, DARK.accentSoft)).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it('keeps body text readable on panels in both themes', () => {
    expect(contrastRatio(LIGHT.textPrimary, LIGHT.panel)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrastRatio(DARK.textPrimary, DARK.panel)).toBeGreaterThanOrEqual(AA_TEXT);
  });
});
