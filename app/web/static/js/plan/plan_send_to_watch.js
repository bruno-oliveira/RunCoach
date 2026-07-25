/**
 * Send-to-watch button wiring.
 *
 * Each workout card carries a `.send-to-watch-btn` and each week card a
 * `.send-week-btn`. Clicking one POSTs to the user's Intervals.icu calendar,
 * which forwards planned workouts on to Garmin, COROS, Wahoo, Suunto or Zwift.
 * When the user hasn't connected Intervals.icu yet, the button kicks off the
 * OAuth connect flow.
 *
 * The setup gate: two toggles inside Intervals.icu decide whether a planned
 * workout ever leaves the calendar, and they live on a platform whose state we
 * can't read. So the checklist is shown *before* the first send and the send
 * waits behind it — previously it appeared afterwards, which meant the first
 * thing a runner with an unconfigured Intervals account saw was a "sent!" toast
 * for a workout that was never going to reach their wrist.
 *
 * Auth is cookie-based (credentials: 'same-origin'); there is no CSRF token.
 */
(function () {
    'use strict';

    // The send the runner asked for, held while the setup wizard is up.
    var pendingSend = null;

    function t(key, fallback) {
        if (window.RC_I18N && typeof window.RC_I18N.t === 'function') {
            var value = window.RC_I18N.t(key);
            if (value && value !== key) return value;
        }
        return fallback;
    }

    function mirrorPanel() {
        return document.getElementById('watch-mirror');
    }

    // Server-rendered from `User.watch_setup_confirmed_at`, so it survives a
    // reload and a new device — unlike the localStorage flag this replaced.
    // Absent panel (a completed plan) means we have nothing to check, so don't
    // stand in the runner's way.
    function setupConfirmed() {
        var el = mirrorPanel();
        return !el || el.dataset.setupConfirmed === '1';
    }

    // Reveal the checklist and bring it into view.
    window.showWatchSetup = function () {
        var panel = document.getElementById('watch-setup');
        if (!panel) return;
        panel.hidden = false;
        panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };

    window.dismissWatchSetup = function () {
        var panel = document.getElementById('watch-setup');
        if (panel) panel.hidden = true;
        pendingSend = null;
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

    // Records the runner's word that both Intervals.icu toggles are set, then
    // releases the send that was waiting on it. A failed record keeps the wizard
    // up rather than proceeding: otherwise the gate would silently reappear on
    // their next visit with no explanation.
    window.confirmWatchSetup = async function () {
        try {
            var resp = await fetch('/api/intervals/watch-setup-confirm', {
                method: 'POST',
                headers: headers(),
                credentials: 'same-origin',
            });
            if (!resp.ok) throw new Error('confirm failed');
        } catch (e) {
            toast('Error', t('watchsetup.confirm_failed', "Couldn't save that. Try again."));
            return;
        }

        var el = mirrorPanel();
        if (el) el.dataset.setupConfirmed = '1';
        var queued = pendingSend;
        window.dismissWatchSetup();
        if (queued) queued.run(queued.btn);
    };

    // Returns true when the send may proceed; otherwise queues it behind the
    // setup wizard.
    function gateOnSetup(run, btn) {
        if (setupConfirmed()) return true;
        pendingSend = { run: run, btn: btn };
        window.showWatchSetup();
        return false;
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
                    data.message || t('watchmirror.sent', 'Sent — syncing to your watch shortly.')
                );
                if (typeof window.refreshWatchStatus === 'function') {
                    window.refreshWatchStatus();
                }
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
                toast('Success', data.message || t('week.sent', 'Week sent to your watch.'));
                // Mark the week's per-workout buttons so the card matches what
                // actually went out.
                var card = btn.closest('.week-card');
                if (card) {
                    card.querySelectorAll('.send-to-watch-btn').forEach(function (b) {
                        b.classList.add('is-sent');
                    });
                }
                if (typeof window.refreshWatchStatus === 'function') {
                    window.refreshWatchStatus();
                }
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
        var run = btn.classList.contains('send-week-btn') ? sendWeek : sendWorkout;
        if (!gateOnSetup(run, btn)) return;
        run(btn);
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
