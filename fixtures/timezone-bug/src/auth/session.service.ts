export class SessionService {
  private sessions = new Set<string>();

  createSession(id: string) { this.sessions.add(id); }
  isValid(id: string) { return this.sessions.has(id); }
}
