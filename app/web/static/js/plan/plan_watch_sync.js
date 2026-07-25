/**
 * Watch-mirror panel: the standing "keep my watch in sync" subscription.
 *
 * The server renders #watch-mirror from the plan's stored mirror state, so the
 * panel is already correct on first paint and after a reload. This file does
 * the three things that need the network:
 *
 *   - reads the calendar back (`GET /watch-status`) and replaces the generic
 *     "keeping your watch in sync" line with a real count of what is on it,
 *   - flips the subscription on and off,
 *   - retries a failed mirror.
 *
 * Deliberately reports "couldn't check" when the read-back fails rather than
 * falling back to a count of button presses — an unverifiable number is the
 * problem this panel exists to fix.
 *
 * Auth is cookie-based (credentials: 'same-origin').
 */
(function () {
    'use strict';

    function t(key, fallback) {
        if (window.RC_I18N && typeof window.RC_I18N.t === 'function') {
            var value = window.RC_I18N.t(key);
            if (value && value !== key) return value;
        }
        return fallback;
    }

    function panel() {
        return document.getElementById('watch-mirror');
    }

    function planId() {
        var el = panel();
        return (el && el.dataset.planId) || (window.APP_CTX && window.APP_CTX.plan_id);
    }

    function toast(kind, message) {
        if (window.api && typeof window.api['show' + kind] === 'function') {
            window.api['show' + kind](message);
        } else if (typeof window.notify === 'function') {
            window.notify(message, { type: (kind || 'Info').toLowerCase() });
        }
    }

    function headers() {
        var extra = { 'Content-Type': 'application/json' };
        return typeof window.authHeaders === 'function'
            ? window.authHeaders(extra)
            : extra;
    }

    // "4 minutes ago" from an ISO timestamp. Coarse on purpose: the runner wants
    // to know whether this is fresh, not the exact second.
    function relativeTime(iso) {
        if (!iso) return '';
        var then = Date.parse(iso.endsWith('Z') || iso.indexOf('+') > 0 ? iso : iso + 'Z');
        if (isNaN(then)) return '';
        var seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
        if (seconds < 90) return t('watchmirror.just_now', 'just now');
        var minutes = Math.round(seconds / 60);
        if (minutes < 60) return minutes + ' ' + t('watchmirror.minutes_ago', 'minutes ago');
        var hours = Math.round(minutes / 60);
        if (hours < 24) return hours + ' ' + t('watchmirror.hours_ago', 'hours ago');
        var days = Math.round(hours / 24);
        return days + ' ' + t('watchmirror.days_ago', 'days ago');
    }

    function describe(data) {
        var when = relativeTime(data.last_synced_at);
        if (data.events_on_calendar === null || data.events_on_calendar === undefined) {
            // The read-back failed. Say so; don't substitute a number we can't
            // stand behind.
            return t(
                'watchmirror.unverified',
                "Couldn't check your calendar just now"
            );
        }
        var count = data.events_on_calendar;
        var noun = count === 1
            ? t('watchmirror.session', 'session')
            : t('watchmirror.sessions', 'sessions');
        var text = count + ' ' + noun + ' ' +
            t('watchmirror.on_calendar', 'on your Intervals.icu calendar');
        return when ? text + ' · ' + t('watchmirror.synced', 'synced') + ' ' + when : text;
    }

    async function refreshWatchStatus() {
        var el = panel();
        if (!el || el.dataset.syncEnabled !== '1' || el.dataset.connected !== '1') return;
        var line = document.getElementById('watch-mirror-status');
        if (!line) return;

        try {
            var resp = await fetch(
                '/api/intervals/watch-status?plan_id=' + encodeURIComponent(planId()),
                { credentials: 'same-origin', headers: headers() }
            );
            if (!resp.ok) return;
            var data = await resp.json();
            // Drop the i18n binding before writing. The placeholder text is a
            // translated string, so leaving the attribute in place lets the next
            // applyTranslations() — on init, or on a language toggle — overwrite
            // the read-back count with the generic line again.
            line.removeAttribute('data-i18n');
            line.textContent = describe(data);
            // A revoked token only surfaces on a call, so the read-back is where
            // we find out. Reload so the server re-renders the reconnect row
            // rather than leaving a friendly line above a dead connection.
            if (data.error === 'auth') window.location.reload();
        } catch (e) {
            /* leave the server-rendered line as-is */
        }
    }

    window.setWatchSync = async function (enabled) {
        var id = planId();
        if (!id) return;
        try {
            var resp = await fetch('/api/intervals/watch-sync', {
                method: 'POST',
                headers: headers(),
                credentials: 'same-origin',
                body: JSON.stringify({ plan_id: id, enabled: !!enabled }),
            });
            var data = {};
            try { data = await resp.json(); } catch (e) { /* non-JSON body */ }
            if (!resp.ok) {
                toast('Error', data.detail || t('watchmirror.toggle_failed', "Couldn't change watch sync."));
                return;
            }
            toast(
                'Success',
                enabled
                    ? t('watchmirror.on_toast', "Your watch will stay in sync with this plan.")
                    : t('watchmirror.off_toast', 'Watch sync is off. Sessions already sent stay on your calendar.')
            );
            window.location.reload();
        } catch (e) {
            toast('Error', t('watchmirror.network', 'Network error. Try again.'));
        }
    };

    window.retryWatchSync = async function () {
        var id = planId();
        if (!id) return;
        try {
            var resp = await fetch('/api/intervals/watch-resync', {
                method: 'POST',
                headers: headers(),
                credentials: 'same-origin',
                body: JSON.stringify({ plan_id: id }),
            });
            var data = {};
            try { data = await resp.json(); } catch (e) { /* non-JSON body */ }
            if (resp.status === 401 || data.error === 'auth') {
                toast('Error', t('watchmirror.reconnect', 'Reconnect to keep your watch in sync'));
                window.location.reload();
                return;
            }
            if (!resp.ok || !data.ok) {
                toast('Error', t('watchmirror.retry_failed', "Still couldn't reach Intervals.icu. Try again shortly."));
                return;
            }
            toast('Success', t('watchmirror.caught_up', 'Your watch is up to date.'));
            window.location.reload();
        } catch (e) {
            toast('Error', t('watchmirror.network', 'Network error. Try again.'));
        }
    };

    window.refreshWatchStatus = refreshWatchStatus;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', refreshWatchStatus);
    } else {
        refreshWatchStatus();
    }
})();
