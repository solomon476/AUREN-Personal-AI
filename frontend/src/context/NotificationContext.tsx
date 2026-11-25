/**
 * Global Notification & Alarm Context Provider.
 *
 * Manages:
 * - Periodic & focus-triggered sync with /api/v1/notifications (due processing + unread state)
 * - In-app toast popups & prominent alarm-style alert modals
 * - Duplicate suppression across sessions via localStorage seen-set
 * - Web Audio chime/alarm playback respecting user preferences & quiet-hour suppression
 * - Service Worker notificationclick & push action deep-linking (Complete / Snooze / Open)
 */

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { useAuth } from './AuthContext';
import {
  completeReminder,
  dismissNotification,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  NotificationItem,
  snoozeReminder,
} from '../api/reminders';
import { useUserProfile } from '../hooks/useSettings';
import { REMINDER_KEYS } from '../hooks/useReminders';
import { playAlertSound, stopAlertSound, unlockAudioContext } from '../lib/soundAlert';

const SEEN_ALERTS_KEY = 'auren_seen_notification_ids';

function loadSeenAlertIds(): Set<string> {
  try {
    const raw = localStorage.getItem(SEEN_ALERTS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return new Set(parsed.slice(-200));
    }
  } catch {
    // ignore storage errors
  }
  return new Set();
}

function saveSeenAlertIds(ids: Set<string>): void {
  try {
    localStorage.setItem(SEEN_ALERTS_KEY, JSON.stringify(Array.from(ids).slice(-200)));
  } catch {
    // ignore storage errors
  }
}

interface NotificationContextValue {
  notifications: NotificationItem[];
  unreadCount: number;
  activePopup: NotificationItem | null;
  activeAlarm: NotificationItem | null;
  isLoading: boolean;
  refreshNotifications: () => Promise<void>;
  markRead: (notificationId: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  dismissActiveAlert: (notificationId: string) => Promise<void>;
  completeFromNotification: (item: NotificationItem) => Promise<void>;
  snoozeFromNotification: (item: NotificationItem, minutes?: number) => Promise<void>;
  openFromNotification: (item: NotificationItem) => Promise<void>;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, session } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data: profile } = useUserProfile(user?.id);
  const prefs = profile?.preferences || {};
  const inAppEnabled = prefs.in_app_notifications_enabled !== false;
  const audibleEnabled = prefs.audible_alerts_enabled !== false;
  const defaultSnoozeMinutes = Number(prefs.default_snooze_minutes || 10);
  const defaultSound = String(prefs.reminder_sound || 'chime');

  const [activePopup, setActivePopup] = useState<NotificationItem | null>(null);
  const [activeAlarm, setActiveAlarm] = useState<NotificationItem | null>(null);
  const seenIdsRef = useRef<Set<string>>(loadSeenAlertIds());

  // Avoid spurious calls if anonymous or during synthetic mock router renders without backend
  const hasSessionToken = Boolean(user && session?.access_token);

  const { data, isLoading, refetch } = useQuery({
    queryKey: REMINDER_KEYS.notifications(user?.id),
    queryFn: async () => {
      try {
        return await getNotifications({ unread_only: false, process_due: true, limit: 50 });
      } catch {
        // Non-blocking in offline or isolated UI test mode
        return { items: [], total: 0, unread_count: 0, due_alerts: [] };
      }
    },
    enabled: hasSessionToken,
    refetchInterval: hasSessionToken ? 15000 : false,
    refetchOnWindowFocus: hasSessionToken,
    staleTime: 5000,
  });

  const notifications = data?.items ?? [];
  const unreadCount = data?.unread_count ?? 0;

  // Unlock Web Audio on first user interaction
  useEffect(() => {
    const unlock = () => unlockAudioContext();
    window.addEventListener('pointerdown', unlock, { once: true });
    window.addEventListener('keydown', unlock, { once: true });
    return () => {
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
    };
  }, []);

  // Trigger in-app popup / alarm overlay once per newly-arrived unread alert
  useEffect(() => {
    if (!inAppEnabled || !data?.due_alerts?.length) return;

    const unseen = data.due_alerts.filter((n) => n.status === 'unread' && !seenIdsRef.current.has(n.id));
    if (unseen.length === 0) return;

    // Prioritize alarm-style alert first, otherwise most recent alert
    const alarmItem = unseen.find((n) => n.is_alarm || n.priority === 'alarm');
    const chosen = alarmItem || unseen[0];

    unseen.forEach((n) => seenIdsRef.current.add(n.id));
    saveSeenAlertIds(seenIdsRef.current);

    if (chosen.is_alarm || chosen.priority === 'alarm') {
      setActiveAlarm(chosen);
    } else {
      setActivePopup(chosen);
    }

    const suppressAudio = Boolean(chosen.metadata?.suppress_audio || chosen.metadata?.quiet_hours_suppressed);
    if (audibleEnabled && !suppressAudio) {
      const soundKey = String(chosen.metadata?.sound_key || defaultSound || 'chime');
      playAlertSound(soundKey, Boolean(chosen.is_alarm || chosen.priority === 'alarm'));
    }
  }, [data?.due_alerts, inAppEnabled, audibleEnabled, defaultSound]);

  const refreshNotifications = useCallback(async () => {
    if (!hasSessionToken) return;
    await refetch();
  }, [hasSessionToken, refetch]);

  const markRead = useCallback(
    async (notificationId: string) => {
      await markNotificationRead(notificationId);
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
    },
    [queryClient, user?.id]
  );

  const markAllRead = useCallback(async () => {
    await markAllNotificationsRead();
    stopAlertSound();
    setActivePopup(null);
    setActiveAlarm(null);
    queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
  }, [queryClient, user?.id]);

  const dismissActiveAlert = useCallback(
    async (notificationId: string) => {
      stopAlertSound();
      if (activePopup?.id === notificationId) setActivePopup(null);
      if (activeAlarm?.id === notificationId) setActiveAlarm(null);
      try {
        await dismissNotification(notificationId);
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
      } catch {
        // ignore network dismiss failure locally
      }
    },
    [activeAlarm?.id, activePopup?.id, queryClient, user?.id]
  );

  const completeFromNotification = useCallback(
    async (item: NotificationItem) => {
      stopAlertSound();
      if (activePopup?.id === item.id) setActivePopup(null);
      if (activeAlarm?.id === item.id) setActiveAlarm(null);
      if (item.reminder_id) {
        await completeReminder(item.reminder_id);
      }
      await dismissNotification(item.id).catch(() => {});
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.all });
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
    },
    [activeAlarm?.id, activePopup?.id, queryClient, user?.id]
  );

  const snoozeFromNotification = useCallback(
    async (item: NotificationItem, minutes?: number) => {
      stopAlertSound();
      if (activePopup?.id === item.id) setActivePopup(null);
      if (activeAlarm?.id === item.id) setActiveAlarm(null);
      const mins = minutes ?? defaultSnoozeMinutes;
      if (item.reminder_id) {
        await snoozeReminder(item.reminder_id, mins);
      }
      await dismissNotification(item.id).catch(() => {});
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.all });
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
    },
    [activeAlarm?.id, activePopup?.id, defaultSnoozeMinutes, queryClient, user?.id]
  );

  const openFromNotification = useCallback(
    async (item: NotificationItem) => {
      stopAlertSound();
      if (activePopup?.id === item.id) setActivePopup(null);
      if (activeAlarm?.id === item.id) setActiveAlarm(null);
      await markNotificationRead(item.id).catch(() => {});
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
      const target = item.task_id ? '/tasks' : item.action_url || '/reminders';
      navigate({ to: target as any });
    },
    [activeAlarm?.id, activePopup?.id, navigate, queryClient, user?.id]
  );

  // Listen to Service Worker push notification clicks & actions
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
    const handler = async (event: MessageEvent) => {
      const payload = event.data;
      if (!payload || payload.type !== 'AUREN_NOTIFICATION_CLICK') return;
      const { action, reminder_id, notification_id, task_id } = payload;
      try {
        if (action === 'complete' && reminder_id) {
          await completeReminder(reminder_id);
          if (notification_id) await dismissNotification(notification_id).catch(() => {});
        } else if (action === 'snooze' && reminder_id) {
          await snoozeReminder(reminder_id, defaultSnoozeMinutes);
          if (notification_id) await dismissNotification(notification_id).catch(() => {});
        } else {
          if (notification_id) await markNotificationRead(notification_id).catch(() => {});
          navigate({ to: (task_id ? '/tasks' : '/reminders') as any });
        }
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.all });
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
      } catch {
        // Fallback navigation
        navigate({ to: '/reminders' });
      }
    };
    navigator.serviceWorker.addEventListener('message', handler);
    return () => navigator.serviceWorker.removeEventListener('message', handler);
  }, [defaultSnoozeMinutes, navigate, queryClient, user?.id]);

  // Also execute action if app was freshly launched by notification click URL params (?notif_action=...)
  useEffect(() => {
    if (!hasSessionToken || typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const notifAction = params.get('notif_action');
    const remId = params.get('reminder_id');
    const notifId = params.get('notification_id');
    if (!notifAction && !notifId) return;

    const runAction = async () => {
      try {
        if (notifAction === 'complete' && remId) {
          await completeReminder(remId);
          if (notifId) await dismissNotification(notifId).catch(() => {});
        } else if (notifAction === 'snooze' && remId) {
          await snoozeReminder(remId, defaultSnoozeMinutes);
          if (notifId) await dismissNotification(notifId).catch(() => {});
        } else if (notifId) {
          await markNotificationRead(notifId).catch(() => {});
        }
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.all });
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
      } finally {
        const cleanUrl = window.location.pathname;
        window.history.replaceState({}, '', cleanUrl);
      }
    };
    runAction();
  }, [hasSessionToken, defaultSnoozeMinutes, queryClient, user?.id]);

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        unreadCount,
        activePopup,
        activeAlarm,
        isLoading,
        refreshNotifications,
        markRead,
        markAllRead,
        dismissActiveAlert,
        completeFromNotification,
        snoozeFromNotification,
        openFromNotification,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
};

export function useNotificationCenter(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx) {
    return {
      notifications: [],
      unreadCount: 0,
      activePopup: null,
      activeAlarm: null,
      isLoading: false,
      refreshNotifications: async () => {},
      markRead: async () => {},
      markAllRead: async () => {},
      dismissActiveAlert: async () => {},
      completeFromNotification: async () => {},
      snoozeFromNotification: async () => {},
      openFromNotification: async () => {},
    };
  }
  return ctx;
}

