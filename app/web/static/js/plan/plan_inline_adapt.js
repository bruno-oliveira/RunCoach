/**
 * plan_inline_adapt.js — the calm, in-place adaptation flow.
 *
 * Replaces the old preview → diff-modal → Apply dance. When the user declares
 * a life-event intent (feeling tired, away, skip, missed, feeling strong), the
 * plan reshapes *immediately*: the affected day cards morph in place and a
 * single quiet bar appears with the coach's one-line reason and an Undo.
 * No spreadsheet of per-day deltas, no Apply button — trust comes from the
 * change being instantly reversible, not from pre-approving a migration.
 *
 * Public API (window.PlanInlineAdapt):
 *   - applyIntent(intent, params, opts)  → runs an intent, patches, toasts
 *   - undo()                             → reverts the last applied change
 *
 * The read-only "See what changed" detail view reuses
 * plan_change_summary.js's openChangePlanModalForApplied().
 */
(function () {
    'use strict';

    var POST_RELOAD_KEY = 'runcoach_adapt_toast';

    function planId() {
        return window.APP_CTX && window.APP_CTX.plan_id;
    }

    function authHeaders() {
        var token = (window.AuthClient && window.AuthClient.getToken
            && window.AuthClient.getToken()) || '';
        var headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = 'Bearer ' + token;
        if (window.APP_CTX && typeof window.APP_CTX.adaptation_revision === 'number') {
            headers['If-Match'] = String(window.APP_CTX.adaptation_revision);
        }
        return headers;
    }

    function postJson(url, body) {
        var opts = { method: 'POST', headers: authHeaders(), credentials: 'same-origin' };
        if (body !== undefined) opts.body = JSON.stringify(body);
        return fetch(url, opts).then(function (res) {
            return res.json().then(function (payload) {
                if (!res.ok) {
                    var err = new Error(
                        (payload && payload.detail && payload.detail.message)
                        || (payload && payload.detail)
                        || 'Request failed'
                    );
                    err.status = res.status;
                    throw err;
                }
                return payload;
            });
        });
    }

    function showError(message) {
        if (window.ApiClient && window.ApiClient.showError) {
            window.ApiClient.showError(message);
        } else if (window.api && window.api.showError) {
            window.api.showError(message);
        } else {
            console.error(message);
        }
    }

    function markSeen(id) {
        return postJson('/api/plan/' + id + '/change-plan/mark-seen').catch(function () {});
    }

    function reload(id) {
        if (id) {
            window.location.href = '/plan/' + id;
        } else {
            window.location.reload();
        }
    }

    // -- the calm adaptation bar ------------------------------------------

    function toastHost() {
        var host = document.getElementById('adapt-toast-host');
        if (!host) {
            host = document.createElement('div');
            host.id = 'adapt-toast-host';
            host.className = 'adapt-toast-host';
            document.body.appendChild(host);
        }
        return host;
    }

    /**
     * Render the adaptation bar.
     *   opts.reason      — the coach's one-line summary (required)
     *   opts.changePlan  — the applied change_plan, for "See what changed"
     *   opts.showUndo    — offer an Undo button (default true)
     *   opts.tone        — 'default' | 'reverted'
     */
    function showToast(opts) {
        opts = opts || {};
        var host = toastHost();
        // Only one adaptation bar at a time — a newer action supersedes the old.
        host.innerHTML = '';

        var bar = document.createElement('div');
        bar.className = 'adapt-toast' + (opts.tone === 'reverted' ? ' is-reverted' : '');
        bar.setAttribute('role', 'status');
        bar.setAttribute('aria-live', 'polite');

        var msg = document.createElement('p');
        msg.className = 'adapt-toast-msg';
        msg.textContent = opts.reason || 'Your plan was updated.';
        bar.appendChild(msg);

        var actions = document.createElement('div');
        actions.className = 'adapt-toast-actions';

        if (opts.changePlan && window.openChangePlanModalForApplied) {
            var details = document.createElement('button');
            details.type = 'button';
            details.className = 'adapt-toast-link';
            details.textContent = 'See what changed';
            details.onclick = function () {
                var clone = JSON.parse(JSON.stringify(opts.changePlan));
                clone.mode = 'applied';
                window.openChangePlanModalForApplied(clone);
            };
            actions.appendChild(details);
        }

        if (opts.showUndo !== false) {
            var undoBtn = document.createElement('button');
            undoBtn.type = 'button';
            undoBtn.className = 'adapt-toast-undo';
            undoBtn.textContent = 'Undo';
            undoBtn.onclick = function () {
                undoBtn.disabled = true;
                dismiss();
                undo();
            };
            actions.appendChild(undoBtn);
        }

        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'adapt-toast-close';
        close.setAttribute('aria-label', 'Dismiss');
        close.innerHTML = '&times;';
        close.onclick = dismiss;
        actions.appendChild(close);

        bar.appendChild(actions);
        host.appendChild(bar);
        // Next frame → trigger the enter transition.
        requestAnimationFrame(function () { bar.classList.add('is-in'); });

        var timer = setTimeout(dismiss, opts.showUndo === false ? 5000 : 12000);

        function dismiss() {
            clearTimeout(timer);
            if (!bar.parentNode) return;
            bar.classList.remove('is-in');
            bar.classList.add('is-out');
            setTimeout(function () { if (bar.parentNode) bar.remove(); }, 260);
        }
    }

    // -- apply / undo ------------------------------------------------------

    function applyPatch(patch, changePlan, id) {
        if (patch && patch.reload_recommended) {
            // A day gained a workout (e.g. a rescheduled run) — its card has no
            // markup to morph, so re-render the page. Carry the bar across the
            // reload so the experience still reads as declare → done → undo.
            stashToast({
                reason: (changePlan && changePlan.reason) || 'Your plan was updated.',
                showUndo: true,
            });
            reload(id);
            return true;
        }
        if (window.planDomSync) {
            window.planDomSync.applyPatch(patch);
            highlight(patch);
        }
        return false;
    }

    function highlight(patch) {
        if (!patch || !Array.isArray(patch.workout_changes)) return;
        patch.workout_changes.forEach(function (c) {
            var item = document.querySelector(
                '.workout-item[data-week-num="' + c.week + '"][data-day-num="' + c.day + '"]'
            );
            if (!item) return;
            item.classList.remove('adapt-just-changed');
            // Force reflow so re-adding the class restarts the animation.
            void item.offsetWidth;
            item.classList.add('adapt-just-changed');
            setTimeout(function () { item.classList.remove('adapt-just-changed'); }, 1600);
        });
    }

    function applyIntent(intent, params, opts) {
        opts = opts || {};
        var id = opts.planId || planId();
        if (!id) { showError('Plan id missing.'); return Promise.resolve(); }
        // When invoked away from this plan's own page (e.g. the analytics
        // "Missed it?" chooser), there are no cards to morph — apply, then
        // carry the bar onto the plan page.
        var onThisPlanPage = planId() === id && !!document.querySelector('.workout-item');

        var btn = opts.button;
        var original = btn ? btn.textContent : null;
        if (btn) { btn.disabled = true; btn.textContent = 'Adjusting…'; }

        function restore() {
            if (btn && original != null) { btn.disabled = false; btn.textContent = original; }
        }

        return postJson('/api/plan/' + id + '/intent', { intent: intent, params: params || {} })
            .then(function (cp) {
                restore();
                if (!cp || !cp.summary) { showError('No response from the coach.'); return; }
                if (!cp.would_change) {
                    showToast({
                        reason: cp.reason || 'Nothing needed changing.',
                        showUndo: false,
                    });
                    markSeen(id);
                    return;
                }
                if (!onThisPlanPage) {
                    stashToast({ reason: cp.reason, showUndo: true });
                    reload(id);
                    return;
                }
                var reloaded = applyPatch(cp.patch, cp, id);
                if (reloaded) return;
                showToast({ reason: cp.reason, changePlan: cp, showUndo: true });
                syncPersistentPanel(cp);
                markSeen(id);
            })
            .catch(function (err) {
                restore();
                if (err.status === 409) {
                    showError('Your plan changed elsewhere — refresh to continue.');
                } else {
                    showError(err.message || 'Could not adjust the plan.');
                }
            });
    }

    function undo() {
        var id = planId();
        if (!id) return Promise.resolve();
        return postJson('/api/plan/' + id + '/intent/undo')
            .then(function (cp) {
                if (!cp || !cp.summary) return;
                if (cp.patch && cp.patch.reload_recommended) {
                    stashToast({ reason: 'Reverted the last change.', showUndo: false,
                        tone: 'reverted' });
                    reload(id);
                    return;
                }
                if (window.planDomSync) {
                    window.planDomSync.applyPatch(cp.patch);
                    highlight(cp.patch);
                }
                clearPersistentPanel();
                showToast({
                    reason: 'Reverted — back to where you were.',
                    showUndo: false,
                    tone: 'reverted',
                });
            })
            .catch(function (err) {
                if (err.status === 409) {
                    showError('Your plan changed elsewhere — refresh to continue.');
                } else {
                    showError(err.message || 'Could not undo the change.');
                }
            });
    }

    // -- the persistent "Latest plan changes" panel -----------------------

    function syncPersistentPanel(cp) {
        // Keep the server-rendered panel honest after an in-place apply, and
        // give it its own durable Undo so the option survives the bar closing.
        window.LAST_CHANGE_PLAN = cp;
        addPanelUndo();
    }

    function clearPersistentPanel() {
        window.LAST_CHANGE_PLAN = null;
        var panel = document.getElementById('latest-changes-panel');
        if (panel) {
            panel.style.transition = 'opacity 0.25s ease';
            panel.style.opacity = '0';
            setTimeout(function () { if (panel.parentNode) panel.remove(); }, 260);
        }
    }

    function addPanelUndo() {
        var panel = document.getElementById('latest-changes-panel');
        if (!panel) return;
        if (panel.querySelector('[data-adapt-panel-undo]')) return;
        var actions = panel.querySelector('.plan-change-plan-panel-header > div:last-child');
        if (!actions) return;
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-ghost btn-small';
        btn.setAttribute('data-adapt-panel-undo', '');
        btn.textContent = 'Undo';
        btn.onclick = function () { btn.disabled = true; undo(); };
        actions.insertBefore(btn, actions.firstChild);
    }

    // -- reload-crossing toast --------------------------------------------

    function stashToast(payload) {
        try { sessionStorage.setItem(POST_RELOAD_KEY, JSON.stringify(payload)); } catch (e) {}
    }

    function drainStashedToast() {
        var raw;
        try { raw = sessionStorage.getItem(POST_RELOAD_KEY); } catch (e) { return; }
        if (!raw) return;
        try { sessionStorage.removeItem(POST_RELOAD_KEY); } catch (e) {}
        try {
            var payload = JSON.parse(raw);
            // The change_plan isn't carried across the reload; the persistent
            // panel provides "See what changed", so the bar just confirms + undo.
            if (window.LAST_CHANGE_PLAN) payload.changePlan = window.LAST_CHANGE_PLAN;
            showToast(payload);
        } catch (e) {}
    }

    function init() {
        drainStashedToast();
        // A change applied server-side between sessions (e.g. a Strava sync
        // auto-adapt) lands here unseen — surface it as the same calm bar,
        // never an interrupting modal.
        var lcp = window.LAST_CHANGE_PLAN;
        if (lcp && lcp.summary && lcp.seen === false
            && lcp.summary.workouts_changed_count > 0) {
            addPanelUndo();
            showToast({
                reason: lcp.reason || 'Your plan adapted to your recent training.',
                changePlan: lcp,
                showUndo: !!(lcp.undo && lcp.undo.length),
            });
            markSeen(planId());
        } else if (lcp && lcp.undo && lcp.undo.length) {
            // Already seen but still undoable — offer it on the panel only.
            addPanelUndo();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.PlanInlineAdapt = { applyIntent: applyIntent, undo: undo, showToast: showToast };
})();
