/**
 * analytics_today.js — the Coach Hub "Today" tab (plan-scoped lead view).
 *
 * Answers "what does my coach think about my training right now?" by
 * combining the coach stance banner, current form (CTL/ATL/TSB), today's
 * planned session, this week's execution strip, and a coach's note (week
 * pulse + pace patterns). Reuses the banner/form renderers and fetch/escape
 * helpers defined on AnalyticsDashboard by analytics_coach.js.
 */
(function () {
    const AD = window.AnalyticsDashboard;

    AD.todayLoadedPlanId = undefined;
    AD.coachNoteLoadedPlanId = undefined;

    const WORKOUT_ICONS = {
        easy: '🟢', recovery: '🟢', long: '🔵', tempo: '🟠', threshold: '🟠',
        interval: '🔴', vo2max: '🔴', fartlek: '🟣', hill: '⛰️', race_pace: '🏁',
        race: '🏁', run_walk: '🟢', rest: '😴', strength: '💪',
    };

    const STATUS_GLYPH = {
        done: '✓', today: '→', missed: '✗', upcoming: '', rest: '·',
    };

    AD.loadToday = async function (planId) {
        const prompt = document.getElementById('todayPrompt');
        const loading = document.getElementById('todayLoading');
        const content = document.getElementById('todayContent');
        const empty = document.getElementById('todayEmpty');
        if (!content) return;

        if (!planId) {
            this.todayLoadedPlanId = null;
            this._show(prompt); this._hide(loading); this._hide(content); this._hide(empty);
            this._loadCoachNote(null);
            return;
        }

        this._hide(prompt); this._hide(empty); this._hide(content); this._show(loading);

        try {
            const [summary, patterns, today] = await Promise.all([
                this._fetchJson('/api/analytics/coach-summary/' + encodeURIComponent(planId)),
                this._fetchJson('/api/analytics/coach-patterns/' + encodeURIComponent(planId)),
                this._fetchJson('/api/analytics/today/' + encodeURIComponent(planId)),
            ]);

            this._hide(loading);

            if (!summary || summary.available === false) {
                const text = document.getElementById('todayEmptyText');
                if (text && summary && summary.reason) text.textContent = summary.reason;
                this._show(empty);
                this._loadCoachNote(null);
                this.todayLoadedPlanId = planId;
                return;
            }

            this._show(content);
            this._loadCoachNote(planId);
            this._renderCoachBanner(summary);
            this._renderCoachForm(summary);
            this._renderTodayWorkout(today, planId);
            this._renderTodayWeek(today);
            this._renderTodayNote(patterns);
            this.todayLoadedPlanId = planId;
        } catch (err) {
            console.error('Today load error:', err);
            this._hide(loading);
            this._show(empty);
            this._loadCoachNote(null);
        }
    };

    /* ----- display helpers ----- */
    AD._show = function (el) { if (el) el.style.display = ''; };
    AD._hide = function (el) { if (el) el.style.display = 'none'; };

    /* ----- Coach's Note (recognition-first AI voice; fetched independently of
       the Promise.all so the rest of the tab renders instantly while the note
       streams in) ----- */
    AD._loadCoachNote = async function (planId) {
        const card = document.getElementById('coachNoteCard');
        const skel = document.getElementById('coachNoteSkeleton');
        if (!card) return;

        if (!planId) {
            this.coachNoteLoadedPlanId = null;
            this._hide(card); this._hide(skel);
            return;
        }
        // Already rendered for this plan this session — skip the skeleton flash
        // on tab switches. A full reload re-fetches (and picks up new runs).
        if (this.coachNoteLoadedPlanId === planId) return;

        this._hide(card); this._show(skel);
        const data = await this._fetchJson('/api/analytics/coach-note/' + encodeURIComponent(planId));
        this._hide(skel);

        if (!data || data.available === false || !data.note) {
            this._hide(card);
            return;
        }

        const prose = document.getElementById('coachNoteProse');
        const chips = document.getElementById('coachNoteChips');
        if (prose) prose.textContent = data.note;
        if (chips) {
            const list = (data.recognition && data.recognition.chips) || [];
            chips.innerHTML = list
                .map((c) => `<span class="coach-note-chip">${this._esc(c)}</span>`)
                .join('');
        }
        this._show(card);
        this.coachNoteLoadedPlanId = planId;
    };

    /* ----- Today's session card ----- */
    AD._renderTodayWorkout = function (today, planId) {
        const chip = document.getElementById('todayWeekChip');
        const body = document.getElementById('todayWorkout');
        if (!body) return;

        if (!today || today.available === false) {
            if (chip) chip.textContent = '';
            body.innerHTML = '<p class="analytics-empty-text">' +
                this._esc((today && today.reason) || 'No schedule for today.') + '</p>';
            return;
        }

        if (chip) {
            const phase = today.phase ? this._titleCase(today.phase) + ' phase · ' : '';
            chip.textContent = `${phase}Week ${today.current_week} of ${today.total_weeks}`;
        }

        const w = today.today;
        if (!w || w.workout_type === 'rest') {
            body.innerHTML =
                '<div class="today-workout-rest">' +
                '<span class="today-workout-rest-icon">😴</span>' +
                '<div><span class="today-workout-rest-title">Rest day</span>' +
                '<span class="today-workout-rest-sub">Recovery is where the adaptation happens.</span></div>' +
                '</div>';
            return;
        }

        const icon = WORKOUT_ICONS[w.workout_type] || '🏃';
        const type = this._titleCase((w.workout_type || '').replace(/_/g, ' '));
        const dist = w.distance_km > 0 ? `${w.distance_km.toFixed(1)} km` : '';
        const dur = w.duration_min ? `≈ ${w.duration_min} min` : '';
        const zone = w.hr_zone_target
            ? `<span class="today-workout-zone hr-zone-${w.hr_zone_target}">Zone ${w.hr_zone_target}${w.hr_zone_label ? ' · ' + this._esc(w.hr_zone_label) : ''}</span>`
            : '';
        const logged = w.logged
            ? '<span class="today-workout-logged">✓ Logged</span>' : '';

        body.innerHTML =
            '<div class="today-workout-main">' +
            `<span class="today-workout-icon today-workout-icon--${this._esc(w.workout_type)}">${icon}</span>` +
            '<div class="today-workout-info">' +
            `<span class="today-workout-type">${this._esc(w.day_name)} · ${this._esc(type)}</span>` +
            `<span class="today-workout-dist">${this._esc([dist, dur].filter(Boolean).join(' · ')) || '—'}</span>` +
            `</div>${logged}</div>` +
            (zone ? `<div class="today-workout-zone-row">${zone}</div>` : '') +
            (w.description ? `<p class="today-workout-desc">${this._esc(w.description)}</p>` : '') +
            `<a class="today-workout-link" href="/plan/${encodeURIComponent(planId)}">Open plan →</a>`;
    };

    /**
     * Inline SVG sparkline. `values` left-to-right (oldest→newest); `baseline`
     * draws a faint reference line. Returns an empty string for <2 points.
     */
    AD._sparkline = function (values, baseline) {
        const pts = values.filter((v) => typeof v === 'number');
        if (pts.length < 2) return '<span class="spark-empty">Not enough data for a trend yet.</span>';
        const w = 220, h = 38, pad = 3;
        const min = Math.min(...pts, baseline != null ? baseline : Infinity);
        const max = Math.max(...pts, baseline != null ? baseline : -Infinity);
        const span = max - min || 1;
        const x = (i) => pad + (i * (w - pad * 2)) / (pts.length - 1);
        const y = (v) => h - pad - ((v - min) / span) * (h - pad * 2);
        const line = pts.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
        const area = `${line} L${x(pts.length - 1).toFixed(1)} ${h - pad} L${x(0).toFixed(1)} ${h - pad} Z`;
        const baseLine = baseline != null
            ? `<line x1="${pad}" y1="${y(baseline).toFixed(1)}" x2="${w - pad}" y2="${y(baseline).toFixed(1)}" class="spark-baseline"/>` : '';
        const last = pts[pts.length - 1];
        return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Trend">` +
            `<path class="spark-area" d="${area}"/>${baseLine}` +
            `<path class="spark-line" d="${line}"/>` +
            `<circle class="spark-dot" cx="${x(pts.length - 1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="2.5"/></svg>`;
    };

    /* ----- This week's execution strip ----- */
    AD._renderTodayWeek = function (today) {
        const strip = document.getElementById('todayWeekStrip');
        const vol = document.getElementById('todayWeekVolume');
        const fill = document.getElementById('todayWeekProgressFill');
        if (!strip) return;

        if (!today || today.available === false || !today.week) {
            strip.innerHTML = '<p class="analytics-empty-text">Set a plan start date to see this week.</p>';
            if (vol) vol.textContent = '';
            if (fill) fill.style.width = '0%';
            return;
        }

        strip.innerHTML = today.week.map((d) => {
            const glyph = STATUS_GLYPH[d.status] || '';
            const kmActual = d.actual_km > 0 ? `${d.actual_km.toFixed(1)}` : '';
            const kmPlanned = d.planned_km > 0 ? `${d.planned_km.toFixed(1)}` : '';
            const km = d.status === 'done' && kmActual ? kmActual : kmPlanned;
            const typeShort = d.workout_type === 'rest' ? 'Rest' : this._titleCase((d.workout_type || '').replace(/_/g, ' ')).slice(0, 8);
            return (
                `<div class="today-day today-day--${this._esc(d.status)}${d.is_today ? ' is-today' : ''}">` +
                `<span class="today-day-name">${this._esc(d.day_name)}</span>` +
                `<span class="today-day-type">${this._esc(typeShort)}</span>` +
                `<span class="today-day-status today-day-status--${this._esc(d.status)}">${glyph}</span>` +
                `<span class="today-day-km">${km ? this._esc(km) + ' km' : '—'}</span>` +
                '</div>'
            );
        }).join('');

        if (vol) {
            const pct = today.week_pct != null ? ` (${today.week_pct}%)` : '';
            vol.textContent = `${today.week_actual_km.toFixed(1)} / ${today.week_planned_km.toFixed(1)} km${pct}`;
        }
        if (fill) fill.style.width = Math.min(100, today.week_pct || 0) + '%';
    };

    /* ----- Coach's note (week pulse + pace patterns) ----- */
    AD._renderTodayNote = function (patterns) {
        const card = document.getElementById('todayNoteCard');
        const pulse = document.getElementById('coachWeekPulse');
        const pat = document.getElementById('coachPatterns');

        const wp = patterns && patterns.week_pulse;
        const list = (patterns && patterns.patterns) || [];
        const hasContent = (wp && wp.message) || list.length > 0;
        if (card) card.style.display = hasContent ? '' : 'none';

        if (pulse) {
            if (wp && wp.message) {
                const details = (wp.details || []).map((d) => `<li>${this._esc(d)}</li>`).join('');
                pulse.innerHTML =
                    `<div class="coach-week-pulse-inner coach-week-pulse--${this._esc(wp.mood || 'neutral')}">` +
                    `<span class="coach-week-pulse-msg">${this._esc(wp.message)}</span>` +
                    (details ? `<ul class="coach-week-pulse-details">${details}</ul>` : '') +
                    '</div>';
            } else {
                pulse.innerHTML = '';
            }
        }

        if (pat) {
            pat.innerHTML = list.length === 0 ? '' : list.map((p) =>
                '<div class="coach-pattern"><span class="coach-pattern-dot"></span>' +
                `<span class="coach-pattern-text">${this._esc(p.message)}</span></div>`
            ).join('');
        }
    };
})();
