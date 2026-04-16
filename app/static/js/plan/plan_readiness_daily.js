/**
 * plan_readiness_daily.js — Daily check-in widget on the plan page.
 *
 * Hydrates the #daily-readiness-widget element:
 *   1. GET /api/readiness/today — render either the prompt or the existing score.
 *   2. On submit, POST /api/readiness with the four 1-5 answers + notes.
 *   3. After a low score, nudge the user to swap tomorrow's hard session
 *      for an easy run (visual-only; backend stores the raw data).
 */
(function () {
    'use strict';

    var WIDGET_ID = 'daily-readiness-widget';
    var INNER_ID = 'daily-readiness-inner';

    var QUESTIONS = [
        { key: 'sleep',    label: 'Sleep',    hint: 'How rested?' },
        { key: 'soreness', label: 'Legs',     hint: 'Muscle feel' },
        { key: 'energy',   label: 'Energy',   hint: 'Drive today' },
        { key: 'stress',   label: 'Stress',   hint: 'Lower = calmer' }
    ];

    var STATUS_META = {
        ready: {
            chip: 'Green light',
            headline: "You're cleared to run hard.",
            message: 'Hit the session as written — you should have the legs for it.'
        },
        caution: {
            chip: 'Amber',
            headline: 'Proceed with care.',
            message: "Keep effort honest today. If tomorrow's workout is a hard session, consider dialling intensity back 10-15%."
        },
        rest: {
            chip: 'Red flag',
            headline: 'Recovery day recommended.',
            message: "Your body is asking for a break. Swap tomorrow's hard session for easy minutes or full rest — it'll pay dividends."
        }
    };

    function $(id) { return document.getElementById(id); }

    function getCsrfToken() {
        var token = localStorage.getItem('access_token');
        return token ? { Authorization: 'Bearer ' + token } : {};
    }

    async function fetchJson(url, options) {
        options = options || {};
        var headers = Object.assign(
            { 'Content-Type': 'application/json' },
            getCsrfToken(),
            options.headers || {}
        );
        var resp = await fetch(url, {
            method: options.method || 'GET',
            headers: headers,
            credentials: 'same-origin',
            body: options.body ? JSON.stringify(options.body) : undefined
        });
        if (resp.status === 401) {
            var err = new Error('unauthorized');
            err.status = 401;
            throw err;
        }
        if (!resp.ok) {
            var detail = '';
            try { detail = (await resp.json()).detail || ''; } catch (e) { /* noop */ }
            throw new Error(detail || 'Request failed (' + resp.status + ')');
        }
        if (resp.status === 204) return null;
        return resp.json();
    }

    /* -------------------------------------------------------------- */
    /*  Rendering                                                      */
    /* -------------------------------------------------------------- */

    var ICON_SVG = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/></svg>';

    function renderPrompt() {
        return (
            '<div class="daily-readiness-prompt">' +
                '<div class="daily-readiness-icon" aria-hidden="true">' + ICON_SVG + '</div>' +
                '<div class="daily-readiness-body">' +
                    '<div class="daily-readiness-eyebrow">Daily check-in</div>' +
                    '<div class="daily-readiness-title">How are you feeling today?</div>' +
                    '<p class="daily-readiness-sub">A 20-second read on your body so we know whether to push or pull back.</p>' +
                '</div>' +
                '<button type="button" class="daily-readiness-action" data-action="open">Check in</button>' +
            '</div>'
        );
    }

    function renderForm(state) {
        var html = '';
        html += '<form class="daily-readiness-form" id="daily-readiness-form" novalidate>';
        html += '  <div class="daily-readiness-form-header">';
        html += '    <h3>How are you feeling today?</h3>';
        html += '    <button type="button" class="daily-readiness-close" data-action="cancel" aria-label="Close">&times;</button>';
        html += '  </div>';
        html += '  <div class="daily-readiness-questions">';
        for (var i = 0; i < QUESTIONS.length; i++) {
            var q = QUESTIONS[i];
            html += '<div class="daily-readiness-question" data-key="' + q.key + '">';
            html += '  <label class="daily-readiness-question-label">' + q.label + ' <span class="daily-readiness-hint">' + q.hint + '</span></label>';
            html += '  <div class="daily-readiness-scale" role="radiogroup" aria-label="' + q.label + '">';
            for (var v = 1; v <= 5; v++) {
                var selected = state[q.key] === v ? ' is-selected' : '';
                html += '<button type="button" class="daily-readiness-dot' + selected + '" data-key="' + q.key + '" data-value="' + v + '" role="radio" aria-checked="' + (state[q.key] === v) + '">' + v + '</button>';
            }
            html += '  </div>';
            html += '</div>';
        }
        html += '  </div>';
        html += '  <textarea class="daily-readiness-notes" placeholder="Anything coach should know? (optional)" maxlength="500">' + (state.notes || '') + '</textarea>';
        html += '  <div class="daily-readiness-submit-row">';
        html += '    <span class="daily-readiness-preview" id="daily-readiness-preview">' + previewText(state) + '</span>';
        html += '    <button type="submit" class="daily-readiness-submit" id="daily-readiness-submit" ' + (isComplete(state) ? '' : 'disabled') + '>Save check-in</button>';
        html += '  </div>';
        html += '  <div class="daily-readiness-error" id="daily-readiness-error" style="display:none"></div>';
        html += '</form>';
        return html;
    }

    function isComplete(state) {
        for (var i = 0; i < QUESTIONS.length; i++) {
            if (!state[QUESTIONS[i].key]) return false;
        }
        return true;
    }

    function computePreviewScore(state) {
        if (!isComplete(state)) return null;
        // Mirror backend formula (readiness_log.compute_score) for instant feedback.
        var sSleep = (state.sleep - 1) / 4;
        var sSore  = (state.soreness - 1) / 4;
        var sEnergy = (state.energy - 1) / 4;
        var sStress = 1 - (state.stress - 1) / 4;
        var weighted = sSleep * 0.25 + sSore * 0.30 + sEnergy * 0.30 + sStress * 0.15;
        return Math.round(weighted * 100);
    }

    function previewText(state) {
        var score = computePreviewScore(state);
        if (score === null) {
            var filled = QUESTIONS.filter(function (q) { return !!state[q.key]; }).length;
            return filled + ' of ' + QUESTIONS.length + ' answered';
        }
        var status = score >= 70 ? 'ready' : score >= 45 ? 'caution' : 'rest';
        return 'Preview: <strong>' + score + '</strong> — ' + STATUS_META[status].chip;
    }

    function renderResult(log, adapted) {
        var status = log.status || 'ready';
        var meta = STATUS_META[status] || STATUS_META.ready;
        var html = '';
        html += '<div class="daily-readiness-result">';
        html += '  <div class="daily-readiness-score">';
        html += '    <span class="daily-readiness-score-number">' + log.score + '</span>';
        html += '    <span class="daily-readiness-score-label">/ 100</span>';
        html += '  </div>';
        html += '  <div class="daily-readiness-result-body">';
        html += '    <span class="daily-readiness-status-chip">' + meta.chip + '</span>';
        html += '    <div class="daily-readiness-headline">' + meta.headline + '</div>';
        html += '    <p class="daily-readiness-message">' + meta.message + '</p>';
        if (adapted) {
            html += '    <div class="daily-readiness-adapted">';
            html += '      <span class="daily-readiness-adapted-label">Workout adjusted</span> ';
            html += '      <span class="daily-readiness-adapted-detail">' + formatAdaptation(adapted) + '</span>';
            html += '    </div>';
        } else if (status !== 'ready') {
            html += '    <button type="button" class="daily-readiness-adapt" data-action="adapt">Adjust today\'s workout</button>';
        }
        html += '    <button type="button" class="daily-readiness-retry" data-action="redo">Update check-in</button>';
        html += '  </div>';
        html += '</div>';
        return html;
    }

    function formatAdaptation(adapted) {
        var orig = adapted.original || {};
        var next = adapted.adapted || {};
        if (next.type === 'rest') {
            return (orig.type || 'workout') + ' ' + (orig.distance || 0) + ' km → Rest day';
        }
        var parts = [];
        if (orig.type !== next.type) parts.push(orig.type + ' → ' + next.type);
        if (orig.distance !== next.distance) parts.push(orig.distance + ' km → ' + next.distance + ' km');
        return parts.length ? parts.join(', ') : 'Intensity eased';
    }

    /* -------------------------------------------------------------- */
    /*  Controller                                                     */
    /* -------------------------------------------------------------- */

    function Widget(root) {
        this.root = root;
        this.inner = root.querySelector('#' + INNER_ID);
        this.state = { sleep: null, soreness: null, energy: null, stress: null, notes: '' };
        this.mode = 'loading'; // loading | prompt | form | result
        this.existing = null;
        this.submitting = false;
    }

    Widget.prototype.mount = async function () {
        try {
            var today = await fetchJson('/api/readiness/today');
            if (today && today.score != null) {
                this.existing = today;
                this.showResult(today);
                this.applyStatus(today.status);
                return;
            }
            this.showPrompt();
        } catch (err) {
            if (err && err.status === 401) {
                // Not logged in — hide widget quietly.
                this.root.classList.add('is-hidden');
                return;
            }
            console.error('[daily-readiness] load failed', err);
            this.showPrompt();
        }
    };

    Widget.prototype.showPrompt = function () {
        this.mode = 'prompt';
        this.applyStatus(null);
        this.inner.innerHTML = renderPrompt();
        this.bindPrompt();
    };

    Widget.prototype.showForm = function () {
        this.mode = 'form';
        if (this.existing) {
            this.state = {
                sleep: this.existing.sleep,
                soreness: this.existing.soreness,
                energy: this.existing.energy,
                stress: this.existing.stress,
                notes: this.existing.notes || ''
            };
        }
        this.inner.innerHTML = renderForm(this.state);
        this.bindForm();
    };

    Widget.prototype.showResult = function (log, adapted) {
        this.mode = 'result';
        this.existing = log;
        this.adapted = adapted || null;
        this.inner.innerHTML = renderResult(log, this.adapted);
        this.bindResult();
    };

    Widget.prototype.applyStatus = function (status) {
        var classes = ['status-ready', 'status-caution', 'status-rest'];
        for (var i = 0; i < classes.length; i++) {
            this.root.classList.remove(classes[i]);
        }
        if (status) this.root.classList.add('status-' + status);
    };

    Widget.prototype.bindPrompt = function () {
        var btn = this.inner.querySelector('[data-action="open"]');
        var self = this;
        if (btn) btn.addEventListener('click', function () { self.showForm(); });
    };

    Widget.prototype.bindResult = function () {
        var self = this;
        var redoBtn = this.inner.querySelector('[data-action="redo"]');
        if (redoBtn) redoBtn.addEventListener('click', function () { self.showForm(); });

        var adaptBtn = this.inner.querySelector('[data-action="adapt"]');
        if (adaptBtn) adaptBtn.addEventListener('click', function () { self.adaptWorkout(adaptBtn); });
    };

    Widget.prototype.adaptWorkout = async function (btn) {
        var planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (!planId) return;

        btn.disabled = true;
        btn.textContent = 'Adjusting…';

        try {
            var result = await fetchJson('/api/readiness/adapt', {
                method: 'POST',
                body: { plan_id: planId }
            });
            this.showResult(this.existing, result);
            // Refresh the workout card on the plan page if available
            if (typeof window.refreshTodaysWorkout === 'function') {
                window.refreshTodaysWorkout();
            }
        } catch (err) {
            console.error('[daily-readiness] adapt failed', err);
            btn.disabled = false;
            btn.textContent = 'Adjust today\'s workout';
            // Show inline error
            var errMsg = (err && err.message) || 'Could not adjust workout.';
            var errEl = document.createElement('div');
            errEl.className = 'daily-readiness-adapt-error';
            errEl.textContent = errMsg;
            btn.parentElement.insertBefore(errEl, btn.nextSibling);
            setTimeout(function () { errEl.remove(); }, 4000);
        }
    };

    Widget.prototype.bindForm = function () {
        var self = this;
        var form = this.inner.querySelector('#daily-readiness-form');
        if (!form) return;

        form.querySelectorAll('.daily-readiness-dot').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var key = btn.getAttribute('data-key');
                var value = parseInt(btn.getAttribute('data-value'), 10);
                self.state[key] = value;
                // Update selection classes within this group without re-rendering.
                var group = btn.parentElement;
                group.querySelectorAll('.daily-readiness-dot').forEach(function (d) {
                    var on = parseInt(d.getAttribute('data-value'), 10) === value;
                    d.classList.toggle('is-selected', on);
                    d.setAttribute('aria-checked', on ? 'true' : 'false');
                });
                self.refreshPreview();
            });
        });

        var notes = form.querySelector('.daily-readiness-notes');
        if (notes) {
            notes.addEventListener('input', function () { self.state.notes = notes.value; });
        }

        var cancel = form.querySelector('[data-action="cancel"]');
        if (cancel) {
            cancel.addEventListener('click', function () {
                if (self.existing) self.showResult(self.existing);
                else self.showPrompt();
            });
        }

        form.addEventListener('submit', function (evt) {
            evt.preventDefault();
            self.submit();
        });
    };

    Widget.prototype.refreshPreview = function () {
        var preview = this.inner.querySelector('#daily-readiness-preview');
        var submit = this.inner.querySelector('#daily-readiness-submit');
        if (preview) preview.innerHTML = previewText(this.state);
        if (submit) submit.disabled = !isComplete(this.state);
    };

    Widget.prototype.submit = async function () {
        if (this.submitting || !isComplete(this.state)) return;
        this.submitting = true;
        var submitBtn = this.inner.querySelector('#daily-readiness-submit');
        var errBox = this.inner.querySelector('#daily-readiness-error');
        if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Saving…'; }
        if (errBox) errBox.style.display = 'none';

        try {
            var log = await fetchJson('/api/readiness', {
                method: 'POST',
                body: {
                    sleep: this.state.sleep,
                    soreness: this.state.soreness,
                    energy: this.state.energy,
                    stress: this.state.stress,
                    notes: this.state.notes || null
                }
            });
            this.existing = log;
            this.applyStatus(log.status);
            this.showResult(log);
            if (log.status !== 'ready' && typeof window.highlightTomorrowSwap === 'function') {
                window.highlightTomorrowSwap(log.status);
            }
        } catch (err) {
            console.error('[daily-readiness] submit failed', err);
            if (errBox) {
                errBox.textContent = (err && err.message) || "Couldn't save check-in. Try again in a moment.";
                errBox.style.display = '';
            }
            if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Save check-in'; }
        } finally {
            this.submitting = false;
        }
    };

    /* -------------------------------------------------------------- */
    /*  Boot                                                           */
    /* -------------------------------------------------------------- */

    function boot() {
        var root = $(WIDGET_ID);
        if (!root) return;
        var widget = new Widget(root);
        widget.mount();
        window.__dailyReadinessWidget = widget;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
