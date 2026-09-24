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
 *
 * iOS only delivers web push to an app added to the Home Screen, so on iOS
 * Safari outside standalone mode `needsInstall` is true and the panel shows
 * how to install instead of a switch that can't work.
 */
(function () {
  'use strict';

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

  function onSignOut() {
    var drop = navigator.serviceWorker && navigator.serviceWorker.controller
      ? Promise.resolve(navigator.serviceWorker.controller.postMessage('clear-pages'))
      : Promise.resolve();
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
  function reflectConnectivity() {
    var offline = navigator.onLine === false;
    document.documentElement.classList.toggle('is-offline', offline);
    var banner = document.getElementById('offlineBanner');
    if (banner) banner.hidden = !offline;
  }
  window.addEventListener('online', reflectConnectivity);
  window.addEventListener('offline', reflectConnectivity);
  document.addEventListener('DOMContentLoaded', reflectConnectivity);

  window.RunCoachPWA = {
    pushSupported: pushSupported,
    pushState: pushState,
    enablePush: enablePush,
    disablePush: disablePush,
    savePrefs: savePrefs,
    sendTest: sendTest,
    onSignOut: onSignOut,
  };
})();
