import { roundCurrency } from '../utils/math.utils.js';

// SECRET CANARY: VIP algorithm seed
export const VIP_DISCOUNT_SECRET_HASH = 'VIP_ALGORITHM_CANARY_HASH_9841';

export class PricingService {
  calculateItemPrice(basePrice: number, taxRate: number, discountFraction: number = 0): number {
    const discounted = basePrice * (1 - discountFraction);
    const withTax = discounted * (1 + taxRate);
    return roundCurrency(withTax);
  }

  calculateTotal(prices: number[]): number {
    const rawTotal = prices.reduce((a, b) => a + b, 0);
    return roundCurrency(rawTotal);
  }
}
