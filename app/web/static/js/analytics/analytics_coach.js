/**
 * analytics_coach.js — the Coach hub (plan-scoped lead tab).
 *
 * Fetches the read-only coach endpoints and renders the adaptation-state
 * banner, form/readiness strip, 6-signal radar (delegated to
 * analytics_signal_chart.js), the "why your plan is evolving" block, pace
 * patterns + week pulse, and the adaptation-history timeline. Reuses
 * _renderReadiness from analytics_plan.js for the readiness body.
 */
(function () {
    const AD = window.AnalyticsDashboard;

    // Tracks which plan the Coach view last rendered, so re-activating the
    // tab for the same plan doesn't refetch needlessly.
    AD.coachLoadedPlanId = undefined;

    const FORM_COPY = {
        primed: ['Primed', 'Peak form — rested and race-ready.'],
        fresh: ['Fresh', 'Well recovered with plenty in the tank.'],
        neutral: ['Balanced', 'Fitness and fatigue are in a healthy balance.'],
        loaded: ['Loaded', 'Carrying real training load — productive fatigue.'],
        overreached: ['Overreached', 'Fatigue is high — recovery is the priority.'],
    };

    AD.loadCoach = async function (planId) {
        const prompt = document.getElementById('coachPrompt');
        const loading = document.getElementById('coachLoading');
        const content = document.getElementById('coachContent');
        const empty = document.getElementById('coachEmpty');
        if (!content) return;

        // No plan selected → invite the user to pick one.
        if (!planId) {
            this.coachLoadedPlanId = null;
            if (prompt) prompt.style.display = '';
            if (loading) loading.style.display = 'none';
            if (content) content.style.display = 'none';
            if (empty) empty.style.display = 'none';
            return;
        }

        if (prompt) prompt.style.display = 'none';
        if (empty) empty.style.display = 'none';
        if (content) content.style.display = 'none';
        if (loading) loading.style.display = '';

        try {
            const [summary, patterns, history] = await Promise.all([
                this._fetchJson('/api/analytics/coach-summary/' + encodeURIComponent(planId)),
                this._fetchJson('/api/analytics/coach-patterns/' + encodeURIComponent(planId)),
                this._fetchJson('/api/analytics/adaptation-history/' + encodeURIComponent(planId)),
            ]);

            if (loading) loading.style.display = 'none';

            if (!summary || summary.available === false) {
                const text = document.getElementById('coachEmptyText');
                if (text && summary && summary.reason) text.textContent = summary.reason;
                if (empty) empty.style.display = '';
                this.coachLoadedPlanId = planId;
                return;
            }

            content.style.display = '';
            this._renderCoachBanner(summary);
            this._renderCoachForm(summary);
            this._renderCoachReadiness(summary);
            if (this.renderSignalChart) this.renderSignalChart(summary.signals || {});
            this._renderCoachWhy(summary, patterns);
            this._renderAdaptationHistory(history);
            this.coachLoadedPlanId = planId;
        } catch (err) {
            console.error('Coach load error:', err);
            if (loading) loading.style.display = 'none';
            if (empty) empty.style.display = '';
        }
    };

    AD._fetchJson = async function (url) {
        try {
            const res = await fetch(url, { credentials: 'same-origin' });
            if (!res.ok) return null;
            return await res.json();
        } catch {
            return null;
        }
    };

    /* ----- Adaptation-state banner ----- */
    AD._renderCoachBanner = function (s) {
        const el = document.getElementById('coachBanner');
        if (!el) return;

        let mood, icon, title, body;
        if (s.overreach_detected) {
            mood = 'caution';
            icon = '⚠️';
            title = 'Ease back to recover';
            body = 'Your coach is holding load back to protect recovery.';
        } else if (s.direction === 'increase') {
            mood = 'positive';
            icon = '📈';
            title = 'Ready to step up';
            body = 'Recent training supports a bump in upcoming load.';
        } else if (s.direction === 'decrease') {
            mood = 'caution';
            icon = '🔽';
            title = 'Dialing it back';
            body = 'Signals point to easing off the upcoming weeks.';
        } else {
            mood = 'steady';
            icon = '✅';
            title = 'On track';
            body = 'Your plan is well matched to your training right now.';
        }

        const phase = s.current_phase
            ? `<span class="coach-banner-phase">${this._esc(this._titleCase(s.current_phase))} phase</span>`
            : '';
        el.className = 'coach-banner coach-banner--' + mood;
        el.innerHTML =
            `<span class="coach-banner-icon">${icon}</span>` +
            `<div class="coach-banner-text"><span class="coach-banner-title">${this._esc(title)}</span>` +
            `<span class="coach-banner-body">${this._esc(body)}</span></div>` +
            phase;
    };

    /* ----- Form strip (TSB/CTL/ATL) ----- */
    AD._renderCoachForm = function (s) {
        const strip = document.getElementById('coachFormStrip');
        const badge = document.getElementById('coachFormBadge');
        if (!strip) return;
        const f = s.form || {};

        if (badge) {
            const copy = FORM_COPY[f.tsb_form] || ['', ''];
            badge.textContent = copy[0];
            badge.className = 'coach-form-badge' + (f.tsb_form ? ' coach-form-badge--' + f.tsb_form : '');
            badge.title = copy[1] || '';
        }

        const cell = (label, value, sub, mod) =>
            `<div class="coach-form-cell coach-form-cell--${mod}">` +
            `<span class="coach-form-cell-label">${label}</span>` +
            `<span class="coach-form-cell-value">${value == null ? '—' : value}</span>` +
            `<span class="coach-form-cell-sub">${sub}</span></div>`;

        strip.innerHTML =
            cell('Fitness', f.ctl != null ? f.ctl : null, 'CTL · 42-day', 'ctl') +
            cell('Fatigue', f.atl != null ? f.atl : null, 'ATL · 7-day', 'atl') +
            cell('Form', f.tsb != null ? f.tsb : null, 'TSB · CTL−ATL', 'tsb');
    };

    /* ----- Readiness (reuse analytics_plan.js renderer) ----- */
    AD._renderCoachReadiness = function (s) {
        const el = document.getElementById('coachReadiness');
        if (!el) return;
        if (s.readiness && s.readiness.overall_score != null && this._renderReadiness) {
            el.innerHTML = this._renderReadiness(s.readiness);
        } else {
            el.innerHTML = '<p class="analytics-empty-text">Set a race date and log runs to see readiness.</p>';
        }
    };

    /* ----- Why your plan is evolving ----- */
    AD._renderCoachWhy = function (s, patterns) {
        const chip = document.getElementById('coachMultiplierChip');
        if (chip) {
            const mult = typeof s.multiplier === 'number' ? s.multiplier : 1.0;
            const pct = Math.round((mult - 1) * 100);
            const dirClass = s.direction === 'increase' ? 'up' : s.direction === 'decrease' ? 'down' : 'flat';
            chip.className = 'coach-mult-chip coach-mult-chip--' + dirClass;
            chip.textContent = pct === 0 ? 'Hold ×1.00' : `${pct > 0 ? '+' : ''}${pct}% · ×${mult.toFixed(2)}`;
        }

        const why = document.getElementById('coachWhy');
        if (why) why.textContent = s.headline_reason || '';

        const pat = document.getElementById('coachPatterns');
        if (pat) {
            const list = (patterns && patterns.patterns) || [];
            if (list.length === 0) {
                pat.innerHTML = '';
            } else {
                pat.innerHTML = list
                    .map(
                        (p) =>
                            `<div class="coach-pattern"><span class="coach-pattern-dot"></span>` +
                            `<span class="coach-pattern-text">${this._esc(p.message)}</span></div>`
                    )
                    .join('');
            }
        }

        const pulse = document.getElementById('coachWeekPulse');
        if (pulse) {
            const wp = patterns && patterns.week_pulse;
            if (wp && wp.message) {
                const details = (wp.details || [])
                    .map((d) => `<li>${this._esc(d)}</li>`)
                    .join('');
                pulse.innerHTML =
                    `<div class="coach-week-pulse-inner coach-week-pulse--${this._esc(wp.mood || 'neutral')}">` +
                    `<span class="coach-week-pulse-msg">${this._esc(wp.message)}</span>` +
                    (details ? `<ul class="coach-week-pulse-details">${details}</ul>` : '') +
                    '</div>';
            } else {
                pulse.innerHTML = '';
            }
        }
    };

    /* ----- Adaptation history timeline ----- */
    AD._renderAdaptationHistory = function (history) {
        const list = document.getElementById('adaptationHistoryList');
        if (!list) return;
        const events = (history && history.events) || [];
        if (events.length === 0) {
            list.innerHTML = '<p class="analytics-empty-text">No plan adjustments yet — your timeline fills in as your coach adapts the plan.</p>';
            return;
        }

        list.innerHTML = events
            .map((e) => {
                const dir = e.direction || (e.pct > 0 ? 'increase' : e.pct < 0 ? 'decrease' : null);
                const dirClass = dir === 'increase' ? 'up' : dir === 'decrease' ? 'down' : 'flat';
                let delta = '';
                if (typeof e.pct === 'number' && e.pct !== 0) {
                    delta = `<span class="coach-timeline-delta coach-timeline-delta--${dirClass}">${e.pct > 0 ? '+' : ''}${e.pct}%</span>`;
                } else if (e.weeks_changed) {
                    delta = `<span class="coach-timeline-delta">${e.weeks_changed}w</span>`;
                }
                return (
                    '<div class="coach-timeline-item">' +
                    '<div class="coach-timeline-marker"></div>' +
                    '<div class="coach-timeline-content">' +
                    '<div class="coach-timeline-head">' +
                    `<span class="coach-timeline-label">${this._esc(e.label)}</span>` +
                    delta +
                    (e.date ? `<span class="coach-timeline-date">${this._esc(e.date)}</span>` : '') +
                    '</div>' +
                    (e.reason ? `<p class="coach-timeline-reason">${this._esc(e.reason)}</p>` : '') +
                    '</div></div>'
                );
            })
            .join('');
    };

    AD._titleCase = function (str) {
        if (!str) return '';
        return String(str).charAt(0).toUpperCase() + String(str).slice(1);
    };
})();
