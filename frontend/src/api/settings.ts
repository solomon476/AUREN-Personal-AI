/**
 * Typed API Client for Profile, Settings & GDPR Data Portability.
 */

import { apiClient } from './client';

export interface UserPreferences {
  theme?: string;
  ai_model?: string;
  ai_tone?: string;
  ai_custom_instructions?: string;
  memory_auto_extraction?: boolean;
  memory_min_confidence?: number;
  notifications_enabled?: boolean;
  [key: string]: unknown;
}

export interface UserProfile {
  id: string;
  email: string | null;
  role: string;
  full_name: string | null;
  avatar_url: string | null;
  preferences: UserPreferences;
  app_metadata: Record<string, unknown>;
  user_metadata: Record<string, unknown>;
}

export interface UserProfileUpdateInput {
  full_name?: string;
  avatar_url?: string;
  preferences?: UserPreferences;
}

export interface UserDataExportBundle {
  user_id: string;
  email: string | null;
  exported_at: string;
  preferences: UserPreferences;
  tasks: unknown[];
  projects: unknown[];
  goals: unknown[];
  memories: unknown[];
  journal_entries: unknown[];
}

export async function getUserProfile(): Promise<UserProfile> {
  return apiClient.get<UserProfile>('/auth/me');
}

export async function updateUserProfile(payload: UserProfileUpdateInput): Promise<UserProfile> {
  return apiClient.patch<UserProfile>('/auth/profile', payload);
}

export async function exportUserData(): Promise<UserDataExportBundle> {
  return apiClient.post<UserDataExportBundle>('/auth/export');
}
