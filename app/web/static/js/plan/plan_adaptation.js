/**
 * plan_adaptation.js — per-week reset wired from the week card header.
 *
 * The old recommendation/alert/recalibrate surfaces have been replaced by the
 * "Adjust my plan" intent menu (plan_intent_menu.js). Per-week reset stays:
 * it reverts a single manually-adjusted week to its baseline distances.
 *
 * Depends on plan_core.js (authHeaders) and plan_dom_sync.js.
 */
(function () {
    'use strict';

    function _parseResponse(res) {
        return res.json().catch(function () { return {}; })
            .then(function (payload) {
                return { ok: res.ok, status: res.status, payload: payload };
            });
    }

    function _toastError(message) {
        if (typeof ApiClient !== 'undefined' && ApiClient.showError) {
            ApiClient.showError(message);
        }
    }

    function _toastSuccess(message) {
        if (typeof ApiClient !== 'undefined' && ApiClient.showSuccess) {
            ApiClient.showSuccess(message);
        }
    }

    window.resetWeek = function (weekNum) {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        var headers = window.authHeaders
            ? window.authHeaders({ 'Content-Type': 'application/json' })
            : { 'Content-Type': 'application/json' };
        if (window.APP_CTX && typeof window.APP_CTX.adaptation_revision === 'number') {
            headers['If-Match'] = String(window.APP_CTX.adaptation_revision);
        }
        fetch('/api/plan/' + planId + '/week/' + weekNum + '/override', {
            method: 'POST',
            headers: headers,
            credentials: 'same-origin',
            body: JSON.stringify({ action: 'reset_week' })
        })
        .then(_parseResponse)
        .then(function (r) {
            var payload = r.payload || {};
            if (!r.ok) {
                _toastError(payload.detail || ('Request failed: ' + r.status));
                return;
            }
            if (payload.ok) {
                _toastSuccess('Week reset to original distances.');
                if (window.planDomSync) {
                    window.planDomSync.applyPatch({
                        adaptation_revision: payload.adaptation_revision,
                        week_totals: payload.week_totals,
                        workout_changes: payload.workout_changes,
                    });
                }
                return;
            }
            _toastError(payload.detail || 'Failed to reset week.');
        })
        .catch(function (err) {
            console.error('[resetWeek] network error', err);
            _toastError('Error: ' + err.message);
        });
    };
})();
