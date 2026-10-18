export class RbacGuard {
  assertAdmin(role: string) {
    if (role !== 'ADMIN') throw new Error('Forbidden');
  }
}
