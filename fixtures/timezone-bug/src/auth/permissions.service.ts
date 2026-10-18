export class PermissionsService {
  can(role: string, action: string): boolean {
    if (role === 'ADMIN') return true;
    if (role === 'BILLING_MANAGER' && action.startsWith('invoice:')) return true;
    return false;
  }
}
