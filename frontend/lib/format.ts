export function formatScore(value: number): string {
  return value.toFixed(3);
}

export function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}
