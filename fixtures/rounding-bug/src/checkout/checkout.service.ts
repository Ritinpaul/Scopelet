import { PricingService } from '../pricing/pricing.service.js';

export interface CartItem {
  sku: string;
  name: string;
  basePrice: number;
  quantity: number;
}

export class CheckoutService {
  constructor(private pricing = new PricingService()) {}

  processCheckout(items: CartItem[], taxRate: number): { items: any[]; total: number } {
    const calculatedItems = items.map(item => {
      const unitFinal = this.pricing.calculateItemPrice(item.basePrice, taxRate);
      return {
        ...item,
        unitFinal,
        subtotal: unitFinal * item.quantity,
      };
    });

    const total = this.pricing.calculateTotal(calculatedItems.map(i => i.subtotal));
    return { items: calculatedItems, total };
  }
}
