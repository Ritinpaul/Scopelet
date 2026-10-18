export class ShippingService {
  calculateShipping(pincode: string): number {
    return pincode.startsWith('400') ? 40 : 100;
  }
}
