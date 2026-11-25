/**
 * Typed API Client for Smart Reminders, In-App Notifications, Push Subscriptions & Delivery Logs.
 */

import { apiClient } from './client';

export type ReminderType =
  | 'general'
  | 'task_before_due'
  | 'task_due'
  | 'task_overdue'
  | 'briefing'
  | 'review'
  | 'alarm'
  | 'appointment'
  | 'goal';

export type ReminderStatus =
  | 'scheduled'
  | 'due'
  | 'snoozed'
  | 'completed'
  | 'cancelled'
  | 'missed';

export type ReminderPriority = 'low' | 'normal' | 'high' | 'alarm';

export type RecurrenceFrequency =
  | 'daily'
  | 'weekdays'
  | 'weekly'
  | 'monthly'
  | 'interval_minutes'
  | 'interval_hours'
  | 'interval_days';

export interface RecurrenceRule {
  frequency: RecurrenceFrequency;
  interval: number;
  days_of_week?: number[] | null;
  day_of_month?: number | null;
  time_of_day?: string | null;
  end_at?: string | null;
}

export interface Reminder {
  id: string;
  user_id: string;
  task_id?: string | null;
  project_id?: string | null;
  goal_id?: string | null;
  task_title?: string | null;
  project_name?: string | null;
  title: string;
  description?: string | null;
  reminder_type: ReminderType;
  trigger_at: string;
  original_trigger_at: string;
  timezone: string;
  recurrence_rule?: RecurrenceRule | null;
  recurrence_text?: string | null;
  status: ReminderStatus;
  priority: ReminderPriority;
  is_alarm: boolean;
  sound_key?: string | null;
  snoozed_until?: string | null;
  snooze_count: number;
  last_triggered_at?: string | null;
  next_retry_at?: string | null;
  delivery_attempts: number;
  max_delivery_attempts: number;
  escalation_count: number;
  completed_at?: string | null;
  cancelled_at?: string | null;
  source: 'manual' | 'chat' | 'task_sync' | 'system_briefing';
  dedupe_key?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReminderCreateInput {
  title: string;
  description?: string | null;
  reminder_type?: ReminderType;
  trigger_at: string;
  timezone?: string;
  recurrence_rule?: RecurrenceRule | null;
  recurrence_text?: string | null;
  priority?: ReminderPriority;
  is_alarm?: boolean;
  sound_key?: string | null;
  task_id?: string | null;
  project_id?: string | null;
  goal_id?: string | null;
  dedupe_key?: string | null;
}

export interface ReminderUpdateInput {
  title?: string;
  description?: string | null;
  reminder_type?: ReminderType;
  trigger_at?: string;
  timezone?: string;
  recurrence_rule?: RecurrenceRule | null;
  recurrence_text?: string | null;
  status?: ReminderStatus;
  priority?: ReminderPriority;
  is_alarm?: boolean;
  sound_key?: string | null;
  task_id?: string | null;
  clear_recurrence?: boolean;
}

export interface ReminderListResponse {
  items: Reminder[];
  total: number;
  page: number;
  page_size: number;
}

export type NotificationStatus = 'unread' | 'read' | 'dismissed' | 'acted' | 'suppressed_quiet_hours';

export interface NotificationItem {
  id: string;
  user_id: string;
  reminder_id?: string | null;
  task_id?: string | null;
  title: string;
  body?: string | null;
  category: string;
  priority: ReminderPriority;
  is_alarm: boolean;
  action_url: string;
  delivery_channel: 'in_app' | 'web_push' | 'both';
  status: NotificationStatus;
  occurrence_key: string;
  metadata: {
    scheduled_at?: string;
    timezone?: string;
    missed_window?: boolean;
    suppress_audio?: boolean;
    quiet_hours_suppressed?: boolean;
    sound_key?: string;
    recurrence_text?: string;
    is_test?: boolean;
    [key: string]: unknown;
  };
  triggered_at: string;
  read_at?: string | null;
  acted_at?: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  unread_count: number;
  due_alerts: NotificationItem[];
}

export interface PushSubscriptionView {
  id: string;
  endpoint: string;
  device_label?: string | null;
  user_agent?: string | null;
  is_active: boolean;
  failure_count: number;
  last_error?: string | null;
  last_success_at?: string | null;
  created_at: string;
}

export interface PushSubscriptionListResponse {
  items: PushSubscriptionView[];
  total: number;
}

export interface VapidPublicKeyResponse {
  configured: boolean;
  public_key: string | null;
  subject: string;
}

export interface DeliveryLogItem {
  id: string;
  user_id: string;
  reminder_id?: string | null;
  notification_id?: string | null;
  subscription_id?: string | null;
  channel: string;
  status: string;
  attempt_number: number;
  http_status?: number | null;
  error_detail?: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Reminder API Calls
// ---------------------------------------------------------------------------
export async function getReminders(params?: {
  status?: string;
  recurring_only?: boolean;
  task_id?: string;
  query?: string;
  page?: number;
  page_size?: number;
}): Promise<ReminderListResponse> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set('status', params.status);
  if (params?.recurring_only) qs.set('recurring_only', 'true');
  if (params?.task_id) qs.set('task_id', params.task_id);
  if (params?.query) qs.set('query', params.query);
  if (params?.page) qs.set('page', String(params.page));
  if (params?.page_size) qs.set('page_size', String(params.page_size));
  const suffix = qs.toString();
  return apiClient.get<ReminderListResponse>(`/reminders${suffix ? `?${suffix}` : ''}`);
}

export async function getReminder(reminderId: string): Promise<Reminder> {
  return apiClient.get<Reminder>(`/reminders/${reminderId}`);
}

export async function createReminder(input: ReminderCreateInput): Promise<Reminder> {
  return apiClient.post<Reminder>('/reminders', input);
}

export async function updateReminder(reminderId: string, input: ReminderUpdateInput): Promise<Reminder> {
  return apiClient.patch<Reminder>(`/reminders/${reminderId}`, input);
}

export async function snoozeReminder(reminderId: string, snoozeMinutes = 10): Promise<Reminder> {
  return apiClient.post<Reminder>(`/reminders/${reminderId}/snooze`, { snooze_minutes: snoozeMinutes });
}

export async function completeReminder(reminderId: string): Promise<Reminder> {
  return apiClient.post<Reminder>(`/reminders/${reminderId}/complete`);
}

export async function cancelReminder(reminderId: string): Promise<Reminder> {
  return apiClient.post<Reminder>(`/reminders/${reminderId}/cancel`);
}

export async function rescheduleReminder(
  reminderId: string,
  triggerAt: string,
  timezone?: string
): Promise<Reminder> {
  return apiClient.post<Reminder>(`/reminders/${reminderId}/reschedule`, {
    trigger_at: triggerAt,
    timezone,
  });
}

export async function deleteReminder(reminderId: string): Promise<void> {
  return apiClient.delete<void>(`/reminders/${reminderId}`);
}

// ---------------------------------------------------------------------------
// Notification Center & Push API Calls
// ---------------------------------------------------------------------------
export async function getNotifications(params?: {
  unread_only?: boolean;
  process_due?: boolean;
  limit?: number;
}): Promise<NotificationListResponse> {
  const qs = new URLSearchParams();
  if (params?.unread_only !== undefined) qs.set('unread_only', String(params.unread_only));
  if (params?.process_due !== undefined) qs.set('process_due', String(params.process_due));
  if (params?.limit) qs.set('limit', String(params.limit));
  const suffix = qs.toString();
  return apiClient.get<NotificationListResponse>(`/notifications${suffix ? `?${suffix}` : ''}`);
}

export async function markNotificationRead(notificationId: string): Promise<NotificationItem> {
  return apiClient.post<NotificationItem>(`/notifications/${notificationId}/read`);
}

export async function dismissNotification(notificationId: string): Promise<NotificationItem> {
  return apiClient.post<NotificationItem>(`/notifications/${notificationId}/dismiss`);
}

export async function markAllNotificationsRead(): Promise<{ marked_read: number }> {
  return apiClient.post<{ marked_read: number }>('/notifications/read-all');
}

export async function getDeliveryLogs(reminderId?: string): Promise<DeliveryLogItem[]> {
  const suffix = reminderId ? `?reminder_id=${encodeURIComponent(reminderId)}` : '';
  return apiClient.get<DeliveryLogItem[]>(`/notifications/delivery-logs${suffix}`);
}

export async function getVapidPublicKey(): Promise<VapidPublicKeyResponse> {
  return apiClient.get<VapidPublicKeyResponse>('/notifications/push/vapid-public-key');
}

export async function getPushSubscriptions(): Promise<PushSubscriptionListResponse> {
  return apiClient.get<PushSubscriptionListResponse>('/notifications/push/subscriptions');
}

export async function subscribeWebPush(payload: {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent?: string;
  device_label?: string;
}): Promise<PushSubscriptionView> {
  return apiClient.post<PushSubscriptionView>('/notifications/push/subscribe', payload);
}

export async function deletePushSubscription(subscriptionId: string): Promise<void> {
  return apiClient.delete<void>(`/notifications/push/subscriptions/${subscriptionId}`);
}

export async function sendTestNotification(): Promise<{
  notification: NotificationItem;
  push_deliveries: Array<{ subscription_id: string; success: boolean; status_code?: number }>;
}> {
  return apiClient.post('/notifications/test-push');
}

