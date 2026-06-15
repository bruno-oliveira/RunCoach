/**
 * plan_intent_menu.js — the single "Adjust my plan" entry point.
 *
 * Presents life-event intents (feeling tired, skip a run, away, sick, etc.).
 * The user picks one (and fills any params), then the chosen intent is sent
 * through the shared preview → apply change-plan modal via
 * window.runChangePlanAction('intent', { body: { intent, params } }).
 *
 * Depends on plan_change_summary.js for the preview/apply modal.
 */
(function () {
    'use strict';

    var INTENTS = [
        {
            id: 'feeling_tired',
            emoji: '😮‍💨',
            label: 'Feeling tired',
            blurb: 'Ease the rest of this week and drop hard sessions to easy.',
        },
        {
            id: 'feeling_strong',
            emoji: '💪',
            label: 'Feeling strong',
            blurb: 'Add a little volume to your upcoming weeks.',
        },
        {
            id: 'skip_run',
            emoji: '⏭️',
            label: 'Skip a run',
            blurb: "Drop a run you can't fit in — no make-up needed.",
            form: 'skip',
        },
        {
            id: 'away',
            emoji: '✈️',
            label: 'Away / travelling',
            blurb: "Mark the days you'll be away as rest.",
            form: 'away',
        },
        {
            id: 'sick_injured',
            emoji: '🤒',
            label: 'Sick or injured',
            blurb: 'Rest now, then ease back gently over the next weeks.',
            form: 'sick',
        },
        {
            id: 'busy_week',
            emoji: '🗓️',
            label: 'Busy week',
            blurb: 'Trim the rest of this week to fit life.',
        },
    ];

    function overlay() { return document.getElementById('intent-menu-overlay'); }
    function body() { return document.getElementById('intent-menu-body'); }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = String(str == null ? '' : str);
        return div.innerHTML;
    }

    function todayISO() {
        var d = new Date();
        var local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
        return local.toISOString().slice(0, 10);
    }

    function bindDismiss(o) {
        o.onclick = function (e) { if (e.target === o) close(); };
        o.querySelectorAll('[data-intent-close]').forEach(function (b) {
            b.onclick = close;
        });
    }

    function open() {
        var o = overlay();
        if (!o) return;
        renderList();
        o.hidden = false;
        o.classList.add('is-open');
        document.body.style.overflow = 'hidden';
        bindDismiss(o);
    }

    function close() {
        var o = overlay();
        if (!o) return;
        o.hidden = true;
        o.classList.remove('is-open');
        document.body.style.overflow = '';
    }

    function renderList() {
        var html = '<ul class="intent-list">';
        INTENTS.forEach(function (it) {
            html += '<li><button type="button" class="intent-option" data-intent="' + it.id + '">'
                + '<span class="intent-option-emoji" aria-hidden="true">' + it.emoji + '</span>'
                + '<span class="intent-option-text"><strong>' + escapeHtml(it.label) + '</strong>'
                + '<span>' + escapeHtml(it.blurb) + '</span></span>'
                + '<svg class="intent-option-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>'
                + '</button></li>';
        });
        html += '</ul>';
        var b = body();
        if (!b) return;
        b.innerHTML = html;
        b.querySelectorAll('[data-intent]').forEach(function (btn) {
            btn.onclick = function () { onSelect(btn.getAttribute('data-intent')); };
        });
    }

    function findIntent(id) {
        for (var i = 0; i < INTENTS.length; i++) {
            if (INTENTS[i].id === id) return INTENTS[i];
        }
        return null;
    }

    function onSelect(id) {
        var it = findIntent(id);
        if (!it) return;
        if (it.form) {
            renderForm(it);
        } else {
            run(id, {});
        }
    }

    function renderForm(it) {
        var b = body();
        if (!b) return;
        var t = todayISO();
        var fields = '';
        if (it.form === 'skip') {
            fields = '<label class="intent-field"><span>Which day?</span>'
                + '<input type="date" id="intent-skip-date" value="' + t + '"></label>';
        } else if (it.form === 'away') {
            fields = '<label class="intent-field"><span>From</span>'
                + '<input type="date" id="intent-away-start" value="' + t + '"></label>'
                + '<label class="intent-field"><span>Until</span>'
                + '<input type="date" id="intent-away-end" value="' + t + '"></label>';
        } else if (it.form === 'sick') {
            fields = '<div class="intent-field"><span>How long do you need?</span>'
                + '<div class="intent-choices">'
                + '<label><input type="radio" name="intent-sick-days" value="3" checked> A few days</label>'
                + '<label><input type="radio" name="intent-sick-days" value="7"> About a week</label>'
                + '<label><input type="radio" name="intent-sick-days" value="14"> Longer</label>'
                + '</div></div>';
        }
        b.innerHTML = '<div class="intent-form">'
            + '<div class="intent-form-head">'
            + '<button type="button" class="intent-back" data-intent-back>← Back</button>'
            + '<strong>' + escapeHtml(it.emoji + ' ' + it.label) + '</strong></div>'
            + '<p class="intent-form-blurb">' + escapeHtml(it.blurb) + '</p>'
            + fields
            + '<div class="intent-form-actions">'
            + '<button type="button" class="btn btn-ghost btn-small" data-intent-back>Cancel</button>'
            + '<button type="button" class="btn btn-primary btn-small" id="intent-confirm">Preview change</button>'
            + '</div></div>';
        b.querySelectorAll('[data-intent-back]').forEach(function (x) {
            x.onclick = renderList;
        });
        var confirmBtn = document.getElementById('intent-confirm');
        if (confirmBtn) confirmBtn.onclick = function () { confirmForm(it); };
    }

    function confirmForm(it) {
        var params = {};
        if (it.form === 'skip') {
            params.date = (document.getElementById('intent-skip-date') || {}).value;
        } else if (it.form === 'away') {
            params.start_date = (document.getElementById('intent-away-start') || {}).value;
            params.end_date = (document.getElementById('intent-away-end') || {}).value;
        } else if (it.form === 'sick') {
            var sel = document.querySelector('input[name=intent-sick-days]:checked');
            params.days = sel ? parseInt(sel.value, 10) : 3;
        }
        run(it.id, params);
    }

    function run(id, params) {
        close();
        if (window.runChangePlanAction) {
            window.runChangePlanAction('intent', { body: { intent: id, params: params } });
        } else if (window.ApiClient && window.ApiClient.showError) {
            window.ApiClient.showError('Adaptation UI unavailable — refresh and try again.');
        }
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            var o = overlay();
            if (o && !o.hidden) close();
        }
    });

    window.PlanIntentMenu = { open: open, close: close };
})();
