export class CouponService {
  applyPercent(total: number, percent: number): number {
    return total * (1 - percent / 100);
  }
}
