export class CurrencyService {
  format(amount: number, currency: string = 'INR'): string {
    return `${currency} ${amount.toFixed(2)}`;
  }
}
