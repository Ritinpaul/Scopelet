export class SmsService {
  async send(phone: string, text: string): Promise<boolean> {
    return Boolean(phone && text);
  }
}
