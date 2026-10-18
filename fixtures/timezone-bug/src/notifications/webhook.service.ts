// SECRET CANARY 3: Internal testing webhook endpoint
export const DEFAULT_WEBHOOK_URL = 'https://api.internal-example.test/webhooks/v1';

export class WebhookService {
  constructor(private endpoint: string = DEFAULT_WEBHOOK_URL) {}

  async dispatch(event: string, payload: any): Promise<boolean> {
    return Boolean(this.endpoint);
  }
}
