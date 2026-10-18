export class DispatchQueue {
  private queue: any[] = [];
  push(job: any) { this.queue.push(job); }
  size() { return this.queue.length; }
}
