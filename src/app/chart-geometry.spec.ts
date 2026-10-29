import { describe, expect, it } from 'vitest';
import { nearestTime, niceAxisScale, pixelToData, PlotArea, priceRange } from './chart-geometry';

const area: PlotArea = {
  minX: 1_000,
  maxX: 2_000,
  minY: 100,
  maxY: 200,
  gridWidth: 400,
  gridHeight: 200,
  translateX: 50,
  translateY: 20,
};

describe('chart geometry', () => {
  it('converts the top-left plot corner to the maximum price', () => {
    expect(pixelToData(50, 20, area)).toEqual({ x: 1_000, y: 200 });
  });

  it('converts the bottom-right plot corner to the minimum price', () => {
    expect(pixelToData(450, 220, area)).toEqual({ x: 2_000, y: 100 });
  });

  it('rejects clicks outside the plot area', () => {
    expect(pixelToData(10, 30, area)).toBeNull();
    expect(pixelToData(60, 400, area)).toBeNull();
  });

  it('rejects a collapsed plot area', () => {
    expect(pixelToData(50, 20, { ...area, gridWidth: 0 })).toBeNull();
  });

  it('snaps a value to the nearest candle time', () => {
    expect(nearestTime(1_480, [1_000, 1_500, 1_900])).toBe(1_500);
    expect(nearestTime(1_950, [1_000, 1_500, 1_900])).toBe(1_900);
    expect(nearestTime(1_000, [])).toBeNull();
  });

  it('scales the price axis to the visible candles, not to zero', () => {
    const range = priceRange([
      { h: 105, l: 101 },
      { h: 110, l: 104 },
      { h: 108, l: 102 },
    ]);

    expect(range).not.toBeNull();
    expect(range!.min).toBeCloseTo(100.64, 2);
    expect(range!.max).toBeCloseTo(110.36, 2);
    expect(range!.min).toBeGreaterThan(0);
  });

  it('keeps a small padding for a flat series', () => {
    expect(priceRange([{ h: 200, l: 200 }])).toEqual({
      min: 198,
      max: 202,
    });
  });

  it('returns null without candles', () => {
    expect(priceRange([])).toBeNull();
  });
});

describe('niceAxisScale', () => {
  it('rounds the bounds and step to nice numbers', () => {
    expect(niceAxisScale(729.98, 790.03)).toEqual({
      min: 720,
      max: 800,
      step: 20,
    });
  });

  it('rounds fractional spans', () => {
    expect(niceAxisScale(14.9, 15.6)).toEqual({
      min: 14.8,
      max: 15.6,
      step: 0.2,
    });
  });

  it('uses fine steps for narrow spans', () => {
    expect(niceAxisScale(0.495, 0.505)).toEqual({
      min: 0.494,
      max: 0.506,
      step: 0.002,
    });
  });

  it('returns the original bounds for invalid spans', () => {
    expect(niceAxisScale(100, 100)).toEqual({
      min: 100,
      max: 100,
      step: 0,
    });
  });
});
