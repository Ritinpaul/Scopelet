export class TrackerService {
  track(eventName: string, meta: Record<string, any>) {
    return { event: eventName, meta, timestamp: Date.now() };
  }
}
