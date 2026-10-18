import { describe, it, expect } from 'vitest';
import { TaxService } from '../src/billing/tax.service.js';

describe('Billing Module', () => {
  it('calculates Maharashtra GST split', () => {
    const tax = new TaxService();
    const rate = tax.getGstRate('MH');
    expect(rate.cgst).toBe(0.09);
    expect(rate.sgst).toBe(0.09);
    expect(rate.igst).toBe(0);
  });
});
