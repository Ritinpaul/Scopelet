import { describe, it, expect } from 'vitest';
import { CustomerRepository } from '../src/customer/customer.repository.js';

describe('Customer Module', () => {
  it('retrieves customer by id', async () => {
    const repo = new CustomerRepository();
    const cust = await repo.getCustomer('cust_1');
    expect(cust).not.toBeNull();
    expect(cust?.name).toBe('Acme Bharat Pvt Ltd');
  });
});
