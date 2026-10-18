import { InvoiceItem } from './invoice.model.js';

export function calculateSubtotal(items: InvoiceItem[]): number {
  return items.reduce((acc, item) => acc + item.total, 0);
}

export function calculateTax(subtotal: number, taxRate: number): number {
  return Math.round(subtotal * taxRate * 100) / 100;
}
