import { describe, it, expect } from 'vitest';
import { ProductRepository } from '../src/catalog/product.repository.js';

describe('Catalog Module', () => {
  it('finds product by sku', () => {
    const repo = new ProductRepository();
    const prod = repo.findProduct('SKU_SHIRT');
    expect(prod?.name).toBe('Premium Linen Shirt');
  });
});
