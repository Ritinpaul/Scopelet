import { describe, it, expect } from 'vitest';
import { CheckoutService } from '../src/checkout/checkout.service.js';
import { PricingService } from '../src/pricing/pricing.service.js';

describe('Currency Rounding Behavior', () => {
  it('correctly rounds half-cent amount ₹249.995 to ₹250.00', () => {
    const pricing = new PricingService();
    const checkout = new CheckoutService(pricing);

    // Base price = 211.86016949..., tax = 18% (0.18)
    // 211.86016949152542 * 1.18 = 249.995
    // With half-up rounding, 249.995 should round to 250.00.
    // Defective Math.floor truncates to 249.99!
    const rounded = pricing.calculateItemPrice(211.86016949152542, 0.18);
    expect(rounded).toBe(250.00);
  });
});
