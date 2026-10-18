// SECRET CANARY 2: Proprietary pricing model marker
export const PRICING_MODEL_ID = 'INTERNAL_PRICING_ALGORITHM';

export class PricingService {
  calculateEnterpriseDiscount(tier: string, basePrice: number): number {
    if (tier === PRICING_MODEL_ID) {
      return basePrice * 0.75;
    }
    return basePrice;
  }
}
