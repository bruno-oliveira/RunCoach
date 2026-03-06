/* =============================================================================
   RunCoach — Service Worker  (update CACHE_VERSION on each deploy)
   Strategies:
     Static assets (CSS / JS / icons / fonts)  → Cache-First
     HTML pages                                 → Network-First + offline fallback
     API calls  (/api/*)                        → Network-Only  (auth-sensitive)
     Google Fonts                               → Stale-While-Revalidate
     Background Sync                            → queued run-log POSTs
   ============================================================================= */

const CACHE_VERSION  = 'v1';
const STATIC_CACHE   = `rc-static-${CACHE_VERSION}`;
const PAGES_CACHE    = `rc-pages-${CACHE_VERSION}`;
const OFFLINE_URL    = '/offline';
const SYNC_TAG       = 'sync-run-logs';
const IDB_NAME       = 'runcoach-offline';
const IDB_VERSION    = 1;
const STORE_QUEUE    = 'run-log-queue';

// App-shell assets to pre-cache on install
const PRECACHE_ASSETS = [
  '/static/css/base.css',
  '/static/css/components.css',
  '/static/css/pwa.css',
  '/static/js/modal.js',
  '/static/js/api.js',
  '/static/js/auth.js',
  '/static/js/pwa.js',
  '/static/manifest.json',
  '/static/icons/icon.svg',
  '/static/icons/icon-192.png',
];

// ---------------------------------------------------------------------------
// Install: pre-cache app shell + offline page
// ---------------------------------------------------------------------------
self.addEventListener('install', event => {
  event.waitUntil(
    (async () => {
      const staticCache = await caches.open(STATIC_CACHE);
      // addAll throws on any failure; use individual puts so one bad asset
      // doesn't abort the whole install
      await Promise.allSettled(
        PRECACHE_ASSETS.map(url =>
          fetch(url).then(r => r.ok ? staticCache.put(url, r) : null).catch(() => null)
        )
      );

      // Cache the offline fallback page
      try {
        const offlineResp = await fetch(OFFLINE_URL);
        if (offlineResp.ok) {
          const pagesCache = await caches.open(PAGES_CACHE);
          await pagesCache.put(OFFLINE_URL, offlineResp);
        }
      } catch { /* ignore */ }

      await self.skipWaiting();
    })()
  );
});

// ---------------------------------------------------------------------------
// Activate: purge old caches and claim all clients immediately
// ---------------------------------------------------------------------------
self.addEventListener('activate', event => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter(k => k !== STATIC_CACHE && k !== PAGES_CACHE)
          .map(k => caches.delete(k))
      );
      await self.clients.claim();
    })()
  );
});

// ---------------------------------------------------------------------------
// Fetch: routing
// ---------------------------------------------------------------------------
self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Cross-origin: Google Fonts → Stale-While-Revalidate, everything else skip
  if (url.origin !== self.location.origin) {
    if (url.hostname.endsWith('fonts.gstatic.com') ||
        url.hostname.endsWith('fonts.googleapis.com')) {
      event.respondWith(staleWhileRevalidate(request, STATIC_CACHE));
    }
    return;
  }

  // Skip: API (auth-sensitive), SW itself, chrome-extension
  const p = url.pathname;
  if (p.startsWith('/api/') || p === '/sw.js' || p.startsWith('/chrome-extension/')) {
    return;
  }

  // Static assets → Cache-First
  if (p.startsWith('/static/')) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // HTML pages → Network-First with offline fallback
  event.respondWith(networkFirstWithFallback(request));
});

// ---------------------------------------------------------------------------
// Strategy helpers
// ---------------------------------------------------------------------------
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirstWithFallback(request) {
  const cache = await caches.open(PAGES_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    const offline = await caches.match(OFFLINE_URL);
    return offline ?? new Response(
      '<!doctype html><title>Offline</title><h1>You are offline</h1>',
      { status: 503, headers: { 'Content-Type': 'text/html' } }
    );
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request)
    .then(r => { if (r.ok) cache.put(request, r.clone()); return r; })
    .catch(() => null);
  return cached ?? (await fetchPromise);
}

// ---------------------------------------------------------------------------
// Background Sync: replay queued run-log POSTs
// ---------------------------------------------------------------------------
self.addEventListener('sync', event => {
  if (event.tag === SYNC_TAG) {
    event.waitUntil(replayQueue());
  }
});

async function replayQueue() {
  let db;
  try {
    db = await openIDB();
  } catch {
    return;
  }

  const items = await idbGetAll(db);
  for (const item of items) {
    try {
      const response = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item.data),
        credentials: 'include',
      });
      if (response.ok) {
        await idbDelete(db, item.id);
      }
    } catch { /* will retry on next sync */ }
  }
}

// ---------------------------------------------------------------------------
// Push Notifications
// ---------------------------------------------------------------------------
self.addEventListener('push', event => {
  if (!event.data) return;
  let payload = {};
  try { payload = event.data.json(); } catch { payload = { body: event.data.text() }; }

  event.waitUntil(
    self.registration.showNotification(payload.title ?? 'RunCoach', {
      body:    payload.body    ?? 'You have a new notification',
      icon:    '/static/icons/icon-192.png',
      badge:   '/static/icons/icon-192.png',
      tag:     payload.tag    ?? 'runcoach',
      data:  { url: payload.url ?? '/' },
      vibrate: [100, 50, 100],
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification?.data?.url ?? '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(wins => {
      for (const w of wins) {
        if (w.url === url && 'focus' in w) return w.focus();
      }
      return clients.openWindow?.(url);
    })
  );
});

// ---------------------------------------------------------------------------
// Message handler (skip-waiting trigger from pwa.js)
// ---------------------------------------------------------------------------
self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// ---------------------------------------------------------------------------
// IndexedDB helpers (Promise wrappers over the callback API)
// ---------------------------------------------------------------------------
function openIDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, IDB_VERSION);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_QUEUE)) {
        db.createObjectStore(STORE_QUEUE, { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}

function idbGetAll(db) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE_QUEUE, 'readonly');
    const req = tx.objectStore(STORE_QUEUE).getAll();
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}

function idbDelete(db, id) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE_QUEUE, 'readwrite');
    const req = tx.objectStore(STORE_QUEUE).delete(id);
    req.onsuccess = () => resolve();
    req.onerror   = e => reject(e.target.error);
  });
}
