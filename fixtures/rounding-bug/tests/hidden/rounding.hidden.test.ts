import { describe, it, expect } from 'vitest';
import { roundCurrency } from '../../src/utils/math.utils.js';

describe('Private Hidden Verification Suite - Comprehensive Rounding', () => {
  it('rounds 0.005 to 0.01', () => {
    expect(roundCurrency(0.005)).toBe(0.01);
  });

  it('rounds 12.345 to 12.35', () => {
    expect(roundCurrency(12.345)).toBe(12.35);
  });

  it('rounds 99.995 to 100.00', () => {
    expect(roundCurrency(99.995)).toBe(100.00);
  });

  it('preserves exact 2 decimal places like 10.50 and 45.25', () => {
    expect(roundCurrency(10.50)).toBe(10.50);
    expect(roundCurrency(45.25)).toBe(45.25);
  });

  it('does not round down on positive fractional precision', () => {
    expect(roundCurrency(1.006)).toBe(1.01);
    expect(roundCurrency(1.004)).toBe(1.00);
  });
});
