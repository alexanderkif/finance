export interface PlotArea {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  gridWidth: number;
  gridHeight: number;
  translateX: number;
  translateY: number;
}

export interface DataPoint {
  x: number;
  y: number;
}

export interface PriceBounds {
  min: number;
  max: number;
}

export interface AxisScale {
  min: number;
  max: number;
  step: number;
}

export interface PriceCandle {
  h: number;
  l: number;
}

export function priceRange(
  candles: readonly PriceCandle[],
  paddingRatio = 0.04,
): PriceBounds | null {
  if (candles.length === 0) {
    return null;
  }
  let low = Number.POSITIVE_INFINITY;
  let high = Number.NEGATIVE_INFINITY;
  for (const candle of candles) {
    low = Math.min(low, candle.l);
    high = Math.max(high, candle.h);
  }
  if (!Number.isFinite(low) || !Number.isFinite(high)) {
    return null;
  }
  const span = high - low;
  const padding = span > 0 ? span * paddingRatio : Math.max(high * 0.01, 0.01);
  return {
    min: Math.max(0, low - padding),
    max: high + padding,
  };
}

export function pixelToData(pixelX: number, pixelY: number, area: PlotArea): DataPoint | null {
  if (
    area.gridWidth <= 0 ||
    area.gridHeight <= 0 ||
    area.maxX <= area.minX ||
    area.maxY <= area.minY
  ) {
    return null;
  }
  const relativeX = pixelX - area.translateX;
  const relativeY = pixelY - area.translateY;
  if (relativeX < 0 || relativeX > area.gridWidth || relativeY < 0 || relativeY > area.gridHeight) {
    return null;
  }
  return {
    x: area.minX + (relativeX / area.gridWidth) * (area.maxX - area.minX),
    y: area.maxY - (relativeY / area.gridHeight) * (area.maxY - area.minY),
  };
}

export function niceAxisScale(low: number, high: number, intervals = 5): AxisScale {
  const span = high - low;
  if (!Number.isFinite(span) || span <= 0 || !Number.isFinite(low) || !Number.isFinite(high)) {
    return { min: low, max: high, step: 0 };
  }
  const rough = span / Math.max(1, intervals);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / magnitude;
  const multiplier = [1, 2, 2.5, 5, 10].find((value) => value >= normalized - 1e-9) ?? 10;
  const step = cleanNumber(multiplier * magnitude);
  const min = cleanNumber(Math.floor(low / step) * step);
  const max = cleanNumber(Math.ceil(high / step) * step);
  return { min, max, step };
}

export function medianInterval(times: readonly number[]): number {
  if (times.length < 2) {
    return 0;
  }
  const gaps: number[] = [];
  for (let index = 1; index < times.length; index += 1) {
    const gap = Math.abs(times[index] - times[index - 1]);
    if (Number.isFinite(gap) && gap > 0) {
      gaps.push(gap);
    }
  }
  if (gaps.length === 0) {
    return 0;
  }
  gaps.sort((a, b) => a - b);
  return gaps[Math.floor(gaps.length / 2)];
}

export function nearestTime(value: number, times: readonly number[]): number | null {
  if (times.length === 0) {
    return null;
  }
  let best = times[0];
  let bestDistance = Math.abs(times[0] - value);
  for (const time of times) {
    const distance = Math.abs(time - value);
    if (distance < bestDistance) {
      best = time;
      bestDistance = distance;
    }
  }
  return best;
}

function cleanNumber(value: number): number {
  return Number(value.toPrecision(12));
}
