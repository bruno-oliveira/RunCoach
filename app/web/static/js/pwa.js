/**
 * pwa.js — service-worker registration, push subscription, offline hint.
 *
 * Loaded on every page. Registers /sw.js (the offline plan + push display),
 * and exposes window.RunCoachPWA for the settings panel:
 *
 *   RunCoachPWA.pushState()      -> Promise<{supported, configured, subscribed,
 *                                   permission, needsInstall, prefs, categories}>
 *   RunCoachPWA.enablePush()     -> Promise<state>   (asks permission)
 *   RunCoachPWA.disablePush()    -> Promise<state>
 *   RunCoachPWA.savePrefs(obj)   -> Promise<state>
 *   RunCoachPWA.sendTest()       -> Promise<{delivered}>
 *   RunCoachPWA.onSignOut()      -> Promise   (unsubscribe + drop cached pages)
 *   RunCoachPWA.onSignIn()       -> Promise   (drop pages saved signed-out)
 *   RunCoachPWA.isStandalone()   -> boolean   (running as an installed app)
 *
 * It also keeps an installed app honest about freshness. A home-screen app has
 * no reload button and iOS resumes it frozen exactly as it was left, so a page
 * the service worker served from its cache, or one that sat in the background
 * for hours, is reloaded as soon as the server answers — see `keepFresh`.
 *
 * iOS only delivers web push to an app added to the Home Screen, so on iOS
 * Safari outside standalone mode `needsInstall` is true and the panel shows
 * how to install instead of a switch that can't work.
 */
(function () {
  'use strict';

  // Shared with sw.js: the stamp it puts on a page served from its cache,
  // and the prefix of the caches it saves pages in (whatever their version).
  var SNAPSHOT_ATTR = 'data-rc-snapshot';
  var PAGE_CACHE_PREFIX = 'rc-pages-';
  // An installed app left in the background this long is reloaded on return.
  var STALE_AFTER_MS = 10 * 60 * 1000;
  var RETRY_MIN_MS = 5000;
  var RETRY_MAX_MS = 60000;

  var swSupported = 'serviceWorker' in navigator;
  var pushSupported = swSupported && 'PushManager' in window && 'Notification' in window;

  var registration = swSupported
    ? navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () { return null; })
    : Promise.resolve(null);

  function isStandalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
      window.navigator.standalone === true;
  }

  function isIOS() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  function headers() {
    var h = { 'Content-Type': 'application/json' };
    try {
      var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (tz) h['X-Timezone'] = tz;
    } catch (e) { /* server falls back to UTC */ }
    return h;
  }

  function api(method, path, body) {
    return fetch(path, {
      method: method,
      credentials: 'same-origin',
      headers: headers(),
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (res) {
      if (!res.ok) throw new Error('http_' + res.status);
      return res.json();
    });
  }

  function keyToBytes(base64url) {
    var padding = '='.repeat((4 - (base64url.length % 4)) % 4);
    var raw = atob((base64url + padding).replace(/-/g, '+').replace(/_/g, '/'));
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  function currentSubscription() {
    return registration.then(function (reg) {
      if (!reg || !pushSupported) return null;
      return reg.pushManager.getSubscription();
    });
  }

  function pushState() {
    return Promise.all([api('GET', '/api/push/config'), currentSubscription()])
      .then(function (results) {
        var config = results[0] || {};
        var sub = results[1];
        return {
          supported: pushSupported,
          configured: !!config.configured,
          subscribed: !!sub,
          permission: pushSupported ? Notification.permission : 'unsupported',
          needsInstall: isIOS() && !isStandalone(),
          devices: config.devices || 0,
          prefs: config.prefs || {},
          categories: config.categories || [],
        };
      });
  }

  function enablePush() {
    if (!pushSupported) return Promise.reject(new Error('unsupported'));
    return api('GET', '/api/push/config').then(function (config) {
      if (!config.configured || !config.public_key) throw new Error('not_configured');
      return Notification.requestPermission().then(function (permission) {
        if (permission !== 'granted') throw new Error('denied');
        return registration.then(function (reg) {
          if (!reg) throw new Error('no_worker');
          return reg.pushManager.getSubscription().then(function (existing) {
            return existing || reg.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: keyToBytes(config.public_key),
            });
          });
        });
      });
    }).then(function (sub) {
      var json = sub.toJSON();
      return api('POST', '/api/push/subscribe', { endpoint: json.endpoint, keys: json.keys });
    }).then(pushState);
  }

  function disablePush() {
    return currentSubscription().then(function (sub) {
      if (!sub) return null;
      var endpoint = sub.endpoint;
      return api('POST', '/api/push/unsubscribe', { endpoint: endpoint })
        .catch(function () { return null; })
        .then(function () { return sub.unsubscribe(); });
    }).then(pushState);
  }

  function savePrefs(prefs) {
    return api('PATCH', '/api/push/prefs', prefs).then(pushState);
  }

  function sendTest() {
    return api('POST', '/api/push/test');
  }

  // Deleted from the page rather than by messaging the worker, so the caller
  // can wait for it: sign-in and sign-out navigate straight afterwards, and a
  // page saved for the previous session must be gone before that load is.
  function dropCachedPages() {
    if (!window.caches) return Promise.resolve();
    return caches.keys().then(function (names) {
      return Promise.all(names.filter(function (name) {
        return name.indexOf(PAGE_CACHE_PREFIX) === 0;
      }).map(function (name) { return caches.delete(name); }));
    }).catch(function () { return null; });
  }

  function onSignIn() {
    return dropCachedPages();
  }

  function onSignOut() {
    var drop = dropCachedPages();
    // The next person on this device must not get the previous runner's
    // "your plan adjusted" on their lock screen.
    var unsubscribe = currentSubscription().then(function (sub) {
      if (!sub) return null;
      return api('POST', '/api/push/unsubscribe', { endpoint: sub.endpoint })
        .catch(function () { return null; })
        .then(function () { return sub.unsubscribe(); });
    }).catch(function () { return null; });
    return Promise.all([drop, unsubscribe]);
  }

  // A cached plan page is useful offline, but it must say it's a snapshot.
  function showOffline(offline) {
    document.documentElement.classList.toggle('is-offline', offline);
    var banner = document.getElementById('offlineBanner');
    if (banner) banner.hidden = !offline;
  }

  // The service worker stamps <html> when it had to serve its saved copy.
  function isSnapshot() {
    return document.documentElement.hasAttribute(SNAPSHOT_ATTR);
  }

  // Asks the server rather than trusting navigator.onLine, which an installed
  // iOS app reports as offline for a while after it is brought back.
  function serverReachable() {
    return fetch('/health/live', { cache: 'no-store' })
      .then(function (res) { return res.ok; })
      .catch(function () { return false; });
  }

  // Reloading under a runner's fingers would throw away what they are typing.
  function isEditing() {
    var el = document.activeElement;
    return !!el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName);
  }

  // One reload per page load: a reload that lands on the cache again starts a
  // new page, which probes again — never a tight loop inside this one.
  var reloading = false;
  function reloadFresh() {
    if (reloading) return;
    if (isEditing()) {
      retryLater();
      return;
    }
    reloading = true;
    // An app back from hours in the background has an expired access token
    // too; renewed first, the reload renders signed in rather than signed out.
    var renewed = window.RunCoachAuth
      ? window.RunCoachAuth.renewIfDue().catch(function () { return null; })
      : Promise.resolve();
    renewed.then(function () { window.location.reload(); });
  }

  // Backs off, so an afternoon with no signal is not a request every few
  // seconds; coming back online starts the count again.
  var retryTimer = null;
  var retryDelay = RETRY_MIN_MS;
  function retryLater() {
    if (retryTimer) return;
    retryTimer = setTimeout(function () {
      retryTimer = null;
      keepFresh();
    }, retryDelay);
    retryDelay = Math.min(retryDelay * 2, RETRY_MAX_MS);
  }

  function onConnectivityChange() {
    retryDelay = RETRY_MIN_MS;
    keepFresh();
  }

  /**
   * Settle what the page should say about itself, and replace it if it is old.
   *
   *  - live page, browser online: nothing to do.
   *  - saved copy on screen, or the browser claims to be offline: ask the
   *    server. Unreachable -> say so and ask again shortly. Reachable -> a
   *    saved copy is replaced by the real page; a live one just loses the
   *    banner, because the browser was wrong.
   */
  function keepFresh() {
    if (!isSnapshot() && navigator.onLine !== false) {
      showOffline(false);
      return;
    }
    showOffline(true);
    serverReachable().then(function (reachable) {
      if (!reachable) {
        retryLater();
      } else if (isSnapshot()) {
        reloadFresh();
      } else {
        showOffline(false);
      }
    });
  }

  // iOS freezes an installed app in the background and resumes it as it was,
  // so "today" could be yesterday's page. A browser tab is left alone: it has
  // a reload button, and its owner did not ask for one to be pressed.
  var hiddenAt = null;
  function onVisibilityChange() {
    if (document.visibilityState === 'hidden') {
      hiddenAt = Date.now();
      return;
    }
    var away = hiddenAt === null ? 0 : Date.now() - hiddenAt;
    hiddenAt = null;
    if (!isStandalone() || away < STALE_AFTER_MS) {
      keepFresh();
      return;
    }
    serverReachable().then(function (reachable) {
      if (reachable) reloadFresh();
      else keepFresh();
    });
  }

  window.addEventListener('online', onConnectivityChange);
  window.addEventListener('offline', onConnectivityChange);
  document.addEventListener('visibilitychange', onVisibilityChange);
  document.addEventListener('DOMContentLoaded', keepFresh);

  window.RunCoachPWA = {
    pushSupported: pushSupported,
    pushState: pushState,
    enablePush: enablePush,
    disablePush: disablePush,
    savePrefs: savePrefs,
    sendTest: sendTest,
    onSignOut: onSignOut,
    onSignIn: onSignIn,
    isStandalone: isStandalone,
  };
})();
