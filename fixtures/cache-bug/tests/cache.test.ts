import { describe, it, expect } from 'vitest';
import { ProfileService } from '../src/profile/profile.service.js';
import { UserRepository } from '../src/repository/user.repository.js';
import { CacheService } from '../src/cache/cache.service.js';

describe('Profile Cache Invalidation', () => {
  it('returns updated profile immediately after update instead of stale cached data', async () => {
    const userRepo = new UserRepository();
    const cache = new CacheService();
    const profileService = new ProfileService(userRepo, cache);

    // 1. Initial fetch warms up the cache with "Alice"
    const initial = await profileService.getProfile('u_alice');
    expect(initial.name).toBe('Alice');

    // 2. Update profile name to "Alice Smith"
    await profileService.updateProfile('u_alice', { name: 'Alice Smith' });

    // 3. Immediately fetch profile again
    // Expected: "Alice Smith"
    // Defect: Cache was not invalidated, returns stale "Alice"!
    const refreshed = await profileService.getProfile('u_alice');
    expect(refreshed.name).toBe('Alice Smith');
  });
});
