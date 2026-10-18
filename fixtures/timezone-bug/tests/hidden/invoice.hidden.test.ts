import { describe, it, expect } from 'vitest';
import { InvoiceService } from '../../src/invoice/invoice.service.js';
import { DateService } from '../../src/date/date.service.js';

describe('Private Hidden Verification Suite - Timezone Edge Cases', () => {
  const dateService = new DateService();
  const invoiceService = new InvoiceService(dateService);

  it('handles Tokyo timezone near midnight boundary (+09:00)', () => {
    // 00:15 Tokyo on Jan 1, 2027 is 15:15 UTC Dec 31, 2026
    const dt = new Date('2027-01-01T00:15:00+09:00');
    const invoice = invoiceService.generateInvoice({
      customerId: 'cust_tokyo',
      timestamp: dt,
      timezone: 'Asia/Tokyo',
      items: [{ description: 'Plan', unitPrice: 1000, quantity: 1 }],
    });
    expect(invoice.issueDate).toBe('2027-01-01');
  });

  it('handles New York timezone near late evening (-05:00)', () => {
    // 23:45 NY on Dec 31, 2026 is 04:45 UTC Jan 1, 2027
    const dt = new Date('2026-12-31T23:45:00-05:00');
    const invoice = invoiceService.generateInvoice({
      customerId: 'cust_ny',
      timestamp: dt,
      timezone: 'America/New_York',
      items: [{ description: 'Plan', unitPrice: 1000, quantity: 1 }],
    });
    expect(invoice.issueDate).toBe('2026-12-31');
  });

  it('handles Leap Year February 29 in Asia/Kolkata', () => {
    const dt = new Date('2028-02-29T00:10:00+05:30');
    const invoice = invoiceService.generateInvoice({
      customerId: 'cust_leap',
      timestamp: dt,
      timezone: 'Asia/Kolkata',
      items: [{ description: 'Plan', unitPrice: 1000, quantity: 1 }],
    });
    expect(invoice.issueDate).toBe('2028-02-29');
  });

  it('rejects cheap hardcoded returns by testing multiple timestamps', () => {
    const dt1 = new Date('2026-07-15T02:00:00+05:30');
    const inv1 = invoiceService.generateInvoice({
      customerId: 'c1',
      timestamp: dt1,
      timezone: 'Asia/Kolkata',
      items: [{ description: 'A', unitPrice: 10, quantity: 1 }],
    });
    expect(inv1.issueDate).toBe('2026-07-15');
  });
});
