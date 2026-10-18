import { TrackerService } from './tracker.service.js';
import { MetricsCollector } from './metrics.collector.js';

export class AnalyticsService {
  constructor(
    private tracker = new TrackerService(),
    private metrics = new MetricsCollector()
  ) {}

  recordInvoiceIssued(id: string, amount: number) {
    this.tracker.track('invoice_issued', { id, amount });
    this.metrics.inc('invoices_total');
  }
}
