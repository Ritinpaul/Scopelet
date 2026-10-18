import { describe, it, expect } from 'vitest';
import { PermissionsService } from '../src/auth/permissions.service.js';

describe('Auth Module', () => {
  it('allows billing manager to manage invoices', () => {
    const perms = new PermissionsService();
    expect(perms.can('BILLING_MANAGER', 'invoice:create')).toBe(true);
    expect(perms.can('USER', 'invoice:create')).toBe(false);
  });
});
