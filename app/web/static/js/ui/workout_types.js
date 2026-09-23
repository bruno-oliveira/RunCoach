/**
 * workout_types.js — the one client-side map of workout type → category.
 *
 * The plan page colours its day dots from the `--wt-*` tokens in base.css,
 * while the analytics charts and the Today card each kept their own map (a
 * different hex palette, different type coverage). A tempo was ochre on the
 * plan and amber on the Coach hub. Every surface now asks this module, and
 * colours resolve from the same CSS tokens the plan uses.
 *
 * Public API (window.RCWorkoutTypes):
 *   - category(type) → 'easy' | 'recovery' | 'long' | 'tempo' | 'interval' |
 *                      'hill' | 'strength' | 'race' | 'rest'
 *   - color(type)    → resolved CSS colour for the type's category
 *   - icon(type)     → emoji glyph for compact text surfaces
 *   - label(type)    → human label ("race_pace" → "Race pace")
 */
(function () {
    'use strict';

    // Keep in step with the `.workout-item.<type>::before` rules in
    // css/plan/weeks.css — both express the same grouping.
    var CATEGORY = {
        easy: 'easy', run_walk: 'easy', main: 'easy', medium_long: 'long',
        warmup: 'easy', cooldown: 'easy',
        recovery: 'recovery',
        long: 'long',
        tempo: 'tempo', threshold: 'tempo', cruise_interval: 'tempo', race_pace: 'tempo',
        interval: 'interval', fartlek: 'interval', vo2max: 'interval',
        vo2max_ladder: 'interval', time_trial: 'interval',
        hill: 'hill',
        strength: 'strength',
        race: 'race',
        rest: 'rest',
    };

    var ICON = {
        easy: '🟢', recovery: '🟢', long: '🔵', tempo: '🟠', interval: '🔴',
        hill: '⛰️', strength: '💪', race: '🏁', rest: '😴',
    };

    var FALLBACK_COLOR = '#A09A93';
    var colorCache = {};

    function category(type) {
        return CATEGORY[type] || 'easy';
    }

    function color(type) {
        var cat = category(type);
        if (colorCache[cat]) return colorCache[cat];
        var value = '';
        try {
            value = getComputedStyle(document.documentElement)
                .getPropertyValue('--wt-' + cat).trim();
        } catch (e) { /* no DOM (tests) — fall through */ }
        colorCache[cat] = value || FALLBACK_COLOR;
        return colorCache[cat];
    }

    function icon(type) {
        return type === 'fartlek' ? '🟣' : (ICON[category(type)] || '🏃');
    }

    function label(type) {
        var t = String(type || '').replace(/_/g, ' ');
        return t.charAt(0).toUpperCase() + t.slice(1);
    }

    window.RCWorkoutTypes = { category: category, color: color, icon: icon, label: label };
})();
