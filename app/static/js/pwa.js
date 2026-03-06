/* =============================================================================
   RunCoach PWA
   - Service Worker registration + update detection
   - Install prompt (beforeinstallprompt / iOS fallback)
   - Online / offline indicator
   - Background-sync queue for run logs (with SyncManager + online-event fallback)
   - Push notification permission helper
   ============================================================================= */

(function () {
  'use strict';

  const IDB_NAME    = 'runcoach-offline';
  const IDB_VERSION = 1;
  const STORE_QUEUE = 'run-log-queue';
  const SYNC_TAG    = 'sync-run-logs';

  // ---------------------------------------------------------------------------
  // Service Worker registration
  // ---------------------------------------------------------------------------
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' })
        .then(reg => {
          console.debug('[PWA] SW registered, scope:', reg.scope);

          // Periodically check for updates (every 60 min)
          setInterval(() => reg.update(), 60 * 60 * 1000);

          // A new SW found during this session
          reg.addEventListener('updatefound', () => {
            const incoming = reg.installing;
            incoming.addEventListener('statechange', () => {
              if (incoming.state === 'installed' && navigator.serviceWorker.controller) {
                showUpdateBanner(incoming);
              }
            });
          });
        })
        .catch(err => console.warn('[PWA] SW registration failed:', err));
    });

    // When a new SW takes control, reload to pick up fresh assets
    let _refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (_refreshing) return;
      _refreshing = true;
      window.location.reload();
    });
  }

  // ---------------------------------------------------------------------------
  // Update banner
  // ---------------------------------------------------------------------------
  function showUpdateBanner(newWorker) {
    const banner = document.getElementById('pwa-update-banner');
    if (!banner) return;
    banner.classList.add('is-visible');

    banner.querySelector('[data-pwa="refresh"]')?.addEventListener('click', () => {
      newWorker.postMessage({ type: 'SKIP_WAITING' });
    });
    banner.querySelector('[data-pwa="dismiss-update"]')?.addEventListener('click', () => {
      banner.classList.remove('is-visible');
    });
  }

  // ---------------------------------------------------------------------------
  // Install prompt (Android / Chrome)
  // ---------------------------------------------------------------------------
  let _deferredPrompt = null;

  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault();
    _deferredPrompt = e;

    // Don't show if user dismissed in the last 30 days
    const ts = localStorage.getItem('pwa-install-dismissed');
    if (ts && Date.now() - parseInt(ts, 10) < 30 * 24 * 60 * 60 * 1000) return;

    // Track visits; show prompt from the 2nd visit onward
    const visits = parseInt(localStorage.getItem('pwa-visit-count') || '1', 10);
    if (visits >= 2) {
      setTimeout(showInstallBanner, 3000);
    }
  });

  window.addEventListener('appinstalled', () => {
    _deferredPrompt = null;
    document.getElementById('pwa-install-banner')?.classList.remove('is-visible');
    console.debug('[PWA] App installed');
  });

  function showInstallBanner() {
    document.getElementById('pwa-install-banner')?.classList.add('is-visible');
  }

  /** Called by the Install button in the banner */
  window.pwaInstall = async function () {
    if (!_deferredPrompt) return;
    document.getElementById('pwa-install-banner')?.classList.remove('is-visible');
    _deferredPrompt.prompt();
    const { outcome } = await _deferredPrompt.userChoice;
    console.debug('[PWA] Install outcome:', outcome);
    _deferredPrompt = null;
    if (outcome === 'dismissed') {
      localStorage.setItem('pwa-install-dismissed', String(Date.now()));
    }
  };

  /** Called by the X button in the banner */
  window.pwaInstallDismiss = function () {
    document.getElementById('pwa-install-banner')?.classList.remove('is-visible');
    localStorage.setItem('pwa-install-dismissed', String(Date.now()));
    _deferredPrompt = null;
  };

  // ---------------------------------------------------------------------------
  // iOS "Add to Home Screen" hint
  // Safari never fires beforeinstallprompt; detect and show hint instead.
  // ---------------------------------------------------------------------------
  function isIosSafari() {
    const ua = navigator.userAgent;
    return /iphone|ipad|ipod/i.test(ua) && /safari/i.test(ua) && !/chrome|crios|fxios/i.test(ua);
  }

  function isStandalone() {
    return window.navigator.standalone === true ||
           window.matchMedia('(display-mode: standalone)').matches;
  }

  function maybeShowIosHint() {
    if (!isIosSafari() || isStandalone()) return;
    const ts = localStorage.getItem('pwa-install-dismissed');
    if (ts && Date.now() - parseInt(ts, 10) < 30 * 24 * 60 * 60 * 1000) return;

    const visits = parseInt(localStorage.getItem('pwa-visit-count') || '1', 10);
    if (visits < 2) return;

    const banner = document.getElementById('pwa-install-banner');
    if (!banner) return;

    // Swap normal install button for iOS-specific hint text
    const hint = banner.querySelector('.pwa-ios-hint');
    const btn  = banner.querySelector('.pwa-install-btn');
    if (hint) hint.style.display = 'block';
    if (btn)  btn.style.display  = 'none';

    setTimeout(() => banner.classList.add('is-visible'), 3000);
  }

  // ---------------------------------------------------------------------------
  // Online / offline indicator
  // ---------------------------------------------------------------------------
  function updateOnlineStatus() {
    const toast = document.getElementById('pwa-offline-toast');
    if (!toast) return;
    if (navigator.onLine) {
      toast.classList.remove('is-visible');
    } else {
      toast.classList.add('is-visible');
    }
  }

  window.addEventListener('online',  updateOnlineStatus);
  window.addEventListener('offline', updateOnlineStatus);

  // ---------------------------------------------------------------------------
  // Visit counter (used by install-prompt logic)
  // ---------------------------------------------------------------------------
  function incrementVisitCount() {
    const n = parseInt(localStorage.getItem('pwa-visit-count') || '0', 10) + 1;
    localStorage.setItem('pwa-visit-count', String(n));
  }

  // ---------------------------------------------------------------------------
  // Background Sync: queue a run-log POST for offline replay
  // ---------------------------------------------------------------------------

  /**
   * Queue a run-log payload and register a Background Sync (or fall back to
   * an online-event listener on browsers that don't support SyncManager).
   *
   * @param {Object} data  The run log payload to POST to /api/runs
   * @returns {Promise<boolean>}  true if queued successfully
   */
  window.queueRunLogForSync = async function (data) {
    try {
      const db = await _openIDB();
      await _idbAdd(db, { data, timestamp: Date.now() });

      if ('serviceWorker' in navigator && 'SyncManager' in window) {
        const reg = await navigator.serviceWorker.ready;
        await reg.sync.register(SYNC_TAG);
        console.debug('[PWA] Background sync registered');
      } else {
        // Fallback: flush as soon as network returns
        window.addEventListener('online', _flushQueue, { once: true });
      }

      return true;
    } catch (err) {
      console.error('[PWA] Failed to queue run log:', err);
      return false;
    }
  };

  async function _flushQueue() {
    try {
      const db    = await _openIDB();
      const items = await _idbGetAll(db);

      for (const item of items) {
        try {
          const resp = await fetch('/api/runs', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(item.data),
            credentials: 'include',
          });
          if (resp.ok) await _idbDelete(db, item.id);
        } catch { /* retry next time */ }
      }
    } catch (err) {
      console.warn('[PWA] Queue flush failed:', err);
    }
  }

  // ---------------------------------------------------------------------------
  // Push notification permission
  // ---------------------------------------------------------------------------

  /**
   * Request push notification permission.
   * @returns {Promise<boolean>}  true if granted
   */
  window.requestPushPermission = async function () {
    if (!('Notification' in window) || !('serviceWorker' in navigator)) return false;
    const permission = await Notification.requestPermission();
    return permission === 'granted';
  };

  // ---------------------------------------------------------------------------
  // IndexedDB helpers
  // ---------------------------------------------------------------------------
  function _openIDB() {
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

  function _idbAdd(db, record) {
    return new Promise((resolve, reject) => {
      const tx  = db.transaction(STORE_QUEUE, 'readwrite');
      const req = tx.objectStore(STORE_QUEUE).add(record);
      req.onsuccess = () => resolve();
      req.onerror   = e => reject(e.target.error);
    });
  }

  function _idbGetAll(db) {
    return new Promise((resolve, reject) => {
      const tx  = db.transaction(STORE_QUEUE, 'readonly');
      const req = tx.objectStore(STORE_QUEUE).getAll();
      req.onsuccess = e => resolve(e.target.result);
      req.onerror   = e => reject(e.target.error);
    });
  }

  function _idbDelete(db, id) {
    return new Promise((resolve, reject) => {
      const tx  = db.transaction(STORE_QUEUE, 'readwrite');
      const req = tx.objectStore(STORE_QUEUE).delete(id);
      req.onsuccess = () => resolve();
      req.onerror   = e => reject(e.target.error);
    });
  }

  // ---------------------------------------------------------------------------
  // Init on DOM ready
  // ---------------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', () => {
    incrementVisitCount();
    updateOnlineStatus();
    maybeShowIosHint();
  });

})();
