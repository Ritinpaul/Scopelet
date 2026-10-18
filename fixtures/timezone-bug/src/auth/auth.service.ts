import { JwtService } from './jwt.service.js';
import { PermissionsService } from './permissions.service.js';

export class AuthService {
  constructor(
    private jwt = new JwtService(),
    private perms = new PermissionsService()
  ) {}

  authenticate(username: string): string {
    return this.jwt.sign({ sub: username, role: 'BILLING_MANAGER' }, 'secret');
  }
}
