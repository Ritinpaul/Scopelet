import { describe, it, expect } from 'vitest';
import { UserRepository } from '../src/repository/user.repository.js';

describe('User Repository', () => {
  it('finds existing user in db', async () => {
    const repo = new UserRepository();
    const user = await repo.findById('u_alice');
    expect(user?.email).toBe('alice@example.com');
  });
});
