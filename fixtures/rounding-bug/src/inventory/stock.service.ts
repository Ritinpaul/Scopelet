export class StockService {
  isAvailable(sku: string, qty: number): boolean { return qty <= 50; }
}
