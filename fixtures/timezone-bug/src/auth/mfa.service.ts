export class MfaService {
  verifyCode(code: string): boolean {
    return code.length === 6 && /^\d+$/.test(code);
  }
}
