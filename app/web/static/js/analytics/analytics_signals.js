/**
 * analytics_signals.js — the Coach Hub "Signals" tab (plan-scoped).
 *
 * The transparent view of the adaptation engine: the six signals with their
 * factors, phase weights, and trend sparklines; expandable detail cards
 * (per-type volume, effort/quality drift, HR-zone adherence, readiness
 * components); a phase-weight comparison; and the adaptation timeline.
 * Reuses renderSignalChart, _renderAdaptationHistory, and the fetch/escape
 * helpers attached to AnalyticsDashboard by analytics_signal_chart.js /
 * analytics_coach.js.
 */
(function () {
    const AD = window.AnalyticsDashboard;

    AD.signalsLoadedPlanId = undefined;

    const SIGNALS = [
        { key: 'volume', label: 'Volume', desc: 'Actual vs planned distance' },
        { key: 'effort', label: 'Effort', desc: 'Perceived exertion trend' },
        { key: 'completion', label: 'Completion', desc: 'Scheduled workouts done' },
        { key: 'hr_zone', label: 'HR Zone', desc: 'Time in target zones' },
        { key: 'feedback', label: 'Feedback', desc: 'Automated coaching sentiment' },
        { key: 'readiness', label: 'Readiness', desc: 'Daily wellness check-ins' },
    ];

    // Mirrors app/contexts/plan/adaptation/tuning.py PHASE_WEIGHTS
    // (volume, effort, completion, hr_zone, feedback, readiness).
    const PHASE_WEIGHTS = {
        base: [0.38, 0.18, 0.18, 0.11, 0.07, 0.08],
        build: [0.33, 0.20, 0.16, 0.14, 0.09, 0.08],
        peak: [0.28, 0.20, 0.16, 0.16, 0.10, 0.10],
        taper: [0.10, 0.20, 0.22, 0.22, 0.14, 0.12],
    };
    const PHASE_ORDER = ['base', 'build', 'peak', 'taper'];

    const PER_TYPE_ORDER = ['easy', 'long', 'tempo', 'interval', 'hill'];

    AD.loadSignals = async function (planId) {
        const prompt = document.getElementById('signalsPrompt');
        const loading = document.getElementById('signalsLoading');
        const content = document.getElementById('signalsContent');
        const empty = document.getElementById('signalsEmpty');
        if (!content) return;

        if (!planId) {
            this.signalsLoadedPlanId = null;
            this._show(prompt); this._hide(loading); this._hide(content); this._hide(empty);
            return;
        }

        this._hide(prompt); this._hide(empty); this._hide(content); this._show(loading);

        try {
            const [summary, history, signalHistory, readinessTrend] = await Promise.all([
                this._fetchJson('/api/analytics/coach-summary/' + encodeURIComponent(planId)),
                this._fetchJson('/api/analytics/adaptation-history/' + encodeURIComponent(planId)),
                this._fetchJson('/api/analytics/signal-history/' + encodeURIComponent(planId)),
                this._fetchJson('/api/analytics/readiness-trend'),
            ]);

            this._hide(loading);

            if (!summary || summary.available === false) {
                const text = document.getElementById('signalsEmptyText');
                if (text && summary && summary.reason) text.textContent = summary.reason;
                this._show(empty);
                this.signalsLoadedPlanId = planId;
                return;
            }

            this._show(content);
            this._renderSignalsOverview(summary, signalHistory);
            if (this.renderSignalChart) this.renderSignalChart(summary.signals || {});
            this._renderSignalsDetail(summary, readinessTrend);
            this._renderPhaseWeights(summary.current_phase);
            this._renderAdaptationHistory(history);
            this.signalsLoadedPlanId = planId;
        } catch (err) {
            console.error('Signals load error:', err);
            this._hide(loading);
            this._show(empty);
        }
    };

    /* ----- Overview: stance chip, headline, signal table ----- */
    AD._renderSignalsOverview = function (summary, signalHistory) {
        const chip = document.getElementById('coachMultiplierChip');
        if (chip) {
            const mult = typeof summary.multiplier === 'number' ? summary.multiplier : 1.0;
            const pct = Math.round((mult - 1) * 100);
            const dirClass = summary.direction === 'increase' ? 'up' : summary.direction === 'decrease' ? 'down' : 'flat';
            chip.className = 'coach-mult-chip coach-mult-chip--' + dirClass;
            chip.textContent = pct === 0 ? 'Hold ×1.00' : `${pct > 0 ? '+' : ''}${pct}% · ×${mult.toFixed(2)}`;
        }

        const why = document.getElementById('coachWhy');
        if (why) why.textContent = summary.headline_reason || '';

        const wrap = document.getElementById('signalsTable');
        if (!wrap) return;

        const snapshots = (signalHistory && signalHistory.snapshots) || [];
        const signalsBlock = summary.signals || {};

        let rows = '';
        for (const sig of SIGNALS) {
            const s = signalsBlock[sig.key] || {};
            const hasData = s.has_data !== false;
            const factor = typeof s.factor === 'number' ? s.factor : null;
            const weight = Math.round((s.weight || 0) * 100);
            const dir = !hasData || factor == null ? 'none' : factor > 1.02 ? 'up' : factor < 0.98 ? 'down' : 'flat';
            const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : dir === 'flat' ? '—' : '';
            const spark = this._signalSpark(snapshots, sig.key);
            const status = this._signalStatus(sig.key, s, summary);

            rows +=
                `<div class="signal-row${hasData ? '' : ' is-muted'}">` +
                `<div class="signal-row-name"><span class="signal-row-label">${this._esc(sig.label)}</span>` +
                `<span class="signal-row-desc">${this._esc(sig.desc)}</span></div>` +
                `<div class="signal-row-factor signal-dir--${dir}">${arrow} ${hasData && factor != null ? factor.toFixed(2) : '—'}</div>` +
                `<div class="signal-row-weight"><div class="signal-weight-bar"><div class="signal-weight-fill" style="width:${weight}%"></div></div><span class="signal-weight-pct">${weight}%</span></div>` +
                `<div class="signal-row-spark">${spark}</div>` +
                `<div class="signal-row-status signal-status--${this._esc(status.tone)}">${this._esc(status.text)}</div>` +
                '</div>';
        }

        wrap.innerHTML =
            '<div class="signal-row signal-row--head">' +
            '<div class="signal-row-name">Signal</div>' +
            '<div class="signal-row-factor">Factor</div>' +
            '<div class="signal-row-weight">Weight</div>' +
            '<div class="signal-row-spark">Trend</div>' +
            '<div class="signal-row-status">Status</div></div>' + rows;
    };

    AD._signalStatus = function (key, s, summary) {
        if (s.has_data === false) return { text: 'No data yet', tone: 'muted' };
        const f = typeof s.factor === 'number' ? s.factor : 1.0;
        const above = f > 1.02, below = f < 0.98;
        switch (key) {
            case 'volume':
                return above ? { text: 'Above plan', tone: 'up' } : below ? { text: 'Below plan', tone: 'down' } : { text: 'On plan', tone: 'flat' };
            case 'effort': {
                const t = summary.effort_trend;
                if (t === 'increasing') return { text: 'Effort climbing', tone: 'down' };
                if (t === 'decreasing') return { text: 'Feeling easier', tone: 'up' };
                return { text: 'Steady', tone: 'flat' };
            }
            case 'completion':
                return above ? { text: 'Strong adherence', tone: 'up' } : below ? { text: 'Lagging', tone: 'down' } : { text: 'On track', tone: 'flat' };
            case 'hr_zone': {
                const t = summary.hr_zone_trend;
                if (t === 'increasing') return { text: 'Improving', tone: 'up' };
                if (t === 'decreasing') return { text: 'Drifting high', tone: 'down' };
                return { text: 'On target', tone: 'flat' };
            }
            case 'feedback':
                return above ? { text: 'Mostly positive', tone: 'up' } : below ? { text: 'Cautionary', tone: 'down' } : { text: 'Balanced', tone: 'flat' };
            case 'readiness':
                return above ? { text: 'Fresh', tone: 'up' } : below ? { text: 'Below average', tone: 'down' } : { text: 'Steady', tone: 'flat' };
            default:
                return { text: '—', tone: 'flat' };
        }
    };

    /** Compact factor sparkline for one signal across adaptation snapshots. */
    AD._signalSpark = function (snapshots, key) {
        if (!snapshots || snapshots.length < 2) return '<span class="signal-spark-empty">—</span>';
        const vals = snapshots.map((s) => {
            const sig = (s.signals || {})[key];
            return sig && typeof sig.factor === 'number' ? sig.factor : null;
        }).filter((v) => v != null);
        if (vals.length < 2) return '<span class="signal-spark-empty">—</span>';
        return this._sparkline(vals, 1.0);
    };

    /* ----- Expandable detail cards ----- */
    AD._renderSignalsDetail = function (summary, readinessTrend) {
        const wrap = document.getElementById('signalsDetail');
        if (!wrap) return;

        const cards = [
            this._volumeDetail(summary),
            this._effortDetail(summary),
            this._hrDetail(summary),
            this._readinessDetail(summary, readinessTrend),
        ];
        wrap.innerHTML = cards.join('');
    };

    AD._detailCard = function (title, factor, summaryText, bodyHtml, open) {
        const f = typeof factor === 'number' ? factor.toFixed(2) : '—';
        const fClass = typeof factor === 'number' ? (factor > 1.02 ? 'up' : factor < 0.98 ? 'down' : 'flat') : 'flat';
        return (
            `<details class="signal-detail-card"${open ? ' open' : ''}>` +
            '<summary class="signal-detail-summary">' +
            `<span class="signal-detail-title">${this._esc(title)}</span>` +
            `<span class="signal-detail-factor signal-dir--${fClass}">${f}</span>` +
            `<span class="signal-detail-sub">${this._esc(summaryText)}</span>` +
            '<span class="signal-detail-caret">▾</span>' +
            '</summary>' +
            `<div class="signal-detail-body">${bodyHtml}</div>` +
            '</details>'
        );
    };

    AD._volumeDetail = function (summary) {
        const ratios = summary.per_type_ratios || {};
        const keys = PER_TYPE_ORDER.filter((k) => k in ratios);
        let bars = '';
        if (keys.length === 0) {
            bars = '<p class="signal-detail-empty">Per-type ratios appear once you log a few of each workout type.</p>';
        } else {
            bars = '<div class="pertype-list">' + keys.map((k) => {
                const r = ratios[k];
                const pct = Math.min(100, Math.max(0, (r / 1.5) * 100));
                const tone = r > 1.03 ? 'up' : r < 0.97 ? 'down' : 'flat';
                return (
                    '<div class="pertype-row">' +
                    `<span class="pertype-label">${this._esc(this._titleCase(k))}</span>` +
                    `<div class="pertype-track"><div class="pertype-fill pertype-fill--${tone}" style="width:${pct}%"></div>` +
                    '<span class="pertype-baseline"></span></div>' +
                    `<span class="pertype-val signal-dir--${tone}">${r.toFixed(2)}</span>` +
                    '</div>'
                );
            }).join('') + '</div>' +
            '<p class="signal-detail-note">Ratios above 1.0 mean you ran more than planned for that type; below 1.0 means less. Low-sample types are pulled toward your overall volume until more data arrives.</p>';
        }
        return this._detailCard('Volume', summary.signals?.volume?.factor,
            'Actual vs planned distance, per workout type', bars, true);
    };

    AD._effortDetail = function (summary) {
        const trend = summary.effort_trend || 'stable';
        const drift = summary.quality_drift;
        const trendText = trend === 'increasing'
            ? 'Perceived effort is climbing — your coach watches for fatigue.'
            : trend === 'decreasing'
                ? 'Runs are feeling easier — a sign fitness is adapting.'
                : 'Perceived effort is holding steady.';
        let driftHtml = '';
        if (typeof drift === 'number') {
            const dTone = drift > 0 ? 'up' : drift < 0 ? 'down' : 'flat';
            const dText = drift > 0 ? 'improving' : drift < 0 ? 'declining' : 'flat';
            driftHtml = `<div class="signal-chip signal-chip--${dTone}">Quality drift ${drift > 0 ? '+' : ''}${drift.toFixed(2)} (${dText})</div>`;
        }
        const body =
            `<p class="signal-detail-text">${this._esc(trendText)}</p>` +
            `<div class="signal-chip-row"><div class="signal-chip">Trend: ${this._esc(this._titleCase(trend))}</div>${driftHtml}</div>`;
        return this._detailCard('Effort', summary.signals?.effort?.factor,
            'How hard your runs feel, and whether that is drifting', body, false);
    };

    AD._hrDetail = function (summary) {
        const trend = summary.hr_zone_trend || 'stable';
        const hasData = summary.signals?.hr_zone?.has_data !== false;
        let body;
        if (!hasData) {
            body = '<p class="signal-detail-empty">Set heart-rate zones and log runs with HR data to unlock zone adherence.</p>';
        } else {
            const trendText = trend === 'increasing'
                ? 'Zone adherence is improving — you are staying closer to target.'
                : trend === 'decreasing'
                    ? 'Runs are drifting above target zones — ease the intensity on easy days.'
                    : 'Zone adherence is holding steady.';
            body = `<p class="signal-detail-text">${this._esc(trendText)}</p>` +
                `<div class="signal-chip-row"><div class="signal-chip">Trend: ${this._esc(this._titleCase(trend))}</div></div>`;
        }
        return this._detailCard('HR Zone', summary.signals?.hr_zone?.factor,
            'How well you stay in your target heart-rate zones', body, false);
    };

    AD._readinessDetail = function (summary, readinessTrend) {
        const logs = (readinessTrend && readinessTrend.logs) || [];
        const latest = logs.length ? logs[logs.length - 1] : null;
        let body;
        if (!latest || !latest.components) {
            body = '<p class="signal-detail-empty">Log daily check-ins (sleep, soreness, energy, stress) to feed this signal.</p>';
        } else {
            const c = latest.components;
            const rows = [
                ['Sleep', c.sleep, false],
                ['Soreness', c.soreness, true],
                ['Energy', c.energy, false],
                ['Stress', c.stress, true],
            ].map(([label, val, inverse]) => {
                if (val == null) return '';
                const pct = (val / 5) * 100;
                const good = inverse ? val <= 2 : val >= 4;
                const bad = inverse ? val >= 4 : val <= 2;
                const tone = good ? 'up' : bad ? 'down' : 'flat';
                return (
                    '<div class="readiness-comp-row">' +
                    `<span class="readiness-comp-label">${this._esc(label)}${inverse ? ' <span class="readiness-comp-hint">(lower is better)</span>' : ''}</span>` +
                    `<div class="readiness-comp-track"><div class="readiness-comp-fill readiness-comp-fill--${tone}" style="width:${pct}%"></div></div>` +
                    `<span class="readiness-comp-val">${val}/5</span></div>`
                );
            }).join('');
            const avg = readinessTrend.avg_7d != null ? `<p class="signal-detail-note">7-day average score: ${readinessTrend.avg_7d}/100 · trend ${this._esc(readinessTrend.trend || 'stable')}.</p>` : '';
            body = `<div class="readiness-comp-list">${rows}</div>${avg}`;
        }
        return this._detailCard('Readiness', summary.signals?.readiness?.factor,
            'Daily wellness check-ins feeding the plan', body, false);
    };

    /* ----- Phase weight comparison ----- */
    AD._renderPhaseWeights = function (currentPhase) {
        const intro = document.getElementById('signalsPhaseIntro');
        const wrap = document.getElementById('signalsPhaseTable');
        if (!wrap) return;

        if (intro) {
            intro.textContent =
                'Each signal counts differently depending on your training phase. Volume dominates early; ' +
                'as you approach your race, completion, HR-zone adherence and readiness gain weight.';
        }

        let head = '<div class="phase-row phase-row--head"><div class="phase-cell-label">Signal</div>';
        for (const ph of PHASE_ORDER) {
            const active = ph === currentPhase ? ' is-active' : '';
            head += `<div class="phase-cell${active}">${this._titleCase(ph)}</div>`;
        }
        head += '</div>';

        let body = '';
        SIGNALS.forEach((sig, idx) => {
            body += `<div class="phase-row"><div class="phase-cell-label">${this._esc(sig.label)}</div>`;
            for (const ph of PHASE_ORDER) {
                const w = PHASE_WEIGHTS[ph][idx];
                const pct = Math.round(w * 100);
                const active = ph === currentPhase ? ' is-active' : '';
                body += `<div class="phase-cell${active}"><div class="phase-bar"><div class="phase-bar-fill" style="width:${Math.min(100, w * 250)}%"></div></div><span class="phase-pct">${pct}%</span></div>`;
            }
            body += '</div>';
        });

        wrap.innerHTML = head + body;
    };
})();
