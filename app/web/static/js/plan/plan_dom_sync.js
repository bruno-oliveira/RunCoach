/**
 * plan_dom_sync.js — patch the plan page in place from API response payloads.
 *
 * Apply endpoints return `{adaptation_revision, week_totals,
 * workout_changes, adaptation_state}` (the "patch" block of a change_plan
 * or the flat payload from a per-week override). This module updates the
 * existing DOM nodes so the user sees the new numbers without a reload.
 */
(function () {
    'use strict';

    function _formatKm(value) {
        var n = Number(value);
        if (!isFinite(n)) return '0.0';
        return n.toFixed(1);
    }

    function applyWeekTotals(weekTotals) {
        if (!Array.isArray(weekTotals)) return;
        weekTotals.forEach(function (entry) {
            var weekEl = document.querySelector('[data-week="' + entry.week + '"]');
            if (!weekEl) return;
            var totalEl = weekEl.querySelector('.week-total');
            if (totalEl) {
                totalEl.textContent = _formatKm(entry.total_km) + ' km';
            }
        });
    }

    function applyWorkoutChanges(changes) {
        if (!Array.isArray(changes)) return;
        changes.forEach(function (c) {
            var item = document.querySelector(
                '.workout-item[data-week-num="' + c.week + '"][data-day-num="' + c.day + '"]'
            );
            if (!item) return;
            var distEl = item.querySelector('.workout-distance');
            if (!distEl) return;
            // The original markup embeds the km text directly inside
            // .workout-distance, followed by optional spans (zone hint,
            // adjusted chip). Walk text nodes and replace the first
            // numeric one so the spans survive.
            var children = distEl.childNodes;
            for (var i = 0; i < children.length; i++) {
                var node = children[i];
                if (node.nodeType === 3 && /\d/.test(node.nodeValue)) {
                    node.nodeValue = _formatKm(c.new_distance_km) + ' km';
                    break;
                }
            }
        });
    }

    function applyAdaptationState(state) {
        if (!state) return;
        var card = document.getElementById('plan-adaptation-card');
        if (state.kind === 'none' || !state.kind) {
            if (card) {
                card.style.opacity = '0';
                card.style.transition = 'opacity 0.25s ease';
                setTimeout(function () { card.remove(); }, 260);
            }
            if (window.APP_CTX) window.APP_CTX.adaptation_state = { kind: 'none' };
            return;
        }

        if (!card) {
            // No existing card and the server says we now have one:
            // a fresh recommendation parked or a new alert raised mid-session.
            // Reloading is the simplest path to render it consistently.
            if (typeof window.reloadPlanPage === 'function') {
                window.reloadPlanPage();
            }
            return;
        }

        card.setAttribute('data-kind', state.kind);
        var headline = document.getElementById('plan-adaptation-card-headline');
        var detail = document.getElementById('plan-adaptation-card-detail');
        if (headline && state.headline) headline.textContent = state.headline;
        if (detail && state.detail) detail.textContent = state.detail;
        if (window.APP_CTX) window.APP_CTX.adaptation_state = state;
    }

    function applyPatch(patch) {
        if (!patch) return;
        if (typeof patch.adaptation_revision === 'number' && window.APP_CTX) {
            window.APP_CTX.adaptation_revision = patch.adaptation_revision;
        }
        applyWorkoutChanges(patch.workout_changes);
        applyWeekTotals(patch.week_totals);
        applyAdaptationState(patch.adaptation_state);
    }

    window.planDomSync = {
        applyPatch: applyPatch,
        applyWeekTotals: applyWeekTotals,
        applyWorkoutChanges: applyWorkoutChanges,
        applyAdaptationState: applyAdaptationState
    };
})();
