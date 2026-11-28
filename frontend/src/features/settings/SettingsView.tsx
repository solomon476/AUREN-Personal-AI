/**
 * Settings & Preferences Management View.
 * Real, operational configuration for Account, AI Persona & Model,
 * Memory Controls, Privacy Guarantees, and GDPR Data Export.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React, { useEffect, useState, useRef } from 'react';
import {
  Settings,
  User,
  Bot,
  Brain,
  Download,
  Save,
  CheckCircle2,
  Database,
  Lock,
  LogOut,
  Cpu,
  Smartphone,
  Monitor,
  ShieldCheck,
  Layers,
  Bell,
  Volume2,
  AlarmClock,
  Moon,
  Trash2,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useTheme, ThemeMode } from '../../context/ThemeContext';
import { useExportUserData, useUpdateUserProfile, useUserProfile, SETTINGS_KEYS } from '../../hooks/useSettings';
import { usePWAInstall } from '../../hooks/usePWAInstall';
import { useCreateReminder, useDeliveryLogs, usePushSubscriptions } from '../../hooks/useReminders';
import { sendTestNotification } from '../../api/reminders';
import { playAlertSound } from '../../lib/soundAlert';
import {
  disableDeviceWebPush,
  enableDeviceWebPush,
  getBrowserNotificationPermission,
  isWebPushSupported,
  syncExistingDevicePushSubscription,
} from '../../lib/pushNotifications';
import { useQueryClient } from '@tanstack/react-query';
import { REMINDER_KEYS } from '../../hooks/useReminders';

export const SettingsView: React.FC = () => {
  const { user, signOut } = useAuth();
  const queryClient = useQueryClient();
  const { data: profile } = useUserProfile(user?.id);
  const updateProfileMutation = useUpdateUserProfile(user?.id);
  const exportDataMutation = useExportUserData();
  const { data: pushSubsData } = usePushSubscriptions(user?.id);
  const { data: deliveryLogsData } = useDeliveryLogs(undefined, user?.id);
  const deliveryLogs = Array.isArray(deliveryLogsData) ? deliveryLogsData : [];
  useCreateReminder(user?.id);
  const { isInstalled, hasDeferredPrompt, promptInstall } = usePWAInstall();

  // Tab State
  const [activeTab, setActiveTab] = useState<'profile' | 'notifications' | 'ai' | 'memory' | 'data' | 'app'>('profile');

  // Form State
  const [fullName, setFullName] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const { theme, setTheme } = useTheme();
  const [aiModel, setAiModel] = useState('gemini-2.5-flash');
  const [aiTone, setAiTone] = useState('concise');
  const [aiCustomInstructions, setAiCustomInstructions] = useState('');
  const [memoryAutoExtraction, setMemoryAutoExtraction] = useState(true);
  const [memoryMinConfidence, setMemoryMinConfidence] = useState(0.7);

  // Notification & Reminder Preferences State
  const [inAppEnabled, setInAppEnabled] = useState(true);
  const [browserPushEnabled, setBrowserPushEnabled] = useState(false);
  const [audibleAlertsEnabled, setAudibleAlertsEnabled] = useState(true);
  const [reminderSound, setReminderSound] = useState('chime');
  const [defaultReminderBehavior, setDefaultReminderBehavior] = useState('notification');
  const [defaultSnoozeMinutes, setDefaultSnoozeMinutes] = useState(10);
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietHoursStart, setQuietHoursStart] = useState('22:00');
  const [quietHoursEnd, setQuietHoursEnd] = useState('07:00');
  const [quietHoursAllowAlarms, setQuietHoursAllowAlarms] = useState(false);
  const [timezonePref, setTimezonePref] = useState(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch {
      return 'UTC';
    }
  });
  const [dailyBriefingEnabled, setDailyBriefingEnabled] = useState(false);
  const [dailyBriefingTime, setDailyBriefingTime] = useState('08:00');
  const [eveningReviewEnabled, setEveningReviewEnabled] = useState(false);
  const [eveningReviewTime, setEveningReviewTime] = useState('19:00');
  const [notifPriorityDefault, setNotifPriorityDefault] = useState('normal');
  const [recurringMissedPolicy, setRecurringMissedPolicy] = useState('trigger_once_then_advance');
  const [taskLeadMinutes, setTaskLeadMinutes] = useState(30);
  const [autoRemindNewTasks, setAutoRemindNewTasks] = useState(true);
  const [overdueTaskReminders, setOverdueTaskReminders] = useState(false);
  const [autoRescheduleTaskReminders, setAutoRescheduleTaskReminders] = useState(true);
  const [suppressOnTaskComplete, setSuppressOnTaskComplete] = useState(true);
  const [hideSensitiveLockscreen, setHideSensitiveLockscreen] = useState(true);
  const [pushActionStatus, setPushActionStatus] = useState<string | null>(null);

  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const hasSyncedRef = useRef(false);

  // Sync profile data when loaded
  useEffect(() => {
    if (profile && !hasSyncedRef.current) {
      hasSyncedRef.current = true;
      setFullName(profile.full_name || '');
      setAvatarUrl(profile.avatar_url || '');
      const prefs = profile.preferences || {};
      if (prefs.theme && ['light', 'dark', 'midnight', 'obsidian'].includes(String(prefs.theme))) {
        setTheme(prefs.theme as ThemeMode);
      }
      if (prefs.ai_model) setAiModel(String(prefs.ai_model));
      if (prefs.ai_tone) setAiTone(String(prefs.ai_tone));
      if (prefs.ai_custom_instructions) setAiCustomInstructions(String(prefs.ai_custom_instructions));
      if (prefs.memory_auto_extraction !== undefined) setMemoryAutoExtraction(Boolean(prefs.memory_auto_extraction));
      if (prefs.memory_min_confidence !== undefined) setMemoryMinConfidence(Number(prefs.memory_min_confidence));

      if (prefs.in_app_notifications_enabled !== undefined) setInAppEnabled(Boolean(prefs.in_app_notifications_enabled));
      if (prefs.browser_push_enabled !== undefined) setBrowserPushEnabled(Boolean(prefs.browser_push_enabled));
      if (prefs.audible_alerts_enabled !== undefined) setAudibleAlertsEnabled(Boolean(prefs.audible_alerts_enabled));
      if (prefs.reminder_sound) setReminderSound(String(prefs.reminder_sound));
      if (prefs.default_reminder_behavior) setDefaultReminderBehavior(String(prefs.default_reminder_behavior));
      if (prefs.default_snooze_minutes !== undefined) setDefaultSnoozeMinutes(Number(prefs.default_snooze_minutes));
      if (prefs.quiet_hours_enabled !== undefined) setQuietHoursEnabled(Boolean(prefs.quiet_hours_enabled));
      if (prefs.quiet_hours_start) setQuietHoursStart(String(prefs.quiet_hours_start));
      if (prefs.quiet_hours_end) setQuietHoursEnd(String(prefs.quiet_hours_end));
      if (prefs.quiet_hours_allow_alarms !== undefined) setQuietHoursAllowAlarms(Boolean(prefs.quiet_hours_allow_alarms));
      if (prefs.timezone) setTimezonePref(String(prefs.timezone));
      if (prefs.daily_briefing_enabled !== undefined) setDailyBriefingEnabled(Boolean(prefs.daily_briefing_enabled));
      if (prefs.daily_briefing_time) setDailyBriefingTime(String(prefs.daily_briefing_time));
      if (prefs.evening_review_enabled !== undefined) setEveningReviewEnabled(Boolean(prefs.evening_review_enabled));
      if (prefs.evening_review_time) setEveningReviewTime(String(prefs.evening_review_time));
      if (prefs.notification_priority_default) setNotifPriorityDefault(String(prefs.notification_priority_default));
      if (prefs.recurring_missed_policy) setRecurringMissedPolicy(String(prefs.recurring_missed_policy));
      if (prefs.task_default_lead_minutes !== undefined) setTaskLeadMinutes(Number(prefs.task_default_lead_minutes));
      if (prefs.auto_remind_new_tasks !== undefined) setAutoRemindNewTasks(Boolean(prefs.auto_remind_new_tasks));
      if (prefs.overdue_task_reminders_enabled !== undefined) setOverdueTaskReminders(Boolean(prefs.overdue_task_reminders_enabled));
      if (prefs.auto_reschedule_task_reminders !== undefined) setAutoRescheduleTaskReminders(Boolean(prefs.auto_reschedule_task_reminders));
      if (prefs.suppress_reminders_on_task_complete !== undefined) setSuppressOnTaskComplete(Boolean(prefs.suppress_reminders_on_task_complete));
      if (prefs.hide_sensitive_lockscreen !== undefined) setHideSensitiveLockscreen(Boolean(prefs.hide_sensitive_lockscreen));
    }
  }, [profile, setTheme]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveStatus(null);
    try {
      await updateProfileMutation.mutateAsync({
        full_name: fullName.trim() || undefined,
        avatar_url: avatarUrl.trim() || undefined,
        preferences: {
          theme,
          ai_model: aiModel,
          ai_tone: aiTone,
          ai_custom_instructions: aiCustomInstructions.trim() || undefined,
          memory_auto_extraction: memoryAutoExtraction,
          memory_min_confidence: memoryMinConfidence,
          in_app_notifications_enabled: inAppEnabled,
          browser_push_enabled: browserPushEnabled,
          audible_alerts_enabled: audibleAlertsEnabled,
          reminder_sound: reminderSound,
          default_reminder_behavior: defaultReminderBehavior,
          default_snooze_minutes: defaultSnoozeMinutes,
          quiet_hours_enabled: quietHoursEnabled,
          quiet_hours_start: quietHoursStart,
          quiet_hours_end: quietHoursEnd,
          quiet_hours_allow_alarms: quietHoursAllowAlarms,
          timezone: timezonePref,
          daily_briefing_enabled: dailyBriefingEnabled,
          daily_briefing_time: dailyBriefingTime,
          evening_review_enabled: eveningReviewEnabled,
          evening_review_time: eveningReviewTime,
          notification_priority_default: notifPriorityDefault,
          recurring_missed_policy: recurringMissedPolicy,
          task_default_lead_minutes: taskLeadMinutes,
          auto_remind_new_tasks: autoRemindNewTasks,
          overdue_task_reminders_enabled: overdueTaskReminders,
          auto_reschedule_task_reminders: autoRescheduleTaskReminders,
          suppress_reminders_on_task_complete: suppressOnTaskComplete,
          hide_sensitive_lockscreen: hideSensitiveLockscreen,
        },
      });
      setSaveStatus('Settings saved successfully.');
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (err: any) {
      setSaveStatus(`Failed to save: ${err.message || 'Unknown error'}`);
    }
  };

  useEffect(() => {
    if (profile?.preferences?.browser_push_enabled === undefined && (pushSubsData?.items ?? []).some((s) => s.is_active)) {
      setBrowserPushEnabled(true);
    }
  }, [profile?.preferences?.browser_push_enabled, pushSubsData?.items]);

  const handleActivatePush = async () => {
    setPushActionStatus('Requesting notification permission & registering device...');
    try {
      const res = await enableDeviceWebPush();
      if (res.success) {
        setBrowserPushEnabled(true);
        setPushActionStatus('Device registered for background Web Push alerts.');
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.pushSubscriptions(user?.id) });
        queryClient.invalidateQueries({ queryKey: SETTINGS_KEYS.profile(user?.id) });
        queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.deliveryLogs(undefined, user?.id) });
        await updateProfileMutation.mutateAsync({ preferences: { browser_push_enabled: true } });
      } else {
        setPushActionStatus(res.error || 'Could not enable Web Push.');
      }
    } catch (err: any) {
      setPushActionStatus(err?.message || 'Push registration failed.');
    }
  };

  const handleSyncThisDevice = async () => {
    setPushActionStatus('Re-syncing browser push subscription...');
    try {
      const res = await syncExistingDevicePushSubscription();
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.pushSubscriptions(user?.id) });
      queryClient.invalidateQueries({ queryKey: SETTINGS_KEYS.profile(user?.id) });
      if (res.synced) {
        setPushActionStatus(`Device subscription repaired (${res.reason}).`);
      } else if (res.reason === 'permission_not_granted') {
        await handleActivatePush();
      } else {
        setPushActionStatus(`Push subscription check complete (${res.reason}).`);
      }
    } catch (err: any) {
      setPushActionStatus(err?.message || 'Device push sync failed.');
    }
  };

  const handleRemoveSubscription = async (subId: string) => {
    setPushActionStatus(null);
    await disableDeviceWebPush(subId);
    queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.pushSubscriptions(user?.id) });
    setPushActionStatus('Push device removed.');
  };

  const handleSendTestAlert = async () => {
    setPushActionStatus('Sending test alert...');
    try {
      if (audibleAlertsEnabled) {
        playAlertSound(reminderSound, defaultReminderBehavior === 'alarm');
      }
      const res: any = await sendTestNotification();
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.notifications(user?.id) });
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.pushSubscriptions(user?.id) });
      queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.deliveryLogs(undefined, user?.id) });
      const deliveries = Array.isArray(res?.push_deliveries) ? res.push_deliveries : [];
      const regCount = Number(res?.registered_devices_count ?? deliveries.length);
      if (regCount === 0) {
        setPushActionStatus(
          'In-app alert sent, but 0 push devices are registered yet. Tap "Enable Push on This Device" above first.'
        );
      } else {
        const succeeded = deliveries.filter((d: any) => d.success).length;
        const failed = deliveries.filter((d: any) => !d.success);
        if (succeeded > 0 && failed.length === 0) {
          setPushActionStatus(`Test push sent to ${succeeded} registered device(s) and Notification Center.`);
        } else {
          const errText = failed[0]?.error || 'Push gateway rejected delivery';
          setPushActionStatus(`Delivered in-app (${succeeded}/${regCount} push ok; error: ${errText}).`);
        }
      }
    } catch (err: any) {
      setPushActionStatus(err?.message || 'Failed sending test notification.');
    }
  };

  const handleExportData = async () => {
    setExportStatus('Generating complete personal data export...');
    try {
      const data = await exportDataMutation.mutateAsync();
      const jsonBlob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const downloadUrl = URL.createObjectURL(jsonBlob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `auren_data_export_${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(downloadUrl);
      setExportStatus('Data export downloaded successfully.');
      setTimeout(() => setExportStatus(null), 3500);
    } catch (err: any) {
      setExportStatus(`Export failed: ${err.message}`);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#07080c] overflow-hidden text-slate-100">
      {/* Top Banner */}
      <div className="px-6 py-4.5 border-b border-white/[0.06] bg-[#0e1017]/70 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center space-x-3.5">
          <div className="p-2.5 rounded-xl bg-champagne-500/10 border border-champagne-500/20 text-champagne-400 shadow-sm">
            <Settings className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold tracking-tight text-white">Settings &amp; Preferences</h1>
              <span className="hidden sm:inline-flex text-[10px] font-mono px-2 py-0.5 rounded bg-graphite-800/90 text-champagne-300 border border-champagne-500/20">
                AUREN Configuration
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Configure your personal AI operating system, privacy boundaries, and model parameters.
            </p>
          </div>
        </div>
      </div>

      {/* Main Container */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Navigation Tabs (Horizontal scroll strip on mobile, vertical sidebar on desktop) */}
        <div className="w-full md:w-64 border-b md:border-b-0 md:border-r border-white/[0.06] p-2.5 sm:p-4 flex flex-row overflow-x-auto scrollbar-none md:flex-col gap-1.5 sm:space-y-1.5 bg-[#07080c] flex-shrink-0">
          <button
            onClick={() => setActiveTab('profile')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'profile'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <User className="w-4 h-4 text-champagne-400" />
            <span>Profile &amp; Account</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('notifications')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'notifications'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Bell className="w-4 h-4 text-champagne-400" />
            <span>Notifications &amp; Alarms</span>
          </button>

          <button
            onClick={() => setActiveTab('ai')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'ai'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Bot className="w-4 h-4 text-champagne-400" />
            <span>AI Model &amp; Tone</span>
          </button>

          <button
            onClick={() => setActiveTab('memory')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'memory'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Brain className="w-4 h-4 text-champagne-400" />
            <span>Memory &amp; Privacy</span>
          </button>

          <button
            onClick={() => setActiveTab('data')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'data'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Database className="w-4 h-4 text-champagne-400" />
            <span>Data Management &amp; Export</span>
          </button>

          <button
            onClick={() => setActiveTab('app')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'app'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Smartphone className="w-4 h-4 text-champagne-400" />
            <span>App &amp; PWA Installation</span>
          </button>
        </div>

        {/* Tab Content Panel */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 max-w-3xl scrollbar-thin">
          <form onSubmit={handleSave} className="space-y-6">
            {saveStatus && (
              <div className="p-3.5 rounded-xl bg-indigo-950/40 border border-indigo-500/30 text-xs text-indigo-200 flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-champagne-400" />
                <span>{saveStatus}</span>
              </div>
            )}

            {/* PROFILE TAB */}
            {activeTab === 'profile' && (
              <div className="space-y-5">
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">User Identity &amp; Profile</h2>
                  <p className="text-xs text-slate-400">Manage your display identity and account credentials.</p>
                </div>

                <div className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">User ID (UUID)</label>
                    <input
                      type="text"
                      disabled
                      value={user?.id || profile?.id || 'Not authenticated'}
                      className="w-full bg-[#0e1017]/50 border border-white/[0.06] rounded-xl px-3.5 py-2 text-xs font-mono text-slate-400 select-all"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Email Address</label>
                    <input
                      type="email"
                      disabled
                      value={user?.email || profile?.email || ''}
                      className="w-full bg-[#0e1017]/50 border border-white/[0.06] rounded-xl px-3.5 py-2 text-xs text-slate-300"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Full Name</label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Your name..."
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-champagne-500/50 transition"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Avatar URL</label>
                    <input
                      type="url"
                      value={avatarUrl}
                      onChange={(e) => setAvatarUrl(e.target.value)}
                      placeholder="https://..."
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-champagne-500/50 transition"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Theme</label>
                    <select
                      value={theme}
                      onChange={(e) => setTheme(e.target.value as ThemeMode)}
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-champagne-500/50 transition"
                    >
                      <option value="light">Executive White (Light Background)</option>
                      <option value="dark">Dark Slate</option>
                      <option value="midnight">Midnight Indigo (Deep Contrast)</option>
                      <option value="obsidian">Pure Obsidian (OLED Black)</option>
                    </select>
                  </div>
                </div>

                {/* Session Management */}
                {user && (
                  <div className="pt-4 border-t border-white/[0.06] space-y-3">
                    <h3 className="text-xs font-semibold text-slate-300">Active Session</h3>
                    <div className="flex items-center justify-between p-4 rounded-xl bg-[#0e1017]/70 border border-white/[0.06]">
                      <div>
                        <span className="text-xs text-slate-200 block font-medium">Logged in as {user.email}</span>
                        <span className="text-[10px] text-slate-500 font-mono">Role: {user.role || 'authenticated'}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => signOut()}
                        className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-white/[0.06] hover:bg-rose-950/60 hover:text-rose-300 hover:border-rose-800/40 text-slate-300 text-xs font-medium transition border border-white/[0.08] cursor-pointer"
                      >
                        <LogOut className="w-3.5 h-3.5" />
                        <span>Sign Out</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* NOTIFICATIONS & REMINDERS TAB */}
            {activeTab === 'notifications' && (
              <div className="space-y-6">
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">Smart Reminders, Alarms &amp; Push Notifications</h2>
                  <p className="text-xs text-slate-400">
                    Configure background Web Push delivery, alarm sounds, quiet hours, timezone, and task reminder policies.
                  </p>
                </div>

                {/* Delivery Channels & Browser Push Registration */}
                <div className="space-y-3">
                  <div className="p-4 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">In-App Popups &amp; Notification Center</span>
                      <span className="text-[11px] text-slate-400">Show immediate popups and alarm overlays while AUREN is open.</span>
                    </div>
                    <input
                      type="checkbox"
                      checked={inAppEnabled}
                      onChange={(e) => setInAppEnabled(e.target.checked)}
                      className="w-4 h-4 accent-emerald-500"
                    />
                  </div>

                  <div className="p-4 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-xs font-semibold text-slate-200 block">Browser / PWA Push Notifications</span>
                        <span className="text-[11px] text-slate-400">
                          Deliver background push alerts when AUREN tabs are closed (subject to OS &amp; browser permissions).
                        </span>
                      </div>
                      <input
                        type="checkbox"
                        checked={browserPushEnabled}
                        onChange={(e) => setBrowserPushEnabled(e.target.checked)}
                        className="w-4 h-4 accent-emerald-500"
                      />
                    </div>

                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={handleActivatePush}
                        className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition cursor-pointer"
                      >
                        Enable Push on This Device
                      </button>
                      <button
                        type="button"
                        onClick={handleSyncThisDevice}
                        className="px-3.5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.08] text-slate-200 text-xs font-medium transition cursor-pointer"
                      >
                        Sync Device
                      </button>
                      <button
                        type="button"
                        onClick={handleSendTestAlert}
                        className="px-3.5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.08] text-slate-200 text-xs font-medium transition cursor-pointer"
                      >
                        Send Test Alert
                      </button>
                      <span className="text-[10px] font-mono text-slate-400">
                        Permission: {getBrowserNotificationPermission()} · Support: {isWebPushSupported() ? 'Ready' : 'Browser Restricted'} · Background Push: {browserPushEnabled ? 'ON' : 'OFF'}
                      </span>
                    </div>

                    {pushActionStatus && (
                      <p className="text-[11px] text-champagne-300 font-mono">{pushActionStatus}</p>
                    )}

                    {/* Registered Devices */}
                    {pushSubsData && pushSubsData.items.length > 0 && (
                      <div className="space-y-1.5 pt-2 border-t border-white/[0.06]">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                          Registered Devices ({pushSubsData.items.length})
                        </span>
                        {pushSubsData.items.map((sub) => (
                          <div key={sub.id} className="flex items-center justify-between p-2.5 rounded-lg bg-[#07080c] border border-white/[0.06] text-xs">
                            <div className="min-w-0">
                              <span className="text-slate-200 font-medium block truncate">
                                {sub.device_label || 'Browser Device'}
                              </span>
                              <span className="text-[10px] text-slate-500 font-mono block">
                                {sub.is_active ? 'Active' : 'Inactive / Expired'}
                                {sub.last_success_at ? ` · Last OK: ${new Date(sub.last_success_at).toLocaleString()}` : ''}
                                {sub.failure_count > 0 ? ` · Failures: ${sub.failure_count}` : ''}
                              </span>
                              {sub.last_error && (
                                <span className="text-[10px] text-rose-400 font-mono block truncate" title={sub.last_error}>
                                  Last Error: {sub.last_error}
                                </span>
                              )}
                            </div>
                            <button
                              type="button"
                              onClick={() => handleRemoveSubscription(sub.id)}
                              className="p-1.5 text-slate-400 hover:text-rose-400 cursor-pointer"
                              title="Remove push device"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Delivery Diagnostics */}
                    {deliveryLogs.length > 0 && (
                      <div className="space-y-1.5 pt-2 border-t border-white/[0.06]">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                          Recent Push & Alert Delivery Diagnostics
                        </span>
                        <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                          {deliveryLogs.slice(0, 6).map((log) => (
                            <div key={log.id} className="flex flex-wrap items-center justify-between gap-2 p-2 rounded-lg bg-[#07080c] border border-white/[0.06] text-[10px] font-mono">
                              <div className="flex items-center space-x-2 min-w-0">
                                <span className="text-slate-300 font-semibold">{log.channel}</span>
                                <span
                                  className={`px-1.5 py-0.5 rounded uppercase ${
                                    log.status === 'sent'
                                      ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                                      : log.status === 'suppressed_quiet_hours' || log.status === 'skipped_disabled'
                                      ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                                      : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                                  }`}
                                >
                                  {log.status}
                                </span>
                                {log.http_status && <span className="text-slate-400">HTTP {log.http_status}</span>}
                                {log.error_detail && (
                                  <span className="text-rose-400 truncate max-w-[210px]" title={log.error_detail}>
                                    {log.error_detail}
                                  </span>
                                )}
                              </div>
                              <span className="text-slate-500">{new Date(log.created_at).toLocaleTimeString()}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <p className="text-[10px] text-slate-500 leading-relaxed">
                      Platform note: Web Browsers and PWAs cannot ring an OS-level native phone alarm when an application is force-closed or muted by OS Do Not Disturb. On iOS, install AUREN to the Home Screen (iOS 16.4+) to receive Web Push alerts.
                    </p>
                  </div>
                </div>

                {/* Sound, Alarm Behavior & Snooze */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                  <div className="p-4 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] flex items-center justify-between sm:col-span-2">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">Audible Alerts</span>
                      <span className="text-[11px] text-slate-400">Play sound chime or alarm tone when reminders trigger in AUREN.</span>
                    </div>
                    <input
                      type="checkbox"
                      checked={audibleAlertsEnabled}
                      onChange={(e) => setAudibleAlertsEnabled(e.target.checked)}
                      className="w-4 h-4 accent-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">
                      <Volume2 className="w-3.5 h-3.5 inline mr-1" />
                      Reminder Sound
                    </label>
                    <div className="flex space-x-2">
                      <select
                        value={reminderSound}
                        onChange={(e) => setReminderSound(e.target.value)}
                        className="flex-1 bg-[#0e1017] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-slate-200"
                      >
                        <option value="chime">Executive Chime</option>
                        <option value="bell">Crystal Bell</option>
                        <option value="pulse">Alarm Pulse</option>
                        <option value="gentle">Gentle Tone</option>
                        <option value="silent">Silent</option>
                      </select>
                      <button
                        type="button"
                        onClick={() => playAlertSound(reminderSound, defaultReminderBehavior === 'alarm')}
                        className="px-3 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.08] text-xs text-slate-200 cursor-pointer"
                      >
                        Preview
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">
                      <AlarmClock className="w-3.5 h-3.5 inline mr-1" />
                      Default Reminder Behavior
                    </label>
                    <select
                      value={defaultReminderBehavior}
                      onChange={(e) => setDefaultReminderBehavior(e.target.value)}
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-slate-200"
                    >
                      <option value="notification">Standard Popup + Push</option>
                      <option value="alarm">Alarm-Style Modal + Repeating Tone</option>
                      <option value="silent">Silent (Notification Center only)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Default Snooze Duration</label>
                    <select
                      value={defaultSnoozeMinutes}
                      onChange={(e) => setDefaultSnoozeMinutes(Number(e.target.value))}
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-slate-200"
                    >
                      <option value={5}>5 minutes</option>
                      <option value={10}>10 minutes</option>
                      <option value={15}>15 minutes</option>
                      <option value={30}>30 minutes</option>
                      <option value={60}>1 hour</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Default Priority</label>
                    <select
                      value={notifPriorityDefault}
                      onChange={(e) => setNotifPriorityDefault(e.target.value)}
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-slate-200"
                    >
                      <option value="low">Low</option>
                      <option value="normal">Normal</option>
                      <option value="high">High</option>
                      <option value="alarm">Urgent Alarm</option>
                    </select>
                  </div>
                </div>

                {/* Quiet Hours & Timezone */}
                <div className="p-4 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] space-y-3.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Moon className="w-4 h-4 text-indigo-400" />
                      <div>
                        <span className="text-xs font-semibold text-slate-200 block">Quiet Hours</span>
                        <span className="text-[11px] text-slate-400">
                          Suppresses noncritical audible &amp; push interruptions while preserving items in Notification Center.
                        </span>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={quietHoursEnabled}
                      onChange={(e) => setQuietHoursEnabled(e.target.checked)}
                      className="w-4 h-4 accent-emerald-500"
                    />
                  </div>

                  {quietHoursEnabled && (
                    <div className="grid grid-cols-2 gap-3 pt-1">
                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">Start Time</label>
                        <input
                          type="time"
                          value={quietHoursStart}
                          onChange={(e) => setQuietHoursStart(e.target.value)}
                          className="w-full bg-[#07080c] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-slate-200"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">End Time</label>
                        <input
                          type="time"
                          value={quietHoursEnd}
                          onChange={(e) => setQuietHoursEnd(e.target.value)}
                          className="w-full bg-[#07080c] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-slate-200"
                        />
                      </div>
                      <label className="col-span-2 flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={quietHoursAllowAlarms}
                          onChange={(e) => setQuietHoursAllowAlarms(e.target.checked)}
                          className="accent-amber-500"
                        />
                        <span>Allow urgent alarm-style reminders to bypass quiet hours</span>
                      </label>
                    </div>
                  )}

                  <div className="pt-2 border-t border-white/[0.06]">
                    <label className="block text-xs font-medium text-slate-400 mb-1">Configured Timezone (IANA)</label>
                    <div className="flex space-x-2">
                      <input
                        type="text"
                        value={timezonePref}
                        onChange={(e) => setTimezonePref(e.target.value)}
                        placeholder="Africa/Nairobi"
                        className="flex-1 bg-[#07080c] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-slate-200"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          try {
                            setTimezonePref(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
                          } catch {}
                        }}
                        className="px-3 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.08] text-xs text-slate-200 cursor-pointer"
                      >
                        Auto-Detect
                      </button>
                    </div>
                  </div>
                </div>

                {/* Daily Briefing, Evening Review, Recurring & Task Sync Policies */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                  <div className="p-3.5 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-200">Daily Briefing</span>
                      <input
                        type="checkbox"
                        checked={dailyBriefingEnabled}
                        onChange={(e) => setDailyBriefingEnabled(e.target.checked)}
                        className="w-4 h-4 accent-emerald-500"
                      />
                    </div>
                    <input
                      type="time"
                      value={dailyBriefingTime}
                      onChange={(e) => setDailyBriefingTime(e.target.value)}
                      className="w-full bg-[#07080c] border border-white/[0.08] rounded-xl px-3 py-1.5 text-xs text-slate-200"
                    />
                  </div>

                  <div className="p-3.5 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-200">Evening Review</span>
                      <input
                        type="checkbox"
                        checked={eveningReviewEnabled}
                        onChange={(e) => setEveningReviewEnabled(e.target.checked)}
                        className="w-4 h-4 accent-emerald-500"
                      />
                    </div>
                    <input
                      type="time"
                      value={eveningReviewTime}
                      onChange={(e) => setEveningReviewTime(e.target.value)}
                      className="w-full bg-[#07080c] border border-white/[0.08] rounded-xl px-3 py-1.5 text-xs text-slate-200"
                    />
                  </div>
                </div>

                {/* Task & Privacy Policies */}
                <div className="p-4 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] space-y-3">
                  <h3 className="text-xs font-semibold text-slate-200">Task &amp; Recurring Reminder Policies</h3>

                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Default Task Lead Reminder</label>
                    <select
                      value={taskLeadMinutes}
                      onChange={(e) => setTaskLeadMinutes(Number(e.target.value))}
                      className="w-full bg-[#07080c] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-slate-200"
                    >
                      <option value={15}>15 minutes before due</option>
                      <option value={30}>30 minutes before due</option>
                      <option value={60}>1 hour before due</option>
                      <option value={1440}>1 day before due</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Missed Recurring Reminder Handling</label>
                    <select
                      value={recurringMissedPolicy}
                      onChange={(e) => setRecurringMissedPolicy(e.target.value)}
                      className="w-full bg-[#07080c] border border-white/[0.08] rounded-xl px-3 py-2 text-xs text-slate-200"
                    >
                      <option value="trigger_once_then_advance">Trigger missed once, then advance to next schedule</option>
                      <option value="skip_missed">Skip directly to next future occurrence</option>
                    </select>
                  </div>

                  <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer pt-1">
                    <span>Auto-schedule reminder when creating a task with a deadline</span>
                    <input
                      type="checkbox"
                      checked={autoRemindNewTasks}
                      onChange={(e) => setAutoRemindNewTasks(e.target.checked)}
                      className="accent-emerald-500"
                    />
                  </label>

                  <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer pt-1">
                    <span>Auto-reschedule reminders when task due date changes</span>
                    <input
                      type="checkbox"
                      checked={autoRescheduleTaskReminders}
                      onChange={(e) => setAutoRescheduleTaskReminders(e.target.checked)}
                      className="accent-emerald-500"
                    />
                  </label>

                  <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer">
                    <span>Suppress future reminders when task is completed</span>
                    <input
                      type="checkbox"
                      checked={suppressOnTaskComplete}
                      onChange={(e) => setSuppressOnTaskComplete(e.target.checked)}
                      className="accent-emerald-500"
                    />
                  </label>

                  <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer">
                    <span>Optional overdue task alerts</span>
                    <input
                      type="checkbox"
                      checked={overdueTaskReminders}
                      onChange={(e) => setOverdueTaskReminders(e.target.checked)}
                      className="accent-emerald-500"
                    />
                  </label>

                  <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer border-t border-white/[0.06] pt-2">
                    <span>Mask sensitive task/reminder titles on lock-screen push alerts</span>
                    <input
                      type="checkbox"
                      checked={hideSensitiveLockscreen}
                      onChange={(e) => setHideSensitiveLockscreen(e.target.checked)}
                      className="accent-emerald-500"
                    />
                  </label>
                </div>
              </div>
            )}

            {/* AI MODEL TAB */}
            {activeTab === 'ai' && (
              <div className="space-y-5">
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">AI Model &amp; Communication Preferences</h2>
                  <p className="text-xs text-slate-400">Control how AUREN reasons, analyzes, and responds.</p>
                </div>

                <div className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Default AI Model</label>
                    <select
                      value={aiModel}
                      onChange={(e) => setAiModel(e.target.value)}
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-champagne-500/50 transition"
                    >
                      <option value="gemini-3.1-flash-lite">Google Gemini 3.1 Flash Lite (Academic Research &amp; Schoolwork — Recommended)</option>
                      <option value="openai/gpt-oss-120b">Groq GPT-OSS 120B (&lt;300ms Sub-Second Inference)</option>
                      <option value="gemini-2.5-flash">Google Gemini 2.5 Flash (Fast High Throughput)</option>
                      <option value="llama-3.3-70b-versatile">Groq Llama 3.3 70B (Versatile Fast Inference)</option>
                      <option value="gpt-4o-mini">OpenAI GPT-4o-mini (High Precision &amp; Generous Rate Limits)</option>
                      <option value="gpt-4o">OpenAI GPT-4o (Frontier Multimodal Reasoning)</option>
                      <option value="gemini-2.5-pro">Google Gemini 2.5 Pro (Deep Reasoning &amp; Complex Analysis)</option>
                      <option value="mock">Local Development Mock (Offline testing)</option>
                    </select>
                    {!['openai/gpt-oss-120b', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-3.1-flash-lite', 'gemini-2.5-pro', 'gemini-3.8-pro', 'gemini-3.5-flash-lite', 'gemini-3.8-flash', 'llama-3.3-70b-versatile', 'gpt-4o-mini', 'gpt-4o', 'mock'].includes(aiModel) && (
                      <p className="text-[11px] text-amber-400 mt-1">
                        Currently saved model ({aiModel}) is not supported by the operational Gemini provider. Please select a supported model above.
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Communication Style / Tone</label>
                    <select
                      value={aiTone}
                      onChange={(e) => setAiTone(e.target.value)}
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-champagne-500/50 transition"
                    >
                      <option value="concise">Concise &amp; Direct (Clear, structured, minimal fluff)</option>
                      <option value="thoughtful">Thoughtful &amp; Socratic (Probing questions, reflective)</option>
                      <option value="detailed">Exhaustive &amp; Technical (Deep breakdowns, high precision)</option>
                      <option value="executive">Executive Brief (Action items, decisions, summaries)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">
                      Custom System Instructions
                    </label>
                    <textarea
                      value={aiCustomInstructions}
                      onChange={(e) => setAiCustomInstructions(e.target.value)}
                      placeholder="Specific preferences, goals, or instructions you want AUREN to always keep in mind..."
                      rows={4}
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl p-3.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-champagne-500/50 leading-relaxed transition"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* MEMORY & PRIVACY TAB */}
            {activeTab === 'memory' && (
              <div className="space-y-5">
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">Memory &amp; Privacy Policies</h2>
                  <p className="text-xs text-slate-400">Configure what AUREN remembers and inspect security invariants.</p>
                </div>

                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">Automatic Memory Extraction</span>
                      <span className="text-[11px] text-slate-400">
                        Allow the background pipeline to extract persistent facts from conversations.
                      </span>
                    </div>
                    <input
                      type="checkbox"
                      checked={memoryAutoExtraction}
                      onChange={(e) => setMemoryAutoExtraction(e.target.checked)}
                      className="w-4 h-4 rounded text-champagne-500 focus:ring-champagne-500 bg-[#07080c] border-white/[0.1]"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                      <span>Minimum Extraction Confidence</span>
                      <span className="font-mono text-champagne-400 font-semibold">{Math.round(memoryMinConfidence * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min={0.5}
                      max={0.95}
                      step={0.05}
                      value={memoryMinConfidence}
                      onChange={(e) => setMemoryMinConfidence(parseFloat(e.target.value))}
                      className="w-full accent-champagne-500"
                    />
                    <span className="text-[10px] text-slate-500">
                      Inferences with confidence below this threshold are quarantined for explicit review.
                    </span>
                  </div>

                  <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-500/30 text-emerald-300 space-y-2">
                    <div className="flex items-center space-x-2 text-xs font-semibold">
                      <Lock className="w-4 h-4 text-emerald-400" />
                      <span>Cryptographic Isolation &amp; Integrity</span>
                    </div>
                    <p className="text-[11px] text-emerald-400/80 leading-relaxed">
                      Journal entries are cryptographically signed with RFC 8785 canonical JSON and HMAC SHA-256 for integrity verification. Reflections are strictly quarantined from ordinary LLM context injection and excluded from automated memory extraction.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* DATA MANAGEMENT TAB */}
            {activeTab === 'data' && (
              <div className="space-y-5">
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">Data Management &amp; Portability</h2>
                  <p className="text-xs text-slate-400">Download all your personal data in open, structured JSON format.</p>
                </div>

                <div className="space-y-4">
                  <div className="p-4.5 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] space-y-3">
                    <div className="flex items-center space-x-2">
                      <Download className="w-4 h-4 text-champagne-400" />
                      <span className="text-xs font-semibold text-slate-200">Complete Personal Data Export</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Exports all your tasks, projects, goals, persistent memories, and private journal entries in one JSON bundle for backup or GDPR portability.
                    </p>
                    <button
                      type="button"
                      disabled={exportDataMutation.isPending}
                      onClick={handleExportData}
                      className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] text-slate-100 text-xs font-medium transition border border-white/[0.08] disabled:opacity-50 cursor-pointer"
                    >
                      <Download className="w-4 h-4" />
                      <span>Export All Data (JSON)</span>
                    </button>
                    {exportStatus && (
                      <p className="text-xs text-champagne-300 font-mono">{exportStatus}</p>
                    )}
                  </div>

                  <div className="p-4.5 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] space-y-3">
                    <div className="flex items-center space-x-2">
                      <Cpu className="w-4 h-4 text-emerald-400" />
                      <span className="text-xs font-semibold text-slate-200">System Integrations &amp; Infrastructure</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      <div className="p-2.5 rounded-xl bg-[#07080c] border border-white/[0.06]">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">Database</span>
                        <span className="text-slate-200 font-medium">PostgreSQL &amp; Supabase RLS</span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-[#07080c] border border-white/[0.06]">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">AI Model</span>
                        <span className="text-slate-200 font-medium">{aiModel}</span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-[#07080c] border border-white/[0.06]">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">Retrieval</span>
                        <span className="text-slate-200 font-medium">Hybrid Lexical &amp; HNSW</span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-[#07080c] border border-white/[0.06]">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">Local Storage</span>
                        <span className="text-slate-200 font-medium">SQLite WAL Engine</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-[#0e1017]/40 border border-white/[0.04] space-y-1">
                    <span className="text-xs font-semibold text-slate-300">Session Security</span>
                    <p className="text-[11px] text-slate-500">
                      Authenticated via Supabase JWT with Row Level Security (RLS) enforcement at the PostgreSQL database level.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* APP & PWA INSTALLATION TAB */}
            {activeTab === 'app' && (
              <div className="space-y-5">
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">App Installation &amp; PWA Identity</h2>
                  <p className="text-xs text-slate-400">
                    Install AUREN onto your smartphone or desktop for a fast, standalone application experience.
                  </p>
                </div>

                {/* Identity & Status Overview */}
                <div className="p-5 rounded-2xl bg-gradient-to-r from-champagne-950/30 via-[#0e111a] to-[#07080c] border border-white/[0.08] flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-subtle-elevation">
                  <div className="flex items-center space-x-4">
                    <div className="w-14 h-14 rounded-2xl bg-[#08090C] border border-champagne-400/40 p-1 flex items-center justify-center flex-shrink-0 shadow-md">
                      <img
                        src="/icons/icon-192.png"
                        alt="AUREN"
                        className="w-full h-full object-contain rounded-xl"
                      />
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <h3 className="text-base font-bold text-white tracking-tight">AUREN</h3>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-champagne-950/80 text-champagne-300 border border-champagne-700/40">
                          v0.1.0-alpha
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">Your Personal AI Command Center</p>
                      <p className="text-[10px] text-champagne-400/80 mt-1 font-mono">
                        Theme: Obsidian (#0C0E14) · Background: (#08090C)
                      </p>
                    </div>
                  </div>

                  <div className="flex sm:flex-col items-center sm:items-end justify-between sm:justify-center border-t sm:border-t-0 border-white/[0.06] pt-3 sm:pt-0">
                    <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">
                      Display Mode
                    </span>
                    {isInstalled ? (
                      <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-emerald-950/80 text-emerald-400 border border-emerald-800/50 text-xs font-semibold mt-1">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Standalone Active</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-amber-950/60 text-amber-300 border border-amber-800/50 text-xs font-semibold mt-1">
                        <Smartphone className="w-3.5 h-3.5" />
                        <span>Browser Mode</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Quick 1-Click Install Button if Native Prompt is Available */}
                {!isInstalled && hasDeferredPrompt && (
                  <div className="p-4 rounded-2xl bg-champagne-950/30 border border-champagne-400/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
                    <div>
                      <span className="text-xs font-semibold text-champagne-300 block">
                        Native Browser Installation Ready
                      </span>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Add AUREN to your device home screen or application launcher with one click.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => promptInstall()}
                      className="px-4 py-2 bg-[#d7ba83] hover:bg-[#e6d4b0] text-[#07080c] font-semibold text-xs rounded-xl shadow-md transition flex items-center justify-center space-x-2 flex-shrink-0 touch-target cursor-pointer"
                    >
                      <Download className="w-4 h-4" />
                      <span>Install AUREN App</span>
                    </button>
                  </div>
                )}

                {/* Installation Guides by Platform */}
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Installation Instructions
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* Android */}
                    <div className="p-4 rounded-2xl bg-[#0c0e14] border border-white/[0.06] space-y-2">
                      <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-400">
                        <Smartphone className="w-4 h-4" />
                        <span>Android (Chrome)</span>
                      </div>
                      <ol className="text-[11px] text-slate-400 space-y-1.5 list-decimal list-inside leading-relaxed">
                        <li>Open this link in Chrome.</li>
                        <li>Tap the three dots (⋮) in the top-right.</li>
                        <li>Select <strong>Install app</strong> or <strong>Add to Home Screen</strong>.</li>
                      </ol>
                    </div>

                    {/* Apple iOS */}
                    <div className="p-4 rounded-2xl bg-[#0c0e14] border border-white/[0.06] space-y-2">
                      <div className="flex items-center space-x-2 text-xs font-semibold text-champagne-300">
                        <Smartphone className="w-4 h-4" />
                        <span>iPhone &amp; iPad (Safari)</span>
                      </div>
                      <ol className="text-[11px] text-slate-400 space-y-1.5 list-decimal list-inside leading-relaxed">
                        <li>Open this link in <strong>Safari</strong>.</li>
                        <li>Tap the <strong>Share</strong> icon in the bottom bar.</li>
                        <li>Tap <strong>Add to Home Screen</strong>, then <strong>Add</strong>.</li>
                      </ol>
                    </div>

                    {/* Desktop */}
                    <div className="p-4 rounded-2xl bg-[#0c0e14] border border-white/[0.06] space-y-2">
                      <div className="flex items-center space-x-2 text-xs font-semibold text-indigo-400">
                        <Monitor className="w-4 h-4" />
                        <span>Desktop (Chrome / Edge)</span>
                      </div>
                      <ol className="text-[11px] text-slate-400 space-y-1.5 list-decimal list-inside leading-relaxed">
                        <li>Look at the right side of the address bar.</li>
                        <li>Click the <strong>Install AUREN</strong> icon.</li>
                        <li>Confirm <strong>Install</strong> to launch standalone.</li>
                      </ol>
                    </div>
                  </div>
                </div>

                {/* Session Persistence & Offline Guarantee */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1.5">
                    <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200">
                      <ShieldCheck className="w-4 h-4 text-champagne-400" />
                      <span>Persistent Supabase Session</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Your authentication token persists in local secure storage. Closing and reopening the installed application retains your active session automatically.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1.5">
                    <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200">
                      <Layers className="w-4 h-4 text-champagne-400" />
                      <span>Zero-Leak Offline Security</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Static application assets cache for instant launch. Private journal entries, vector memories, and AI conversations are strictly protected and never cached offline.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Save Button */}
            {activeTab !== 'data' && activeTab !== 'app' && (
              <div className="pt-4 border-t border-white/[0.06] flex justify-end">
                <button
                  type="submit"
                  disabled={updateProfileMutation.isPending}
                  className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-[#d7ba83] hover:bg-[#e6d4b0] text-[#07080c] text-xs font-semibold transition shadow-sm hover:shadow-[0_0_16px_rgba(215,186,131,0.25)] disabled:opacity-50 cursor-pointer"
                >
                  <Save className="w-4 h-4" />
                  <span>Save Changes</span>
                </button>
              </div>
            )}
          </form>
        </div>
      </div>
    </div>
  );
};
