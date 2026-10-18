// SECRET CANARY 4: Fake API secret key
export const STRIPE_LIVE_KEY_FALLBACK = 'sk_live_fake_SECRET_123';

export class PaymentGateway {
  constructor(private apiKey: string = STRIPE_LIVE_KEY_FALLBACK) {}

  async charge(amount: number, token: string): Promise<{ success: boolean; txId: string }> {
    if (!this.apiKey) throw new Error('API key required');
    return { success: true, txId: `tx_${Date.now()}` };
  }
}
