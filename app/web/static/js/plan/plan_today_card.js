/**
 * plan_today_card.js — wires the Today card at the head of the plan.
 *
 * The card itself is server-rendered (correct on first paint, survives a
 * reload). This adds the three things that can't be:
 *
 *   1. the check-in slot, filled by the shared readiness_checkin.js;
 *   2. the advisory under today's session, re-read from the server after a
 *      check-in — the payoff of folding the capture in here, and re-read
 *      rather than recomputed in JS so the wording has one implementation;
 *   3. the "Missed it?" chooser, shared with the Coach hub.
 *
 * Depends on readiness_checkin.js, and optionally plan_missed_today.js and
 * plan_proactive_nudge.js; degrades quietly when any is absent.
 */
(function () {
    'use strict';

    function planId() {
        return window.APP_CTX && window.APP_CTX.plan_id;
    }

    /* Re-read the one line under today's session. The band that produces it
       lives on the server, so a check-in is the only thing that can change it
       without a reload. */
    function refreshAdvisory() {
        var id = planId();
        var line = document.getElementById('today-session-advisory');
        if (!id || !line) return;

        fetch('/api/plan/' + encodeURIComponent(id) + '/today-card', {
            credentials: 'same-origin',
        })
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (data) {
                if (!data) return;
                var card = document.getElementById('today-card');
                if (card) card.setAttribute('data-band', data.readiness_band || '');
                if (data.advisory) {
                    line.textContent = data.advisory;
                    line.hidden = false;
                } else {
                    line.textContent = '';
                    line.hidden = true;
                }
            })
            .catch(function () { /* best-effort; the rendered line stays */ });
    }

    function init() {
        var card = document.getElementById('today-card');
        if (!card) return;

        var host = document.getElementById('readinessCheckinCard');
        if (host && window.ReadinessCheckIn) {
            host.style.display = '';
            window.ReadinessCheckIn.onSaved = function () {
                refreshAdvisory();
                // A run-down morning is one of the proactive guards, so re-ask
                // rather than making the runner reload to see the offer.
                if (window.PlanProactiveNudge) window.PlanProactiveNudge.load();
            };
            window.ReadinessCheckIn.load(planId());
        }

        var missed = document.getElementById('today-missed-cta');
        if (missed) {
            missed.addEventListener('click', function () {
                if (!window.MissedTodayChooser) return;
                window.MissedTodayChooser.open(
                    planId(),
                    window.APP_CTX && window.APP_CTX.today_iso
                );
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
