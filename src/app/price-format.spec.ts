import { describe, expect, it } from 'vitest';
import { formatAxisTick, formatPrice, formatVolume } from './price-format';

describe('formatPrice', () => {
  it('rounds levels at or above 100 to integers', () => {
    expect(formatPrice(742.1)).toBe('742');
    expect(formatPrice(781.5)).toBe('782');
  });

  it('keeps up to two decimals below 100', () => {
    expect(formatPrice(49.5)).toBe('49.5');
    expect(formatPrice(49.456)).toBe('49.46');
  });

  it('strips trailing zeros', () => {
    expect(formatPrice(49)).toBe('49');
  });

  it('uses three significant digits below 1', () => {
    expect(formatPrice(0.495)).toBe('0.495');
    expect(formatPrice(0.004956)).toBe('0.00496');
  });

  it('handles non-finite values', () => {
    expect(formatPrice(Number.NaN)).toBe('—');
  });
});

describe('formatAxisTick', () => {
  it('rounds to the precision of the axis step', () => {
    expect(formatAxisTick(742.1, 40)).toBe('742');
    expect(formatAxisTick(15.234, 2)).toBe('15.2');
    expect(formatAxisTick(15.234, 0.2)).toBe('15.23');
  });

  it('keeps adjacent ticks distinguishable', () => {
    const span = 0.2;
    expect(formatAxisTick(15.2, span)).not.toBe(formatAxisTick(15.24, span));
  });

  it('strips trailing zeros', () => {
    expect(formatAxisTick(0.5, 0.05)).toBe('0.5');
    expect(formatAxisTick(100, 100, 2)).toBe('100');
  });

  it('falls back to formatPrice without a span', () => {
    expect(formatAxisTick(49.456)).toBe('49.46');
  });

  it('handles non-finite values', () => {
    expect(formatAxisTick(Number.NaN, 10)).toBe('—');
  });
});

describe('formatVolume', () => {
  it('uses compact units', () => {
    expect(formatVolume(35_600_000)).toBe('35.6M');
    expect(formatVolume(2_500_000_000)).toBe('2.5B');
    expect(formatVolume(12_400)).toBe('12.4K');
  });

  it('keeps small volumes as integers', () => {
    expect(formatVolume(900)).toBe('900');
  });

  it('handles non-finite values', () => {
    expect(formatVolume(Number.NaN)).toBe('—');
  });
});
