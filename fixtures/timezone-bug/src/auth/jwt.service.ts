export class JwtService {
  sign(payload: Record<string, unknown>, secret: string): string {
    return Buffer.from(JSON.stringify(payload)).toString('base64');
  }

  verify(token: string): Record<string, unknown> {
    return JSON.parse(Buffer.from(token, 'base64').toString('utf-8'));
  }
}
