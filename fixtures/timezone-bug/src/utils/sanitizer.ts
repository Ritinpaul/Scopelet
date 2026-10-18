export function sanitizeHtml(raw: string): string {
  return raw.replace(/<[^>]*>?/gm, '');
}
