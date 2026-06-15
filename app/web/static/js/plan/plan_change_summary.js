/**
 * plan_change_summary.js — Renders ChangePlan payloads in the
 * shared modal and wires preview → apply flow for every adaptation
 * action that mutates plan distances.
 *
 * Public entry points exposed on `window`:
 *   - runChangePlanAction(action, options)
 *       Initiates the preview → apply flow for a given action.
 *       action ∈ "adjust" | "accept_recommendation" | "reset" | "auto_adjust"
 *       options.planId is optional (defaults to window.APP_CTX.plan_id).
 *       options.skipPreview=true bypasses preview and applies immediately
 *         (used internally for actions without a preview endpoint).
 *       options.button is an optional button element to restore on cancel.
 *       Returns a promise.
 *   - openChangePlanModalForApplied(changePlan)
 *       Used on page-init to show the modal for an unseen auto-adjust.
 */
(function () {
    'use strict';

    var ACTION_TITLES = {
        adjust: 'Adjust plan',
        accept_recommendation: 'Apply recommendation',
        reset: 'Reset to original',
        auto_adjust: 'RunCoach auto-adjustment',
        // Intent actions — the change_plan returns the intent name as its action.
        feeling_tired: 'Feeling tired',
        feeling_strong: 'Feeling strong',
        skip_run: 'Skip a run',
        away: 'Away / travelling',
        sick_injured: 'Sick or injured',
        busy_week: 'Busy week',
    };

    var ENDPOINTS = {
        adjust: {
            preview: '/api/plan/{id}/adjust/preview',
            apply: '/api/plan/{id}/adjust',
        },
        accept_recommendation: {
            preview: '/api/plan/{id}/accept-recommendation/preview',
            apply: '/api/plan/{id}/accept-recommendation',
        },
        reset: {
            preview: '/api/plan/{id}/reset-adjustment/preview',
            apply: '/api/plan/{id}/reset-adjustment',
        },
        // Single endpoint pair for every life-event intent; the chosen
        // intent + params travel in the request body.
        intent: {
            preview: '/api/plan/{id}/intent/preview',
            apply: '/api/plan/{id}/intent',
        },
    };

    function authHeaders() {
        var token = (window.AuthClient && window.AuthClient.getToken && window.AuthClient.getToken()) || '';
        var headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = 'Bearer ' + token;
        return headers;
    }

    function getPlanId(options) {
        if (options && options.planId) return options.planId;
        return window.APP_CTX && window.APP_CTX.plan_id;
    }

    function escapeHtml(str) {
        if (str == null) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(String(str)));
        return div.innerHTML;
    }

    function formatKm(value) {
        if (value === null || value === undefined) return '—';
        var num = Number(value);
        if (!isFinite(num)) return '—';
        if (num <= 0) return '0.0 km';
        // Truncate to one decimal (no rounding) to match the server-side
        // format_km() so a workout never displays more distance than prescribed.
        return (Math.floor(num * 10) / 10).toFixed(1) + ' km';
    }

    function formatDelta(value) {
        if (value === null || value === undefined) return '0';
        var num = Number(value);
        if (!isFinite(num) || num === 0) return '0';
        var sign = num > 0 ? '+' : '';
        return sign + num.toFixed(1);
    }

    function formatPercent(value) {
        if (value === null || value === undefined) return '—';
        return Math.round(Number(value) * 100) + '%';
    }

    function renderSignals(signals) {
        if (!signals) return '';
        var entries = [];
        if (signals.runs_analyzed != null) {
            entries.push(['Runs analysed', String(signals.runs_analyzed)]);
        }
        if (signals.phase) entries.push(['Phase', signals.phase]);
        if (signals.effort_trend) entries.push(['Effort trend', signals.effort_trend]);
        if (signals.completion_rate != null) entries.push(['Completion', formatPercent(signals.completion_rate)]);
        if (signals.volume_ratio != null) entries.push(['Volume vs plan', formatPercent(signals.volume_ratio)]);
        if (signals.avg_effort != null) entries.push(['Avg effort', Number(signals.avg_effort).toFixed(1) + '/10']);
        if (signals.tsb_form) entries.push(['TSB form', signals.tsb_form]);
        if (signals.overreach_detected) entries.push(['Overreach', 'detected']);
        if (signals.confidence) entries.push(['Confidence', signals.confidence]);
        if (!entries.length) return '';
        var html = '<div class="cp-signals">';
        entries.forEach(function (e) {
            html += '<div><span class="cp-signal-key">' + escapeHtml(e[0]) + ':</span><span class="cp-signal-value">' + escapeHtml(e[1]) + '</span></div>';
        });
        html += '</div>';
        return html;
    }

    function statusClass(workout) {
        if (workout.status === 'changed') {
            return 'cp-status-changed' + (workout.delta_km < 0 ? ' is-down' : '');
        }
        if (workout.status === 'protected') return 'cp-status-protected';
        return 'cp-status-unchanged';
    }

    function statusLabel(workout) {
        if (workout.status === 'changed') return workout.delta_km < 0 ? 'Reduced' : 'Increased';
        if (workout.status === 'protected') return 'Protected';
        if (workout.status === 'past') return 'Past';
        return 'Unchanged';
    }

    function renderWorkoutRow(workout) {
        var showDistances = workout.status === 'changed' || workout.old_distance_km !== workout.new_distance_km;
        var distanceHtml;
        if (showDistances && workout.status === 'changed') {
            distanceHtml = formatKm(workout.old_distance_km) + ' → <strong>' + formatKm(workout.new_distance_km) + '</strong>';
        } else {
            distanceHtml = formatKm(workout.new_distance_km);
        }
        var reasonHtml = workout.reason
            ? '<div class="cp-workout-reason">' + escapeHtml(workout.reason) + '</div>'
            : '';
        return '<li class="cp-workout-row">'
            + '<span class="cp-workout-day">' + escapeHtml(workout.day) + '</span>'
            + '<span class="cp-workout-type">' + escapeHtml(workout.type || 'easy') + '</span>'
            + '<span class="cp-workout-distances">' + distanceHtml + '</span>'
            + '<span class="cp-workout-status ' + statusClass(workout) + '">' + statusLabel(workout) + '</span>'
            + reasonHtml
            + '</li>';
    }

    function renderWeek(week) {
        var delta = (week.total_km_after || 0) - (week.total_km_before || 0);
        var deltaClass = delta > 0.05 ? 'is-up' : delta < -0.05 ? 'is-down' : '';
        var deltaText = delta === 0 ? 'no change' : formatDelta(delta) + ' km';
        var workoutsHtml = week.workouts.map(renderWorkoutRow).join('');
        var openAttr = week.workouts.some(function (w) { return w.status === 'changed'; }) ? ' open' : '';
        return '<details class="cp-week"' + openAttr + '>'
            + '<summary>'
            + '<span class="cp-week-week">Week ' + escapeHtml(week.week) + ' · '
            + escapeHtml(formatKm(week.total_km_before)) + ' → '
            + escapeHtml(formatKm(week.total_km_after)) + '</span>'
            + '<span class="cp-week-delta ' + deltaClass + '">' + escapeHtml(deltaText) + '</span>'
            + '</summary>'
            + '<ul class="cp-workout-list">' + workoutsHtml + '</ul>'
            + '</details>';
    }

    // Belt-and-suspenders normalisation: a stored ChangePlan written
    // before the server-side display-precision fix may still tag rows
    // as 'changed' when the rounded km values are identical, or carry
    // weeks where every workout is protected/unchanged. Strip both so
    // the UI never advertises an "Increased"/"Reduced" label that the
    // user can't actually see in the numbers.
    function normalizeChangePlan(cp) {
        if (!cp || !cp.weeks) return cp;
        var changedCount = 0;
        var protectedCount = 0;
        var visibleWeeks = [];
        cp.weeks.forEach(function (week) {
            (week.workouts || []).forEach(function (wo) {
                if (wo.status === 'changed' && wo.old_distance_km === wo.new_distance_km) {
                    wo.status = 'unchanged';
                    wo.delta_km = 0;
                }
                if (wo.status === 'changed') changedCount++;
                else if (wo.status === 'protected') protectedCount++;
            });
            var hasChange = (week.workouts || []).some(function (wo) {
                return wo.status === 'changed';
            });
            if (hasChange) visibleWeeks.push(week);
        });
        cp.weeks = visibleWeeks;
        if (cp.summary) {
            cp.summary.workouts_changed_count = changedCount;
            cp.summary.workouts_protected_count = protectedCount;
            cp.summary.weeks_affected = visibleWeeks.map(function (w) { return w.week; });
        }
        return cp;
    }

    function renderChangePlanBody(cp) {
        normalizeChangePlan(cp);
        var summary = cp.summary || {};
        var anyChange = summary.workouts_changed_count > 0 || (cp.summary && cp.summary.vdot_change);

        // Outcome chip
        var outcomeChip;
        if (cp.mode === 'preview') {
            outcomeChip = anyChange
                ? '<span class="cp-outcome-chip is-preview">Preview · would change</span>'
                : '<span class="cp-outcome-chip is-nochange">Preview · no change needed</span>';
        } else {
            outcomeChip = anyChange
                ? '<span class="cp-outcome-chip is-applied">Applied</span>'
                : '<span class="cp-outcome-chip is-nochange">No change made</span>';
        }
        var actionTitle = ACTION_TITLES[cp.action] || 'Plan change';
        var outcomeRow = '<div class="cp-outcome-row">' + outcomeChip
            + '<span class="cp-action-label">' + escapeHtml(actionTitle) + '</span></div>';

        // Stat cards
        var multiplierVal = summary.multiplier != null
            ? '×' + Number(summary.multiplier).toFixed(2)
            : '—';
        var deltaVal = summary.total_km_delta != null
            ? formatDelta(summary.total_km_delta) + ' km'
            : '—';
        var deltaClass = summary.total_km_delta > 0 ? 'is-up' : summary.total_km_delta < 0 ? 'is-down' : 'is-neutral';
        var stats = '<div class="cp-stats">'
            + '<div class="cp-stat"><span class="cp-stat-label">Workouts changed</span>'
            + '<span class="cp-stat-value">' + escapeHtml(String(summary.workouts_changed_count || 0)) + '</span>'
            + '<span class="cp-stat-sub">across ' + (summary.weeks_affected ? summary.weeks_affected.length : 0) + ' week(s)</span></div>'
            + '<div class="cp-stat"><span class="cp-stat-label">Protected</span>'
            + '<span class="cp-stat-value">' + escapeHtml(String(summary.workouts_protected_count || 0)) + '</span>'
            + '<span class="cp-stat-sub">key/tempo/intervals</span></div>'
            + '<div class="cp-stat"><span class="cp-stat-label">Total km delta</span>'
            + '<span class="cp-stat-value ' + deltaClass + '">' + escapeHtml(deltaVal) + '</span>'
            + '<span class="cp-stat-sub">' + escapeHtml(formatKm(summary.total_km_before)) + ' → ' + escapeHtml(formatKm(summary.total_km_after)) + '</span></div>'
            + '<div class="cp-stat"><span class="cp-stat-label">Multiplier</span>'
            + '<span class="cp-stat-value">' + escapeHtml(multiplierVal) + '</span>'
            + (summary.vdot_change
                ? '<span class="cp-stat-sub">VDOT ' + escapeHtml(summary.vdot_change.before) + ' → ' + escapeHtml(summary.vdot_change.after) + '</span>'
                : '')
            + '</div>'
            + '</div>';

        // Reason
        var reasonBlock = '';
        if (cp.reason) {
            reasonBlock += '<div class="cp-reason-block">' + escapeHtml(cp.reason) + '</div>';
        }
        if (cp.no_change_reasons && cp.no_change_reasons.length) {
            reasonBlock += '<div class="cp-reason-block is-warning"><strong>Why no change?</strong>'
                + '<ul class="cp-no-change-list">'
                + cp.no_change_reasons.map(function (r) {
                    return '<li>' + escapeHtml(r) + '</li>';
                }).join('')
                + '</ul></div>';
        }

        // Weeks
        var weeksHtml = '';
        if (cp.weeks && cp.weeks.length) {
            weeksHtml = '<div class="cp-weeks">' + cp.weeks.map(renderWeek).join('') + '</div>';
        }

        var signalsHtml = renderSignals(cp.signals);

        return outcomeRow + stats + reasonBlock + weeksHtml + signalsHtml;
    }

    function ensureModal() {
        var overlay = document.getElementById('change-plan-modal-overlay');
        if (!overlay) {
            console.warn('[change_summary] modal overlay not found in DOM');
        }
        return overlay;
    }

    function setBusy(modal, busy) {
        if (!modal) return;
        modal.classList.toggle('is-loading', !!busy);
        var apply = modal.querySelector('[data-change-plan-apply]');
        var cancel = modal.querySelector('[data-change-plan-cancel]');
        if (apply) apply.disabled = !!busy;
        if (cancel) cancel.disabled = !!busy;
    }

    function openModal(overlay) {
        overlay.hidden = false;
        overlay.classList.add('active');
        overlay.classList.add('is-open');
        document.body.style.overflow = 'hidden';
    }

    function closeModal(overlay) {
        overlay.hidden = true;
        overlay.classList.remove('active');
        overlay.classList.remove('is-open');
        document.body.style.overflow = '';
    }

    function renderInto(overlay, changePlan) {
        var host = overlay.querySelector('#change-plan-summary-host');
        if (host) host.innerHTML = renderChangePlanBody(changePlan);
        var title = overlay.querySelector('#change-plan-modal-title');
        if (title) title.textContent = ACTION_TITLES[changePlan.action] || 'Plan changes';
    }

    function configureFooter(overlay, opts) {
        var apply = overlay.querySelector('[data-change-plan-apply]');
        var cancel = overlay.querySelector('[data-change-plan-cancel]');
        var close = overlay.querySelector('.modal-footer [data-change-plan-close]');
        if (apply) apply.hidden = !opts.showApply;
        if (cancel) cancel.hidden = !opts.showCancel;
        if (close) close.hidden = !opts.showClose;
    }

    function postJson(url, opts) {
        opts = opts || {};
        var headers = authHeaders();
        // Attach the page's current revision so the server can reject
        // stale writes (409) when another tab / a Strava sync has moved
        // the plan forward.
        if (opts.sendRevision !== false && window.APP_CTX
                && typeof window.APP_CTX.adaptation_revision === 'number') {
            headers['If-Match'] = String(window.APP_CTX.adaptation_revision);
        }
        var fetchOpts = {
            method: 'POST',
            headers: headers,
            credentials: 'same-origin',
        };
        if (opts.body !== undefined) {
            fetchOpts.body = JSON.stringify(opts.body);
        }
        return fetch(url, fetchOpts).then(function (res) {
            return res.json().then(function (body) {
                if (!res.ok) {
                    if (res.status === 409) {
                        var err409 = new Error(
                            (body && body.detail && body.detail.message)
                                || 'Plan was updated elsewhere — refresh to continue.'
                        );
                        err409.body = body;
                        err409.status = 409;
                        throw err409;
                    }
                    var err = new Error(body && body.detail ? body.detail : 'Request failed');
                    err.body = body;
                    err.status = res.status;
                    throw err;
                }
                return body;
            });
        });
    }

    function unwrapChangePlan(result) {
        if (!result) return null;
        if (result.change_plan) return result.change_plan;
        if (result.action && result.summary) return result; // preview endpoint returns the plan directly
        return null;
    }

    function showError(message) {
        if (window.ApiClient && window.ApiClient.showError) {
            window.ApiClient.showError(message);
        } else {
            console.error(message);
        }
    }

    function showSuccess(message) {
        if (window.ApiClient && window.ApiClient.showSuccess) {
            window.ApiClient.showSuccess(message);
        }
    }

    function markSeen(planId) {
        return postJson('/api/plan/' + planId + '/change-plan/mark-seen').catch(function () {
            // best-effort; ignore errors
        });
    }

    function reloadPlanPage(planId) {
        if (planId) {
            window.location.href = '/plan/' + planId;
        } else {
            window.location.reload();
        }
    }

    /**
     * Public entry point. Runs preview → apply for the given action.
     */
    function runChangePlanAction(action, options) {
        options = options || {};
        var planId = getPlanId(options);
        if (!planId) {
            showError('Plan id missing.');
            return Promise.resolve();
        }
        var endpoints = ENDPOINTS[action];
        if (!endpoints) {
            showError('Unknown action: ' + action);
            return Promise.resolve();
        }
        var overlay = ensureModal();
        if (!overlay) {
            showError('Change-plan modal not available — falling back.');
            return Promise.resolve();
        }

        var btn = options.button;
        var originalLabel = btn ? btn.textContent : null;
        if (btn) { btn.disabled = true; btn.textContent = 'Loading…'; }

        var previewUrl = endpoints.preview.replace('{id}', encodeURIComponent(planId));
        var applyUrl = endpoints.apply.replace('{id}', encodeURIComponent(planId));

        function resetButton() {
            if (btn && originalLabel != null) {
                btn.disabled = false;
                btn.textContent = originalLabel;
            }
        }

        return postJson(previewUrl, { body: options.body })
            .then(function (preview) {
                var cp = unwrapChangePlan(preview);
                if (!cp) {
                    showError('Preview returned no data.');
                    resetButton();
                    return;
                }
                openPreview(overlay, cp, action, applyUrl, planId, btn, originalLabel, options.body);
            })
            .catch(function (err) {
                showError(err.message || 'Preview failed.');
                resetButton();
            });
    }

    function openPreview(overlay, cp, action, applyUrl, planId, btn, originalLabel, applyBody) {
        renderInto(overlay, cp);
        var canApply = cp.would_change;
        configureFooter(overlay, {
            showApply: canApply,
            showCancel: canApply,
            showClose: !canApply,
        });
        openModal(overlay);

        var applyBtn = overlay.querySelector('[data-change-plan-apply]');
        var cancelBtn = overlay.querySelector('[data-change-plan-cancel]');
        var closeBtns = overlay.querySelectorAll('[data-change-plan-close]');

        function restoreButton() {
            if (btn && originalLabel != null) {
                btn.disabled = false;
                btn.textContent = originalLabel;
            }
        }

        function cleanup() {
            if (applyBtn) applyBtn.onclick = null;
            if (cancelBtn) cancelBtn.onclick = null;
            closeBtns.forEach(function (b) { b.onclick = null; });
            overlay.onclick = null;
        }

        function dismissPreview() {
            cleanup();
            closeModal(overlay);
            restoreButton();
        }

        if (cancelBtn) cancelBtn.onclick = dismissPreview;
        closeBtns.forEach(function (b) { b.onclick = dismissPreview; });
        overlay.onclick = function (event) {
            if (event.target === overlay) dismissPreview();
        };

        if (applyBtn) {
            applyBtn.onclick = function () {
                cleanup();
                setBusy(overlay, true);
                postJson(applyUrl, { body: applyBody })
                    .then(function (applied) {
                        var appliedCp = unwrapChangePlan(applied);
                        var changedCount = appliedCp
                            && appliedCp.summary
                            && appliedCp.summary.workouts_changed_count;
                        if (changedCount > 0) {
                            showSuccess('Plan updated.');
                        } else {
                            showSuccess('No changes needed.');
                        }
                        closeModal(overlay);
                        // Patch the page in place from the response so the
                        // user sees the new totals immediately. Reload only
                        // if patch is unavailable (older endpoint shapes), or
                        // for intents — those can change a workout's *type*
                        // (skip → rest, tempo → easy) which the in-place patch
                        // doesn't repaint, so a reload keeps the card honest.
                        var patch = appliedCp && appliedCp.patch;
                        if (action !== 'intent' && patch && window.planDomSync) {
                            window.planDomSync.applyPatch(patch);
                            markSeen(planId);
                        } else {
                            reloadPlanPage(planId);
                        }
                    })
                    .catch(function (err) {
                        showError(err.message || 'Apply failed.');
                        restoreButton();
                        closeModal(overlay);
                        setBusy(overlay, false);
                    });
            };
        }
    }

    function openChangePlanModalForApplied(changePlan) {
        var overlay = ensureModal();
        if (!overlay) return;
        renderInto(overlay, changePlan);
        configureFooter(overlay, {
            showApply: false,
            showCancel: false,
            showClose: true,
        });
        openModal(overlay);
        var planId = getPlanId();
        var closeBtn = overlay.querySelector('.modal-footer [data-change-plan-close]');
        var headerClose = overlay.querySelector('.modal-header [data-change-plan-close]');
        function onClose() {
            closeModal(overlay);
            if (planId) markSeen(planId);
        }
        if (closeBtn) closeBtn.onclick = onClose;
        if (headerClose) headerClose.onclick = onClose;
        overlay.onclick = function (event) {
            if (event.target === overlay) onClose();
        };
        // Allow Escape to close
        document.addEventListener('keydown', function escHandler(e) {
            if (e.key === 'Escape' && !overlay.hidden) {
                onClose();
                document.removeEventListener('keydown', escHandler);
            }
        });
    }

    // Auto-open unseen ChangePlan on page load.
    function bootstrap() {
        var data = window.LAST_CHANGE_PLAN;
        if (data && data.summary && data.seen === false) {
            // Normalize first so a stale plan with no visible changes
            // doesn't auto-pop an effectively empty modal.
            normalizeChangePlan(data);
            if (data.summary && data.summary.workouts_changed_count > 0) {
                openChangePlanModalForApplied(data);
            }
        }
        // Hook persistent panel "View details" link
        document.querySelectorAll('[data-change-plan-view]').forEach(function (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                if (window.LAST_CHANGE_PLAN) {
                    var clone = JSON.parse(JSON.stringify(window.LAST_CHANGE_PLAN));
                    clone.mode = 'applied';
                    openChangePlanModalForApplied(clone);
                }
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap);
    } else {
        bootstrap();
    }

    window.runChangePlanAction = runChangePlanAction;
    window.openChangePlanModalForApplied = openChangePlanModalForApplied;
})();
