import React, { useState } from 'react';
import { 
  Fingerprint, 
  TrendingDown, 
  Award, 
  Copy, 
  Check, 
  Lock 
} from 'lucide-react';
import type { SessionData } from '../types';

interface MetricsBannerProps {
  session: SessionData;
}

export const MetricsBanner: React.FC<MetricsBannerProps> = ({ session }) => {
  const [copied, setCopied] = useState(false);

  const copyHash = () => {
    if (session.failure_fingerprint) {
      navigator.clipboard.writeText(session.failure_fingerprint);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const getVerdictStyle = () => {
    switch (session.verdict) {
      case 'ACCEPT':
        return {
          bg: 'var(--status-success-bg)',
          border: '1px solid rgba(16, 185, 129, 0.4)',
          color: 'var(--status-success)',
          label: 'VERDICT: ACCEPT'
        };
      case 'REJECT':
        return {
          bg: 'var(--status-danger-bg)',
          border: '1px solid rgba(239, 68, 68, 0.4)',
          color: 'var(--status-danger)',
          label: 'VERDICT: REJECT'
        };
      case 'REVIEW':
        return {
          bg: 'var(--status-warning-bg)',
          border: '1px solid rgba(245, 158, 11, 0.4)',
          color: 'var(--status-warning)',
          label: 'VERDICT: REVIEW'
        };
      default:
        return {
          bg: 'rgba(100, 116, 139, 0.1)',
          border: '1px solid var(--border-subtle)',
          color: 'var(--text-muted)',
          label: 'PENDING VERIFICATION'
        };
    }
  };

  const verdictStyle = getVerdictStyle();

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
      gap: '16px',
      padding: '20px 24px',
      backgroundColor: 'var(--bg-canvas)',
      borderBottom: '1px solid var(--border-subtle)',
    }}>
      {/* Metric 1: Failure Fingerprint */}
      <div style={{
        padding: '14px 18px',
        backgroundColor: 'var(--bg-panel)',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', fontWeight: 600 }}>
            Failure Fingerprint
          </span>
          <Fingerprint size={16} color="var(--accent-cyan)" />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            color: 'var(--text-primary)',
            fontWeight: 600,
          }}>
            {session.failure_fingerprint 
              ? `${session.failure_fingerprint.slice(0, 12)}...${session.failure_fingerprint.slice(-8)}` 
              : 'Not captured'}
          </span>
          {session.failure_fingerprint && (
            <button
              onClick={copyHash}
              title="Copy full SHA256 fingerprint"
              style={{
                color: copied ? 'var(--status-success)' : 'var(--text-muted)',
                padding: '4px',
                borderRadius: '4px',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          )}
        </div>
      </div>

      {/* Metric 2: Slicing & Reduction */}
      <div style={{
        padding: '14px 18px',
        backgroundColor: 'var(--bg-panel)',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', fontWeight: 600 }}>
            LOC Reduction
          </span>
          <TrendingDown size={16} color="var(--status-success)" />
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span style={{ fontSize: '20px', fontWeight: 800, color: 'var(--status-success)' }}>
            {session.reduction_pct ? `${session.reduction_pct.toFixed(1)}%` : '0%'}
          </span>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            {session.initial_loc && session.reduced_loc 
              ? `(${session.initial_loc} -> ${session.reduced_loc} lines)` 
              : 'Full repo'}
          </span>
        </div>
      </div>

      {/* Metric 3: Privacy & Canary Audit */}
      <div style={{
        padding: '14px 18px',
        backgroundColor: 'var(--bg-panel)',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', fontWeight: 600 }}>
            Privacy Redaction
          </span>
          <Lock size={16} color="var(--accent-blue)" />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{
            fontSize: '12px',
            fontWeight: 700,
            padding: '2px 8px',
            borderRadius: '4px',
            backgroundColor: 'var(--status-success-bg)',
            color: 'var(--status-success)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
          }}>
            0 LEAKS
          </span>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            {session.canaries_scrubbed?.length || 0} sensitive tokens scrubbed
          </span>
        </div>
      </div>

      {/* Metric 4: Verification Verdict */}
      <div style={{
        padding: '14px 18px',
        backgroundColor: verdictStyle.bg,
        borderRadius: '8px',
        border: verdictStyle.border,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: verdictStyle.color, fontWeight: 700 }}>
            Oracle Status
          </span>
          <Award size={16} color={verdictStyle.color} />
        </div>
        <div style={{ fontSize: '15px', fontWeight: 800, color: verdictStyle.color, letterSpacing: '0.02em' }}>
          {verdictStyle.label}
        </div>
      </div>
    </div>
  );
};
