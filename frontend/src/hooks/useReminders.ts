/**
 * TanStack Query Hooks for Reminders, Notifications, and Push Subscriptions.
 */

import { useContext } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AuthContext } from '../context/AuthContext';
import * as remindersApi from '../api/reminders';
import { PRODUCTIVITY_KEYS } from './useProductivity';

function useResolvedUserId(explicitUserId?: string): string {
  const auth = useContext(AuthContext);
  return explicitUserId ?? auth?.user?.id ?? 'anonymous';
}

export const REMINDER_KEYS = {
  all: ['reminders'] as const,
  lists: (userId?: string) => ['reminders', 'list', userId ?? 'anonymous'] as const,
  list: (params: Record<string, unknown> | undefined, userId?: string) =>
    ['reminders', 'list', userId ?? 'anonymous', params ?? {}] as const,
  notifications: (userId?: string) => ['notifications', userId ?? 'anonymous'] as const,
  pushSubscriptions: (userId?: string) => ['push_subscriptions', userId ?? 'anonymous'] as const,
  vapidKey: () => ['vapid_public_key'] as const,
  deliveryLogs: (reminderId?: string, userId?: string) =>
    ['delivery_logs', userId ?? 'anonymous', reminderId ?? 'all'] as const,
};

export function useReminders(
  params?: {
    status?: string;
    recurring_only?: boolean;
    task_id?: string;
    query?: string;
    page?: number;
    page_size?: number;
  },
  userId?: string
) {
  const uid = useResolvedUserId(userId);
  return useQuery({
    queryKey: REMINDER_KEYS.list(params, uid),
    queryFn: () => remindersApi.getReminders(params),
    enabled: uid !== 'anonymous',
    staleTime: 1000 * 15,
  });
}

export function useCreateReminder(userId?: string) {
  const qc = useQueryClient();
  const uid = useResolvedUserId(userId);
  return useMutation({
    mutationFn: (input: remindersApi.ReminderCreateInput) => remindersApi.createReminder(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.lists(uid) });
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(uid) });
    },
  });
}

export function useUpdateReminder(userId?: string) {
  const qc = useQueryClient();
  const uid = useResolvedUserId(userId);
  return useMutation({
    mutationFn: ({ reminderId, input }: { reminderId: string; input: remindersApi.ReminderUpdateInput }) =>
      remindersApi.updateReminder(reminderId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.lists(uid) });
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(uid) });
    },
  });
}

export function useSnoozeReminder(userId?: string) {
  const qc = useQueryClient();
  const uid = useResolvedUserId(userId);
  return useMutation({
    mutationFn: ({ reminderId, snoozeMinutes }: { reminderId: string; snoozeMinutes?: number }) =>
      remindersApi.snoozeReminder(reminderId, snoozeMinutes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.lists(uid) });
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(uid) });
    },
  });
}

export function useCompleteReminder(userId?: string) {
  const qc = useQueryClient();
  const uid = useResolvedUserId(userId);
  return useMutation({
    mutationFn: (reminderId: string) => remindersApi.completeReminder(reminderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.lists(uid) });
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(uid) });
      qc.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.all });
    },
  });
}

export function useCancelReminder(userId?: string) {
  const qc = useQueryClient();
  const uid = useResolvedUserId(userId);
  return useMutation({
    mutationFn: (reminderId: string) => remindersApi.cancelReminder(reminderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.lists(uid) });
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(uid) });
    },
  });
}

export function useRescheduleReminder(userId?: string) {
  const qc = useQueryClient();
  const uid = useResolvedUserId(userId);
  return useMutation({
    mutationFn: ({ reminderId, triggerAt, timezone }: { reminderId: string; triggerAt: string; timezone?: string }) =>
      remindersApi.rescheduleReminder(reminderId, triggerAt, timezone),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.lists(uid) });
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(uid) });
    },
  });
}

export function useDeleteReminder(userId?: string) {
  const qc = useQueryClient();
  const uid = useResolvedUserId(userId);
  return useMutation({
    mutationFn: (reminderId: string) => remindersApi.deleteReminder(reminderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.lists(uid) });
      qc.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(uid) });
    },
  });
}

export function usePushSubscriptions(userId?: string) {
  const uid = useResolvedUserId(userId);
  return useQuery({
    queryKey: REMINDER_KEYS.pushSubscriptions(uid),
    queryFn: () => remindersApi.getPushSubscriptions(),
    enabled: uid !== 'anonymous',
  });
}

export function useVapidPublicKey() {
  return useQuery({
    queryKey: REMINDER_KEYS.vapidKey(),
    queryFn: () => remindersApi.getVapidPublicKey(),
    staleTime: 1000 * 60 * 10,
  });
}

