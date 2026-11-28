/**
 * AUREN Progressive Web App Service Worker.
 *
 * Implements strict, security-first static asset caching AND Web Push notification handling:
 * - SAFE: Caches static UI assets (HTML, CSS, JS, fonts, icons).
 * - SECURE: STRICTLY BYPASSES and NEVER CACHES:
 *   - Authenticated backend API requests (/api/v1/*)
 *   - Supabase PostgREST, Auth, and Storage (*.supabase.co/*)
 *   - Real-time Server-Sent Events (SSE) AI streaming
 *   - Private journal entries, user reflections, memory context
 * - WEB PUSH: Renders background reminder/alarm notifications cleanly with privacy awareness,
 *   vibration, actions (Complete / Snooze), and click navigation into AUREN.
 */

const CACHE_NAME = 'auren-shell-v15';

const STATIC_PRECACHE = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/favicon.svg',
  '/favicon-32x32.png',
  '/favicon-16x16.png',
  '/favicon.ico',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-maskable-512.png',
  '/icons/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_PRECACHE))
      .then(() => self.skipWaiting())
      .catch((err) => {
        console.warn('[AUREN SW] Pre-cache warning:', err);
      })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((cacheNames) =>
        Promise.all(
          cacheNames.map((name) => {
            if (name !== CACHE_NAME) {
              return caches.delete(name);
            }
          })
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 1. NON-GET: Always bypass service worker
  if (request.method !== 'GET') {
    return;
  }

  // 2. SENSITIVE DATA BYPASS: NEVER cache APIs, Supabase, or AI SSE streams
  const isApi = url.pathname.startsWith('/api/') || url.pathname.startsWith('/v1/');
  const isSupabase = url.hostname.includes('supabase.co');
  const isStream = request.headers.get('accept')?.includes('text/event-stream');

  if (isApi || isSupabase || isStream) {
    return;
  }

  // 3. NAVIGATION REQUESTS
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put('/index.html', clone));
          }
          return networkResponse;
        })
        .catch(async () => {
          const cache = await caches.open(CACHE_NAME);
          const cachedShell = await cache.match('/index.html');
          return (
            cachedShell ||
            new Response(
              '<!DOCTYPE html><html><head><meta charset="utf-8"><title>AUREN — Offline</title><style>body{background:#08090C;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;}h1{color:#d7ba83;font-size:1.5rem;}p{color:#94a3b8;font-size:0.9rem;}</style></head><body><div><h1>AUREN</h1><p>You are currently offline. Please reconnect to access AI dialogues and synchronized data.</p></div></body></html>',
              { headers: { 'Content-Type': 'text/html' } }
            )
          );
        })
    );
    return;
  }

  // 4. STATIC ASSET REQUESTS
  if (
    url.pathname.match(/\.(js|css|woff2?|ttf|png|svg|ico|webmanifest)$/) ||
    url.pathname.startsWith('/assets/') ||
    url.pathname.startsWith('/icons/')
  ) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        const networkFetch = fetch(request)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              const responseToCache = networkResponse.clone();
              caches.open(CACHE_NAME).then((cache) => {
                cache.put(request, responseToCache);
              });
            }
            return networkResponse;
          })
          .catch(() => cachedResponse);

        return cachedResponse || networkFetch;
      })
    );
  }
});

// ---------------------------------------------------------------------------
// Web Push Notification Delivery & Interactive Click Handling
// ---------------------------------------------------------------------------
self.addEventListener('push', (event) => {
  let payload = {
    title: 'AUREN Reminder',
    body: 'You have a scheduled item due.',
    tag: '',
    is_alarm: false,
    url: '/reminders',
    reminder_id: null,
    notification_id: null,
    task_id: null,
  };

  if (event.data) {
    try {
      const parsed = event.data.json();
      payload = { ...payload, ...parsed };
    } catch {
      try {
        payload.body = event.data.text();
      } catch {
        // Keep safe defaults
      }
    }
  }

  const options = {
    body: payload.body,
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    tag: payload.tag || (payload.reminder_id ? `auren-rem-${payload.reminder_id}` : 'auren-reminder'),
    renotify: Boolean(payload.is_alarm),
    requireInteraction: Boolean(payload.is_alarm),
    vibrate: payload.is_alarm ? [300, 120, 300, 120, 300] : [150, 75, 150],
    data: {
      url: payload.url || '/reminders',
      reminder_id: payload.reminder_id,
      notification_id: payload.notification_id,
      task_id: payload.task_id,
      is_alarm: Boolean(payload.is_alarm),
    },
    actions: [
      { action: 'complete', title: 'Complete' },
      { action: 'snooze', title: 'Snooze' },
    ],
  };

  const notifTitle = payload.title || 'AUREN Reminder';
  event.waitUntil(
    self.registration.showNotification(notifTitle, options).catch(() =>
      self.registration.showNotification(notifTitle, {
        body: payload.body || 'You have a due reminder.',
        icon: '/icons/icon-192.png',
        badge: '/icons/icon-192.png',
        tag: options.tag,
        data: options.data,
      })
    )
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const notifData = event.notification.data || {};
  const action = event.action || 'open';
  const basePath = notifData.url || '/reminders';

  const params = new URLSearchParams();
  if (notifData.reminder_id) params.set('reminder_id', notifData.reminder_id);
  if (notifData.notification_id) params.set('notification_id', notifData.notification_id);
  if (action && action !== 'open') params.set('notif_action', action);

  const query = params.toString();
  const targetUrl = query ? `${basePath}?${query}` : basePath;

  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then(async (windowClients) => {
        for (const client of windowClients) {
          if (client.url && client.url.startsWith(self.location.origin)) {
            if ('focus' in client) {
              await client.focus();
            }
            client.postMessage({
              type: 'AUREN_NOTIFICATION_CLICK',
              action,
              url: targetUrl,
              reminder_id: notifData.reminder_id || null,
              notification_id: notifData.notification_id || null,
              task_id: notifData.task_id || null,
            });
            return;
          }
        }
        if (self.clients.openWindow) {
          return self.clients.openWindow(targetUrl);
        }
      })
  );
});
