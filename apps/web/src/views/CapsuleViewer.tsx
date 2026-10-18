import React, { useState } from 'react';
import { PackageCheck, Download } from 'lucide-react';
import type { SessionData } from '../types';

interface CapsuleViewerProps {
  session: SessionData;
}

export const CapsuleViewer: React.FC<CapsuleViewerProps> = ({ session }) => {
  const [activeTab, setActiveTab] = useState<'task' | 'manifest'>('task');

  const taskYamlContent = `schema_version: "1.0"
title: "${session.task_spec?.title || 'Scopelet Isolated Reproduction Capsule'}"
command: "${session.task_spec?.command || 'npm test'}"
allowed_changes:
${(session.task_spec?.allowed_changes || ['src/date/timezone.ts']).map(f => `  - ${f}`).join('\n')}
expected:
  test_should_pass: true
runtime:
  node: "${session.task_spec?.runtime.node || '22'}"
network:
  allowed: false
resource_limits:
  memory: 512m
  cpu: 0.5
  pids: 256
`;

  const manifestJsonContent = JSON.stringify({
    schema_version: "1.0",
    capsule_hash: session.capsule_hash || "90f9b3ec702581c7ba12001a1efcd580c851167b558d19762dfb37c63b400912",
    title: session.task_spec?.title || "Timezone Formatting Offset Defect",
    created_at: session.created_at,
    runtime: { node: "22" },
    command: session.task_spec?.command || "npm test",
    allowed_changes: session.task_spec?.allowed_changes || ["src/date/timezone.ts"],
    expected: { test_should_pass: true },
    network_allowed: false,
    files: (session.active_files || ['src/date/timezone.ts', 'src/billing/invoice.service.ts']).map(f => ({
      path: f,
      sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }))
  }, null, 2);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Capsule Metadata Card */}
      <div style={{
        padding: '20px',
        backgroundColor: 'var(--bg-panel)',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            padding: '12px',
            borderRadius: '8px',
            backgroundColor: 'rgba(6, 182, 212, 0.1)',
            border: '1px solid rgba(6, 182, 212, 0.3)',
          }}>
            <PackageCheck size={28} color="var(--accent-cyan)" />
          </div>
          <div>
            <div style={{ fontSize: '16px', fontWeight: 800 }}>Standalone Capsule Archive</div>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span>Size: ~{Math.round((session.capsule_size_bytes || 28410) / 1024)} KB</span>
              <span>•</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>SHA256: {session.capsule_hash?.slice(0, 16) || 'pending'}...</span>
            </div>
          </div>
        </div>

        <button
          onClick={() => alert(`Downloading standalone capsule archive for ${session.name}`)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: '6px',
            backgroundColor: 'var(--accent-cyan)',
            color: '#070A11',
            fontSize: '13px',
            fontWeight: 700,
          }}
        >
          <Download size={15} />
          Download .scopelet
        </button>
      </div>

      {/* Code Inspector Tabs */}
      <div style={{
        backgroundColor: 'var(--bg-panel)',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        overflow: 'hidden',
      }}>
        <div style={{
          display: 'flex',
          borderBottom: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--bg-canvas)',
          padding: '4px 12px',
          gap: '8px'
        }}>
          <button
            onClick={() => setActiveTab('task')}
            style={{
              padding: '8px 14px',
              fontSize: '12px',
              fontWeight: 600,
              color: activeTab === 'task' ? 'var(--accent-cyan)' : 'var(--text-secondary)',
              borderBottom: activeTab === 'task' ? '2px solid var(--accent-cyan)' : 'none',
            }}
          >
            task.yaml
          </button>
          <button
            onClick={() => setActiveTab('manifest')}
            style={{
              padding: '8px 14px',
              fontSize: '12px',
              fontWeight: 600,
              color: activeTab === 'manifest' ? 'var(--accent-cyan)' : 'var(--text-secondary)',
              borderBottom: activeTab === 'manifest' ? '2px solid var(--accent-cyan)' : 'none',
            }}
          >
            manifest.json
          </button>
        </div>

        <div style={{ padding: '16px' }}>
          <pre style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            backgroundColor: 'var(--bg-canvas)',
            padding: '16px',
            borderRadius: '6px',
            border: '1px solid var(--border-subtle)',
            color: activeTab === 'task' ? '#67E8F9' : '#93C5FD',
            overflowX: 'auto',
            maxHeight: '400px',
            whiteSpace: 'pre-wrap'
          }}>
            {activeTab === 'task' ? taskYamlContent : manifestJsonContent}
          </pre>
        </div>
      </div>
    </div>
  );
};
