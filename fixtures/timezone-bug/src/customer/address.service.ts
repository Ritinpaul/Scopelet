export interface CustomerAddress {
  line1: string;
  city: string;
  state: string;
  postalCode: string;
  country: string;
}

export class AddressService {
  validate(addr: CustomerAddress): boolean {
    return Boolean(addr.line1 && addr.city && addr.country);
  }
}
