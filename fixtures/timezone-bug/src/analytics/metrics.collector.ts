export class MetricsCollector {
  private counters = new Map<string, number>();
  inc(name: string) { this.counters.set(name, (this.counters.get(name) || 0) + 1); }
  get(name: string) { return this.counters.get(name) || 0; }
}
