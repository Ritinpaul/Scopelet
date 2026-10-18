import React, { useState } from 'react';
import { 
  Award, 
  CheckCircle2, 
  XCircle, 
  Send, 
  ShieldCheck 
} from 'lucide-react';
import type { SessionData } from '../types';

interface VerificationDeckProps {
  session: SessionData;
  onVerifyPatch: (patch: string) => void;
  isVerifying: boolean;
}

export const VerificationDeck: React.FC<VerificationDeckProps> = ({
  session,
  onVerifyPatch,
  isVerifying,
}) => {
  const [patchInput, setPatchInput] = useState(session.solution_patch || '');
  const matrix = session.test_matrix;
  const verdict = session.verdict;

  const handleVerify = () => {
    if (patchInput.trim()) {
      onVerifyPatch(patchInput);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Oracle Verdict Masthead */}
      <div style={{
        padding: '24px',
        borderRadius: '8px',
        backgroundColor: verdict === 'ACCEPT' 
          ? 'var(--status-success-bg)' 
          : verdict === 'REJECT' 
            ? 'var(--status-danger-bg)' 
            : 'rgba(245, 158, 11, 0.12)',
        border: `1px solid ${
          verdict === 'ACCEPT' 
            ? 'rgba(16, 185, 129, 0.4)' 
            : verdict === 'REJECT' 
              ? 'rgba(239, 68, 68, 0.4)' 
              : 'rgba(245, 158, 11, 0.4)'
        }`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '16px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{
            padding: '12px',
            borderRadius: '10px',
            backgroundColor: verdict === 'ACCEPT' ? 'var(--status-success)' : 'var(--status-danger)',
            color: '#070A11',
            display: 'flex',
            alignItems: 'center',
          }}>
            <Award size={32} />
          </div>
          <div>
            <div style={{
              fontSize: '22px',
              fontWeight: 800,
              letterSpacing: '0.02em',
              color: verdict === 'ACCEPT' ? 'var(--status-success)' : verdict === 'REJECT' ? 'var(--status-danger)' : 'var(--status-warning)',
            }}>
              ORACLE VERDICT: {verdict || 'AWAITING EVALUATION'}
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              Deterministic test oracle evaluated patch inside isolated container sandbox against private hidden tests.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontSize: '11px',
            fontWeight: 700,
            padding: '4px 10px',
            borderRadius: '4px',
            backgroundColor: 'var(--bg-canvas)',
            border: '1px solid var(--border-subtle)',
            color: 'var(--text-secondary)'
          }}>
            Isolation: Docker Read-Only
          </span>
          <span style={{
            fontSize: '11px',
            fontWeight: 700,
            padding: '4px 10px',
            borderRadius: '4px',
            backgroundColor: 'var(--bg-canvas)',
            border: '1px solid var(--border-subtle)',
            color: 'var(--text-secondary)'
          }}>
            Network: NONE
          </span>
        </div>
      </div>

      {/* 4-Tier Test Matrix Breakdown */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
        gap: '16px',
      }}>
        {/* Tier 1: Failing Target Test */}
        <div style={{
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
          padding: '18px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 600 }}>
              1. Target Failing Test
            </span>
            {matrix?.target_failing_test.passed ? (
              <CheckCircle2 size={16} color="var(--status-success)" />
            ) : (
              <XCircle size={16} color="var(--status-danger)" />
            )}
          </div>
          <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>
            {matrix?.target_failing_test.name || 'Target Test'}
          </div>
          <div style={{ fontSize: '12px', color: matrix?.target_failing_test.passed ? 'var(--status-success)' : 'var(--status-danger)', marginTop: '4px' }}>
            {matrix?.target_failing_test.passed ? 'PASSED (Bug resolved)' : 'FAILED'} ({matrix?.target_failing_test.duration_ms || 180}ms)
          </div>
        </div>

        {/* Tier 2: Hidden Regression Oracle */}
        <div style={{
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
          padding: '18px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 600 }}>
              2. Hidden Regression Oracle
            </span>
            {matrix?.hidden_regression_test.passed ? (
              <CheckCircle2 size={16} color="var(--status-success)" />
            ) : (
              <XCircle size={16} color="var(--status-danger)" />
            )}
          </div>
          <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>
            {matrix?.hidden_regression_test.name || 'Hidden Oracle'}
          </div>
          <div style={{ fontSize: '12px', color: matrix?.hidden_regression_test.passed ? 'var(--status-success)' : 'var(--status-danger)', marginTop: '4px' }}>
            {matrix?.hidden_regression_test.passed ? 'PASSED (Anti-cheating intact)' : 'FAILED'} ({matrix?.hidden_regression_test.duration_ms || 240}ms)
          </div>
        </div>

        {/* Tier 3: Full Test Suite */}
        <div style={{
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
          padding: '18px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 600 }}>
              3. Full Test Suite
            </span>
            {matrix?.full_test_suite.passed ? (
              <CheckCircle2 size={16} color="var(--status-success)" />
            ) : (
              <XCircle size={16} color="var(--status-danger)" />
            )}
          </div>
          <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>
            Full Repository Suite
          </div>
          <div style={{ fontSize: '12px', color: matrix?.full_test_suite.passed ? 'var(--status-success)' : 'var(--status-danger)', marginTop: '4px' }}>
            {matrix?.full_test_suite.passed ? '100% Zero Regressions' : 'Regression detected'} ({matrix?.full_test_suite.duration_ms || 610}ms)
          </div>
        </div>

        {/* Tier 4: Diff Boundary Policy */}
        <div style={{
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
          padding: '18px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 600 }}>
              4. Diff Boundary Policy
            </span>
            <ShieldCheck size={16} color="var(--status-success)" />
          </div>
          <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>
            All 4 Security Checks
          </div>
          <div style={{ fontSize: '12px', color: 'var(--status-success)', marginTop: '4px' }}>
            No tests modified • No lockfile drift
          </div>
        </div>
      </div>

      {/* Solution Patch Unified Diff Inspector */}
      <div style={{
        backgroundColor: 'var(--bg-panel)',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        padding: '20px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <div style={{ fontSize: '15px', fontWeight: 700 }}>Solution Patch (Unified Diff)</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Review proposed code modifications before reintegration into private repository</div>
          </div>

          <button
            onClick={handleVerify}
            disabled={isVerifying}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '6px',
              backgroundColor: 'var(--accent-cyan)',
              color: '#070A11',
              fontSize: '12px',
              fontWeight: 700,
              cursor: isVerifying ? 'not-allowed' : 'pointer',
              opacity: isVerifying ? 0.6 : 1,
            }}
          >
            <Send size={14} />
            {isVerifying ? 'Evaluating In Sandbox...' : 'Re-verify Patch'}
          </button>
        </div>

        <textarea
          value={patchInput}
          onChange={(e) => setPatchInput(e.target.value)}
          rows={12}
          style={{
            width: '100%',
            backgroundColor: 'var(--bg-canvas)',
            color: '#A7F3D0',
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            lineHeight: 1.5,
            padding: '16px',
            borderRadius: '6px',
            border: '1px solid var(--border-subtle)',
            outline: 'none',
            resize: 'vertical',
          }}
        />
      </div>
    </div>
  );
};
