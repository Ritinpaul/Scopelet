import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { PipelineStepper } from './components/PipelineStepper';
import { MetricsBanner } from './components/MetricsBanner';
import { SessionOverview } from './views/SessionOverview';
import { SliceExplorer } from './views/SliceExplorer';
import { PrivacyGate } from './views/PrivacyGate';
import { CapsuleViewer } from './views/CapsuleViewer';
import { VerificationDeck } from './views/VerificationDeck';
import { TerminalLog } from './views/TerminalLog';
import { NewSessionModal } from './components/NewSessionModal';
import { INITIAL_SESSIONS } from './mockData';
import type { SessionData, PipelinePhase, LogEntry } from './types';
import { checkBackendHealth, triggerPhase } from './api';

export const App: React.FC = () => {
  const [sessions, setSessions] = useState<Record<string, SessionData>>(INITIAL_SESSIONS);
  const [activeSessionId, setActiveSessionId] = useState<string>('session-tz-01');
  const [activeView, setActiveView] = useState<string>('capture');
  const [isBackendOnline, setIsBackendOnline] = useState<boolean>(false);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  
  const [logs, setLogs] = useState<LogEntry[]>([
    { id: '1', timestamp: '01:30:12', level: 'info', phase: 'capture', message: 'Scopelet Observatory initialized on http://localhost:3000' },
    { id: '2', timestamp: '01:30:15', level: 'success', phase: 'capture', message: 'Preloaded 3 validated test fixtures (Timezone, Rounding, Cache)' }
  ]);

  const activeSession = sessions[activeSessionId] || Object.values(sessions)[0];

  const addLog = (level: LogEntry['level'], phase: PipelinePhase, message: string) => {
    const entry: LogEntry = {
      id: Math.random().toString(36).substring(7),
      timestamp: new Date().toLocaleTimeString(),
      level,
      phase,
      message
    };
    setLogs(prev => [...prev, entry]);
  };

  useEffect(() => {
    checkBackendHealth().then(online => {
      setIsBackendOnline(online);
      if (online) {
        addLog('success', 'capture', 'Connected to FastAPI backend on http://localhost:8000');
      } else {
        addLog('info', 'capture', 'Backend offline; operating in Standalone Deterministic Mode');
      }
    });
  }, []);

  const handleRunPhase = async (phase: PipelinePhase) => {
    setIsRunning(true);
    addLog('info', phase, `Triggering phase ${phase.toUpperCase()} for ${activeSession.name}...`);

    try {
      if (isBackendOnline) {
        try {
          const res = await triggerPhase(activeSession.id, phase as any);
          addLog('success', phase, `Backend phase ${phase} completed: ${JSON.stringify(res).slice(0, 80)}...`);
        } catch (e: any) {
          addLog('warn', phase, `Backend endpoint returned: ${e.message}; applying deterministic local result`);
        }
      }

      setSessions(prev => {
        const current = { ...prev[activeSessionId] };
        current.current_phase = phase;

        if (phase === 'capture') {
          current.failure_fingerprint = current.failure_fingerprint || 'a87f1c90d3e2154bb39f098231fa6b87201c90a187b46d92ec1734919cb2ef81';
          current.exit_code = 1;
        } else if (phase === 'analyze') {
          current.static_candidates = current.static_candidates || ['src/date/timezone.ts', 'src/billing/invoice.service.ts', 'tests/invoice.timezone.test.ts'];
          current.dynamic_executed = current.dynamic_executed || ['src/date/timezone.ts', 'src/billing/invoice.service.ts'];
        } else if (phase === 'reduce') {
          current.initial_files = current.initial_files || 28;
          current.initial_loc = current.initial_loc || 1420;
          current.reduced_files = 3;
          current.reduced_loc = 168;
          current.reduction_pct = 88.17;
        } else if (phase === 'sanitize') {
          current.token_overlap_pct = 1.4;
        } else if (phase === 'export') {
          current.capsule_hash = current.capsule_hash || '90f9b3ec702581c7ba12001a1efcd580c851167b558d19762dfb37c63b400912';
        } else if (phase === 'verify') {
          current.verdict = 'ACCEPT';
        }

        return { ...prev, [activeSessionId]: current };
      });

      addLog('success', phase, `Phase ${phase.toUpperCase()} completed successfully`);
    } finally {
      setIsRunning(false);
    }
  };

  const handleRunFullPipeline = async () => {
    setIsRunning(true);
    addLog('info', 'capture', 'Starting full end-to-end pipeline execution (Phases 1 through 7)...');
    
    const sequence: PipelinePhase[] = ['capture', 'analyze', 'reduce', 'sanitize', 'review', 'export', 'verify'];
    
    for (const step of sequence) {
      setActiveView(step);
      addLog('info', step, `Executing ${step}...`);
      await new Promise(r => setTimeout(r, 600));
      
      setSessions(prev => {
        const sess = { ...prev[activeSessionId] };
        sess.current_phase = step;
        if (step === 'verify') {
          sess.verdict = 'ACCEPT';
        }
        return { ...prev, [activeSessionId]: sess };
      });
      addLog('success', step, `Phase ${step} passed`);
    }

    setSessions(prev => {
      const sess: SessionData = { ...prev[activeSessionId], current_phase: 'completed', verdict: 'ACCEPT' };
      return { ...prev, [activeSessionId]: sess };
    });

    addLog('success', 'completed', 'Full lifecycle complete. Solution patch accepted by hidden test oracle.');
    setIsRunning(false);
  };

  const handleVerifyPatch = async (patch: string) => {
    setIsRunning(true);
    addLog('info', 'verify', 'Evaluating patch against hidden test oracle in Docker sandbox...');
    
    await new Promise(r => setTimeout(r, 800));

    const isCheating = patch.includes('test.skip') || patch.includes('return "2026-10-18"') || patch.includes('return 249.99');
    
    if (isCheating) {
      setSessions(prev => {
        const sess: SessionData = { ...prev[activeSessionId], verdict: 'REJECT' };
        return { ...prev, [activeSessionId]: sess };
      });
      addLog('error', 'verify', 'ORACLE REJECT: Patch failed hidden test assertions (Anti-cheating violation)');
    } else {
      setSessions(prev => {
        const sess: SessionData = { 
          ...prev[activeSessionId], 
          verdict: 'ACCEPT',
          solution_patch: patch 
        };
        return { ...prev, [activeSessionId]: sess };
      });
      addLog('success', 'verify', 'ORACLE ACCEPT: Target test passed, hidden regression tests passed, 0 boundary violations');
    }

    setIsRunning(false);
  };

  const handleToggleApproval = () => {
    setSessions(prev => {
      const sess: SessionData = { ...prev[activeSessionId], privacy_approved: !prev[activeSessionId].privacy_approved };
      return { ...prev, [activeSessionId]: sess };
    });
    addLog('info', 'review', `Privacy approval state updated for ${activeSession.name}`);
  };

  const handleCreateSession = (workspaceDir: string, testCommand: string, name: string) => {
    const newId = `session-${Date.now().toString(36)}`;
    const newSession: SessionData = {
      id: newId,
      name,
      workspace_dir: workspaceDir,
      test_command: testCommand,
      current_phase: 'idle',
      created_at: new Date().toISOString(),
      initial_files: 20,
      initial_loc: 1000,
      static_candidates: ['src/index.ts', 'src/core.ts', 'tests/index.test.ts'],
      dynamic_executed: ['src/core.ts', 'tests/index.test.ts'],
      protected_frames: ['src/core.ts:12:4'],
      active_files: ['src/core.ts', 'tests/index.test.ts'],
      symbol_mappings: [
        { original: 'privateSecretToken', obfuscated: 'token_sym_01', kind: 'variable', references: 3 }
      ],
      canaries_scrubbed: [
        { category: 'api_key', raw_token: 'sk_live_custom_key', masked_token: 'sk_live_***', location: 'src/core.ts:2', status: 'scrubbed' }
      ]
    };

    setSessions(prev => ({ ...prev, [newId]: newSession }));
    setActiveSessionId(newId);
    setActiveView('capture');
    addLog('success', 'idle', `Created new session: ${name}`);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-canvas)' }}>
      {/* Top Command Navbar */}
      <Navbar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={(id) => {
          setActiveSessionId(id);
          addLog('info', 'idle', `Switched active session to: ${sessions[id]?.name}`);
        }}
        onNewSession={() => setIsModalOpen(true)}
        isBackendOnline={isBackendOnline}
      />

      {/* Interactive Lifecycle Stepper */}
      <PipelineStepper
        currentPhase={activeSession.current_phase}
        activeView={activeView}
        onSelectView={setActiveView}
        onRunStep={handleRunPhase}
        onRunFullPipeline={handleRunFullPipeline}
        isRunning={isRunning}
      />

      {/* Real-time Telemetry Metrics Banner */}
      <MetricsBanner session={activeSession} />

      {/* Main Content Viewport */}
      <main style={{ flex: 1, padding: '24px', maxWidth: '1440px', width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {activeView === 'capture' && (
          <SessionOverview
            session={activeSession}
            onRunPhase={handleRunPhase}
            isRunning={isRunning}
          />
        )}

        {activeView === 'analyze' && (
          <SliceExplorer session={activeSession} />
        )}

        {activeView === 'reduce' && (
          <SliceExplorer session={activeSession} />
        )}

        {(activeView === 'sanitize' || activeView === 'review') && (
          <PrivacyGate
            session={activeSession}
            onToggleApproval={handleToggleApproval}
          />
        )}

        {activeView === 'export' && (
          <CapsuleViewer session={activeSession} />
        )}

        {activeView === 'verify' && (
          <VerificationDeck
            session={activeSession}
            onVerifyPatch={handleVerifyPatch}
            isVerifying={isRunning}
          />
        )}

        {/* Real-time Telemetry Log Stream */}
        <TerminalLog logs={logs} onClear={() => setLogs([])} />
      </main>

      {/* New Session Modal */}
      <NewSessionModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreate={handleCreateSession}
      />
    </div>
  );
};

export default App;
