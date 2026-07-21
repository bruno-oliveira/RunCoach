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

    function toast(kind, message) {
        if (window.api && typeof window.api['show' + kind] === 'function') {
            window.api['show' + kind](message);
        } else {
            alert(message);
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

    function onClick(e) {
        e.preventDefault();
        e.stopPropagation();
        var btn = e.currentTarget;
        if (btn.classList.contains('is-sending')) return;
        if (btn.classList.contains('is-disconnected')) {
            startConnect();
            return;
        }
        sendWorkout(btn);
    }

    function bind() {
        document.querySelectorAll('.send-to-watch-btn').forEach(function (btn) {
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
