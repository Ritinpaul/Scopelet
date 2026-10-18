export class AggregationEngine {
  sum(numbers: number[]): number { return numbers.reduce((a, b) => a + b, 0); }
  avg(numbers: number[]): number { return numbers.length ? this.sum(numbers) / numbers.length : 0; }
}
