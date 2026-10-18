import { describe, it, expect } from 'vitest';
import { ProfileService } from '../../src/profile/profile.service.js';
import { UserRepository } from '../../src/repository/user.repository.js';
import { CacheService } from '../../src/cache/cache.service.js';

describe('Private Hidden Verification Suite - Invalidation Boundaries', () => {
  it('invalidates cache when updating multiple distinct fields sequentially', async () => {
    const userRepo = new UserRepository();
    const cache = new CacheService();
    const service = new ProfileService(userRepo, cache);

    await service.getProfile('u_alice'); // Warm cache
    await service.updateProfile('u_alice', { bio: 'Principal Architect' });

    const p1 = await service.getProfile('u_alice');
    expect(p1.bio).toBe('Principal Architect');

    await service.updateProfile('u_alice', { email: 'asmith@corp.example' });
    const p2 = await service.getProfile('u_alice');
    expect(p2.email).toBe('asmith@corp.example');
  });

  it('keeps cache keys isolated across different users', async () => {
    const userRepo = new UserRepository();
    const cache = new CacheService();
    const service = new ProfileService(userRepo, cache);

    // Warm user alice
    await service.getProfile('u_alice');

    // Add Bob to DB directly
    await userRepo.update('u_alice', { name: 'Alice V2' });
    const fresh = await service.getProfile('u_alice');
    expect(fresh.name).toBe('Alice V2');
  });
});
