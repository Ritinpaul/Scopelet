import { describe, it, expect } from 'vitest';
import { InvoiceService } from '../src/invoice/invoice.service.js';
import { DateService } from '../src/date/date.service.js';

describe('Invoice Timezone Generation', () => {
  it('generates correct calendar date for invoice created at 00:30 IST', () => {
    const dateService = new DateService();
    const invoiceService = new InvoiceService(dateService);

    // 00:30 on October 18, 2026 IST (+05:30) is 19:00 UTC on October 17, 2026.
    const billingTime = new Date('2026-10-18T00:30:00+05:30');

    const invoice = invoiceService.generateInvoice({
      customerId: 'cust_1',
      timestamp: billingTime,
      timezone: 'Asia/Kolkata',
      items: [{ description: 'SaaS Pro Monthly Subscription', unitPrice: 2499, quantity: 1 }],
    });

    // In customer's timezone (Asia/Kolkata), the date is October 18, 2026.
    // The defective implementation erroneously produces "2026-10-17".
    expect(invoice.issueDate).toBe('2026-10-18');
  });
});
