/**
 * Utility functions for currency calculation.
 *
 * BUG: Uses Math.floor truncation rather than half-up / standard rounding.
 * e.g. roundCurrency(249.995) results in 249.99 instead of 250.00!
 */
export function roundCurrency(amount: number): number {
  return Math.floor(amount * 100) / 100;
}

export function preciseAdd(a: number, b: number): number {
  return Math.round((a + b) * 100) / 100;
}
