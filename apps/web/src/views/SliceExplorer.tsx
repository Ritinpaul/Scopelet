import React, { useState } from 'react';
import { GitFork, Layers, CheckCircle2, ShieldCheck, Activity } from 'lucide-react';
import type { SessionData } from '../types';

interface SliceExplorerProps {
  session: SessionData;
}

export const SliceExplorer: React.FC<SliceExplorerProps> = ({ session }) => {
  const [filter, setFilter] = useState<'all' | 'retained' | 'culled'>('all');

  const staticCandidates = session.static_candidates || [];
  const dynamicExecuted = session.dynamic_executed || [];
  const protectedFrames = session.protected_frames || [];
  const activeFiles = session.active_files || session.combined_slice || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Slicing Breakdown Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '16px',
      }}>
        {/* Tier 1: Static Graph */}
        <div style={{
          padding: '16px',
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 600 }}>
              Static AST Graph
            </span>
            <GitFork size={15} color="var(--accent-blue)" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--accent-blue)' }}>
            {staticCandidates.length} <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-muted)' }}>files</span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Transitively reachable from test imports
          </div>
        </div>

        {/* Tier 2: Dynamic Coverage */}
        <div style={{
          padding: '16px',
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 600 }}>
              Dynamic V8 Coverage
            </span>
            <Activity size={15} color="var(--accent-cyan)" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--accent-cyan)' }}>
            {dynamicExecuted.length} <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-muted)' }}>files</span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Actually executed during failing test run
          </div>
        </div>

        {/* Tier 3: Protected Stack Frames */}
        <div style={{
          padding: '16px',
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 600 }}>
              Protected Frames
            </span>
            <ShieldCheck size={15} color="var(--status-warning)" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--status-warning)' }}>
            {protectedFrames.length} <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-muted)' }}>files</span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Never removed during delta debugging
          </div>
        </div>

        {/* Tier 4: Final Reduced Slice */}
        <div style={{
          padding: '16px',
          backgroundColor: 'var(--bg-panel)',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 600 }}>
              Final Capsule Slice
            </span>
            <Layers size={15} color="var(--status-success)" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 800, color: 'var(--status-success)' }}>
            {activeFiles.length} <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-muted)' }}>files</span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Reproduces exact same failure fingerprint
          </div>
        </div>
      </div>

      {/* Candidate File Inspector */}
      <div style={{
        backgroundColor: 'var(--bg-panel)',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        padding: '20px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <div style={{ fontSize: '15px', fontWeight: 700 }}>Candidate Repository Slices &amp; Decisions</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Inspect why files were included or excluded from the reproduction capsule</div>
          </div>

          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              onClick={() => setFilter('all')}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 600,
                backgroundColor: filter === 'all' ? 'var(--accent-cyan)' : 'var(--bg-canvas)',
                color: filter === 'all' ? '#070A11' : 'var(--text-secondary)',
              }}
            >
              All Files ({staticCandidates.length})
            </button>
            <button
              onClick={() => setFilter('retained')}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 600,
                backgroundColor: filter === 'retained' ? 'var(--status-success)' : 'var(--bg-canvas)',
                color: filter === 'retained' ? '#070A11' : 'var(--text-secondary)',
              }}
            >
              Retained ({activeFiles.length})
            </button>
            <button
              onClick={() => setFilter('culled')}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 600,
                backgroundColor: filter === 'culled' ? 'var(--status-danger)' : 'var(--bg-canvas)',
                color: filter === 'culled' ? '#FFFFFF' : 'var(--text-secondary)',
              }}
            >
              Culled ({Math.max(0, staticCandidates.length - activeFiles.length)})
            </button>
          </div>
        </div>

        <div style={{
          border: '1px solid var(--border-subtle)',
          borderRadius: '6px',
          overflow: 'hidden',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-canvas)', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '10px 14px' }}>FILE PATH</th>
                <th style={{ padding: '10px 14px' }}>STATIC</th>
                <th style={{ padding: '10px 14px' }}>DYNAMIC TRACE</th>
                <th style={{ padding: '10px 14px' }}>STACK FRAME</th>
                <th style={{ padding: '10px 14px' }}>CAPSULE STATUS</th>
              </tr>
            </thead>
            <tbody>
              {staticCandidates
                .filter(file => {
                  const isRetained = activeFiles.includes(file);
                  if (filter === 'retained') return isRetained;
                  if (filter === 'culled') return !isRetained;
                  return true;
                })
                .map((file, i) => {
                  const isDynamic = dynamicExecuted.includes(file);
                  const isProtected = protectedFrames.some(f => f.includes(file));
                  const isRetained = activeFiles.includes(file);

                  return (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border-subtle)', backgroundColor: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                      <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)', color: isRetained ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                        {file}
                      </td>
                      <td style={{ padding: '10px 14px', color: 'var(--accent-blue)' }}>
                        <CheckCircle2 size={14} />
                      </td>
                      <td style={{ padding: '10px 14px', color: isDynamic ? 'var(--accent-cyan)' : 'var(--text-muted)' }}>
                        {isDynamic ? <CheckCircle2 size={14} /> : <span style={{ opacity: 0.3 }}>—</span>}
                      </td>
                      <td style={{ padding: '10px 14px', color: isProtected ? 'var(--status-warning)' : 'var(--text-muted)' }}>
                        {isProtected ? <CheckCircle2 size={14} /> : <span style={{ opacity: 0.3 }}>—</span>}
                      </td>
                      <td style={{ padding: '10px 14px' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: 700,
                          backgroundColor: isRetained ? 'var(--status-success-bg)' : 'var(--status-danger-bg)',
                          color: isRetained ? 'var(--status-success)' : 'var(--status-danger)',
                        }}>
                          {isRetained ? 'INCLUDED' : 'CULLED (DD)'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
