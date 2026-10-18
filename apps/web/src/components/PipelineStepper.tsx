import React from 'react';
import { 
  Camera, 
  GitFork, 
  Minimize2, 
  EyeOff, 
  ShieldAlert, 
  PackageCheck, 
  CheckCircle2, 
  Play,
  RotateCcw
} from 'lucide-react';
import type { PipelinePhase } from '../types';

interface Step {
  id: PipelinePhase;
  label: string;
  sublabel: string;
  icon: React.ReactNode;
}

const STEPS: Step[] = [
  { id: 'capture', label: '1. Capture', sublabel: 'Fingerprint', icon: <Camera size={16} /> },
  { id: 'analyze', label: '2. Slice', sublabel: 'Static & Dynamic', icon: <GitFork size={16} /> },
  { id: 'reduce', label: '3. Reduce', sublabel: 'Delta Debugging', icon: <Minimize2 size={16} /> },
  { id: 'sanitize', label: '4. Sanitize', sublabel: 'AST Obfuscation', icon: <EyeOff size={16} /> },
  { id: 'review', label: '5. Review', sublabel: 'Privacy Gate', icon: <ShieldAlert size={16} /> },
  { id: 'export', label: '6. Export', sublabel: 'Capsule Archive', icon: <PackageCheck size={16} /> },
  { id: 'verify', label: '7. Verify', sublabel: 'Hidden Oracle', icon: <CheckCircle2 size={16} /> }
];

interface PipelineStepperProps {
  currentPhase: PipelinePhase;
  activeView: string;
  onSelectView: (view: string) => void;
  onRunStep: (phase: PipelinePhase) => void;
  onRunFullPipeline: () => void;
  isRunning: boolean;
}

export const PipelineStepper: React.FC<PipelineStepperProps> = ({
  currentPhase,
  activeView,
  onSelectView,
  onRunStep: _onRunStep,
  onRunFullPipeline,
  isRunning,
}) => {
  const getPhaseIndex = (phase: PipelinePhase): number => {
    const map: Record<PipelinePhase, number> = {
      idle: -1,
      capture: 0,
      analyze: 1,
      reduce: 2,
      sanitize: 3,
      review: 4,
      export: 5,
      verify: 6,
      completed: 7,
    };
    return map[phase] ?? -1;
  };

  const currentIndex = getPhaseIndex(currentPhase);

  return (
    <div style={{
      padding: '16px 24px',
      backgroundColor: 'var(--bg-panel)',
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '20px',
    }}>
      {/* Step Sequence */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, overflowX: 'auto' }}>
        {STEPS.map((step, idx) => {
          const isDone = currentIndex > idx || currentPhase === 'completed';
          const isCurrent = currentIndex === idx;
          const isSelected = activeView === step.id;

          return (
            <React.Fragment key={step.id}>
              <button
                onClick={() => onSelectView(step.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '8px 14px',
                  borderRadius: '8px',
                  backgroundColor: isSelected 
                    ? 'rgba(6, 182, 212, 0.14)' 
                    : isCurrent 
                      ? 'rgba(59, 130, 246, 0.10)' 
                      : 'var(--bg-canvas)',
                  border: isSelected
                    ? '1px solid var(--accent-cyan)'
                    : isCurrent
                      ? '1px solid rgba(59, 130, 246, 0.5)'
                      : '1px solid var(--border-subtle)',
                  color: isSelected 
                    ? 'var(--accent-cyan)' 
                    : isDone 
                      ? 'var(--status-success)' 
                      : isCurrent 
                        ? 'var(--text-primary)' 
                        : 'var(--text-secondary)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  flexShrink: 0,
                }}
              >
                <div style={{
                  color: isSelected ? 'var(--accent-cyan)' : isDone ? 'var(--status-success)' : 'inherit',
                  display: 'flex',
                  alignItems: 'center'
                }}>
                  {step.icon}
                </div>
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, lineHeight: 1.1 }}>{step.label}</div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{step.sublabel}</div>
                </div>
              </button>

              {idx < STEPS.length - 1 && (
                <div style={{
                  width: '20px',
                  height: '2px',
                  backgroundColor: isDone ? 'var(--status-success)' : 'var(--border-subtle)',
                  flexShrink: 0,
                }} />
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Global Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
        <button
          onClick={onRunFullPipeline}
          disabled={isRunning}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: 'var(--accent-cyan)',
            color: '#070A11',
            padding: '8px 16px',
            borderRadius: '6px',
            fontWeight: 700,
            fontSize: '13px',
            cursor: isRunning ? 'not-allowed' : 'pointer',
            opacity: isRunning ? 0.6 : 1,
            boxShadow: '0 0 15px rgba(6, 182, 212, 0.25)',
            transition: 'all 0.15s ease',
          }}
          onMouseEnter={(e) => !isRunning && (e.currentTarget.style.backgroundColor = '#22D3EE')}
          onMouseLeave={(e) => !isRunning && (e.currentTarget.style.backgroundColor = 'var(--accent-cyan)')}
        >
          {isRunning ? <RotateCcw size={15} className="animate-spin" /> : <Play size={15} fill="#070A11" />}
          {isRunning ? 'Processing...' : 'Run Full Pipeline'}
        </button>
      </div>
    </div>
  );
};
