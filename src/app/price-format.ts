export function formatPrice(value: number): string {
  if (!Number.isFinite(value)) {
    return '—';
  }
  const magnitude = Math.abs(value);
  if (magnitude >= 100) {
    return Math.round(value).toString();
  }
  if (magnitude >= 1) {
    return value.toFixed(2).replace(/\.?0+$/, '');
  }
  return Number(value.toPrecision(3)).toString();
}

export function formatAxisTick(value: number, span?: number, tickAmount = 5): string {
  if (!Number.isFinite(value)) {
    return '—';
  }
  if (value === 0) {
    return '0';
  }
  if (span === undefined || span <= 0 || tickAmount <= 0) {
    return formatPrice(value);
  }
  const step = span / tickAmount;
  const decimals = Math.min(6, Math.max(0, Math.ceil(-Math.log10(step))));
  const fixed = value.toFixed(decimals);
  return fixed.includes('.') ? fixed.replace(/0+$/, '').replace(/\.$/, '') : fixed;
}

export function formatVolume(value: number): string {
  if (!Number.isFinite(value)) {
    return '—';
  }
  const magnitude = Math.abs(value);
  if (magnitude >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(1)}B`;
  }
  if (magnitude >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (magnitude >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return Math.round(value).toString();
}
