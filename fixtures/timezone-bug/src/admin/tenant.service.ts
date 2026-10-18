export class TenantService {
  getTenantIsolationDomain(tenantId: string): string {
    return `${tenantId}.internal.cloud`;
  }
}
