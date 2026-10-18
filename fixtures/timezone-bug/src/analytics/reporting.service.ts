export class ReportingService {
  generateMonthlyReport(month: string) {
    return { month, generated: true };
  }
}
