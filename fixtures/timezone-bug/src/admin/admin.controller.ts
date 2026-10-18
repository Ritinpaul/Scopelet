import { SystemHealthService } from './system_health.service.js';

export class AdminController {
  constructor(private health = new SystemHealthService()) {}
  getHealth() { return this.health.check(); }
}
