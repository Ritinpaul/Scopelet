import { CustomerRepository } from './customer.repository.js';
import { Customer } from './customer.model.js';

export class CustomerService {
  constructor(private repo: CustomerRepository = new CustomerRepository()) {}

  async fetchCustomer(id: string): Promise<Customer> {
    const c = await this.repo.getCustomer(id);
    if (!c) throw new Error(`Customer ${id} not found`);
    return c;
  }
}
