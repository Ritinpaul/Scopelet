import { ProfileService } from './profile.service.js';

export class ProfileController {
  constructor(private service: ProfileService) {}

  async handleGet(id: string) {
    return this.service.getProfile(id);
  }

  async handleUpdate(id: string, body: any) {
    return this.service.updateProfile(id, body);
  }
}
