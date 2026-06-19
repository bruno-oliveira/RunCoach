/**
 * plan_proactive_nudge.js — proactive, suggest-only adaptation banner.
 *
 * On plan load, asks the server whether the runner's logged data warrants a
 * proactive suggestion (currently: a fitness-jump bump). If so, renders a
 * single clearly-flagged banner. "Review" opens the *existing* preview → apply
 * change-plan modal for the suggested intent (feeling_strong) via
 * window.runChangePlanAction — the plan never changes without the user's
 * confirmation. "Dismiss" tells the server to keep quiet until the situation
 * materially changes.
 *
 * Depends on plan_change_summary.js (runChangePlanAction).
 */
(function () {
    'use strict';

    function planId() {
        return window.APP_CTX && window.APP_CTX.plan_id;
    }

    function authHeaders() {
        var token = (window.AuthClient && window.AuthClient.getToken
            && window.AuthClient.getToken()) || '';
        var headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = 'Bearer ' + token;
        return headers;
    }

    function escapeHtml(str) {
        if (str == null) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(String(str)));
        return div.innerHTML;
    }

    function dismiss(signature) {
        var id = planId();
        if (!id) return;
        fetch('/api/plan/' + id + '/proactive-nudge/dismiss', {
            method: 'POST',
            headers: authHeaders(),
            credentials: 'same-origin',
            body: JSON.stringify({ signature: signature || null })
        }).catch(function () { /* best-effort */ });
    }

    function render(host, nudge) {
        var tone = nudge.tone === 'caution' ? 'caution' : 'positive';
        host.innerHTML =
            '<div class="proactive-nudge is-' + tone + '" role="status">'
            + '<span class="proactive-nudge-flag">RunCoach noticed</span>'
            + '<div class="proactive-nudge-body">'
            + '<strong class="proactive-nudge-headline">'
            + escapeHtml(nudge.headline) + '</strong>'
            + '<p class="proactive-nudge-detail">'
            + escapeHtml(nudge.detail) + '</p>'
            + '</div>'
            + '<div class="proactive-nudge-actions">'
            + '<button type="button" class="btn btn-small proactive-nudge-review">'
            + escapeHtml(nudge.cta || 'Review') + '</button>'
            + '<button type="button" class="btn btn-ghost btn-small proactive-nudge-dismiss">'
            + 'Not now</button>'
            + '</div>'
            + '</div>';
        host.hidden = false;

        var reviewBtn = host.querySelector('.proactive-nudge-review');
        var dismissBtn = host.querySelector('.proactive-nudge-dismiss');

        if (reviewBtn) {
            reviewBtn.addEventListener('click', function () {
                if (typeof window.runChangePlanAction !== 'function') {
                    console.warn('[proactive_nudge] change-plan modal unavailable');
                    return;
                }
                // Reuse the same preview → apply flow every intent uses. The
                // user reviews the diff and confirms; applying reloads the page.
                window.runChangePlanAction('intent', {
                    body: { intent: nudge.intent, params: {} },
                    button: reviewBtn
                });
            });
        }

        if (dismissBtn) {
            dismissBtn.addEventListener('click', function () {
                dismiss(nudge.signature);
                host.hidden = true;
                host.innerHTML = '';
            });
        }
    }

    function load() {
        var host = document.getElementById('proactive-nudge-host');
        var id = planId();
        if (!host || !id) return;

        fetch('/api/plan/' + id + '/proactive-nudge', {
            method: 'GET',
            headers: authHeaders(),
            credentials: 'same-origin'
        })
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (data) {
                if (data && data.available && data.nudge) {
                    render(host, data.nudge);
                }
            })
            .catch(function () { /* best-effort; banner just stays hidden */ });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', load);
    } else {
        load();
    }
})();
