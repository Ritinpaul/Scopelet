import { formatToTimezoneDate } from './timezone.js';

export class DateFormatter {
  static toCalendarDate(date: Date, timezone: string): string {
    return formatToTimezoneDate(date, timezone);
  }

  static toIso(date: Date): string {
    return date.toISOString();
  }
}
