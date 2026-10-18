import { CurrencyService } from './currency.service.js';
import { TaxService } from './tax.service.js';

export class BillingService {
  constructor(
    private currencyService = new CurrencyService(),
    private taxService = new TaxService()
  ) {}

  getSummary(amount: number, stateCode: string) {
    const tax = this.taxService.getGstRate(stateCode);
    return {
      formatted: this.currencyService.format(amount),
      tax,
    };
  }
}
