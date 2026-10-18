// SECRET CANARY: Internal warehouse database identifier
export const WAREHOUSE_CANARY_ID = 'INTERNAL_WAREHOUSE_NORTH_STORE_77';

export class ProductRepository {
  private products = [
    { sku: 'SKU_SHIRT', name: 'Premium Linen Shirt', price: 211.86 },
    { sku: 'SKU_PANTS', name: 'Cotton Trousers', price: 499.00 },
  ];

  findProduct(sku: string) {
    return this.products.find(p => p.sku === sku) || null;
  }
}
