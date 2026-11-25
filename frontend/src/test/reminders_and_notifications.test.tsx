/**
 * Comprehensive Frontend Tests for AUREN Smart Reminders, Alarms, Notification Center,
 * Settings Preferences, Task-Reminder Sync, Audio Synthesis, Push Permissions, and Service Worker.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import * as remindersApi from '../api/reminders';
import * as settingsApi from '../api/settings';
import * as soundAlert from '../lib/soundAlert';
import { NotificationProvider } from '../context/NotificationContext';
import { NotificationBell } from '../components/notifications/NotificationBell';
import { AlarmNotificationOverlay } from '../components/notifications/AlarmNotificationOverlay';
import { RemindersView } from '../features/reminders/RemindersView';
import { SettingsView } from '../features/settings/SettingsView';
import { TaskModal } from '../components/productivity/TaskModal';
import { TasksView } from '../features/tasks/TasksView';
import * as productivityApi from '../api/productivity';

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<any>();
  return {
    ...actual,
    Link: ({ children, to, ...props }: any) => (
      <a href={typeof to === 'string' ? to : '#'} {...props}>
        {children}
      </a>
    ),
    useNavigate: () => vi.fn(),
  };
});

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<any>();
  const user = { id: 'user-rem-1', email: 'solomon@auren.ai', role: 'authenticated' };
  const session = { access_token: 'mock-access-token', user };
  return {
    ...actual,
    AuthContext: React.createContext({ user, session, isAuthenticated: true, isLoading: false }),
    useAuth: () => ({ user, session, isAuthenticated: true, isLoading: false }),
  };
});

vi.mock('../api/reminders', async () => {
  const actual = await vi.importActual<any>('../api/reminders');
  return {
    ...actual,
    getReminders: vi.fn(),
    createReminder: vi.fn(),
    updateReminder: vi.fn(),
    snoozeReminder: vi.fn(),
    completeReminder: vi.fn(),
    cancelReminder: vi.fn(),
    deleteReminder: vi.fn(),
    getNotifications: vi.fn(),
    markNotificationRead: vi.fn(),
    markAllNotificationsRead: vi.fn(),
    dismissNotification: vi.fn(),
    getVapidPublicKey: vi.fn(),
    getPushSubscriptions: vi.fn(),
    subscribeWebPush: vi.fn(),
    deletePushSubscription: vi.fn(),
    sendTestNotification: vi.fn(),
  };
});

vi.mock('../api/settings', async () => {
  const actual = await vi.importActual<any>('../api/settings');
  return {
    ...actual,
    getUserProfile: vi.fn(),
    updateUserProfile: vi.fn(),
  };
});

vi.mock('../api/productivity', async () => {
  const actual = await vi.importActual<any>('../api/productivity');
  return {
    ...actual,
    getTasks: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 }),
    getProjects: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 }),
  };
});

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function makeProfile(prefOverrides: Record<string, any> = {}) {
  return {
    id: 'user-rem-1',
    email: 'solomon@auren.ai',
    full_name: 'Solomon',
    avatar_url: null,
    preferences: {
      theme: 'light',
      ai_model: 'gemini-3.1-flash-lite',
      in_app_notifications_enabled: true,
      browser_push_enabled: false,
      audible_alerts_enabled: true,
      reminder_sound: 'chime',
      default_snooze_minutes: 10,
      timezone: 'Africa/Nairobi',
      quiet_hours_enabled: false,
      quiet_hours_start: '22:00',
      quiet_hours_end: '07:00',
      ...prefOverrides,
    },
    created_at: new Date().toISOString(),
  };
}

describe('Smart Reminders, Notifications & Alarms UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(settingsApi.getUserProfile).mockResolvedValue(makeProfile() as any);
    vi.mocked(remindersApi.getReminders).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
    vi.mocked(remindersApi.getNotifications).mockResolvedValue({
      items: [],
      total: 0,
      unread_count: 0,
      due_alerts: [],
    });
    vi.mocked(remindersApi.getVapidPublicKey).mockResolvedValue({
      configured: true,
      public_key: 'BPublicVapidTestKey123',
      subject: 'mailto:notifications@auren.ai',
    });
    vi.mocked(remindersApi.getPushSubscriptions).mockResolvedValue({ items: [], total: 0 });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders Reminder Center with reminder metadata, timezone, recurrence, and actions', async () => {
    const qc = createQueryClient();
    const mockRem: remindersApi.Reminder = {
      id: 'rem-100',
      user_id: 'user-rem-1',
      title: 'Review finances monthly budget',
      description: 'Check expenses and savings goals',
      reminder_type: 'alarm',
      trigger_at: '2026-12-01T09:00:00Z',
      original_trigger_at: '2026-12-01T09:00:00Z',
      timezone: 'Africa/Nairobi',
      recurrence_rule: { frequency: 'monthly', interval: 1, day_of_month: 1, time_of_day: '09:00' },
      recurrence_text: '1st of every month at 9:00 AM',
      status: 'scheduled',
      priority: 'alarm',
      is_alarm: true,
      sound_key: 'bell',
      snooze_count: 0,
      delivery_attempts: 0,
      max_delivery_attempts: 5,
      escalation_count: 0,
      source: 'chat',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    vi.mocked(remindersApi.getReminders).mockResolvedValue({
      items: [mockRem],
      total: 1,
      page: 1,
      page_size: 100,
    });
    vi.mocked(remindersApi.completeReminder).mockResolvedValue({ ...mockRem, status: 'completed' });
    vi.mocked(remindersApi.snoozeReminder).mockResolvedValue({ ...mockRem, status: 'snoozed', snooze_count: 1 });

    render(
      <QueryClientProvider client={qc}>
        <NotificationProvider>
          <RemindersView />
        </NotificationProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Review finances monthly budget')).toBeInTheDocument();
      expect(screen.getByText('Africa/Nairobi')).toBeInTheDocument();
      expect(screen.getByText('1st of every month at 9:00 AM')).toBeInTheDocument();
      expect(screen.getByText('Alarm')).toBeInTheDocument();
    });

    // Verify all tab pills never squash or overlap via touch-target min-width compression
    const dueTab = screen.getByRole('button', { name: 'Due & Snoozed' });
    expect(dueTab.className).toContain('flex-shrink-0');
    expect(dueTab.className).toContain('whitespace-nowrap');
    expect(dueTab.className).not.toContain('touch-target');

    await userEvent.click(screen.getByTitle('Mark completed'));
    expect(remindersApi.completeReminder).toHaveBeenCalledWith('rem-100');

    await userEvent.click(screen.getByTitle('Snooze 10 minutes'));
    expect(remindersApi.snoozeReminder).toHaveBeenCalledWith('rem-100', 10);
  });

  it('displays alarm dialog, respects quiet-hour audio suppression, and prevents duplicate popups', async () => {
    const qc = createQueryClient();
    const playSpy = vi.spyOn(soundAlert, 'playAlertSound').mockReturnValue(true);

    const alarmNotif: remindersApi.NotificationItem = {
      id: 'notif-alarm-1',
      user_id: 'user-rem-1',
      reminder_id: 'rem-alarm-1',
      title: 'Wake Up & Deep Work',
      body: 'Morning priority focus block',
      category: 'alarm',
      priority: 'alarm',
      is_alarm: true,
      action_url: '/reminders',
      delivery_channel: 'in_app',
      status: 'unread',
      occurrence_key: 'rem:alarm-1:1',
      metadata: { sound_key: 'bell', suppress_audio: false },
      triggered_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
    };

    vi.mocked(remindersApi.getNotifications).mockResolvedValue({
      items: [alarmNotif],
      total: 1,
      unread_count: 1,
      due_alerts: [alarmNotif],
    });
    vi.mocked(remindersApi.snoozeReminder).mockResolvedValue({} as any);
    vi.mocked(remindersApi.dismissNotification).mockResolvedValue({ ...alarmNotif, status: 'dismissed' });

    const { unmount } = render(
      <QueryClientProvider client={qc}>
        <NotificationProvider>
          <NotificationBell />
          <AlarmNotificationOverlay />
        </NotificationProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('notification-unread-badge')).toHaveTextContent('1');
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
      expect(screen.getByText('Wake Up & Deep Work')).toBeInTheDocument();
    });
    expect(playSpy).toHaveBeenCalledTimes(1);
    expect(playSpy).toHaveBeenCalledWith('bell', true);

    // Snooze 5m triggers API call and closes alarm dialog
    await userEvent.click(screen.getByRole('button', { name: '5m' }));
    await waitFor(() => {
      expect(remindersApi.snoozeReminder).toHaveBeenCalledWith('rem-alarm-1', 5);
    });
    unmount();

    // Re-mounting with same seen notification ID must NOT replay alarm or popup
    playSpy.mockClear();
    const qcDup = createQueryClient();
    const { unmount: unmountDup } = render(
      <QueryClientProvider client={qcDup}>
        <NotificationProvider>
          <AlarmNotificationOverlay />
        </NotificationProvider>
      </QueryClientProvider>
    );
    await waitFor(() => {
      expect(remindersApi.getNotifications).toHaveBeenCalled();
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(playSpy).not.toHaveBeenCalled();
    unmountDup();

    // Quiet-hour suppressed alert renders visual alert banner WITHOUT playing audio
    const quietNotif: remindersApi.NotificationItem = {
      ...alarmNotif,
      id: 'notif-quiet-2',
      is_alarm: false,
      priority: 'normal',
      title: 'Quiet Wind-Down',
      metadata: { quiet_hours_suppressed: true, suppress_audio: true, sound_key: 'silent' },
    };
    const qcQuiet = createQueryClient();
    vi.mocked(remindersApi.getNotifications).mockResolvedValue({
      items: [quietNotif],
      total: 1,
      unread_count: 1,
      due_alerts: [quietNotif],
    });

    render(
      <QueryClientProvider client={qcQuiet}>
        <NotificationProvider>
          <AlarmNotificationOverlay />
        </NotificationProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Quiet Wind-Down')).toBeInTheDocument();
    });
    expect(playSpy).not.toHaveBeenCalled();
  });

  it('respects user push-permission decline without nagging repeatedly', async () => {
    const qc = createQueryClient();
    // Simulate browser supporting Push in default permission state
    Object.defineProperty(window, 'Notification', {
      configurable: true,
      value: { permission: 'default', requestPermission: vi.fn().mockResolvedValue('denied') },
    });
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: { addEventListener: vi.fn(), removeEventListener: vi.fn() },
    });
    (window as any).PushManager = function () {};

    render(
      <QueryClientProvider client={qc}>
        <NotificationProvider>
          <NotificationBell />
        </NotificationProvider>
      </QueryClientProvider>
    );

    await userEvent.click(screen.getByRole('button', { name: 'Open Notification Center' }));
    expect(screen.getByText('Enable Background Push Alerts')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'No thanks' }));
    expect(localStorage.getItem('auren_push_permission_declined')).toBe('true');
    expect(screen.queryByText('Enable Background Push Alerts')).not.toBeInTheDocument();
  });

  it('renders Settings Notifications & Alarms tab and saves preferences', async () => {
    const qc = createQueryClient();
    vi.mocked(settingsApi.updateUserProfile).mockResolvedValue(makeProfile({ quiet_hours_enabled: true }) as any);

    render(
      <QueryClientProvider client={qc}>
        <SettingsView />
      </QueryClientProvider>
    );

    await userEvent.click(await screen.findByRole('button', { name: /Notifications & Alarms/i }));
    expect(screen.getByText(/Smart Reminders, Alarms & Push Notifications/i)).toBeInTheDocument();

    const lockCheckbox = screen.getByLabelText(/Mask sensitive task\/reminder titles on lock-screen push alerts/i);
    expect(lockCheckbox).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Save Changes/i }));
    await waitFor(() => {
      expect(settingsApi.updateUserProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          preferences: expect.objectContaining({
            in_app_notifications_enabled: true,
            timezone: 'Africa/Nairobi',
          }),
        })
      );
    });
  });

  it('keeps task deadline distinct from task reminder options inside TaskModal and TasksView', async () => {
    const qc = createQueryClient();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    const { unmount } = render(
      <QueryClientProvider client={qc}>
        <TaskModal isOpen={true} onClose={vi.fn()} onSubmit={onSubmit} />
      </QueryClientProvider>
    );

    await userEvent.type(screen.getByPlaceholderText(/What needs to be done\?/i), 'Prepare thesis draft');
    const dueInput = document.querySelector('input[type="datetime-local"]') as HTMLInputElement;
    fireEvent.change(dueInput, { target: { value: '2026-12-10T14:00' } });

    const remSelect = screen.getByLabelText('Task reminder schedule');
    await userEvent.selectOptions(remSelect, 'before_30');
    await userEvent.click(screen.getByLabelText(/Alarm-style prominent alert/i));

    await userEvent.click(screen.getByRole('button', { name: /Create Task/i }));
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Prepare thesis draft',
          reminder_mode: 'before_due',
          reminder_offset_minutes: 30,
          reminder_is_alarm: true,
        })
      );
    });
    unmount();

    // Verify quick "Set reminder" button in TasksView opens ReminderModal linked to task
    vi.mocked(productivityApi.getTasks).mockResolvedValue({
      items: [
        {
          id: 'task-42',
          user_id: 'user-rem-1',
          title: 'Review lecture notes',
          status: 'todo',
          priority: 'high',
          tags: [],
          position: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        } as any,
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    const qcTasks = createQueryClient();
    render(
      <QueryClientProvider client={qcTasks}>
        <TasksView />
      </QueryClientProvider>
    );
    const setRemBtn = await screen.findByRole('button', { name: 'Set reminder' });
    await userEvent.click(setRemBtn);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Schedule Reminder/i })).toBeInTheDocument();
      expect(screen.getByDisplayValue('Review lecture notes')).toBeInTheDocument();
    });
  });

  it('synthesizes Web Audio tones cleanly and skips when sound is silent', () => {
    const startMock = vi.fn();
    const stopMock = vi.fn();
    class MockAudioContext {
      state = 'running';
      currentTime = 0;
      destination = {};
      resume = vi.fn().mockResolvedValue(undefined);
      createOscillator() {
        return {
          type: 'sine',
          frequency: { setValueAtTime: vi.fn() },
          connect: vi.fn(),
          start: startMock,
          stop: stopMock,
        };
      }
      createGain() {
        return {
          gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
          connect: vi.fn(),
        };
      }
    }
    (window as any).AudioContext = MockAudioContext;

    expect(soundAlert.playAlertSound('silent', false)).toBe(false);
    expect(startMock).not.toHaveBeenCalled();

    expect(soundAlert.playAlertSound('chime', false)).toBe(true);
    expect(startMock).toHaveBeenCalled();
  });

  it('executes Service Worker push and notificationclick handlers properly', async () => {
    const loadNodeBuiltin = (spec: string) => import(/* @vite-ignore */ spec);
    const fs = await loadNodeBuiltin('node:fs');
    const path = await loadNodeBuiltin('node:path');
    const vm = await loadNodeBuiltin('node:vm');
    const swPath = path.resolve((globalThis as any).process.cwd(), 'public/sw.js');
    const swSource = fs.readFileSync(swPath, 'utf-8');

    const listeners: Record<string, (evt: any) => void> = {};
    const showNotification = vi.fn().mockResolvedValue(undefined);
    const focusFn = vi.fn().mockResolvedValue(undefined);
    const postMessageFn = vi.fn();
    const openWindowFn = vi.fn().mockResolvedValue(undefined);

    const sandboxSelf: any = {
      location: { origin: 'https://auren.app' },
      addEventListener: (evt: string, fn: (e: any) => void) => {
        listeners[evt] = fn;
      },
      registration: { showNotification },
      clients: {
        claim: vi.fn(),
        matchAll: vi.fn().mockResolvedValue([
          { url: 'https://auren.app/chat', focus: focusFn, postMessage: postMessageFn },
        ]),
        openWindow: openWindowFn,
      },
      skipWaiting: vi.fn(),
    };

    vm.runInNewContext(swSource, {
      self: sandboxSelf,
      caches: { open: vi.fn(), keys: vi.fn().mockResolvedValue([]), delete: vi.fn(), match: vi.fn() },
      fetch: vi.fn(),
      URL,
      URLSearchParams,
      Response,
    });

    expect(typeof listeners.push).toBe('function');
    expect(typeof listeners.notificationclick).toBe('function');

    // Simulate incoming Web Push event for an alarm
    let pushPromise: Promise<any> | undefined;
    listeners.push({
      data: {
        json: () => ({
          title: 'Alarm: Morning Routine',
          body: 'Review daily priorities',
          is_alarm: true,
          reminder_id: 'rem-sw-1',
          notification_id: 'notif-sw-1',
          url: '/reminders',
        }),
      },
      waitUntil: (p: Promise<any>) => {
        pushPromise = p;
      },
    });
    await pushPromise;

    expect(showNotification).toHaveBeenCalledWith(
      'Alarm: Morning Routine',
      expect.objectContaining({
        requireInteraction: true,
        renotify: true,
        actions: expect.arrayContaining([
          expect.objectContaining({ action: 'complete' }),
          expect.objectContaining({ action: 'snooze' }),
        ]),
      })
    );

    // Simulate clicking notification -> focuses active tab and dispatches AUREN_NOTIFICATION_CLICK
    let clickPromise: Promise<any> | undefined;
    const closeSpy = vi.fn();
    listeners.notificationclick({
      action: 'snooze',
      notification: {
        close: closeSpy,
        data: { url: '/reminders', reminder_id: 'rem-sw-1', notification_id: 'notif-sw-1' },
      },
      waitUntil: (p: Promise<any>) => {
        clickPromise = p;
      },
    });
    await clickPromise;

    expect(closeSpy).toHaveBeenCalled();
    expect(focusFn).toHaveBeenCalled();
    expect(postMessageFn).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'AUREN_NOTIFICATION_CLICK',
        action: 'snooze',
        reminder_id: 'rem-sw-1',
        notification_id: 'notif-sw-1',
      })
    );
  });
});
