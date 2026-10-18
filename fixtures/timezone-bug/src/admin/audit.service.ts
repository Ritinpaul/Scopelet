export class AuditService {
  logAction(userId: string, action: string) {
    return { userId, action, time: new Date() };
  }
}
