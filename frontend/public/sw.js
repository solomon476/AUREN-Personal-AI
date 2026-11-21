/**
 * AUREN Progressive Web App Service Worker.
 *
 * Implements strict, security-first static asset caching:
 * - SAFE: Caches static UI assets (HTML, CSS, JS, fonts, icons).
 * - SECURE: STRICTLY BYPASSES and NEVER CACHES:
 *   - Authenticated backend API requests (/api/v1/*)
 *   - Supabase PostgREST, Auth, and Storage (*.supabase.co/*)
 *   - Real-time Server-Sent Events (SSE) AI streaming
 *   - Private journal entries, user reflections, memory context
 * - OFFLINE RESILIENT: Delivers app shell for navigation requests when offline.
 */

const CACHE_NAME = 'auren-shell-v7';

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

  // 1. NON-GET: Always bypass service worker (POST, PUT, DELETE, PATCH)
  if (request.method !== 'GET') {
    return;
  }

  // 2. SENSITIVE DATA BYPASS: NEVER cache APIs, Supabase, or AI SSE streams
  const isApi = url.pathname.startsWith('/api/') || url.pathname.startsWith('/v1/');
  const isSupabase = url.hostname.includes('supabase.co');
  const isStream = request.headers.get('accept')?.includes('text/event-stream');

  if (isApi || isSupabase || isStream) {
    // Direct network passthrough - no caching of user data, auth, or AI tokens
    return;
  }

  // 3. NAVIGATION REQUESTS (SPA routes like /chat, /tasks, /settings, /journal)
  // Network-First: always fetch latest HTML from Vercel; fallback to offline shell if offline
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

  // 4. STATIC ASSET REQUESTS (JS, CSS, Fonts, Images, Icons)
  // Stale-While-Revalidate: serve cached version immediately, fetch and update cache in background
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

