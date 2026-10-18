import { CartItem } from '../checkout/checkout.service.js';

export class CartService {
  private items: CartItem[] = [];

  addItem(item: CartItem) { this.items.push(item); }
  getItems() { return [...this.items]; }
  clear() { this.items = []; }
}
