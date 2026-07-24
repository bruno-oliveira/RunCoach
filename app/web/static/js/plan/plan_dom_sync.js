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
        if (!isFinite(n) || n <= 0) return '0.0';
        // Truncate to one decimal (no rounding) so the displayed distance
        // never claims more than the workout prescribes and matches the
        // server-side format_km() exactly.
        return (Math.floor(n * 10) / 10).toFixed(1);
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

    // Every workout-type class the card can carry, so a type change can strip
    // the old one before adding the new (keeps the card's colour honest).
    var TYPE_CLASSES = [
        'easy', 'recovery', 'long', 'tempo', 'threshold', 'interval', 'speed',
        'vo2max', 'race_pace', 'marathon_pace', 'goal_pace', 'fartlek', 'hill',
        'progression', 'run_walk', 'cross_train', 'strength', 'rest'
    ];

    function _titleCase(type) {
        return String(type || '')
            .replace(/_/g, ' ')
            .replace(/\b\w/g, function (m) { return m.toUpperCase(); });
    }

    function _setDistanceText(distEl, km) {
        // The km text is a bare text node followed by optional spans (zone
        // hint, adjusted chip). Replace the first numeric text node so the
        // spans survive.
        var children = distEl.childNodes;
        for (var i = 0; i < children.length; i++) {
            var node = children[i];
            if (node.nodeType === 3 && /\d/.test(node.nodeValue)) {
                node.nodeValue = _formatKm(km) + ' km';
                return;
            }
        }
        // No numeric node yet (was a rest/duration line) — prepend one.
        distEl.insertBefore(
            document.createTextNode(_formatKm(km) + ' km'), distEl.firstChild
        );
    }

    function _updateAdjustedChip(item, distEl, km, baselineKm) {
        var chip = distEl.querySelector('.workout-adjusted-chip');
        var isAdjusted = baselineKm != null && Math.abs(baselineKm - km) >= 0.05;
        item.classList.toggle('is-adjusted', isAdjusted);
        item.classList.toggle('is-adjusted-down', isAdjusted && km < baselineKm);
        if (chip) chip.remove();  // repaint fresh below to avoid stale arrows
        if (!isAdjusted) return;
        var down = km < baselineKm;
        var span = document.createElement('span');
        span.className = 'workout-adjusted-chip' + (down ? ' is-down' : '');
        span.title = 'Adjusted from ' + _formatKm(baselineKm)
            + ' km — open the latest changes panel for the reason';
        span.innerHTML = '<span class="workout-adjusted-chip-arrow" aria-hidden="true">'
            + (down ? '↓' : '↑') + '</span> adjusted from ' + _formatKm(baselineKm) + ' km';
        distEl.appendChild(span);
    }

    function _becomeRest(item) {
        // Turning a run into a rest day: drop the distance line and the
        // action controls the template omits for rest workouts.
        var distEl = item.querySelector('.workout-distance');
        if (distEl) distEl.remove();
        ['.send-to-watch-btn', '.download-fit-btn', '.log-run-btn',
            '.key-workout-badge', '.workout-structure', '.workout-details',
            '.run-walk-intervals'].forEach(function (sel) {
            var el = item.querySelector(sel);
            if (el) el.remove();
        });
    }

    function _repaintType(item, newType) {
        TYPE_CLASSES.forEach(function (t) { item.classList.remove(t); });
        item.classList.add(newType);
        var typeEl = item.querySelector('.workout-type');
        if (typeEl) typeEl.textContent = _titleCase(newType);
        // A demoted session no longer carries its key-workout structure.
        ['.key-workout-badge', '.workout-structure', '.workout-details'].forEach(
            function (sel) {
                var el = item.querySelector(sel);
                if (el) el.remove();
            }
        );
    }

    function applyWorkoutChanges(changes) {
        if (!Array.isArray(changes)) return;
        changes.forEach(function (c) {
            var item = document.querySelector(
                '.workout-item[data-week-num="' + c.week + '"][data-day-num="' + c.day + '"]'
            );
            if (!item) return;

            if (c.is_rest) {
                _repaintCardClasses(item, 'rest');
                _becomeRest(item);
                var typeEl = item.querySelector('.workout-type');
                if (typeEl) typeEl.textContent = 'Rest';
                item.classList.remove('is-adjusted', 'is-adjusted-down');
                return;
            }

            if (c.type_changed && c.new_type) {
                _repaintType(item, c.new_type);
            }

            var distEl = item.querySelector('.workout-distance');
            if (distEl) {
                _setDistanceText(distEl, c.new_distance_km);
                if ('baseline_distance_km' in c) {
                    _updateAdjustedChip(item, distEl, c.new_distance_km,
                        c.baseline_distance_km);
                }
            }
        });
    }

    function _repaintCardClasses(item, newType) {
        TYPE_CLASSES.forEach(function (t) { item.classList.remove(t); });
        item.classList.add(newType);
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
