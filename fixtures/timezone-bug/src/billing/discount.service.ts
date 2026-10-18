export class DiscountService {
  getDiscountForVolume(quantity: number): number {
    return quantity > 10 ? 0.1 : 0.0;
  }
}
