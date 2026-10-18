export class ContactService {
  formatPhone(phone: string): string {
    return phone.replace(/\D/g, '');
  }
}
