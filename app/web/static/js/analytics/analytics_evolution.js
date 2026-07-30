/**
 * analytics_evolution.js - Evolution Over Time tab for AnalyticsDashboard
 *
 * Handles period controls, data filtering/grouping, summary stats, and
 * four evolution charts: pace, VDOT, aerobic efficiency, and volume.
 */
(function() {
    const AD = window.AnalyticsDashboard;

    /* ------------------------------------------------------------------ */
    /*  Evolution data window                                              */
    /*                                                                     */
    /*  Evolution shares the global period selector (header dropdown).     */
    /*  We track which period the charts were last rendered for so we can  */
    /*  re-render lazily when the user changes the period elsewhere.       */
    /* ------------------------------------------------------------------ */

    AD.loadEvolution = async function() {
        const emptyEl = document.getElementById('evolutionEmpty');
        const syncEl  = document.getElementById('evolutionSyncIndicator');
        if (syncEl) syncEl.style.display = 'flex';
        this.evolutionLoadedForDays = this.currentPeriodDays;
        try {
            if (this.activityProvider) {
                await this.syncActivityPeriod(this.periodSyncDays(this.currentPeriodDays));
                await this.reloadRuns();
            }
            const evoRuns = this._filterEvolutionRuns();
            const weeks   = this._groupEvolutionByWeek(evoRuns);
            if (weeks.length < 2) {
                if (emptyEl) emptyEl.style.display = 'block';
                return;
            }
            if (emptyEl) emptyEl.style.display = 'none';
            this.renderEvolutionStats(evoRuns, weeks);
            this.renderEvoPaceChart(weeks);
            this.renderEvoVdotChart(weeks);
            this.renderEvoEffChart(weeks);
            this.renderEvoVolumeChart(weeks);
        } catch (err) {
            console.error('Evolution load error:', err);
        } finally {
            if (syncEl) syncEl.style.display = 'none';
        }
    };

    AD._filterEvolutionRuns = function() {
        const window = this.periodWindow(this.currentPeriodDays);
        if (!window) return [...this.allRuns];
        return this.allRuns.filter(r => r.date && new Date(r.date) >= window.start);
    };

    AD._groupEvolutionByWeek = function(runs) {
        const buckets = {};
        for (const r of runs) {
            if (!r.date) continue;
            const d   = new Date(r.date);
            const mon = this.startOfWeek(d);
            const key = `${mon.getFullYear()}-${String(mon.getMonth()+1).padStart(2,'0')}-${String(mon.getDate()).padStart(2,'0')}`;
            if (!buckets[key]) buckets[key] = [];
            buckets[key].push(r);
        }
        return Object.keys(buckets).sort().map(key => {
            const group    = buckets[key];
            const paceRuns = group.filter(r => r.avg_pace_min_km > 0);
            const avgPace  = paceRuns.length ? paceRuns.reduce((s, r) => s + r.avg_pace_min_km, 0) / paceRuns.length : null;
            const vdotRuns = group.filter(r => r.vdot > 0);
            const bestVdot = vdotRuns.length ? Math.max(...vdotRuns.map(r => r.vdot)) : null;
            const effRuns  = group.filter(r => r.avg_pace_min_km > 0 && r.avg_heart_rate > 0);
            // Aerobic Efficiency: speed (m/min) / heart rate x 100
            const avgEff   = effRuns.length ? effRuns.reduce((s, r) => s + (1000 / r.avg_pace_min_km) / r.avg_heart_rate * 100, 0) / effRuns.length : null;
            const totalKm  = group.reduce((s, r) => s + (r.distance_km || 0), 0);
            const [y, m, day] = key.split('-').map(Number);
            const label    = new Date(y, m - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            return { key, label, avgPace, bestVdot, avgEff, totalKm, runCount: group.length };
        });
    };

    /* ------------------------------------------------------------------ */
    /*  Evolution Summary Stats                                            */
    /* ------------------------------------------------------------------ */
    AD.renderEvolutionStats = function(evoRuns, weeks) {
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        const badge = (id, text, cls) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.textContent = text;
            el.className = 'evolution-stat-badge ' + cls;
        };
        const n          = weeks.length;
        const sliceSize  = Math.max(1, Math.ceil(n / 4));
        const firstSlice = weeks.slice(0, sliceSize);
        const lastSlice  = weeks.slice(-sliceSize);

        // Pace: positive diff = faster now
        const fp = firstSlice.map(w => w.avgPace).filter(Boolean);
        const lp = lastSlice.map(w => w.avgPace).filter(Boolean);
        if (fp.length && lp.length) {
            const fAvg = fp.reduce((a, b) => a + b, 0) / fp.length;
            const lAvg = lp.reduce((a, b) => a + b, 0) / lp.length;
            const diff = Math.round((fAvg - lAvg) * 60);
            set('evoStatPaceChange', `${diff > 0 ? '-' : '+'}${Math.abs(diff)}s`);
            badge('evoStatPaceBadge',
                diff > 3 ? 'Faster ↑' : diff < -3 ? 'Slower ↓' : 'Stable →',
                Math.abs(diff) <= 3 ? 'trend-neutral' : diff > 0 ? 'trend-up' : 'trend-down');
            set('evoStatPaceSub', `${this.formatPace(fAvg)} → ${this.formatPace(lAvg)}`);
        } else {
            set('evoStatPaceChange', '--');
            set('evoStatPaceSub', 'No pace data');
        }

        // VDOT
        const fv = firstSlice.map(w => w.bestVdot).filter(Boolean);
        const lv = lastSlice.map(w => w.bestVdot).filter(Boolean);
        if (fv.length && lv.length) {
            const delta = (Math.max(...lv) - Math.max(...fv)).toFixed(1);
            set('evoStatVdotChange', `${parseFloat(delta) > 0 ? '+' : ''}${delta}`);
            badge('evoStatVdotBadge',
                parseFloat(delta) > 0.5 ? 'Improving ↑' : parseFloat(delta) < -0.5 ? 'Declining ↓' : 'Stable →',
                Math.abs(delta) < 0.5 ? 'trend-neutral' : parseFloat(delta) > 0 ? 'trend-up' : 'trend-down');
            set('evoStatVdotSub', `${Math.max(...fv).toFixed(1)} → ${Math.max(...lv).toFixed(1)} VDOT`);
        } else {
            set('evoStatVdotChange', '--');
            set('evoStatVdotSub', 'No VDOT data');
        }

        // Aerobic efficiency
        const fe = firstSlice.map(w => w.avgEff).filter(Boolean);
        const le = lastSlice.map(w => w.avgEff).filter(Boolean);
        if (fe.length && le.length) {
            const fa  = fe.reduce((a, b) => a + b, 0) / fe.length;
            const la  = le.reduce((a, b) => a + b, 0) / le.length;
            const pct = ((la - fa) / fa * 100).toFixed(1);
            set('evoStatEffChange', `${parseFloat(pct) > 0 ? '+' : ''}${pct}%`);
            badge('evoStatEffBadge',
                parseFloat(pct) > 1 ? 'Improving ↑' : parseFloat(pct) < -1 ? 'Declining ↓' : 'Stable →',
                Math.abs(pct) < 1 ? 'trend-neutral' : parseFloat(pct) > 0 ? 'trend-up' : 'trend-down');
            set('evoStatEffSub', `${fa.toFixed(2)} → ${la.toFixed(2)} EF`);
        } else {
            set('evoStatEffChange', '--');
            set('evoStatEffSub', 'No HR data');
        }

        // Total runs
        set('evoStatTotalRuns', evoRuns.length);
        badge('evoStatRunsBadge', `${n}w`, 'trend-neutral');
        set('evoStatRunsSub', `${(evoRuns.length / Math.max(1, n)).toFixed(1)} runs/week avg`);
    };

    /* ------------------------------------------------------------------ */
    /*  Trend Badge Helper                                                 */
    /* ------------------------------------------------------------------ */
    AD._evolutionTrendBadge = function(values, badgeId, annotationId, lowerIsBetter) {
        const badgeEl = document.getElementById(badgeId);
        if (!badgeEl) return;
        const valid = values.filter(v => v != null);
        if (valid.length < 3) return;
        const trend = this.computeTrendLine(values);
        const first = trend.find(v => v != null);
        const last  = [...trend].reverse().find(v => v != null);
        if (!first || !last || first === 0) return;
        const pct       = ((last - first) / Math.abs(first)) * 100;
        const improving = lowerIsBetter ? pct < -1 : pct > 1;
        const declining = lowerIsBetter ? pct > 1  : pct < -1;
        const cls   = improving ? 'trend-up' : declining ? 'trend-down' : 'trend-neutral';
        const arrow = improving ? '↑' : declining ? '↓' : '→';
        badgeEl.textContent = `${arrow} ${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`;
        badgeEl.className = 'evolution-trend-badge ' + cls;
        if (annotationId) {
            const ann = document.getElementById(annotationId);
            if (ann) ann.textContent = improving ? 'Trend: Improving' : declining ? 'Trend: Declining' : 'Trend: Stable';
        }
    };

    /* ------------------------------------------------------------------ */
    /*  Evolution Charts                                                   */
    /* ------------------------------------------------------------------ */
    AD.renderEvoPaceChart = function(weeks) {
        const card = document.getElementById('evoPaceChartCard');
        if (!card) return;
        const labels = weeks.map(w => w.label);
        const values = weeks.map(w => w.avgPace);
        if (!values.some(v => v != null)) { card.style.display = 'none'; return; }
        card.style.display = '';
        const trend = this.computeTrendLine(values);
        this._evolutionTrendBadge(values, 'evoPaceTrendBadge', 'evoPaceAnnotation', true);
        if (this.evolutionCharts.pace) this.evolutionCharts.pace.destroy();
        const ctx  = document.getElementById('evoPaceChart').getContext('2d');
        const opts = this._baseChartOptions(3.0, {
            reverse: true,
            ticks: { callback: v => this.formatPace(v), font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.legend  = { display: false };
        opts.plugins.tooltip = { callbacks: { label: c => c.dataset.label === 'Trend' ? null : `Avg pace: ${this.formatPace(c.parsed.y)}/km` } };
        this.evolutionCharts.pace = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets: [
                { label: 'Avg Pace', data: values, borderColor: this.COLORS.accent, backgroundColor: this.COLORS.accentFill, fill: true, tension: 0.35, pointRadius: 3, spanGaps: true },
                { label: 'Trend',    data: trend,  borderColor: 'rgba(255,98,70,0.45)', borderWidth: 2, borderDash: [5,4], pointRadius: 0, fill: false, tension: 0, spanGaps: true },
            ]},
            options: opts,
        });
    };

    AD.renderEvoVdotChart = function(weeks) {
        const card = document.getElementById('evoVdotChartCard');
        if (!card) return;
        const labels = weeks.map(w => w.label);
        const values = weeks.map(w => w.bestVdot);
        if (!values.some(v => v != null)) { card.style.display = 'none'; return; }
        card.style.display = '';
        const trend = this.computeTrendLine(values);
        this._evolutionTrendBadge(values, 'evoVdotTrendBadge', 'evoVdotAnnotation', false);
        if (this.evolutionCharts.vdot) this.evolutionCharts.vdot.destroy();
        const ctx  = document.getElementById('evoVdotChart').getContext('2d');
        const minV = Math.max(0, Math.min(...values.filter(Boolean)) - 2);
        const opts = this._baseChartOptions(3.0, {
            suggestedMin: minV,
            ticks: { callback: v => v != null ? v.toFixed(1) : '', font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.tooltip = { callbacks: { label: c => c.dataset.label === 'Trend' ? null : `VDOT: ${c.parsed.y != null ? c.parsed.y.toFixed(1) : '--'}` } };
        this.evolutionCharts.vdot = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets: [
                { label: 'Weekly Best VDOT', data: values, borderColor: this.COLORS.purple, backgroundColor: this.COLORS.purpleFill, fill: true, tension: 0.35, pointRadius: 3, spanGaps: true },
                { label: 'Trend',            data: trend,  borderColor: 'rgba(124,58,237,0.45)', borderWidth: 2, borderDash: [5,4], pointRadius: 0, fill: false, tension: 0, spanGaps: true },
            ]},
            options: opts,
        });
    };

    AD.renderEvoEffChart = function(weeks) {
        const card = document.getElementById('evoEffChartCard');
        if (!card) return;
        const labels = weeks.map(w => w.label);
        const values = weeks.map(w => w.avgEff);
        if (!values.some(v => v != null)) { card.style.display = 'none'; return; }
        card.style.display = '';
        const trend = this.computeTrendLine(values);
        this._evolutionTrendBadge(values, 'evoEffTrendBadge', 'evoEffAnnotation', false);
        if (this.evolutionCharts.eff) this.evolutionCharts.eff.destroy();
        const ctx   = document.getElementById('evoEffChart').getContext('2d');
        const opts  = this._baseChartOptions(3.0, {
            ticks: { callback: v => v != null ? v.toFixed(2) : '', font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        const rating = v => v >= 85 ? 'Excellent' : v >= 70 ? 'Good' : v >= 55 ? 'Developing' : 'Building';
        opts.plugins.tooltip = { callbacks: { label: c => c.dataset.label === 'Trend' ? null : `EF: ${c.parsed.y?.toFixed(2)} — ${rating(c.parsed.y)}` } };
        this.evolutionCharts.eff = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets: [
                { label: 'Aerobic Efficiency', data: values, borderColor: this.COLORS.secondary, backgroundColor: this.COLORS.secondaryFill, fill: true, tension: 0.35, pointRadius: 3, spanGaps: true },
                { label: 'Trend',              data: trend,  borderColor: 'rgba(13,148,136,0.45)', borderWidth: 2, borderDash: [5,4], pointRadius: 0, fill: false, tension: 0, spanGaps: true },
            ]},
            options: opts,
        });
    };

    AD.renderEvoVolumeChart = function(weeks) {
        const card = document.getElementById('evoVolumeChartCard');
        if (!card) return;
        const labels = weeks.map(w => w.label);
        const values = weeks.map(w => parseFloat(w.totalKm.toFixed(1)));
        if (values.every(v => v === 0)) { card.style.display = 'none'; return; }
        card.style.display = '';
        this._evolutionTrendBadge(values, 'evoVolumeTrendBadge', null, false);
        if (this.evolutionCharts.volume) this.evolutionCharts.volume.destroy();
        const ctx  = document.getElementById('evoVolumeChart').getContext('2d');
        const opts = this._baseChartOptions(3.5, {
            beginAtZero: true,
            ticks: { callback: v => `${v} km`, font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.tooltip = { callbacks: { label: c => `Volume: ${c.parsed.y.toFixed(1)} km` } };
        this.evolutionCharts.volume = new Chart(ctx, {
            type: 'bar',
            data: { labels, datasets: [{
                label: 'Weekly Volume', data: values,
                backgroundColor: this.COLORS.primaryFill, borderColor: this.COLORS.primary,
                borderWidth: 1.5, borderRadius: 4, borderSkipped: false,
            }]},
            options: opts,
        });
    };
})();
