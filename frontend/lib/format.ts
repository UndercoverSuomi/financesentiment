function toFiniteNumber(value: unknown): number | null {
  if (typeof value !== 'number') return null;
  if (!Number.isFinite(value)) return null;
  return value;
}

export function formatScore(value: unknown): string {
  const safe = toFiniteNumber(value);
  if (safe === null) return 'n/a';
  return safe.toFixed(3);
}

export function formatPct(value: unknown): string {
  const safe = toFiniteNumber(value);
  if (safe === null) return 'n/a';
  return `${(safe * 100).toFixed(1)}%`;
}

export function formatUsd(value: unknown, fractionDigits: number = 2): string {
  const safe = toFiniteNumber(value);
  if (safe === null) return 'n/a';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(safe);
}
