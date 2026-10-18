import { describe, it, expect } from 'vitest';
import { CartService } from '../src/cart/cart.service.js';

describe('Cart Module', () => {
  it('stores and clears items', () => {
    const cart = new CartService();
    cart.addItem({ sku: 'A', name: 'Item A', basePrice: 10, quantity: 1 });
    expect(cart.getItems().length).toBe(1);
    cart.clear();
    expect(cart.getItems().length).toBe(0);
  });
});
