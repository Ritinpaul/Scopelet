import type { SessionData, Verdict } from './types';

const API_BASE = '/sessions';

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch('/health', { method: 'GET', signal: AbortSignal.timeout(1000) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function createRemoteSession(workspace_dir: string, test_command: string): Promise<SessionData> {
  const res = await fetch(API_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_dir, test_command })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to create session');
  }
  const data = await res.json();
  return {
    id: data.id,
    name: `Session: ${workspace_dir.split(/[\\/]/).pop() || workspace_dir}`,
    workspace_dir: data.workspace_dir,
    test_command: data.test_command,
    current_phase: 'idle',
    created_at: data.created_at
  };
}

export async function triggerPhase(sessionId: string, phase: 'capture' | 'analyze' | 'reduce' | 'sanitize' | 'export', payload?: unknown): Promise<any> {
  const res = await fetch(`${API_BASE}/${sessionId}/${phase}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Phase ${phase} failed`);
  }
  return res.json();
}

export async function triggerVerify(sessionId: string, solution_patch: string): Promise<{ verdict: Verdict; rejection_reasons: string[] }> {
  const res = await fetch(`${API_BASE}/${sessionId}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ solution_patch })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Verification failed');
  }
  return res.json();
}

export async function fetchRemoteReport(sessionId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/${sessionId}/report`);
  if (!res.ok) {
    throw new Error('Failed to fetch report');
  }
  return res.json();
}
