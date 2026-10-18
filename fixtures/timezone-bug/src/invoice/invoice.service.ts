import { DateService } from '../date/date.service.js';
import { Invoice, InvoiceItem } from './invoice.model.js';
import { InvoiceRepository } from './invoice.repository.js';
import { calculateSubtotal, calculateTax } from './invoice.calculator.js';

export interface GenerateInvoiceParams {
  customerId: string;
  timestamp: Date;
  timezone: string;
  items: Array<{ description: string; unitPrice: number; quantity: number }>;
  taxRate?: number;
  currency?: string;
}

export class InvoiceService {
  constructor(
    private dateService: DateService,
    private repository: InvoiceRepository = new InvoiceRepository()
  ) {}

  generateInvoice(params: GenerateInvoiceParams): Invoice {
    const items: InvoiceItem[] = params.items.map((it, idx) => ({
      id: `item_${idx + 1}`,
      description: it.description,
      unitPrice: it.unitPrice,
      quantity: it.quantity,
      total: it.unitPrice * it.quantity,
    }));

    const subtotal = calculateSubtotal(items);
    const taxRate = params.taxRate ?? 0.18;
    const taxAmount = calculateTax(subtotal, taxRate);
    const totalAmount = subtotal + taxAmount;

    // Critical call: uses dateService to get issueDate in customer timezone
    const issueDate = this.dateService.formatInvoiceDate(params.timestamp, params.timezone);
    const dueDate = this.dateService.formatDueDate(params.timestamp, 30, params.timezone);

    const invoice: Invoice = {
      id: `inv_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
      invoiceNumber: `INV-2026-${Math.floor(1000 + Math.random() * 9000)}`,
      customerId: params.customerId,
      issueDate,
      dueDate,
      items,
      subtotal,
      taxAmount,
      totalAmount,
      currency: params.currency || 'INR',
      status: 'ISSUED',
      timezone: params.timezone,
    };

    return invoice;
  }
}
