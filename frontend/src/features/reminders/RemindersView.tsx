/**
 * AUREN Reminder Center — Upcoming, Due, Recurring, Completed, Cancelled, & History.
 */

import React, { useState } from 'react';
import {
  AlarmClock,
  Ban,
  Bell,
  BellRing,
  CheckCircle2,
  Clock,
  Edit2,
  FolderKanban,
  Globe,
  History,
  Plus,
  Repeat,
  RotateCw,
  Search,
  Smartphone,
  Trash2,
} from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { useAuth } from '../../context/AuthContext';
import {
  Reminder,
  ReminderCreateInput,
  ReminderUpdateInput,
  sendTestNotification,
} from '../../api/reminders';
import {
  REMINDER_KEYS,
  useCancelReminder,
  useCompleteReminder,
  useCreateReminder,
  useDeleteReminder,
  useDeliveryLogs,
  usePushSubscriptions,
  useReminders,
  useSnoozeReminder,
  useUpdateReminder,
} from '../../hooks/useReminders';
import { SETTINGS_KEYS, useUpdateUserProfile, useUserProfile } from '../../hooks/useSettings';
import { useNotificationCenter } from '../../context/NotificationContext';
import {
  enableDeviceWebPush,
  getBrowserNotificationPermission,
  isWebPushSupported,
  syncExistingDevicePushSubscription,
} from '../../lib/pushNotifications';
import { ReminderModal } from './ReminderModal';

type ReminderTab = 'upcoming' | 'due' | 'recurring' | 'completed' | 'history' | 'notifications';

function formatInTimezone(iso: string, tz: string): string {
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone: tz || 'UTC',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return new Date(iso).toLocaleString();
  }
}

export const RemindersView: React.FC = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ReminderTab>('upcoming');
  const [searchQuery, setSearchQuery] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingReminder, setEditingReminder] = useState<Reminder | null>(null);
  const [pushBannerStatus, setPushBannerStatus] = useState<string | null>(null);
  const [isEnablingPush, setIsEnablingPush] = useState(false);

  const { notifications, completeFromNotification, snoozeFromNotification, markRead } = useNotificationCenter();
  const { data: profile } = useUserProfile(user?.id);
  const updateProfileMutation = useUpdateUserProfile(user?.id);
  const { data: pushSubsData } = usePushSubscriptions(user?.id);
  const { data: deliveryLogsData } = useDeliveryLogs(undefined, user?.id);
  const activePushSubs = (pushSubsData?.items ?? []).filter((s) => s.is_active);
  const deliveryLogs = Array.isArray(deliveryLogsData) ? deliveryLogsData : [];
  const browserPerm = getBrowserNotificationPermission();
  const isLockscreenMasked = Boolean(profile?.preferences?.hide_sensitive_lockscreen);
  const needsPhonePushSetup = Boolean(
    user && isWebPushSupported() && (browserPerm !== 'granted' || activePushSubs.length === 0)
  );

  const handleEnablePhonePush = async () => {
    setIsEnablingPush(true);
    setPushBannerStatus(null);
    try {
      const res = await enableDeviceWebPush();
      if (res.success) {
        setPushBannerStatus('Phone/browser push enabled! Sending a quick test alert...');
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.pushSubscriptions(user?.id) });
        queryClient.invalidateQueries({ queryKey: SETTINGS_KEYS.profile(user?.id) });
        const testRes = await sendTestNotification().catch(() => null);
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.deliveryLogs(undefined, user?.id) });
        const deliveries = Array.isArray(testRes?.push_deliveries) ? testRes.push_deliveries : [];
        if (deliveries.some((d) => d.success)) {
          setPushBannerStatus('Push alerts active on this device — check your phone notification tray!');
        } else if (deliveries.length > 0 && deliveries[0]?.error) {
          setPushBannerStatus(`Push registered, but gateway returned: ${deliveries[0].error}`);
        } else {
          setPushBannerStatus('Device registered for Web Push! You will receive due reminder alerts on this device.');
        }
      } else {
        setPushBannerStatus(res.error || 'Could not enable push alerts on this device.');
      }
    } catch (err: any) {
      setPushBannerStatus(err?.message || 'Push registration failed.');
    } finally {
      setIsEnablingPush(false);
    }
  };

  const handleSyncOrRepairPush = async () => {
    setIsEnablingPush(true);
    setPushBannerStatus('Syncing device push registration & sending test alert...');
    try {
      const perm = getBrowserNotificationPermission();
      if (perm !== 'granted') {
        await handleEnablePhonePush();
        return;
      }
      await syncExistingDevicePushSubscription();
      const res = await enableDeviceWebPush();
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.pushSubscriptions(user?.id) });
      queryClient.invalidateQueries({ queryKey: SETTINGS_KEYS.profile(user?.id) });
      const testRes = await sendTestNotification().catch(() => null);
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.deliveryLogs(undefined, user?.id) });
      const deliveries = Array.isArray(testRes?.push_deliveries) ? testRes.push_deliveries : [];
      if (deliveries.some((d) => d.success)) {
        setPushBannerStatus('Device synced and test push delivered! Check your notification tray.');
      } else if (!res.success) {
        setPushBannerStatus(res.error || 'Could not sync push subscription.');
      } else if (deliveries.length > 0 && deliveries[0]?.error) {
        setPushBannerStatus(`Synced device, but push gateway reported: ${deliveries[0].error}`);
      } else {
        setPushBannerStatus('Device push registration refreshed.');
      }
    } catch (err: any) {
      setPushBannerStatus(err?.message || 'Device push sync failed.');
    } finally {
      setIsEnablingPush(false);
    }
  };

  const { data: remindersData, isLoading, refetch } = useReminders(
    activeTab === 'notifications'
      ? undefined
      : {
          status:
            activeTab === 'recurring'
              ? 'upcoming'
              : activeTab === 'history'
              ? 'history'
              : activeTab,
          recurring_only: activeTab === 'recurring',
          query: searchQuery || undefined,
          page: 1,
          page_size: 100,
        },
    user?.id
  );

  const createMutation = useCreateReminder(user?.id);
  const updateMutation = useUpdateReminder(user?.id);
  const snoozeMutation = useSnoozeReminder(user?.id);
  const completeMutation = useCompleteReminder(user?.id);
  const cancelMutation = useCancelReminder(user?.id);
  const deleteMutation = useDeleteReminder(user?.id);

  const handleOpenCreate = () => {
    setEditingReminder(null);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (rem: Reminder) => {
    setEditingReminder(rem);
    setIsModalOpen(true);
  };

  const handleModalSubmit = async (data: ReminderCreateInput | ReminderUpdateInput) => {
    if (editingReminder) {
      await updateMutation.mutateAsync({ reminderId: editingReminder.id, input: data as ReminderUpdateInput });
    } else {
      await createMutation.mutateAsync(data as ReminderCreateInput);
    }
  };

  const handleDelete = async (rem: Reminder) => {
    if (window.confirm(`Permanently delete reminder "${rem.title}"?`)) {
      await deleteMutation.mutateAsync(rem.id);
    }
  };

  const items = remindersData?.items ?? [];

  return (
    <div className="flex-1 flex flex-col h-full bg-white overflow-hidden text-slate-900">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between p-4 sm:p-6 border-b border-slate-200 bg-white gap-3 flex-shrink-0">
        <div className="flex items-center space-x-3.5">
          <div className="p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-600 shadow-sm">
            <BellRing className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold tracking-tight text-slate-900">Reminders &amp; Alarms</h1>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold">
                {remindersData?.total ?? 0} Items
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Persistent scheduled reminders, recurring routines, alarm alerts, and notification history.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => refetch()}
            className="flex-shrink-0 flex items-center space-x-1.5 px-3 py-2 min-h-[40px] rounded-xl bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700 cursor-pointer"
            title="Refresh reminders"
          >
            <RotateCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>

          <button
            type="button"
            onClick={handleOpenCreate}
            className="flex-shrink-0 flex items-center space-x-2 px-4 py-2 min-h-[40px] bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-xl shadow-sm transition cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>New Reminder</span>
          </button>
        </div>
      </div>

      {/* Tabs & Search */}
      <div className="p-4 sm:px-6 pb-3 space-y-3 border-b border-slate-200 bg-slate-50/70 flex-shrink-0">
        <div className="flex flex-wrap items-center gap-2 pb-1">
          {[
            { id: 'upcoming', label: 'Upcoming' },
            { id: 'due', label: 'Due & Snoozed' },
            { id: 'recurring', label: 'Recurring' },
            { id: 'completed', label: 'Completed' },
            { id: 'history', label: 'Cancelled & Missed' },
            { id: 'notifications', label: 'Alert History' },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id as ReminderTab)}
              className={`flex-shrink-0 px-3.5 py-2 min-h-[40px] rounded-xl text-xs font-semibold whitespace-nowrap transition cursor-pointer ${
                activeTab === tab.id
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'bg-white text-slate-600 border border-slate-200 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {isLockscreenMasked && (
          <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
            <div className="min-w-0">
              <p className="text-xs font-bold text-amber-950">
                Lock-Screen Push Alerts Are Currently Masked
              </p>
              <p className="text-[11px] text-amber-800 leading-snug">
                Your saved privacy setting hides task details and sends &quot;AUREN Reminder&quot;. Tap to show exact reminder titles &amp; times.
              </p>
            </div>
            <button
              type="button"
              onClick={async () => {
                await updateProfileMutation.mutateAsync({
                  preferences: { hide_sensitive_lockscreen: false },
                });
                queryClient.invalidateQueries({ queryKey: SETTINGS_KEYS.profile(user?.id) });
                setPushBannerStatus('Lock-screen alerts updated: reminders will now show specific titles & due times.');
              }}
              disabled={updateProfileMutation.isPending}
              className="flex-shrink-0 px-3.5 py-2 min-h-[38px] rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold transition cursor-pointer disabled:opacity-60"
            >
              Show Specific Task Details
            </button>
          </div>
        )}

        {(needsPhonePushSetup || pushBannerStatus) && (
          <div className="p-3 rounded-xl bg-emerald-50/90 border border-emerald-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
            <div className="flex items-start space-x-2.5 min-w-0">
              <Smartphone className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-bold text-emerald-950">
                  {browserPerm === 'denied'
                    ? 'Phone Push Notifications Are Blocked in Browser'
                    : 'Receive Alerts Even When Tab Is Closed'}
                </p>
                <p className="text-[11px] text-emerald-800 leading-snug">
                  {pushBannerStatus ||
                    (browserPerm === 'denied'
                      ? 'Open Chrome/browser Site Settings -> Notifications -> Allow for AUREN, then tap Enable below.'
                      : 'Tap Enable Phone Alerts to register this device for background push notifications.')}
                </p>
              </div>
            </div>
            {needsPhonePushSetup && (
              <button
                type="button"
                onClick={handleEnablePhonePush}
                disabled={isEnablingPush}
                className="flex-shrink-0 px-3.5 py-2 min-h-[38px] rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition cursor-pointer disabled:opacity-60"
              >
                {isEnablingPush ? 'Activating...' : 'Enable Phone Alerts'}
              </button>
            )}
          </div>
        )}

        {activeTab !== 'notifications' && (
          <div className="relative max-w-md">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search reminders..."
              className="w-full pl-10 pr-3.5 py-2 bg-white border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-emerald-500"
            />
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-3 scrollbar-thin">
        {!user ? (
          <div className="p-8 text-center rounded-2xl border border-slate-200 bg-slate-50 space-y-2">
            <Bell className="w-8 h-8 mx-auto text-emerald-600 opacity-80" />
            <h3 className="text-sm font-bold text-slate-900">Sign In to Manage Reminders</h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Personal reminders and Web Push notifications require an authenticated AUREN account.
            </p>
          </div>
        ) : activeTab === 'notifications' ? (
          <div className="space-y-4">
            {/* Background Web Push Status & Delivery Diagnostics */}
            <div className="p-4 rounded-2xl border border-slate-200 bg-slate-50/80 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    Background Push & Delivery Diagnostics
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Permission: <span className="font-mono font-semibold text-slate-700">{browserPerm}</span> ·
                    Registered devices:{' '}
                    <span className="font-mono font-semibold text-slate-700">{activePushSubs.length}</span>
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={isEnablingPush}
                    onClick={handleSyncOrRepairPush}
                    className="px-3 py-1.5 rounded-xl bg-white hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-700 flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <RotateCw className="w-3.5 h-3.5" />
                    <span>Sync & Test Push</span>
                  </button>
                </div>
              </div>

              {deliveryLogs.length > 0 && (
                <div className="space-y-1.5 pt-2 border-t border-slate-200/80">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">
                    Recent Delivery Attempts
                  </span>
                  <div className="space-y-1 max-h-44 overflow-y-auto pr-1">
                    {deliveryLogs.slice(0, 8).map((log) => (
                      <div
                        key={log.id}
                        className="flex flex-wrap items-center justify-between gap-2 text-[11px] px-2.5 py-1.5 rounded-lg bg-white border border-slate-200"
                      >
                        <div className="flex items-center space-x-2 min-w-0">
                          <span className="font-mono font-semibold text-slate-700">{log.channel}</span>
                          <span
                            className={`text-[10px] font-mono uppercase px-1.5 py-0.5 rounded ${
                              log.status === 'sent'
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : log.status === 'suppressed_quiet_hours' || log.status === 'skipped_disabled'
                                ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                : 'bg-rose-50 text-rose-700 border border-rose-200'
                            }`}
                          >
                            {log.status}
                          </span>
                          {log.http_status && (
                            <span className="text-[10px] font-mono text-slate-500">HTTP {log.http_status}</span>
                          )}
                          {log.error_detail && (
                            <span className="text-[10px] text-rose-600 truncate max-w-[240px]" title={log.error_detail}>
                              {log.error_detail}
                            </span>
                          )}
                        </div>
                        <span className="text-[10px] font-mono text-slate-400">
                          {new Date(log.created_at).toLocaleString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {notifications.length === 0 ? (
              <div className="p-10 text-center rounded-2xl border border-dashed border-slate-300 bg-slate-50/50 text-xs text-slate-500">
                <History className="w-8 h-8 mx-auto text-slate-300 mb-2" />
                No notification deliveries recorded yet.
              </div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className={`p-4 rounded-2xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                    n.status === 'unread' ? 'bg-emerald-50/40 border-emerald-300' : 'bg-white border-slate-200'
                  }`}
                >
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center space-x-2">
                      {n.is_alarm ? (
                        <AlarmClock className="w-4 h-4 text-amber-600 flex-shrink-0" />
                      ) : (
                        <Bell className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                      )}
                      <span className="text-xs sm:text-sm font-bold text-slate-900 truncate">{n.title}</span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-600 uppercase">
                        {n.status}
                      </span>
                    </div>
                    {n.body && <p className="text-xs text-slate-600 pl-6">{n.body}</p>}
                    <p className="text-[10px] text-slate-400 font-mono pl-6">
                      Triggered: {new Date(n.triggered_at).toLocaleString()} • Channel: {n.delivery_channel}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 pl-6 sm:pl-0">
                    {n.status === 'unread' && (
                      <button
                        type="button"
                        onClick={() => markRead(n.id)}
                        className="px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-700 cursor-pointer"
                      >
                        Mark Read
                      </button>
                    )}
                    {n.reminder_id && (
                      <>
                        <button
                          type="button"
                          onClick={() => snoozeFromNotification(n)}
                          className="px-3 py-1.5 rounded-xl bg-amber-50 hover:bg-amber-100 border border-amber-200 text-xs font-semibold text-amber-800 cursor-pointer"
                        >
                          Snooze
                        </button>
                        <button
                          type="button"
                          onClick={() => completeFromNotification(n)}
                          className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-semibold text-white cursor-pointer"
                        >
                          Complete
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        ) : isLoading ? (
          <div className="p-10 text-center text-xs text-slate-500 flex items-center justify-center">
            <Clock className="w-4 h-4 animate-spin mr-2 text-emerald-600" />
            Loading reminders...
          </div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center rounded-2xl border border-dashed border-slate-300 bg-slate-50/50 space-y-3">
            <Bell className="w-10 h-10 mx-auto text-slate-300" />
            <div>
              <h3 className="text-sm font-bold text-slate-800">No reminders in this view</h3>
              <p className="text-xs text-slate-500 mt-1">
                Schedule one here or ask AUREN in Chat (e.g. &ldquo;Remind me at 4 PM to continue working on AUREN&rdquo;).
              </p>
            </div>
            <button
              type="button"
              onClick={handleOpenCreate}
              className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold cursor-pointer"
            >
              Create Reminder
            </button>
          </div>
        ) : (
          items.map((rem) => (
            <div
              key={rem.id}
              className={`p-4 rounded-2xl border transition shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                rem.status === 'due'
                  ? 'bg-amber-50/50 border-amber-300'
                  : rem.status === 'completed'
                  ? 'bg-slate-50 border-slate-200 opacity-75'
                  : 'bg-white border-slate-200 hover:border-emerald-300'
              }`}
            >
              <div className="space-y-1.5 min-w-0 flex-1">
                <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                  {rem.is_alarm ? (
                    <AlarmClock className="w-4 h-4 text-amber-600 flex-shrink-0" />
                  ) : (
                    <Bell className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                  )}
                  <span
                    className={`text-sm font-bold ${
                      rem.status === 'completed' ? 'line-through text-slate-400' : 'text-slate-900'
                    }`}
                  >
                    {rem.title}
                  </span>
                  <span
                    className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${
                      rem.status === 'due'
                        ? 'bg-amber-100 text-amber-800 border-amber-300'
                        : rem.status === 'snoozed'
                        ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                        : rem.status === 'completed'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : rem.status === 'cancelled' || rem.status === 'missed'
                        ? 'bg-rose-50 text-rose-700 border-rose-200'
                        : 'bg-slate-100 text-slate-700 border-slate-200'
                    }`}
                  >
                    {rem.status}
                  </span>
                  {rem.is_alarm && (
                    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                      Alarm
                    </span>
                  )}
                </div>

                {rem.description && <p className="text-xs text-slate-600 pl-6">{rem.description}</p>}

                <div className="flex items-center flex-wrap gap-2 pl-6 text-[11px] text-slate-600">
                  <span className="flex items-center font-medium text-slate-800">
                    <Clock className="w-3 h-3 mr-1 text-emerald-600" />
                    {formatInTimezone(rem.snoozed_until || rem.trigger_at, rem.timezone)}
                  </span>

                  <span className="flex items-center text-[10px] font-mono bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200 text-slate-600">
                    <Globe className="w-3 h-3 mr-1 text-slate-400" />
                    {rem.timezone}
                  </span>

                  {rem.recurrence_text && (
                    <span className="flex items-center text-[10px] font-semibold bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200">
                      <Repeat className="w-3 h-3 mr-1" />
                      {rem.recurrence_text}
                    </span>
                  )}

                  {rem.task_id && (
                    <Link
                      to="/tasks"
                      className="flex items-center text-[10px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 px-2 py-0.5 rounded border border-slate-200"
                    >
                      <FolderKanban className="w-3 h-3 mr-1 text-emerald-600" />
                      {rem.task_title || 'Linked Task'}
                    </Link>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center flex-wrap gap-1.5 pl-6 sm:pl-0 flex-shrink-0">
                {rem.status !== 'completed' && rem.status !== 'cancelled' && (
                  <>
                    <button
                      type="button"
                      onClick={() => completeMutation.mutate(rem.id)}
                      className="flex-shrink-0 px-3 py-2 min-h-[40px] rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center space-x-1 cursor-pointer"
                      title="Mark completed"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Complete</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => snoozeMutation.mutate({ reminderId: rem.id, snoozeMinutes: 10 })}
                      className="flex-shrink-0 px-3 py-2 min-h-[40px] rounded-xl bg-amber-50 hover:bg-amber-100 border border-amber-200 text-amber-800 text-xs font-semibold flex items-center space-x-1 cursor-pointer"
                      title="Snooze 10 minutes"
                    >
                      <Clock className="w-3.5 h-3.5" />
                      <span>Snooze</span>
                    </button>
                  </>
                )}

                <button
                  type="button"
                  onClick={() => handleOpenEdit(rem)}
                  className="flex-shrink-0 p-2 rounded-xl text-slate-500 hover:text-slate-900 hover:bg-slate-100 border border-slate-200 cursor-pointer touch-target flex items-center justify-center"
                  title="Edit / Reschedule"
                  aria-label="Edit reminder"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                </button>

                {rem.status !== 'completed' && rem.status !== 'cancelled' && (
                  <button
                    type="button"
                    onClick={() => cancelMutation.mutate(rem.id)}
                    className="flex-shrink-0 p-2 rounded-xl text-slate-500 hover:text-amber-700 hover:bg-amber-50 border border-slate-200 cursor-pointer touch-target flex items-center justify-center"
                    title="Cancel reminder"
                    aria-label="Cancel reminder"
                  >
                    <Ban className="w-3.5 h-3.5" />
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => handleDelete(rem)}
                  className="flex-shrink-0 p-2 rounded-xl text-slate-500 hover:text-rose-600 hover:bg-rose-50 border border-slate-200 cursor-pointer touch-target flex items-center justify-center"
                  title="Delete reminder"
                  aria-label="Delete reminder"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <ReminderModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleModalSubmit}
        initialReminder={editingReminder}
      />
    </div>
  );
};

