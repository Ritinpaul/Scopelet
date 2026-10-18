import React from 'react';
import { ShieldCheck, Terminal, Plus, Server } from 'lucide-react';
import type { SessionData } from '../types';

interface NavbarProps {
  sessions: Record<string, SessionData>;
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  isBackendOnline: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  isBackendOnline,
}) => {
  const activeSession = sessions[activeSessionId];

  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '12px 24px',
      backgroundColor: 'var(--bg-panel)',
      borderBottom: '1px solid var(--border-subtle)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
    }}>
      {/* Brand & Mission */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '6px 12px',
          backgroundColor: 'rgba(6, 182, 212, 0.08)',
          borderRadius: '8px',
          border: '1px solid rgba(6, 182, 212, 0.3)',
        }}>
          <ShieldCheck size={22} color="var(--accent-cyan)" />
          <div>
            <div style={{ fontWeight: 800, fontSize: '15px', letterSpacing: '-0.02em', color: '#FFFFFF', display: 'flex', alignItems: 'center', gap: '6px' }}>
              SCOPELET <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--accent-cyan)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Observatory</span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: 1.1 }}>
              Deterministic Reduction &amp; Verification
            </div>
          </div>
        </div>

        {/* Target Session Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <select 
            value={activeSessionId}
            onChange={(e) => onSelectSession(e.target.value)}
            style={{
              backgroundColor: 'var(--bg-canvas)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '6px',
              padding: '7px 12px',
              color: 'var(--text-primary)',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
              outline: 'none',
              minWidth: '280px',
            }}
          >
            {Object.values(sessions).map((sess) => (
              <option key={sess.id} value={sess.id}>
                {sess.name} ({sess.current_phase})
              </option>
            ))}
          </select>

          <button
            onClick={onNewSession}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: 'rgba(59, 130, 246, 0.12)',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              borderRadius: '6px',
              padding: '7px 12px',
              color: 'var(--accent-blue)',
              fontSize: '13px',
              fontWeight: 600,
              transition: 'all 0.15s ease',
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.22)'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.12)'}
          >
            <Plus size={15} />
            New Session
          </button>
        </div>
      </div>

      {/* Telemetry Status Indicators */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {activeSession && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-canvas)',
            padding: '5px 10px',
            borderRadius: '6px',
            border: '1px solid var(--border-subtle)',
            fontFamily: 'var(--font-mono)'
          }}>
            <Terminal size={14} color="var(--accent-cyan)" />
            <span>{activeSession.workspace_dir}</span>
          </div>
        )}

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          fontSize: '12px',
          fontWeight: 600,
          padding: '5px 10px',
          borderRadius: '6px',
          backgroundColor: isBackendOnline ? 'var(--status-success-bg)' : 'rgba(245, 158, 11, 0.12)',
          border: `1px solid ${isBackendOnline ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
          color: isBackendOnline ? 'var(--status-success)' : 'var(--status-warning)'
        }}>
          <Server size={14} />
          <span>{isBackendOnline ? 'REST API (Port 8000)' : 'Standalone Simulator'}</span>
        </div>
      </div>
    </header>
  );
};
