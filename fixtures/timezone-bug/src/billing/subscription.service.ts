export class SubscriptionService {
  isActive(status: string): boolean {
    return status === 'ACTIVE';
  }
}
