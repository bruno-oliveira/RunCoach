/*
 * RunCoach service worker — push notifications and the offline plan.
 *
 * Served from /sw.js (not /static/) because a worker only controls pages at or
 * below its own path, and it has to control the whole site.
 *
 * Two jobs:
 *
 * 1. Push. Show what the server sent and, on tap, bring the runner to the page
 *    it points at (focusing an open tab rather than stacking new ones).
 *
 * 2. Offline. Runners open the plan at a trailhead with one bar of signal.
 *    Page navigations are network-first — the plan adapts, so a cached copy is
 *    only ever a fallback — and a successful load is kept so the last-seen
 *    plan still opens with no signal at all. Static assets are
 *    stale-while-revalidate. The JSON API is never cached: a stale "today"
 *    answer is worse than an honest failure.
 *
 * Signing out posts "clear-pages" so the next person on a shared device can't
 * open the previous runner's plan from cache.
 */
'use strict';

var PAGE_CACHE = 'rc-pages-v1';
var ASSET_CACHE = 'rc-assets-v1';
var KEEP = [PAGE_CACHE, ASSET_CACHE];
var MAX_PAGES = 25;
var NO_CACHE_PREFIXES = ['/api/', '/admin', '/unsubscribe', '/sw.js'];

var OFFLINE_HTML =
  '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width,initial-scale=1">' +
  '<title>Offline · RunCoach</title><style>' +
  'body{font-family:system-ui,-apple-system,sans-serif;background:#FBFBFA;color:#1a1a1a;' +
  'display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:24px}' +
  'main{max-width:340px;text-align:center}h1{font-size:1.25rem;margin:0 0 8px}' +
  'p{color:#555;line-height:1.5}a{color:#0E7C5A;font-weight:600}' +
  '@media (prefers-color-scheme:dark){body{background:#111;color:#eee}p{color:#aaa}}' +
  '</style></head><body><main><h1>You’re offline</h1>' +
  '<p>This page hasn’t been saved on this device yet. Your plan opens offline ' +
  'once you’ve viewed it with a connection.</p>' +
  '<p><a href="/">Try again</a></p></main></body></html>';

self.addEventListener('install', function () {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(
        names.filter(function (n) { return KEEP.indexOf(n) === -1; })
          .map(function (n) { return caches.delete(n); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

function cacheablePath(path) {
  for (var i = 0; i < NO_CACHE_PREFIXES.length; i++) {
    if (path.indexOf(NO_CACHE_PREFIXES[i]) === 0) return false;
  }
  return true;
}

function trimPages(cache) {
  return cache.keys().then(function (keys) {
    if (keys.length <= MAX_PAGES) return;
    return cache.delete(keys[0]).then(function () { return trimPages(cache); });
  });
}

function networkFirstPage(request) {
  return fetch(request).then(function (response) {
    var type = response.headers.get('content-type') || '';
    if (response.ok && type.indexOf('text/html') !== -1) {
      var copy = response.clone();
      caches.open(PAGE_CACHE).then(function (cache) {
        return cache.put(request, copy).then(function () { return trimPages(cache); });
      });
    }
    return response;
  }).catch(function () {
    return caches.open(PAGE_CACHE).then(function (cache) {
      return cache.match(request, { ignoreSearch: true }).then(function (hit) {
        if (hit) return hit;
        // /today is a server redirect to the plan in progress, which can't be
        // resolved offline — so open the plan page seen most recently instead.
        if (new URL(request.url).pathname === '/today') {
          return cache.keys().then(function (keys) {
            for (var i = keys.length - 1; i >= 0; i--) {
              if (new URL(keys[i].url).pathname.indexOf('/plan/') === 0) {
                return cache.match(keys[i]);
              }
            }
            return null;
          });
        }
        return null;
      }).then(function (hit) {
        return hit || new Response(OFFLINE_HTML, {
          status: 503,
          headers: { 'Content-Type': 'text/html; charset=utf-8' },
        });
      });
    });
  });
}

function staleWhileRevalidate(request) {
  return caches.open(ASSET_CACHE).then(function (cache) {
    return cache.match(request).then(function (hit) {
      var refresh = fetch(request).then(function (response) {
        if (response.ok) cache.put(request, response.clone());
        return response;
      }).catch(function () { return hit; });
      return hit || refresh;
    });
  });
}

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;
  var url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (!cacheablePath(url.pathname)) return;

  if (request.mode === 'navigate') {
    event.respondWith(networkFirstPage(request));
  } else if (url.pathname.indexOf('/static/') === 0) {
    event.respondWith(staleWhileRevalidate(request));
  }
});

self.addEventListener('message', function (event) {
  if (event.data === 'clear-pages') {
    event.waitUntil(caches.delete(PAGE_CACHE));
  }
});

self.addEventListener('push', function (event) {
  var data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'RunCoach', body: event.data ? event.data.text() : '' };
  }
  var title = data.title || 'RunCoach';
  var options = {
    body: data.body || '',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    data: { url: data.url || '/' },
  };
  if (data.tag) {
    options.tag = data.tag;
    // Same tag replaces the old note — still worth a buzz, it's news.
    options.renotify = true;
  }
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var raw = (event.notification.data && event.notification.data.url) || '/';
  // Only ever navigate within this site, whatever a payload says.
  var target = new URL(raw, self.location.origin);
  if (target.origin !== self.location.origin) target = new URL('/', self.location.origin);

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        var client = list[i];
        if (new URL(client.url).pathname === target.pathname && 'focus' in client) {
          if ('navigate' in client && client.url !== target.href) {
            // navigate() rejects for a tab this worker doesn't control yet.
            return client.navigate(target.href)
              .then(function (c) { return c && c.focus(); })
              .catch(function () { return self.clients.openWindow(target.href); });
          }
          return client.focus();
        }
      }
      return self.clients.openWindow(target.href);
    })
  );
});
