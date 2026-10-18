export class EmailService {
  async send(to: string, subject: string, body: string): Promise<boolean> {
    return Boolean(to && subject);
  }
}
