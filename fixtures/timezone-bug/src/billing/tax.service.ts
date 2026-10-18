export class TaxService {
  getGstRate(stateCode: string): { cgst: number; sgst: number; igst: number } {
    if (stateCode === 'MH') return { cgst: 0.09, sgst: 0.09, igst: 0 };
    return { cgst: 0, sgst: 0, igst: 0.18 };
  }
}
