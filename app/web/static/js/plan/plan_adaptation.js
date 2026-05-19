/**
 * plan_adaptation.js — single unified adaptation card + recalibration.
 *
 * Depends on plan_core.js (authHeaders, escapeHtml, runChangePlanAction).
 * Depends on plan_dom_sync.js for in-place DOM patches.
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

    /* -------------------------------------------------------------- */
    /*  Pending recommendation — accept / dismiss                      */
    /* -------------------------------------------------------------- */

    window.acceptRecommendation = function () {
        var btn = document.querySelector('#plan-adaptation-card .btn-primary');
        if (window.runChangePlanAction) {
            return window.runChangePlanAction('accept_recommendation', { button: btn });
        }
        _toastError('Change-plan UI unavailable.');
    };

    window.dismissRecommendation = function () {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        fetch('/api/plan/' + planId + '/dismiss-recommendation', {
            method: 'POST',
            headers: window.authHeaders ? window.authHeaders() : { 'Content-Type': 'application/json' },
            credentials: 'same-origin'
        })
        .then(function (res) { return res.json(); })
        .then(function () {
            if (window.planDomSync) {
                window.planDomSync.applyAdaptationState({ kind: 'none' });
            }
        })
        .catch(function (err) {
            console.error('[recommendation] dismiss failed:', err);
        });
    };

    /* -------------------------------------------------------------- */
    /*  Adaptation alert — dismiss                                     */
    /* -------------------------------------------------------------- */

    window.dismissAdaptationAlert = function () {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        fetch('/api/plan/' + planId + '/dismiss-alert', {
            method: 'POST',
            headers: window.authHeaders ? window.authHeaders() : { 'Content-Type': 'application/json' },
            credentials: 'same-origin'
        })
        .then(function (res) { return res.json(); })
        .then(function () {
            if (window.planDomSync) {
                window.planDomSync.applyAdaptationState({ kind: 'none' });
            }
        })
        .catch(function (err) {
            console.error('[alert] dismiss failed:', err);
        });
    };

    /* -------------------------------------------------------------- */
    /*  Per-week reset (called from the week card header)              */
    /* -------------------------------------------------------------- */

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

    /* -------------------------------------------------------------- */
    /*  Recalibrate — user-initiated, not part of the banner stack     */
    /* -------------------------------------------------------------- */

    window.showRecalibrateModal = function () {
        var modal = document.getElementById('recalibrate-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.recalibratePlan = function (strategy) {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        fetch('/api/plan/' + planId + '/recalibrate', {
            method: 'POST',
            headers: window.authHeaders ? window.authHeaders({ 'Content-Type': 'application/json' }) : { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ strategy: strategy })
        })
        .then(_parseResponse)
        .then(function (r) {
            var payload = r.payload || {};
            var modal = document.getElementById('recalibrate-modal');
            if (!r.ok) {
                _toastError(payload.detail || ('Request failed: ' + r.status));
                return;
            }
            if (payload.ok) {
                if (modal) modal.style.display = 'none';
                _toastSuccess(payload.reason || 'Plan recalibrated.');
                // Recalibrate is a heavier mutation that may rewrite many
                // weeks — fall back to reload here since we don't get a
                // patch payload back.
                if (typeof window.reloadPlanPage === 'function') {
                    window.reloadPlanPage();
                }
                return;
            }
            _toastError(payload.error || payload.detail || 'Recalibration failed.');
        })
        .catch(function (err) {
            console.error('[recalibratePlan] network error', err);
            _toastError('Error: ' + err.message);
        });
    };
})();
