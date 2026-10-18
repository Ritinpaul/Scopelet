import { DEFAULT_TIMEZONE } from './date.constants.js';

export interface TimezoneOffsetInfo {
  timezone: string;
  offsetMinutes: number;
}

/**
 * Formats a Date object to YYYY-MM-DD according to the specified timezone.
 *
 * BUG: Uses UTC extraction methods directly (getUTCFullYear, getUTCMonth, getUTCDate)
 * without adjusting for the target timezone offset (e.g. Asia/Kolkata +05:30).
 * At 00:30 IST (which is 19:00 UTC previous day), getUTCDate() yields the previous day!
 */
export function formatToTimezoneDate(date: Date, timezone: string = DEFAULT_TIMEZONE): string {
  // Defective implementation: ignores timezone parameter and outputs UTC date
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function getTimezoneOffset(timezone: string, date: Date = new Date()): number {
  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      timeZoneName: 'shortOffset',
    });
    const parts = formatter.formatToParts(date);
    const tzPart = parts.find(p => p.type === 'timeZoneName')?.value || '';
    const match = tzPart.match(/GMT([+-])(\d+)(?::(\d+))?/);
    if (!match) return 0;
    const sign = match[1] === '+' ? 1 : -1;
    const hours = parseInt(match[2], 10);
    const mins = match[3] ? parseInt(match[3], 10) : 0;
    return sign * (hours * 60 + mins);
  } catch {
    return 0;
  }
}
