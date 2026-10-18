export class PasswordHasher {
  hash(pw: string): string {
    return `hash_${pw.length}_${pw.slice(0, 2)}`;
  }
}
