/**
 * Authentication and User Profile API Service.
 */

import { apiClient } from './client';

export interface UserProfileResponse {
  id: string;
  email: string | null;
  role: string;
  full_name: string | null;
  avatar_url: string | null;
  app_metadata: Record<string, unknown>;
  user_metadata: Record<string, unknown>;
}

export async function fetchMyProfile(): Promise<UserProfileResponse> {
  return apiClient.get<UserProfileResponse>('/auth/me');
}
