export type PipelinePhase = 
  | 'idle'
  | 'capture'
  | 'analyze'
  | 'reduce'
  | 'sanitize'
  | 'review'
  | 'export'
  | 'verify'
  | 'completed';

export type Verdict = 'ACCEPT' | 'REJECT' | 'REVIEW';

export interface SymbolMapping {
  original: string;
  obfuscated: string;
  kind: 'function' | 'variable' | 'class' | 'type' | 'module';
  references: number;
}

export interface CanaryFinding {
  category: 'api_key' | 'jwt' | 'email' | 'db_url' | 'customer_name' | 'base64' | 'pii';
  raw_token: string;
  masked_token: string;
  location: string;
  status: 'scrubbed' | 'quarantined';
}

export interface TestResult {
  name: string;
  passed: boolean;
  duration_ms: number;
  output?: string;
}

export interface SessionData {
  id: string;
  name: string;
  workspace_dir: string;
  test_command: string;
  current_phase: PipelinePhase;
  created_at: string;
  
  // Phase 1: Capture
  failure_fingerprint?: string;
  exit_code?: number;
  stack_frames?: string[];
  failure_output?: string;
  
  // Phase 2: Slice Analysis
  static_candidates?: string[];
  dynamic_executed?: string[];
  protected_frames?: string[];
  combined_slice?: string[];
  
  // Phase 3: Reduction
  initial_files?: number;
  initial_loc?: number;
  reduced_files?: number;
  reduced_loc?: number;
  reduction_pct?: number;
  reducer_evaluations?: number;
  active_files?: string[];
  
  // Phase 4: Sanitization
  symbol_mappings?: SymbolMapping[];
  canaries_scrubbed?: CanaryFinding[];
  token_overlap_pct?: number;
  privacy_approved?: boolean;
  
  // Phase 5: Capsule
  capsule_hash?: string;
  capsule_size_bytes?: number;
  task_spec?: {
    title: string;
    command: string;
    allowed_changes: string[];
    runtime: { node: string };
    network_allowed: boolean;
  };
  
  // Phase 6: Verification
  verdict?: Verdict;
  solution_patch?: string;
  test_matrix?: {
    target_failing_test: TestResult;
    hidden_regression_test: TestResult;
    full_test_suite: TestResult;
    boundary_policy_checks: {
      no_test_modifications: boolean;
      no_package_json_drift: boolean;
      no_network_additions: boolean;
      diff_within_bounds: boolean;
    };
  };
  rejection_reasons?: string[];
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: 'info' | 'success' | 'warn' | 'error';
  phase: PipelinePhase;
  message: string;
}
