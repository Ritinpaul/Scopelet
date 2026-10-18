import React, { useRef, useEffect } from 'react';
import { Terminal, Copy, Check, Trash2 } from 'lucide-react';
import type { LogEntry } from '../types';

interface TerminalLogProps {
  logs: LogEntry[];
  onClear: () => void;
}

export const TerminalLog: React.FC<TerminalLogProps> = ({ logs, onClear }) => {
  const [copied, setCopied] = React.useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const copyLogs = () => {
    const text = logs.map(l => `[${l.timestamp}] [${l.level.toUpperCase()}] [${l.phase}] ${l.message}`).join('\n');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getLevelColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'success': return 'var(--status-success)';
      case 'warn': return 'var(--status-warning)';
      case 'error': return 'var(--status-danger)';
      default: return 'var(--accent-cyan)';
    }
  };

  return (
    <div style={{
      backgroundColor: 'var(--bg-panel)',
      borderRadius: '8px',
      border: '1px solid var(--border-subtle)',
      overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 16px',
        backgroundColor: 'var(--bg-canvas)',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 700 }}>
          <Terminal size={15} color="var(--accent-cyan)" />
          <span>Scopelet Execution Telemetry Stream</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={copyLogs}
            title="Copy logs"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '4px 8px',
              borderRadius: '4px',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-subtle)',
              color: copied ? 'var(--status-success)' : 'var(--text-secondary)',
              fontSize: '11px',
            }}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            onClick={onClear}
            title="Clear logs"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '4px 8px',
              borderRadius: '4px',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              fontSize: '11px',
            }}
          >
            <Trash2 size={12} />
            Clear
          </button>
        </div>
      </div>

      <div style={{
        maxHeight: '240px',
        overflowY: 'auto',
        padding: '12px 16px',
        fontFamily: 'var(--font-mono)',
        fontSize: '11px',
        lineHeight: 1.6,
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
        backgroundColor: '#05070D',
      }}>
        {logs.map((log) => (
          <div key={log.id} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
            <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{log.timestamp}</span>
            <span style={{
              color: getLevelColor(log.level),
              fontWeight: 700,
              flexShrink: 0,
              width: '54px',
            }}>
              [{log.level.toUpperCase()}]
            </span>
            <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>[{log.phase}]</span>
            <span style={{ color: 'var(--text-primary)', wordBreak: 'break-word' }}>{log.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};
