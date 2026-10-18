import type { SessionData } from './types';

export const INITIAL_SESSIONS: Record<string, SessionData> = {
  'session-tz-01': {
    id: 'session-tz-01',
    name: 'Fixture A: Timezone Formatting Defect',
    workspace_dir: 'fixtures/timezone-bug',
    test_command: 'npm test',
    current_phase: 'completed',
    created_at: new Date(Date.now() - 3600000).toISOString(),
    
    // Capture
    failure_fingerprint: 'a87f1c90d3e2154bb39f098231fa6b87201c90a187b46d92ec1734919cb2ef81',
    exit_code: 1,
    stack_frames: [
      'src/date/timezone.ts:16:3',
      'src/billing/invoice.service.ts:42:15',
      'tests/invoice.timezone.test.ts:28:10'
    ],
    failure_output: 'FAIL tests/invoice.timezone.test.ts\n  ● Invoice Timezone Generation › should format date in Asia/Kolkata timezone\n    Expected: "2026-10-18"\n    Received: "2026-10-17"\n      14 |   const inv = generateInvoice(testOrder, "Asia/Kolkata");\n    > 15 |   expect(inv.dateStr).toBe("2026-10-18");\n         |                       ^\n',
    
    // Slicing
    static_candidates: [
      'src/date/timezone.ts',
      'src/billing/invoice.service.ts',
      'src/billing/plans.config.ts',
      'src/analytics/telemetry.service.ts',
      'src/auth/jwt.verifier.ts',
      'src/db/connection.pool.ts',
      'tests/invoice.timezone.test.ts'
    ],
    dynamic_executed: [
      'src/date/timezone.ts',
      'src/billing/invoice.service.ts',
      'tests/invoice.timezone.test.ts'
    ],
    protected_frames: [
      'src/date/timezone.ts',
      'src/billing/invoice.service.ts',
      'tests/invoice.timezone.test.ts'
    ],
    combined_slice: [
      'src/date/timezone.ts',
      'src/billing/invoice.service.ts',
      'tests/invoice.timezone.test.ts'
    ],
    
    // Reduction
    initial_files: 28,
    initial_loc: 1420,
    reduced_files: 3,
    reduced_loc: 168,
    reduction_pct: 88.17,
    reducer_evaluations: 14,
    active_files: [
      'src/date/timezone.ts',
      'src/billing/invoice.service.ts',
      'tests/invoice.timezone.test.ts'
    ],
    
    // Sanitization
    symbol_mappings: [
      { original: 'CUSTOMER_PROJECT_NEBULA_7429', obfuscated: 'SYM_PROJ_001', kind: 'variable', references: 4 },
      { original: 'INTERNAL_PRICING_ALGORITHM', obfuscated: 'sym_pricing_fn', kind: 'function', references: 2 },
      { original: 'BillingAccountRecord', obfuscated: 'EntityRecord_09', kind: 'type', references: 7 },
      { original: 'generateInternalInvoiceId', obfuscated: 'generateId_fn_3', kind: 'function', references: 5 },
      { original: 'sk_live_fake_SECRET_123', obfuscated: '[REDACTED_API_KEY]', kind: 'variable', references: 1 }
    ],
    canaries_scrubbed: [
      { category: 'api_key', raw_token: 'sk_live_fake_SECRET_123', masked_token: 'sk_live_***REDACTED***', location: 'src/billing/plans.config.ts:8', status: 'scrubbed' },
      { category: 'jwt', raw_token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.fake_token_sign', masked_token: 'eyJhbGci***REDACTED***', location: 'src/auth/jwt.verifier.ts:12', status: 'scrubbed' },
      { category: 'customer_name', raw_token: 'CUSTOMER_PROJECT_NEBULA_7429', masked_token: 'CUSTOMER_***_REDACTED', location: 'src/billing/invoice.service.ts:4', status: 'scrubbed' },
      { category: 'db_url', raw_token: 'postgres://admin:pwd@internal-db.corp.net/prod', masked_token: 'postgres://***REDACTED***', location: 'src/db/connection.pool.ts:2', status: 'scrubbed' }
    ],
    token_overlap_pct: 1.4,
    privacy_approved: true,
    
    // Capsule
    capsule_hash: '90f9b3ec702581c7ba12001a1efcd580c851167b558d19762dfb37c63b400912',
    capsule_size_bytes: 28410,
    task_spec: {
      title: 'Timezone Formatting Offset Defect',
      command: 'npm test -- invoice-timezone',
      allowed_changes: ['src/date/timezone.ts'],
      runtime: { node: '22' },
      network_allowed: false
    },
    
    // Verification
    verdict: 'ACCEPT',
    solution_patch: `--- a/src/date/timezone.ts
+++ b/src/date/timezone.ts
@@ -15,7 +15,11 @@
 export function formatToTimezoneDate(date: Date, timezone: string = DEFAULT_TIMEZONE): string {
-  const year = date.getUTCFullYear();
-  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
-  const day = String(date.getUTCDate()).padStart(2, '0');
-  return \`\${year}-\${month}-\${day}\`;
+  const formatter = new Intl.DateTimeFormat('en-CA', {
+    timeZone: timezone,
+    year: 'numeric',
+    month: '2-digit',
+    day: '2-digit',
+  });
  return formatter.format(date);
 }`,
    test_matrix: {
      target_failing_test: { name: 'invoice.timezone.test.ts', passed: true, duration_ms: 182, output: '1 test passed' },
      hidden_regression_test: { name: 'invoice.hidden.test.ts (Oracle)', passed: true, duration_ms: 245, output: '3 tests passed (DST & Month Boundaries)' },
      full_test_suite: { name: 'Full Test Suite', passed: true, duration_ms: 610, output: '14 tests passed, 0 failed' },
      boundary_policy_checks: {
        no_test_modifications: true,
        no_package_json_drift: true,
        no_network_additions: true,
        diff_within_bounds: true
      }
    },
    rejection_reasons: []
  },
  
  'session-round-02': {
    id: 'session-round-02',
    name: 'Fixture B: Currency Rounding Truncation',
    workspace_dir: 'fixtures/rounding-bug',
    test_command: 'npm test',
    current_phase: 'completed',
    created_at: new Date(Date.now() - 7200000).toISOString(),
    failure_fingerprint: '3b092ac01f92e847c1308a0d2f9b8813aef19280cdfa4298104d9c72051fba32',
    exit_code: 1,
    stack_frames: [
      'src/utils/math.utils.ts:8:3',
      'tests/rounding.test.ts:19:12'
    ],
    failure_output: 'FAIL tests/rounding.test.ts\n  ● Currency Rounding Calculation › should round half-up correctly for fractional cents\n    Expected: 249.99\n    Received: 249.98\n',
    initial_files: 18,
    initial_loc: 890,
    reduced_files: 2,
    reduced_loc: 94,
    reduction_pct: 89.44,
    symbol_mappings: [
      { original: 'roundCurrencyInternal', obfuscated: 'round_fn_01', kind: 'function', references: 6 },
      { original: 'ACC_SECRET_PAYMENT_SALT', obfuscated: '[REDACTED_SALT]', kind: 'variable', references: 1 }
    ],
    canaries_scrubbed: [
      { category: 'api_key', raw_token: 'pk_live_stripe_999901_fake', masked_token: 'pk_live_***REDACTED***', location: 'src/utils/math.utils.ts:3', status: 'scrubbed' }
    ],
    token_overlap_pct: 0.8,
    privacy_approved: true,
    capsule_hash: '2c88019ab0091ff8217730e2f9d8a11bc329a0081d0092bc491910efab7731c2',
    verdict: 'ACCEPT',
    solution_patch: `--- a/src/utils/math.utils.ts
+++ b/src/utils/math.utils.ts
@@ -7,3 +7,3 @@
 export function roundCurrency(amount: number): number {
-  return Math.floor(amount * 100) / 100;
+  return Math.round((amount + 1e-9) * 100) / 100;
 }`,
    test_matrix: {
      target_failing_test: { name: 'rounding.test.ts', passed: true, duration_ms: 120, output: '1 test passed' },
      hidden_regression_test: { name: 'rounding.hidden.test.ts (Oracle)', passed: true, duration_ms: 160, output: '4 tests passed' },
      full_test_suite: { name: 'Full Test Suite', passed: true, duration_ms: 390, output: '9 tests passed' },
      boundary_policy_checks: {
        no_test_modifications: true,
        no_package_json_drift: true,
        no_network_additions: true,
        diff_within_bounds: true
      }
    },
    rejection_reasons: []
  },

  'session-cache-03': {
    id: 'session-cache-03',
    name: 'Fixture C: In-Memory Cache Invalidation',
    workspace_dir: 'fixtures/cache-bug',
    test_command: 'npm test',
    current_phase: 'review',
    created_at: new Date(Date.now() - 1800000).toISOString(),
    failure_fingerprint: '7a1190bc9831efaa0029b9c02d189b88231efb0928a011cdba772019ff210082',
    exit_code: 1,
    stack_frames: [
      'src/cache/lru.service.ts:34:5',
      'tests/cache.test.ts:22:9'
    ],
    failure_output: 'FAIL tests/cache.test.ts\n  ● Cache Invalidation › should evict stale entries upon TTL expiration\n    Expected: undefined\n    Received: {"token":"stale_001"}\n',
    initial_files: 22,
    initial_loc: 1120,
    reduced_files: 3,
    reduced_loc: 140,
    reduction_pct: 87.5,
    symbol_mappings: [
      { original: 'LruCacheStorageEngine', obfuscated: 'StorageEngine_01', kind: 'class', references: 8 },
      { original: 'CUSTOMER_SESSION_SIGNATURE', obfuscated: 'SYM_SIG_01', kind: 'variable', references: 3 }
    ],
    canaries_scrubbed: [
      { category: 'email', raw_token: 'lead-dev@internal-secret.org', masked_token: 'lead***@***.org', location: 'src/cache/lru.service.ts:2', status: 'scrubbed' }
    ],
    token_overlap_pct: 1.2,
    privacy_approved: false,
    capsule_hash: '55b0189af0092bc719082ca110bc8911ef230a081912cc491910efab7731c2'
  }
};
