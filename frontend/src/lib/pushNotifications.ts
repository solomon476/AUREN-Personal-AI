/**
 * Browser Web Push & Permission Management Helper.
 * Handles explicit permission requests (never nagging after decline),
 * VAPID applicationServerKey conversion, PushManager registration,
 * and unregistration.
 */

import {
  deletePushSubscription,
  getPushSubscriptions,
  getVapidPublicKey,
  subscribeWebPush,
  PushSubscriptionView,
} from '../api/reminders';
import { updateUserProfile } from '../api/settings';

const PUSH_DECLINED_KEY = 'auren_push_permission_declined';

export function isWebPushSupported(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    'Notification' in window &&
    'serviceWorker' in navigator &&
    'PushManager' in window
  );
}

export function getBrowserNotificationPermission(): NotificationPermission | 'unsupported' {
  if (typeof window === 'undefined' || !('Notification' in window)) {
    return 'unsupported';
  }
  return Notification.permission;
}

export function hasUserDeclinedPush(): boolean {
  if (getBrowserNotificationPermission() === 'denied') return true;
  try {
    return localStorage.getItem(PUSH_DECLINED_KEY) === 'true';
  } catch {
    return false;
  }
}

export function markUserDeclinedPush(): void {
  try {
    localStorage.setItem(PUSH_DECLINED_KEY, 'true');
  } catch {
    // Ignore storage failure
  }
}

export function clearUserDeclinedPush(): void {
  try {
    localStorage.removeItem(PUSH_DECLINED_KEY);
  } catch {
    // Ignore
  }
}

export function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

function arrayBufferToBase64Url(buffer: ArrayBuffer | null): string {
  if (!buffer) return '';
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export interface PushEnableResult {
  success: boolean;
  permission: NotificationPermission | 'unsupported';
  subscription?: PushSubscriptionView;
  error?: string;
}

async function getReadyServiceWorkerRegistration(): Promise<ServiceWorkerRegistration> {
  let reg = await navigator.serviceWorker.getRegistration();
  if (!reg) {
    reg = await navigator.serviceWorker.register('/sw.js');
  }
  const timeoutPromise = new Promise<never>((_, reject) =>
    window.setTimeout(
      () => reject(new Error('Service worker activation timed out. Please reload the app and try again.')),
      10000
    )
  );
  return Promise.race([navigator.serviceWorker.ready, timeoutPromise]);
}

function keysMatch(a: ArrayBuffer | null | undefined, expected: Uint8Array): boolean {
  if (!a) return false;
  const view = new Uint8Array(a);
  if (view.byteLength !== expected.byteLength) return false;
  for (let i = 0; i < view.byteLength; i++) {
    if (view[i] !== expected[i]) return false;
  }
  return true;
}

/**
 * Must ONLY be invoked inside a direct user interaction (button click)
 * to satisfy browser notification permission policies.
 */
export async function enableDeviceWebPush(deviceLabel?: string): Promise<PushEnableResult> {
  if (!isWebPushSupported()) {
    return {
      success: false,
      permission: 'unsupported',
      error: 'Web Push notifications are not supported by this browser or context (requires HTTPS).',
    };
  }

  let permission = Notification.permission;
  if (permission === 'default') {
    permission = await Notification.requestPermission();
  }

  if (permission !== 'granted') {
    markUserDeclinedPush();
    return {
      success: false,
      permission,
      error:
        permission === 'denied'
          ? 'Notifications were blocked by the browser. Please allow them in site settings if you change your mind.'
          : 'Notification permission was dismissed.',
    };
  }

  clearUserDeclinedPush();

  // Fetch public VAPID key from backend (never exposes private key)
  const vapidInfo = await getVapidPublicKey();
  if (!vapidInfo.configured || !vapidInfo.public_key) {
    return {
      success: false,
      permission,
      error: 'Push server VAPID keys are not configured yet on the backend.',
    };
  }

  const appServerKey = urlBase64ToUint8Array(vapidInfo.public_key);
  const registration = await getReadyServiceWorkerRegistration();
  let existingSub = await registration.pushManager.getSubscription();
  if (existingSub && !keysMatch(existingSub.options?.applicationServerKey, appServerKey)) {
    // Re-subscribe cleanly if browser holds a subscription signed with an outdated VAPID key
    await existingSub.unsubscribe().catch(() => {});
    existingSub = null;
  }

  if (!existingSub) {
    existingSub = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: appServerKey as unknown as BufferSource,
    });
  }

  const p256dh = arrayBufferToBase64Url(existingSub.getKey('p256dh'));
  const auth = arrayBufferToBase64Url(existingSub.getKey('auth'));
  if (!p256dh || !auth) {
    return {
      success: false,
      permission,
      error: 'Browser failed to provide Web Push encryption keys.',
    };
  }

  const saved = await subscribeWebPush({
    endpoint: existingSub.endpoint,
    keys: { p256dh, auth },
    user_agent: navigator.userAgent,
    device_label: deviceLabel || inferDeviceLabel(),
  });

  // Ensure server-side preference stays aligned whenever a device explicitly enables Web Push.
  await updateUserProfile({ preferences: { browser_push_enabled: true } }).catch(() => {});

  return {
    success: true,
    permission,
    subscription: saved,
  };
}

/**
 * Silently ensures an already-granted browser PushManager subscription matches the server's
 * current VAPID key and exists as an active row on the backend, without prompting the user.
 */
export async function syncExistingDevicePushSubscription(
  knownActiveEndpoints?: string[]
): Promise<{ synced: boolean; reason: string; subscription?: PushSubscriptionView }> {
  if (!isWebPushSupported() || Notification.permission !== 'granted') {
    return { synced: false, reason: 'permission_not_granted' };
  }

  const vapidInfo = await getVapidPublicKey();
  if (!vapidInfo.configured || !vapidInfo.public_key) {
    return { synced: false, reason: 'vapid_unconfigured' };
  }

  const appServerKey = urlBase64ToUint8Array(vapidInfo.public_key);
  const registration = await getReadyServiceWorkerRegistration();
  let existingSub = await registration.pushManager.getSubscription();
  const keyMismatch = Boolean(existingSub && !keysMatch(existingSub.options?.applicationServerKey, appServerKey));

  if (keyMismatch && existingSub) {
    await existingSub.unsubscribe().catch(() => {});
    existingSub = null;
  }

  let createdFreshSub = false;
  if (!existingSub) {
    existingSub = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: appServerKey as unknown as BufferSource,
    });
    createdFreshSub = true;
  }

  let activeEndpoints = knownActiveEndpoints;
  if (!activeEndpoints) {
    try {
      const subsResp = await getPushSubscriptions();
      activeEndpoints = (subsResp?.items ?? []).filter((s) => s.is_active).map((s) => s.endpoint);
    } catch {
      activeEndpoints = [];
    }
  }

  const missingOnBackend = !activeEndpoints.includes(existingSub.endpoint);
  if (!createdFreshSub && !keyMismatch && !missingOnBackend) {
    return { synced: false, reason: 'already_in_sync' };
  }

  const p256dh = arrayBufferToBase64Url(existingSub.getKey('p256dh'));
  const auth = arrayBufferToBase64Url(existingSub.getKey('auth'));
  if (!p256dh || !auth) {
    return { synced: false, reason: 'missing_keys' };
  }

  const saved = await subscribeWebPush({
    endpoint: existingSub.endpoint,
    keys: { p256dh, auth },
    user_agent: navigator.userAgent,
    device_label: inferDeviceLabel(),
  });

  return {
    synced: true,
    reason: keyMismatch || createdFreshSub ? 'resubscribed' : 'repaired_backend_row',
    subscription: saved,
  };
}

export async function disableDeviceWebPush(subscriptionId?: string): Promise<void> {
  if (typeof window !== 'undefined' && 'serviceWorker' in navigator) {
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await sub.unsubscribe();
      }
    } catch {
      // Ignore SW unsubscribe failures
    }
  }
  if (subscriptionId) {
    await deletePushSubscription(subscriptionId);
  }
}

function inferDeviceLabel(): string {
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
  if (/iphone|ipad|ipod/i.test(ua)) return 'iOS Device';
  if (/android/i.test(ua)) return 'Android Device';
  if (/linux/i.test(ua)) return 'Linux Browser';
  if (/macintosh|mac os/i.test(ua)) return 'Mac Browser';
  if (/windows/i.test(ua)) return 'Windows Browser';
  return 'AUREN Device';
}

