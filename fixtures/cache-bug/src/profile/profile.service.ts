import { UserRepository, UserRecord } from '../repository/user.repository.js';
import { CacheService } from '../cache/cache.service.js';

export class ProfileService {
  constructor(
    private userRepo: UserRepository,
    private cache: CacheService
  ) {}

  async getProfile(userId: string): Promise<UserRecord> {
    const cacheKey = `user:profile:${userId}`;
    const cached = await this.cache.get<UserRecord>(cacheKey);
    if (cached) {
      return cached;
    }

    const user = await this.userRepo.findById(userId);
    if (!user) throw new Error(`User not found: ${userId}`);

    // Cache for 60 seconds
    await this.cache.set(cacheKey, user, 60);
    return user;
  }

  /**
   * Updates user profile in DB.
   *
   * BUG: Omits cache invalidation (`await this.cache.delete(cacheKey)`).
   * As a result, subsequent calls to getProfile continue returning the stale
   * cached record for 60 seconds!
   */
  async updateProfile(userId: string, updates: Partial<UserRecord>): Promise<UserRecord> {
    const updated = await this.userRepo.update(userId, updates);
    // Defect: Cache entry is NOT deleted or refreshed!
    // await this.cache.delete(`user:profile:${userId}`); <-- MISSING
    return updated;
  }
}
