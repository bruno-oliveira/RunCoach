/**
 * analytics_plan.js - Plan-scoped features for AnalyticsDashboard
 *
 * Handles: Race Readiness, Gap Analysis, Gap Trend chart, and
 * Workout Adherence heatmap. All require a selected plan.
 */
(function() {
    const AD = window.AnalyticsDashboard;

    /* ------------------------------------------------------------------ */
    /*  Race Readiness (plan-scoped)                                       */
    /* ------------------------------------------------------------------ */
    AD.loadReadiness = async function(planId) {
        const loading = document.getElementById('analyticsReadinessLoading');
        const content = document.getElementById('analyticsReadinessContent');
        const empty   = document.getElementById('analyticsReadinessEmpty');
        if (!content) return;

        if (loading) loading.style.display = '';
        if (content) content.style.display = 'none';
        if (empty) empty.style.display = 'none';

        try {
            const res = await fetch('/api/plan/' + planId + '/readiness', { credentials: 'same-origin' });
            if (!res.ok) throw new Error('readiness fetch failed');
            const data = await res.json();

            if (loading) loading.style.display = 'none';
            if (!data.available) {
                if (empty) { empty.style.display = ''; empty.querySelector('p').textContent = data.reason || 'Not enough data yet.'; }
                return;
            }
            content.style.display = '';
            content.innerHTML = this._renderReadiness(data);
        } catch (err) {
            console.error('Readiness load error:', err);
            if (loading) loading.style.display = 'none';
            if (empty) { empty.style.display = ''; }
        }
    };

    AD._renderReadiness = function(d) {
        const scoreClass = d.overall_score >= 75 ? 'score-strong' : d.overall_score >= 50 ? 'score-good' : 'score-developing';

        let html = '<div class="readiness-hero">';
        html += `<div class="readiness-score-ring ${scoreClass}">`;
        html += `<span class="readiness-score-number">${d.overall_score}</span>`;
        html += '<span class="readiness-score-label">/ 100</span></div>';
        html += '<div class="readiness-hero-meta">';
        html += `<span class="readiness-hero-label">${this._esc(d.overall_label)}</span>`;
        html += `<span class="readiness-hero-sub">${this._esc(d.distance_label)} — ${d.weeks_remaining}w to race day</span>`;
        if (d.days_to_race != null) html += `<span class="readiness-hero-date">${this._esc(d.race_date_display)} (${d.days_to_race}d)</span>`;
        html += '</div></div>';

        // Component bars
        html += '<div class="readiness-components">';
        for (const [key, comp] of Object.entries(d.components)) {
            const label = key === 'fitness' ? 'Fitness (VDOT)' : key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
            html += `<div class="readiness-bar-row">`;
            html += `<span class="readiness-bar-label">${label}</span>`;
            html += `<div class="readiness-bar-track"><div class="readiness-bar-fill readiness-bar--${comp.label.toLowerCase().replace(/\s+/g, '-')}" style="width:${comp.score}%"></div></div>`;
            html += `<span class="readiness-bar-score">${comp.score}</span>`;
            html += '</div>';
            if (comp.detail) html += `<div class="readiness-bar-detail">${this._esc(comp.detail)}</div>`;
        }
        html += '</div>';

        // Mountain simulation proxies (only for trail + flat training setups)
        if (d.mountain_simulation) {
            const sim = d.mountain_simulation;
            const simClass = sim.score >= 75 ? 'sim-strong' : sim.score >= 50 ? 'sim-good' : 'sim-developing';
            html += `<div class="readiness-mountain ${simClass}">`;
            html += '<h4>Mountain Simulation (Flat Access)</h4>';
            html += `<div class="readiness-mountain-head"><span class="readiness-mountain-score">${sim.score}</span><span class="readiness-mountain-label">/ 100</span></div>`;
            if (sim.detail) html += `<div class="readiness-mountain-detail">${this._esc(sim.detail)}</div>`;
            html += '<div class="readiness-mountain-grid">';
            html += `<div class="mountain-metric"><span class="mountain-key">Uphill</span><span class="mountain-val">${sim.actual.uphill_effort_min || 0}/${sim.planned.uphill_effort_min || 0} min</span><span class="mountain-pct">${sim.completion_pct.uphill || 0}%</span></div>`;
            html += `<div class="mountain-metric"><span class="mountain-key">Downhill</span><span class="mountain-val">${sim.actual.downhill_eccentric_min || 0}/${sim.planned.downhill_eccentric_min || 0} min</span><span class="mountain-pct">${sim.completion_pct.downhill || 0}%</span></div>`;
            html += `<div class="mountain-metric"><span class="mountain-key">Transitions</span><span class="mountain-val">${sim.actual.hike_run_transition_reps || 0}/${sim.planned.hike_run_transition_reps || 0} reps</span><span class="mountain-pct">${sim.completion_pct.transitions || 0}%</span></div>`;
            html += '</div>';
            html += '<details class="readiness-mountain-explainer">';
            html += '<summary>How this score is computed</summary>';
            html += '<p>This score tracks how closely your logged runs match your weekly mountain-simulation targets while training on flat terrain. It combines uphill-effort minutes, downhill-eccentric minutes, and hike-run transitions. Higher completion means your flat training is better matching mountain race demands.</p>';
            html += '</details>';
            html += '</div>';
        }

        // Scenarios
        if (d.scenarios && d.scenarios.length > 0) {
            html += '<div class="readiness-scenarios"><h4>Race Scenarios</h4><div class="readiness-scenarios-grid">';
            for (const s of d.scenarios) {
                html += `<div class="readiness-scenario">`;
                html += `<span class="readiness-scenario-name">${this._esc(s.name)}</span>`;
                html += `<span class="readiness-scenario-time">${this._esc(s.time)}</span>`;
                html += `<span class="readiness-scenario-pace">${this._esc(s.pace)}</span>`;
                html += `<span class="readiness-scenario-prob">${s.probability}%</span>`;
                html += '</div>';
            }
            html += '</div></div>';
        }

        return html;
    };

    /* ------------------------------------------------------------------ */
    /*  Gap Analysis (plan-scoped)                                         */
    /* ------------------------------------------------------------------ */
    AD.loadGapAnalysis = async function(planId) {
        const loading = document.getElementById('analyticsGapLoading');
        const content = document.getElementById('analyticsGapContent');
        const empty   = document.getElementById('analyticsGapEmpty');
        if (!content) return;

        if (loading) loading.style.display = '';
        if (content) content.style.display = 'none';
        if (empty) empty.style.display = 'none';

        try {
            const res = await fetch('/api/plan/' + planId + '/gaps', { credentials: 'same-origin' });
            if (!res.ok) throw new Error('gap fetch failed');
            const data = await res.json();

            if (loading) loading.style.display = 'none';
            if (!data.available) {
                if (empty) { empty.style.display = ''; const p = empty.querySelector('p'); if (p) p.textContent = data.reason || 'Not enough data yet.'; }
                return;
            }
            content.style.display = '';
            content.innerHTML = this._renderGapAnalysis(data);
        } catch (err) {
            console.error('Gap analysis load error:', err);
            if (loading) loading.style.display = 'none';
            if (empty) empty.style.display = '';
        }
    };

    AD._renderGapAnalysis = function(data) {
        const verdictLabels = { on_track: 'On Track', close: 'Close', behind: 'Behind', far_behind: 'Far Behind', needs_attention: 'Needs Attention', insufficient_data: 'No Data' };
        const verdictColors = { on_track: '#16a34a', close: '#ca8a04', behind: '#ea580c', far_behind: '#dc2626', needs_attention: '#ea580c', insufficient_data: '#999' };

        let html = '';
        if (data.overall_verdict) {
            const vl = verdictLabels[data.overall_verdict] || data.overall_verdict;
            html += `<div class="gap-overall"><span class="gap-overall-label">Overall: </span><span class="gap-verdict gap-verdict--${data.overall_verdict}">${this._esc(vl)}</span></div>`;
        }

        if (data.dimensions) {
            html += '<div class="gap-dimensions">';
            for (const dim of data.dimensions) {
                const vl = verdictLabels[dim.verdict] || dim.verdict;
                const color = verdictColors[dim.verdict] || '#999';
                const pct = Math.min(100, Math.max(0, dim.pct || 0));
                html += '<div class="gap-dimension-row">';
                html += `<div class="gap-dim-header"><span class="gap-dim-label">${this._esc(dim.label)}</span><span class="gap-verdict gap-verdict--${dim.verdict}">${this._esc(vl)}</span></div>`;
                html += `<div class="gap-bar-track"><div class="gap-bar-fill" style="width:${pct}%;background:${color}"></div></div>`;
                if (dim.detail) html += `<div class="gap-dim-detail">${this._esc(dim.detail)}</div>`;
                html += '</div>';
            }
            html += '</div>';
        }

        return html;
    };

    /* ------------------------------------------------------------------ */
    /*  Gap Trend Chart (plan-scoped)                                      */
    /* ------------------------------------------------------------------ */
    AD.loadGapTrend = async function(planId) {
        const card = document.getElementById('gapTrendChartCard');
        if (!card) return;

        try {
            const res = await fetch('/api/analytics/gap-trend/' + planId, { credentials: 'same-origin' });
            if (!res.ok) { card.style.display = 'none'; return; }
            const data = await res.json();
            if (!data.available || !data.weeks || data.weeks.length === 0) {
                card.style.display = 'none';
                return;
            }

            card.style.display = '';
            const labels = data.weeks.map(w => 'W' + w.week);
            const volumePcts = data.weeks.map(w => w.volume_pct);
            const longRunPcts = data.weeks.map(w => w.long_run_pct);

            if (this.charts.gapTrend) this.charts.gapTrend.destroy();
            const ctx = document.getElementById('gapTrendChart');
            if (!ctx) return;

            this.charts.gapTrend = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Volume %',
                            data: volumePcts,
                            borderColor: this.COLORS.primary,
                            backgroundColor: this.COLORS.primaryFill,
                            fill: false,
                            tension: 0.3,
                        },
                        {
                            label: 'Long Run %',
                            data: longRunPcts,
                            borderColor: this.COLORS.accent,
                            backgroundColor: this.COLORS.accentFill,
                            fill: false,
                            tension: 0.3,
                        },
                        {
                            label: '100% Target',
                            data: labels.map(() => 100),
                            borderColor: 'rgba(0,0,0,0.15)',
                            borderDash: [4, 4],
                            pointRadius: 0,
                            fill: false,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: true, position: 'top' } },
                    scales: {
                        y: {
                            min: 0,
                            max: 150,
                            grid: { color: this.COLORS.grid },
                            ticks: { callback: v => v + '%' },
                        },
                        x: { grid: { display: false } },
                    },
                },
            });
        } catch (err) {
            console.error('Gap trend load error:', err);
            card.style.display = 'none';
        }
    };

    /* ------------------------------------------------------------------ */
    /*  Workout Adherence Heatmap (plan-scoped)                            */
    /* ------------------------------------------------------------------ */
    AD.loadAdherenceHeatmap = async function(planId) {
        const card = document.getElementById('adherenceHeatmapCard');
        const wrap = document.getElementById('adherenceHeatmap');
        if (!card || !wrap) return;

        try {
            const res = await fetch('/api/analytics/workout-adherence/' + planId, { credentials: 'same-origin' });
            if (!res.ok) { card.style.display = 'none'; return; }
            const data = await res.json();
            if (!data.available || !data.grid || data.grid.length === 0) {
                card.style.display = 'none';
                return;
            }

            card.style.display = '';
            const types = data.workout_types;
            const grid = data.grid;

            let html = '<table class="adherence-table">';
            html += '<thead><tr><th></th>';
            types.forEach(t => { html += '<th>' + t.charAt(0).toUpperCase() + t.slice(1) + '</th>'; });
            html += '</tr></thead><tbody>';

            grid.forEach(row => {
                html += '<tr>';
                html += '<td class="adherence-week-label">W' + row.week + '</td>';
                types.forEach(t => {
                    const status = row.cells[t] || 'future';
                    html += '<td><span class="adherence-cell adherence-cell--' + status + '" title="' + status + '"></span></td>';
                });
                html += '</tr>';
            });

            html += '</tbody></table>';
            wrap.innerHTML = html;
        } catch (err) {
            console.error('Adherence heatmap load error:', err);
            card.style.display = 'none';
        }
    };
})();
