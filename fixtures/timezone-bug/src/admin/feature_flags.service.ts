export class FeatureFlagsService {
  isEnabled(flag: string): boolean {
    return flag === 'new_invoicing';
  }
}
