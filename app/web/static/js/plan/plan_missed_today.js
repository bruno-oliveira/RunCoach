/**
 * plan_missed_today.js — focused 3-option chooser for a single missed or
 * not-yet-logged workout ("Missed it?" CTA on the Today tab / plan page).
 *
 * A scoped sibling of plan_intent_menu.js: instead of the general life-event
 * list, presents exactly the missed_today choices (reschedule / lighter
 * version / skip it) for one (planId, date) pair, then rides the same
 * preview → apply change-plan modal via
 * window.runChangePlanAction('intent', { body: { intent: 'missed_today', params } }).
 */
(function () {
    'use strict';

    var CHOICES = [
        {
            id: 'reschedule',
            emoji: '🔁',
            label: 'Reschedule it',
            blurb: 'Move it to the nearest free day this week.',
        },
        {
            id: 'ease',
            emoji: '🪶',
            label: 'Lighter version',
            blurb: 'Swap in a shorter version of the same run.',
        },
        {
            id: 'skip',
            emoji: '⏭️',
            label: 'Skip it',
            blurb: "No make-up needed — move on.",
        },
    ];

    function overlay() { return document.getElementById('missed-today-overlay'); }
    function body() { return document.getElementById('missed-today-body'); }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = String(str == null ? '' : str);
        return div.innerHTML;
    }

    function bindDismiss(o) {
        o.onclick = function (e) { if (e.target === o) close(); };
        o.querySelectorAll('[data-missed-today-close]').forEach(function (b) {
            b.onclick = close;
        });
    }

    function close() {
        var o = overlay();
        if (!o) return;
        o.hidden = true;
        o.classList.remove('is-open');
        document.body.style.overflow = '';
    }

    function render(planId, dateIso) {
        var html = '<ul class="intent-list">';
        CHOICES.forEach(function (c) {
            html += '<li><button type="button" class="intent-option" data-choice="' + c.id + '">'
                + '<span class="intent-option-emoji" aria-hidden="true">' + c.emoji + '</span>'
                + '<span class="intent-option-text"><strong>' + escapeHtml(c.label) + '</strong>'
                + '<span>' + escapeHtml(c.blurb) + '</span></span>'
                + '<svg class="intent-option-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>'
                + '</button></li>';
        });
        html += '</ul>';
        var b = body();
        if (!b) return;
        b.innerHTML = html;
        b.querySelectorAll('[data-choice]').forEach(function (btn) {
            btn.onclick = function () {
                var choice = btn.getAttribute('data-choice');
                close();
                if (window.runChangePlanAction) {
                    window.runChangePlanAction('intent', {
                        planId: planId,
                        body: { intent: 'missed_today', params: { choice: choice, date: dateIso } },
                    });
                } else if (window.ApiClient && window.ApiClient.showError) {
                    window.ApiClient.showError('Adaptation UI unavailable — refresh and try again.');
                }
            };
        });
    }

    function open(planId, dateIso) {
        var o = overlay();
        if (!o || !planId || !dateIso) return;
        render(planId, dateIso);
        o.hidden = false;
        o.classList.add('is-open');
        document.body.style.overflow = 'hidden';
        bindDismiss(o);
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            var o = overlay();
            if (o && !o.hidden) close();
        }
    });

    window.MissedTodayChooser = { open: open, close: close };
})();
