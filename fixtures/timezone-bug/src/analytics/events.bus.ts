export class EventBus {
  private listeners: Array<(event: string, data: any) => void> = [];
  on(fn: (event: string, data: any) => void) { this.listeners.push(fn); }
  emit(event: string, data: any) { this.listeners.forEach(fn => fn(event, data)); }
}
