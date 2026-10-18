import { Invoice } from './invoice.model.js';

export class InvoiceRepository {
  private invoices = new Map<string, Invoice>();

  async save(invoice: Invoice): Promise<Invoice> {
    this.invoices.set(invoice.id, { ...invoice });
    return invoice;
  }

  async findById(id: string): Promise<Invoice | null> {
    return this.invoices.get(id) || null;
  }

  async listByCustomer(customerId: string): Promise<Invoice[]> {
    return Array.from(this.invoices.values()).filter(inv => inv.customerId === customerId);
  }
}
