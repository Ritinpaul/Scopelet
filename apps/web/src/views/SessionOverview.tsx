import React from 'react';
import { 
  FolderLock, 
  Package, 
  Sparkles
} from 'lucide-react';
import type { SessionData, PipelinePhase } from '../types';

interface SessionOverviewProps {
  session: SessionData;
  onRunPhase: (phase: PipelinePhase) => void;
  isRunning: boolean;
}

export const SessionOverview: React.FC<SessionOverviewProps> = ({
  session,
  onRunPhase,
  isRunning,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Action Trigger Bar */}
      <div style={{
        padding: '16px 20px',
        backgroundColor: 'var(--bg-panel)',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Sparkles size={18} color="var(--accent-cyan)" />
          <div>
            <div style={{ fontSize: '14px', fontWeight: 700 }}>Interactive Lifecycle Controls</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Execute deterministic pipeline stages sequentially or re-run specific phases</div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <button
            onClick={() => onRunPhase('capture')}
            disabled={isRunning}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              backgroundColor: 'rgba(6, 182, 212, 0.12)',
              border: '1px solid rgba(6, 182, 212, 0.3)',
              color: 'var(--accent-cyan)',
              fontSize: '12px',
              fontWeight: 600,
            }}
          >
            1. Capture Baseline
          </button>
          <button
            onClick={() => onRunPhase('analyze')}
            disabled={isRunning}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              backgroundColor: 'rgba(59, 130, 246, 0.12)',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              color: 'var(--accent-blue)',
              fontSize: '12px',
              fontWeight: 600,
            }}
          >
            2. Compute Slice
          </button>
          <button
            onClick={() => onRunPhase('reduce')}
            disabled={isRunning}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              backgroundColor: 'rgba(16, 185, 129, 0.12)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              color: 'var(--status-success)',
              fontSize: '12px',
              fontWeight: 600,
            }}
          >
            3. Reduce (DD)
          </button>
          <button
            onClick={() => onRunPhase('sanitize')}
            disabled={isRunning}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              backgroundColor: 'rgba(245, 158, 11, 0.12)',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              color: 'var(--status-warning)',
              fontSize: '12px',
              fontWeight: 600,
            }}
          >
            4. Sanitize AST
          </button>
          <button
            onClick={() => onRunPhase('export')}
            disabled={isRunning}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              backgroundColor: 'rgba(168, 85, 247, 0.12)',
              border: '1px solid rgba(168, 85, 247, 0.3)',
              color: '#A855F7',
              fontSize: '12px',
              fontWeight: 600,
            }}
          >
            5. Export Capsule
          </button>
        </div>
      </div>

      {/* Split Comparison View: Host Workspace (Private) vs Capsule (Public) */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
        gap: '20px',
      }}>
        {/* Left: Private Host Repository */}
        <div style={{
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FolderLock size={18} color="var(--status-warning)" />
              <span style={{ fontWeight: 700, fontSize: '15px' }}>Private Host Workspace</span>
            </div>
            <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '4px', backgroundColor: 'rgba(245, 158, 11, 0.12)', color: 'var(--status-warning)', fontWeight: 700 }}>
              NEVER EXPORTED
            </span>
          </div>

          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            Contains full proprietary monorepo code, production credentials, database seeds, and private hidden regression tests.
          </div>

          {/* Test Command Box */}
          <div style={{ backgroundColor: 'var(--bg-canvas)', padding: '12px', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>
              Failing Test Execution
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--accent-cyan)' }}>
              $ {session.test_command}
            </div>
          </div>

          {/* Captured Stack Frames */}
          <div>
            <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '6px', color: 'var(--text-primary)' }}>
              Protected Stack Trace Frames ({session.stack_frames?.length || 0})
            </div>
            <div style={{
              backgroundColor: 'var(--bg-canvas)',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              padding: '10px 14px',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}>
              {session.stack_frames && session.stack_frames.length > 0 ? (
                session.stack_frames.map((frame, i) => (
                  <div key={i} style={{ color: i === 0 ? 'var(--status-danger)' : 'var(--text-secondary)' }}>
                    • {frame}
                  </div>
                ))
              ) : (
                <span style={{ color: 'var(--text-muted)' }}>No stack frames recorded yet. Run Capture Baseline.</span>
              )}
            </div>
          </div>

          {/* Captured Failure Output */}
          {session.failure_output && (
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '6px', color: 'var(--text-primary)' }}>
                Baseline Failure Log
              </div>
              <pre style={{
                backgroundColor: 'var(--bg-canvas)',
                padding: '12px',
                borderRadius: '6px',
                border: '1px solid var(--border-subtle)',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: 'var(--status-danger)',
                overflowX: 'auto',
                whiteSpace: 'pre-wrap',
                maxHeight: '160px',
              }}>
                {session.failure_output}
              </pre>
            </div>
          )}
        </div>

        {/* Right: Exported Capsule Artifact */}
        <div style={{
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Package size={18} color="var(--accent-cyan)" />
              <span style={{ fontWeight: 700, fontSize: '15px' }}>Standalone Scopelet Capsule</span>
            </div>
            <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '4px', backgroundColor: 'rgba(6, 182, 212, 0.12)', color: 'var(--accent-cyan)', fontWeight: 700 }}>
              STANDALONE &amp; SAFE
            </span>
          </div>

          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            Self-contained execution archive containing only the minimal reduced code slice, sanitized identifiers, and reproduction harness.
          </div>

          {/* Task.yaml constraints */}
          <div style={{ backgroundColor: 'var(--bg-canvas)', padding: '12px', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>
              task.yaml Security Policy
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '12px' }}>
              <div>Allowed files: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{session.task_spec?.allowed_changes.join(', ') || 'Auto-computed'}</span></div>
              <div>Network mode: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--status-success)' }}>ISOLATED (None)</span></div>
              <div>Runtime: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>Node {session.task_spec?.runtime.node || '22'} (read-only)</span></div>
              <div>Expected: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--status-success)' }}>test_should_pass: true</span></div>
            </div>
          </div>

          {/* Active Sliced Files */}
          <div>
            <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '6px', color: 'var(--text-primary)' }}>
              Exported File Slice ({session.active_files?.length || 0} of {session.initial_files || 0} files)
            </div>
            <div style={{
              backgroundColor: 'var(--bg-canvas)',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              padding: '10px 14px',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}>
              {session.active_files && session.active_files.length > 0 ? (
                session.active_files.map((file, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-primary)' }}>{file}</span>
                    <span style={{ fontSize: '10px', color: 'var(--status-success)', padding: '1px 6px', borderRadius: '3px', backgroundColor: 'var(--status-success-bg)' }}>
                      Retained
                    </span>
                  </div>
                ))
              ) : (
                <span style={{ color: 'var(--text-muted)' }}>Reduction not executed yet.</span>
              )}
            </div>
          </div>

          {/* Capsule Hash */}
          <div style={{ marginTop: 'auto', paddingTop: '10px', borderTop: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
            <span style={{ color: 'var(--text-muted)' }}>Capsule SHA256:</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)' }}>
              {session.capsule_hash ? `${session.capsule_hash.slice(0, 16)}...` : 'Pending export'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
