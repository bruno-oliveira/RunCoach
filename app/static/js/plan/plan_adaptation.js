/**
 * plan_adaptation.js — Adaptation banners, inline suggestions, recalibration.
 *
 * Depends on plan_core.js (escapeHtml, authHeaders, reloadPlanPage).
 */
(function () {
    'use strict';

    /* -------------------------------------------------------------- */
    /*  Adaptation banner                                              */
    /* -------------------------------------------------------------- */

    function showAdaptationBanner(reason) {
        var banner = document.getElementById('adaptation-banner');
        var reasonText = document.getElementById('adaptation-reason');

        if (reasonText) reasonText.textContent = reason || 'Based on your synced runs, we recommend adjusting your plan.';
        if (banner && banner.style) {
            banner.style.display = 'block';
            banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    function dismissAdaptationBanner() {
        var banner = document.getElementById('adaptation-banner');
        if (banner && banner.style) banner.style.display = 'none';
    }

    function viewAdaptationDetails() {
        var perfSection = document.querySelector('.plan-insights');
        if (perfSection) {
            perfSection.scrollIntoView({ behavior: 'smooth' });
        }
        dismissAdaptationBanner();
    }

    /* -------------------------------------------------------------- */
    /*  In-plan adaptive suggestions (Phase 3)                         */
    /* -------------------------------------------------------------- */

    var suggestionsLoaded = false;

    window.loadSuggestions = function () {
        if (suggestionsLoaded) return;
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) {
            console.log('[suggestions] No plan_id in APP_CTX');
            return;
        }

        fetch('/api/plan/' + planId + '/suggestions', {
            headers: window.authHeaders(),
            credentials: 'same-origin'
        })
        .then(function (res) {
            if (!res.ok) {
                console.warn('[suggestions] HTTP ' + res.status);
                return { suggestions: [] };
            }
            return res.json();
        })
        .then(function (data) {
            suggestionsLoaded = true;
            if (!data.suggestions || data.suggestions.length === 0) {
                console.log('[suggestions] No suggestions returned (need more run data)');
                return;
            }
            console.log('[suggestions] Rendering ' + data.suggestions.length + ' week(s) of suggestions');
            renderSuggestionCards(data.suggestions);
        })
        .catch(function (err) {
            console.error('[suggestions] Fetch error:', err);
        });
    };

    function renderSuggestionCards(suggestions) {
        suggestions.forEach(function (weekSuggestion) {
            var weekNum = weekSuggestion.week;
            var weekCard = document.querySelector('[data-week="' + weekNum + '"]');
            if (!weekCard) {
                console.warn('[suggestions] Week card not found for week ' + weekNum);
                return;
            }

            var container = document.createElement('div');
            container.className = 'suggestion-cards';

            weekSuggestion.suggestions.forEach(function (s) {
                var card = document.createElement('div');
                card.className = 'suggestion-card suggestion-card--' + s.type;

                var html = '<div class="suggestion-message">' + window.escapeHtml(s.message) + '</div>';

                if (s.action === 'accept') {
                    html += '<div class="suggestion-actions">';
                    html += '<button class="btn btn-small btn-primary" onclick="acceptSuggestion(\'' + weekNum + '\', \'' + s.type + '\', this)">Accept</button>';
                    html += '<button class="btn btn-small btn-ghost" onclick="skipSuggestion(this)">Skip</button>';
                    html += '</div>';
                } else if (s.action === 'reduce') {
                    html += '<div class="suggestion-actions">';
                    html += '<button class="btn btn-small btn-primary" onclick="reduceWeek(' + weekNum + ')">Reduce 30%</button>';
                    html += '<button class="btn btn-small btn-ghost" onclick="skipSuggestion(this)">Skip</button>';
                    html += '</div>';
                }

                card.innerHTML = html;
                container.appendChild(card);
            });

            var weekHeader = weekCard.querySelector('.week-header, .week-card-header');
            if (weekHeader) {
                weekHeader.after(container);
            } else {
                weekCard.prepend(container);
            }
        });
    }

    window.acceptSuggestion = function (weekNum, suggestionType, btn) {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        var actionMap = {
            'exceeding': 'bump',
            'deficit': 'ease_deficit',
            'long_run': 'extend_long_run'
        };
        var action = actionMap[suggestionType];
        if (!action) return;

        if (btn) { btn.disabled = true; btn.textContent = 'Applying...'; }

        fetch('/api/plan/' + planId + '/week/' + weekNum + '/override', {
            method: 'POST',
            headers: window.authHeaders({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({ action: action })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.ok) {
                ApiClient.showSuccess('Suggestion applied. Reloading...');
                setTimeout(function () { window.reloadPlanPage(); }, 1200);
            } else {
                ApiClient.showError(data.detail || 'Failed to apply suggestion.');
                if (btn) { btn.disabled = false; btn.textContent = 'Accept'; }
            }
        })
        .catch(function (err) {
            ApiClient.showError('Error: ' + err.message);
            if (btn) { btn.disabled = false; btn.textContent = 'Accept'; }
        });
    };

    window.reduceWeek = function (weekNum) {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        fetch('/api/plan/' + planId + '/week/' + weekNum + '/override', {
            method: 'POST',
            headers: window.authHeaders({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({ action: 'reduce_30' })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.ok) {
                ApiClient.showSuccess('Week reduced by 30%. Reloading...');
                setTimeout(function () { window.reloadPlanPage(); }, 1200);
            }
        })
        .catch(function (err) {
            ApiClient.showError('Error: ' + err.message);
        });
    };

    window.resetWeek = function (weekNum) {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        fetch('/api/plan/' + planId + '/week/' + weekNum + '/override', {
            method: 'POST',
            headers: window.authHeaders({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({ action: 'reset_week' })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.ok) {
                ApiClient.showSuccess('Week reset to original distances. Reloading...');
                setTimeout(function () { window.reloadPlanPage(); }, 1200);
            } else {
                ApiClient.showError(data.detail || 'Failed to reset week.');
            }
        })
        .catch(function (err) {
            ApiClient.showError('Error: ' + err.message);
        });
    };

    /* -------------------------------------------------------------- */
    /*  Proactive adaptation alerts (Phase 4)                          */
    /* -------------------------------------------------------------- */

    window.showRecalibrateModal = function () {
        var modal = document.getElementById('recalibrate-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.dismissAdaptationAlert = function () {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        fetch('/api/plan/' + planId + '/dismiss-alert', {
            method: 'POST',
            headers: window.authHeaders(),
            credentials: 'same-origin'
        })
        .then(function (res) { return res.json(); })
        .then(function () {
            var banner = document.getElementById('adaptation-alert-banner');
            if (banner) {
                banner.style.opacity = '0';
                banner.style.transition = 'opacity 0.3s ease';
                setTimeout(function () { banner.remove(); }, 300);
            }
        })
        .catch(function (err) {
            console.error('[alert] dismiss failed:', err);
        });
    };

    window.recalibratePlan = function (strategy) {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        fetch('/api/plan/' + planId + '/recalibrate', {
            method: 'POST',
            headers: window.authHeaders({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({ strategy: strategy })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            var modal = document.getElementById('recalibrate-modal');
            if (modal) modal.style.display = 'none';

            if (data.ok) {
                ApiClient.showSuccess(data.reason || 'Plan recalibrated.');
                setTimeout(function () { window.reloadPlanPage(); }, 1500);
            } else {
                ApiClient.showError(data.error || 'Recalibration failed.');
            }
        })
        .catch(function (err) {
            ApiClient.showError('Error: ' + err.message);
        });
    };

    function initAdaptationAlert() {
        var alertText = document.getElementById('adaptation-alert-text');
        var alertDetail = document.getElementById('recalibrate-alert-detail');
        if (!alertText) return;

        try {
            var alertData = window.APP_CTX && window.APP_CTX.adaptation_alert;
            if (alertData) {
                alertText.textContent = alertData.message || 'Your plan needs attention.';
                if (alertDetail) alertDetail.textContent = alertData.message || '';

                // For fatigue alerts, highlight the recovery insertion option
                if (alertData.type === 'fatigue_high' && alertData.suggestion === 'recovery_insertion') {
                    var recoveryBtn = document.querySelector('[onclick*="recovery_insertion"]');
                    if (recoveryBtn) {
                        recoveryBtn.classList.add('recalibrate-option--recommended');
                        var badge = document.createElement('span');
                        badge.className = 'recommended-badge';
                        badge.textContent = 'Recommended';
                        recoveryBtn.prepend(badge);
                    }
                }
            }
        } catch (e) {
            alertText.textContent = 'Your plan may need adjustment.';
        }
    }

    window.skipSuggestion = function (btn) {
        var card = btn.closest('.suggestion-card');
        if (card) {
            card.style.opacity = '0';
            card.style.transition = 'opacity 0.3s ease';
            setTimeout(function () { card.remove(); }, 300);
        }
    };

    /* -------------------------------------------------------------- */
    /*  Pending adaptation recommendations (auto-triggered)            */
    /* -------------------------------------------------------------- */

    window.acceptRecommendation = function () {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        var btn = document.querySelector('#pending-recommendation-banner .btn-primary');
        if (btn) { btn.disabled = true; btn.textContent = 'Applying…'; }

        fetch('/api/plan/' + planId + '/accept-recommendation', {
            method: 'POST',
            headers: window.authHeaders ? window.authHeaders() : { 'Content-Type': 'application/json' },
            credentials: 'same-origin'
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.accepted || data.adjusted) {
                if (typeof ApiClient !== 'undefined' && ApiClient.showSuccess) {
                    ApiClient.showSuccess(data.reason || 'Recommendation applied.');
                }
                setTimeout(function () { window.location.reload(); }, 1200);
            } else {
                if (typeof ApiClient !== 'undefined' && ApiClient.showInfo) {
                    ApiClient.showInfo(data.reason || 'No changes needed.');
                }
                _removeRecommendationBanner();
            }
        })
        .catch(function (err) {
            if (typeof ApiClient !== 'undefined' && ApiClient.showError) {
                ApiClient.showError('Error: ' + err.message);
            }
            if (btn) { btn.disabled = false; btn.textContent = 'Accept'; }
        });
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
        .then(function () { _removeRecommendationBanner(); })
        .catch(function (err) {
            console.error('[recommendation] dismiss failed:', err);
        });
    };

    function _removeRecommendationBanner() {
        var banner = document.getElementById('pending-recommendation-banner');
        if (banner) {
            banner.style.opacity = '0';
            banner.style.transition = 'opacity 0.3s ease';
            setTimeout(function () { banner.remove(); }, 300);
        }
    }

    function initPendingRecommendation() {
        var rec = window.APP_CTX && window.APP_CTX.pending_recommendation;
        if (!rec) return;
        var textEl = document.getElementById('recommendation-reason-text');
        if (textEl) {
            textEl.textContent = rec.reason || 'We have a training adjustment recommendation for you.';
        }
    }

    /* -------------------------------------------------------------- */
    /*  Expose init helpers for plan_core.js DOMContentLoaded          */
    /* -------------------------------------------------------------- */

    window.showAdaptationBanner = showAdaptationBanner;
    window.dismissAdaptationBanner = dismissAdaptationBanner;
    window.viewAdaptationDetails = viewAdaptationDetails;
    window._initAdaptationAlert = initAdaptationAlert;
    window._initPendingRecommendation = initPendingRecommendation;
})();
