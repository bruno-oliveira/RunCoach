/**
 * analytics_charts.js - Chart rendering for AnalyticsDashboard
 *
 * Renders: Pace trend, Distance/volume bar, Aerobic Efficiency line,
 * and Pace Zone doughnut charts.
 */
(function() {
    const AD = window.AnalyticsDashboard;

    /* ------------------------------------------------------------------ */
    /*  Aerobic Efficiency Chart                                           */
    /* ------------------------------------------------------------------ */
    AD.renderEfficiencyChart = function(grouping) {
        const data   = this.getGroupedData(grouping);
        const labels = data.map(d => d.label);
        const values = data.map(d => d.avgEfficiency);
        if (!values.some(v => v != null)) { this.hideChart('efficiencyChartCard'); return; }
        this.showChart('efficiencyChartCard');
        const trend = this.computeTrendLine(values.map(v => v ?? null));

        // Compute improvement for badge
        const validValues = values.filter(v => v != null);
        this._renderEfficiencyBadge(validValues);

        this.destroyChart('efficiencyChart');
        const ctx = document.getElementById('efficiencyChart').getContext('2d');
        const opts = this._baseChartOptions(2.2, {
            ticks: { callback: v => v != null ? v.toFixed(2) : '', font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.tooltip = {
            callbacks: {
                label: c => {
                    if (c.dataset.label === 'Trend') return null;
                    const v = c.parsed.y;
                    if (v == null) return '--';
                    const rating = v >= 0.85 ? 'Excellent' : v >= 0.70 ? 'Good' : v >= 0.55 ? 'Developing' : 'Building';
                    return `EF: ${v.toFixed(3)} — ${rating}  (speed/HR × 100)`;
                },
            },
        };

        this.charts.efficiencyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Aerobic Efficiency',
                        data: values,
                        borderColor: this.COLORS.secondary,
                        backgroundColor: this.COLORS.secondaryFill,
                        fill: true,
                        tension: 0.35,
                        pointRadius: 3,
                        pointBackgroundColor: this.COLORS.secondary,
                        pointHoverRadius: 5,
                        spanGaps: true,
                    },
                    {
                        label: 'Trend',
                        data: trend,
                        borderColor: this.COLORS.accent,
                        borderWidth: 1.5,
                        borderDash: [4, 3],
                        pointRadius: 0,
                        fill: false,
                        tension: 0,
                    },
                ],
            },
            options: opts,
        });
    };

    AD._renderEfficiencyBadge = function(validValues) {
        const header = document.querySelector('#efficiencyChartCard .analytics-card-header');
        if (!header) return;
        const old = header.querySelector('.efficiency-trend-badge');
        if (old) old.remove();

        if (validValues.length < 3) return;
        const first = validValues.slice(0, Math.ceil(validValues.length / 3));
        const last  = validValues.slice(-Math.ceil(validValues.length / 3));
        const avgFirst = first.reduce((a, b) => a + b, 0) / first.length;
        const avgLast  = last.reduce((a, b) => a + b, 0) / last.length;
        const pctChange = ((avgLast - avgFirst) / avgFirst * 100).toFixed(1);

        const badge = document.createElement('span');
        const improving = pctChange > 1;
        const declining = pctChange < -1;
        badge.className = 'efficiency-trend-badge ' + (improving ? 'trend-up' : declining ? 'trend-down' : 'trend-neutral');
        badge.textContent = `${pctChange > 0 ? '+' : ''}${pctChange}%`;
        badge.title = improving ? 'Aerobic fitness improving' : declining ? 'Aerobic fitness declining' : 'Aerobic fitness stable';

        const select = header.querySelector('.grouping-select');
        if (select) header.insertBefore(badge, select);
        else header.appendChild(badge);
    };

    /* ------------------------------------------------------------------ */
    /*  Pace Zone Distribution                                             */
    /* ------------------------------------------------------------------ */
    AD.paceZoneData = null;

    AD.renderPaceZonesChart = async function() {
        const card = document.getElementById('paceZonesCard');
        if (!card) return;

        // Fetch zones if not yet loaded
        if (!this.paceZoneData) {
            try {
                const res = await fetch('/api/analytics/pace-zones', { credentials: 'same-origin' });
                if (!res.ok) { card.style.display = 'none'; return; }
                const data = await res.json();
                if (!data.available) { card.style.display = 'none'; return; }
                this.paceZoneData = data;
            } catch { card.style.display = 'none'; return; }
        }

        const zones = this.paceZoneData.zones;
        const runs = this.runs.filter(r => r.avg_pace_min_km && r.avg_pace_min_km > 0);
        if (runs.length === 0) { card.style.display = 'none'; return; }

        // Zone boundaries (faster = lower pace number)
        // R < I < T < M < E_slow  (pace in min/km, lower = faster)
        const boundaries = [
            { name: 'Repetition', key: 'R', min: 0,                          max: zones.R.pace_min_km, color: '#EF4444' },
            { name: 'Interval',   key: 'I', min: zones.R.pace_min_km,        max: zones.I.pace_min_km, color: '#F97316' },
            { name: 'Threshold',  key: 'T', min: zones.I.pace_min_km,        max: zones.T.pace_min_km, color: '#EAB308' },
            { name: 'Marathon',   key: 'M', min: zones.T.pace_min_km,        max: zones.M.pace_min_km, color: '#3B82F6' },
            { name: 'Easy',       key: 'E', min: zones.M.pace_min_km,        max: 99,                  color: '#10B981' },
        ];

        // Classify runs by total distance in each zone
        const zoneKm = boundaries.map(() => 0);
        for (const r of runs) {
            const pace = r.avg_pace_min_km;
            for (let i = 0; i < boundaries.length; i++) {
                if (pace >= boundaries[i].min && pace < boundaries[i].max) {
                    zoneKm[i] += r.distance_km || 0;
                    break;
                }
            }
            // Catch very slow runs in Easy
            if (pace >= boundaries[boundaries.length - 1].min) {
                zoneKm[boundaries.length - 1] += r.distance_km || 0;
            }
        }

        const totalKm = zoneKm.reduce((a, b) => a + b, 0);
        if (totalKm === 0) { card.style.display = 'none'; return; }

        card.style.display = '';

        // Show 80/20 badge
        const easyPct = (zoneKm[4] + zoneKm[3]) / totalKm * 100; // Easy + Marathon = low intensity
        const badge = document.getElementById('paceZonesBadge');
        if (badge) {
            const ratio = Math.round(easyPct);
            badge.textContent = `${ratio}/${100 - ratio} split`;
            badge.title = `${ratio}% low intensity / ${100 - ratio}% high intensity`;
        }

        this.destroyChart('paceZonesChart');
        const ctx = document.getElementById('paceZonesChart');
        if (!ctx) return;

        this.charts.paceZonesChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: boundaries.map(b => b.name),
                datasets: [{
                    data: zoneKm.map(v => parseFloat(v.toFixed(1))),
                    backgroundColor: boundaries.map(b => b.color),
                    borderWidth: 2,
                    borderColor: 'var(--color-bg, #fff)',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: this._mobileRatio(1.8, 1.4),
                cutout: '55%',
                plugins: {
                    legend: {
                        display: true,
                        position: 'right',
                        labels: { boxWidth: 12, font: { size: 11 }, padding: 8 },
                    },
                    tooltip: {
                        callbacks: {
                            label: c => {
                                const km = c.parsed;
                                const pct = (km / totalKm * 100).toFixed(1);
                                return ` ${c.label}: ${km.toFixed(1)} km (${pct}%)`;
                            },
                        },
                    },
                },
            },
        });
    };

    /* ------------------------------------------------------------------ */
    /*  Pace Trend Chart                                                   */
    /* ------------------------------------------------------------------ */
    AD.renderPaceChart = function(grouping) {
        const data   = this.getGroupedData(grouping);
        const labels = data.map(d => d.label);
        const values = data.map(d => d.avgPace);
        if (!values.some(v => v != null)) { this.hideChart('paceChartCard'); return; }
        this.showChart('paceChartCard');
        const trend = this.computeTrendLine(values);

        this.destroyChart('paceChart');
        const ctx = document.getElementById('paceChart').getContext('2d');
        const opts = this._baseChartOptions(2.2, {
            reverse: true,
            ticks: { callback: v => this.formatPace(v), font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.tooltip = {
            callbacks: { label: c => c.dataset.label + ': ' + this.formatPace(c.parsed.y) },
        };

        this.charts.paceChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Avg Pace',
                        data: values,
                        borderColor: this.COLORS.accent,
                        backgroundColor: this.COLORS.accentFill,
                        fill: true,
                        tension: 0.35,
                        pointRadius: 3,
                        pointBackgroundColor: this.COLORS.accent,
                        pointHoverRadius: 5,
                    },
                    {
                        label: 'Trend',
                        data: trend,
                        borderColor: 'rgba(255,98,70,0.4)',
                        borderDash: [4, 4],
                        pointRadius: 0,
                        fill: false,
                        tension: 0,
                    },
                ],
            },
            options: opts,
        });
    };

    /* ------------------------------------------------------------------ */
    /*  Distance / Volume Bar Chart                                        */
    /* ------------------------------------------------------------------ */
    AD.renderDistanceChart = function(grouping) {
        const data   = this.getGroupedData(grouping);
        const labels = data.map(d => d.label);
        const values = data.map(d => d.totalKm);

        this.destroyChart('distanceChart');
        const ctx = document.getElementById('distanceChart').getContext('2d');
        const opts = this._baseChartOptions(2.8, {
            beginAtZero: true,
            ticks: { callback: v => `${v} km`, font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.tooltip = {
            callbacks: { label: c => `${c.parsed.y.toFixed(1)} km` },
        };

        this.charts.distanceChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Distance',
                    data: values,
                    backgroundColor: this.COLORS.primaryFill,
                    borderColor: this.COLORS.primary,
                    borderWidth: 1.5,
                    borderRadius: 5,
                    borderSkipped: false,
                }],
            },
            options: opts,
        });
    };
})();
