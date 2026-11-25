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
  in_app_notifications_enabled?: boolean;
  browser_push_enabled?: boolean;
  audible_alerts_enabled?: boolean;
  reminder_sound?: string;
  default_reminder_behavior?: string;
  default_snooze_minutes?: number;
  quiet_hours_enabled?: boolean;
  quiet_hours_start?: string;
  quiet_hours_end?: string;
  quiet_hours_allow_alarms?: boolean;
  timezone?: string;
  daily_briefing_enabled?: boolean;
  daily_briefing_time?: string;
  evening_review_enabled?: boolean;
  evening_review_time?: string;
  notification_priority_default?: string;
  recurring_auto_advance?: boolean;
  recurring_missed_policy?: string;
  task_default_lead_minutes?: number;
  auto_remind_new_tasks?: boolean;
  overdue_task_reminders_enabled?: boolean;
  auto_reschedule_task_reminders?: boolean;
  suppress_reminders_on_task_complete?: boolean;
  hide_sensitive_lockscreen?: boolean;
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
