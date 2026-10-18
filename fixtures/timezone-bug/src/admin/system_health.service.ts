export class SystemHealthService {
  check() { return { status: 'HEALTHY', uptime: process.uptime() }; }
}
