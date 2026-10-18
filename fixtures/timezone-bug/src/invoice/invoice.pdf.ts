import { Invoice } from './invoice.model.js';

export class InvoicePdfRenderer {
  renderToBuffer(invoice: Invoice): Buffer {
    const raw = `INVOICE:${invoice.invoiceNumber}|DATE:${invoice.issueDate}|TOTAL:${invoice.totalAmount}`;
    return Buffer.from(raw, 'utf-8');
  }
}
