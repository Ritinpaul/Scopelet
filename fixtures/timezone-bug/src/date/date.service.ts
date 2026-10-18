import { DateFormatter } from './date.formatter.js';
import { formatToTimezoneDate } from './timezone.js';

export class DateService {
  formatInvoiceDate(timestamp: Date, timezone: string): string {
    return DateFormatter.toCalendarDate(timestamp, timezone);
  }

  formatDueDate(timestamp: Date, daysAhead: number, timezone: string): string {
    const due = new Date(timestamp.getTime() + daysAhead * 24 * 60 * 60 * 1000);
    return formatToTimezoneDate(due, timezone);
  }
}
