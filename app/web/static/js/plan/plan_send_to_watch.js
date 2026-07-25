/**
 * Send-to-watch button wiring.
 *
 * Each workout card carries a `.send-to-watch-btn` (next to the .fit download
 * button). Clicking it POSTs the workout to the user's Intervals.icu calendar,
 * which forwards it to Garmin Connect automatically. When the user hasn't
 * connected Intervals.icu yet, the button kicks off the OAuth connect flow.
 *
 * Auth is cookie-based (credentials: 'same-origin'); there is no CSRF token.
 */
(function () {
    'use strict';

    // The Intervals connection is one click, but forwarding to Garmin needs two
    // toggles inside Intervals.icu we can't automate. We reveal the setup
    // checklist (#watch-setup) once, the first time a send succeeds — that's
    // when "will this actually reach my watch?" is top of mind. Persisted so it
    // doesn't nag on every visit; re-openable via window.showWatchSetup().
    var SETUP_SEEN_KEY = 'rc_watch_setup_seen';

    function setupSeen() {
        try { return localStorage.getItem(SETUP_SEEN_KEY) === '1'; } catch (e) { return false; }
    }

    function markSetupSeen() {
        try { localStorage.setItem(SETUP_SEEN_KEY, '1'); } catch (e) { /* ignore */ }
    }

    // Reveal the checklist and bring it into view. `force` re-opens it even if
    // the user has seen (and dismissed) it before.
    window.showWatchSetup = function (force) {
        var panel = document.getElementById('watch-setup');
        if (!panel) return;
        if (!force && setupSeen()) return;
        panel.hidden = false;
        panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
        markSetupSeen();
    };

    window.dismissWatchSetup = function () {
        var panel = document.getElementById('watch-setup');
        if (panel) panel.hidden = true;
        markSetupSeen();
    };

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

    async function startConnect() {
        try {
            var resp = await fetch('/api/intervals/connect', {
                credentials: 'same-origin',
            });
            if (!resp.ok) throw new Error('connect failed');
            var data = await resp.json();
            if (data.authorize_url) {
                window.location.href = data.authorize_url;
                return;
            }
            throw new Error('missing authorize_url');
        } catch (e) {
            toast('Error', 'Could not start Intervals.icu connection. Try again.');
        }
    }

    async function sendWorkout(btn) {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        var week = parseInt(btn.dataset.week, 10);
        var day = parseInt(btn.dataset.day, 10);
        if (!planId || !week || !day) {
            toast('Error', 'Could not identify this workout.');
            return;
        }

        btn.classList.add('is-sending');
        try {
            var resp = await fetch('/api/intervals/push-workout', {
                method: 'POST',
                headers: headers(),
                credentials: 'same-origin',
                body: JSON.stringify({ plan_id: planId, week: week, day: day }),
            });
            var data = {};
            try {
                data = await resp.json();
            } catch (e) {
                /* non-JSON error body */
            }
            if (resp.ok) {
                btn.classList.add('is-sent');
                toast(
                    'Success',
                    data.message || 'Sent to your watch — syncing to Garmin shortly.'
                );
                // First successful send: show the one-time Garmin setup checklist
                // so the two Intervals toggles land before they wonder why the
                // watch is empty. No-ops on later sends.
                window.showWatchSetup();
            } else if (resp.status === 401) {
                toast(
                    'Error',
                    data.detail ||
                        'Reconnect Intervals.icu (grant calendar access) to send.'
                );
                startConnect();
            } else if (resp.status === 400) {
                // Not connected, or nothing to send — offer the connect flow.
                toast('Info', data.detail || 'Connect Intervals.icu to send workouts.');
                if (btn.classList.contains('is-disconnected')) startConnect();
            } else {
                toast('Error', data.detail || 'Could not send this workout.');
            }
        } catch (e) {
            toast('Error', 'Network error sending to your watch. Try again.');
        } finally {
            btn.classList.remove('is-sending');
        }
    }

    // Whole-week push. One bulk request server-side, so a five-run week costs a
    // single round trip instead of five presses. Rest days are skipped there.
    async function sendWeek(btn) {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        var week = parseInt(btn.dataset.week, 10);
        if (!planId || !week) {
            toast('Error', 'Could not identify this week.');
            return;
        }

        btn.classList.add('is-sending');
        try {
            var resp = await fetch('/api/intervals/push-week', {
                method: 'POST',
                headers: headers(),
                credentials: 'same-origin',
                body: JSON.stringify({ plan_id: planId, week: week }),
            });
            var data = {};
            try {
                data = await resp.json();
            } catch (e) {
                /* non-JSON error body */
            }
            if (resp.ok) {
                btn.classList.add('is-sent');
                toast('Success', data.message || 'Week sent to your watch.');
                // Mark the week's per-workout buttons so the card matches what
                // actually went out.
                var card = btn.closest('.week-card');
                if (card) {
                    card.querySelectorAll('.send-to-watch-btn').forEach(function (b) {
                        b.classList.add('is-sent');
                    });
                }
                window.showWatchSetup();
            } else if (resp.status === 401) {
                toast('Error', data.detail || 'Reconnect Intervals.icu (grant calendar access) to send.');
                startConnect();
            } else if (resp.status === 400) {
                toast('Info', data.detail || 'Connect Intervals.icu to send workouts.');
                if (btn.classList.contains('is-disconnected')) startConnect();
            } else {
                toast('Error', data.detail || "Couldn't send this week.");
            }
        } catch (e) {
            toast('Error', 'Network error sending to your watch. Try again.');
        } finally {
            btn.classList.remove('is-sending');
        }
    }

    function onClick(e) {
        e.preventDefault();
        e.stopPropagation();
        var btn = e.currentTarget;
        if (btn.classList.contains('is-sending')) return;
        if (btn.classList.contains('is-disconnected')) {
            startConnect();
            return;
        }
        if (btn.classList.contains('send-week-btn')) {
            sendWeek(btn);
            return;
        }
        sendWorkout(btn);
    }

    function bind() {
        var selector = '.send-to-watch-btn, .send-week-btn';
        document.querySelectorAll(selector).forEach(function (btn) {
            if (btn.dataset.stwBound) return;
            btn.dataset.stwBound = '1';
            btn.addEventListener('click', onClick);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bind);
    } else {
        bind();
    }

    // Re-bind after the plan DOM is re-rendered (e.g. adaptation updates).
    window.bindSendToWatch = bind;
})();
