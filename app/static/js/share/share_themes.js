/**
 * share_themes.js — Theme and colour constant definitions for ShareCard.
 *
 * Must be loaded BEFORE share_card.js.
 * Defines window.SHARE_THEMES, window.SHARE_QUALITY_COLORS,
 * window.SHARE_WORKOUT_COLORS for the card object to pick up.
 */
(function () {
    'use strict';

    window.SHARE_THEMES = {
        midnight: {
            label: 'Midnight',
            bg:            ['#0F172A', '#162044', '#1E3A5F'],
            accent:        '#FF6246',
            accentSlash:   'rgba(255, 98, 70, 0.06)',
            textPrimary:   '#FFFFFF',
            textSecondary: '#94A3B8',
            textMuted:     '#475569',
            ringBg:        'rgba(255,255,255,0.08)',
            divider:       'rgba(255,255,255,0.08)',
            topoStroke:    '#FFFFFF',
            topoAlpha:     0.04,
            vdotBadgeBg:   'rgba(255, 98, 70, 0.12)',
        },
        dawn: {
            label: 'Dawn',
            bg:            ['#FAFAF7', '#F3F0E8', '#EBE6DC'],
            accent:        '#1D4ED8',
            accentSlash:   'rgba(29, 78, 216, 0.04)',
            textPrimary:   '#1C1917',
            textSecondary: '#6B6560',
            textMuted:     '#A09A93',
            ringBg:        'rgba(28, 25, 23, 0.06)',
            divider:       'rgba(28, 25, 23, 0.10)',
            topoStroke:    '#1D4ED8',
            topoAlpha:     0.05,
            vdotBadgeBg:   'rgba(29, 78, 216, 0.08)',
        },
        dusk: {
            label: 'Dusk',
            bg:            ['#0A0A12', '#140E20', '#1C1230'],
            accent:        '#C084FC',
            accentSlash:   'rgba(192, 132, 252, 0.05)',
            textPrimary:   '#F1F0FB',
            textSecondary: '#8B83A8',
            textMuted:     '#5B5475',
            ringBg:        'rgba(241,240,251,0.07)',
            divider:       'rgba(241,240,251,0.07)',
            topoStroke:    '#C084FC',
            topoAlpha:     0.035,
            vdotBadgeBg:   'rgba(192, 132, 252, 0.12)',
        },
    };

    window.SHARE_QUALITY_COLORS = {
        'Nailed it': '#22C55E',
        'On track':  '#3B82F6',
        'Too easy':  '#EAB308',
        'Too hard':  '#EF4444',
        'Easy':      '#22C55E',
        'Moderate':  '#3B82F6',
        'Hard':      '#F97316',
        'Max':       '#EF4444',
    };

    window.SHARE_WORKOUT_COLORS = {
        easy:     '#22C55E',
        recovery: '#22C55E',
        tempo:    '#F97316',
        interval: '#EF4444',
        long:     '#3B82F6',
        hill:     '#8B5CF6',
        race:     '#EC4899',
    };
})();
