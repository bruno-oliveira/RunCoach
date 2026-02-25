/**
 * Analytics Dashboard — client-side aggregation + Chart.js rendering.
 */
const AnalyticsDashboard = {
    allRuns: [],
    runs: [],
    charts: {},

    COLORS: {
        primary:      '#1D4ED8',
        primaryFill:  'rgba(29, 78, 216, 0.15)',
        accent:       '#FF6246',
        accentFill:   'rgba(255, 98, 70, 0.15)',
        secondary:    '#0D9488',
        secondaryFill:'rgba(13, 148, 136, 0.15)',
        trend:        'rgba(29, 78, 216, 0.45)',
    },

    /* ------------------------------------------------------------------ */
    /*  Init                                                               */
    /* ------------------------------------------------------------------ */
    async init() {
        const dashboard = document.getElementById('analyticsDashboard');
        const loading   = document.getElementById('analyticsLoading');
        const empty     = document.getElementById('analyticsEmpty');
        if (!dashboard) return;

        try {
            // Check if Strava is connected
            const stravaConnected = await this.checkStravaConnection();

            // If Strava connected, sync default period (30 days) before loading
            if (stravaConnected) {
                await this.syncStravaPeriod(30);
            }

            const res = await fetch('/api/analytics/runs', { credentials: 'same-origin' });
            if (!res.ok) throw new Error('Failed to fetch runs');
            const data = await res.json();
            this.allRuns = data.runs.filter(r => r.date);

            loading.style.display = 'none';

            if (this.allRuns.length === 0) {
                empty.style.display = 'block';
                return;
            }

            dashboard.style.display = 'block';
            this.filterByPeriod(30);
            this.bindGroupingControls();
            this.bindPeriodSelector();
        } catch (err) {
            console.error('Analytics load error:', err);
            loading.style.display = 'none';
            empty.style.display = 'block';
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Period Filtering                                                    */
    /* ------------------------------------------------------------------ */
    filterByPeriod(days) {
        if (days === 'all') {
            this.runs = [...this.allRuns];
        } else {
            const now = new Date();
            // Local midnight N days ago — consistent with start_date_local stored in DB.
            // Dates returned by the API have no TZ suffix, so JS parses them as local time;
            // the cutoff must also be local midnight to avoid off-by-timezone-offset mismatches.
            const cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate() - Number(days));
            this.runs = this.allRuns.filter(r => new Date(r.date) >= cutoff);
        }
        this.renderSummary();
        this.renderCurrentCharts();
    },

    bindPeriodSelector() {
        const el = document.getElementById('periodSelector');
        if (!el) return;

        el.addEventListener('change', async () => {
            const days = el.value;

            // Apply filter immediately so charts reflect the new period right away
            this.filterByPeriod(days);

            // Check Strava connection; if connected, sync then re-render with full data
            const stravaConnected = await this.checkStravaConnection();
            if (!stravaConnected) return;

            // Show inline sync indicator while the Strava pull runs
            this.showSyncIndicator();
            el.disabled = true;

            try {
                // For specific periods: force re-pull that window.
                // For "all time": incremental sync (no force_days) to catch
                // any new activities since last sync, then show all stored runs.
                const daysBack = days !== 'all' ? parseInt(days) : null;
                await this.syncStravaPeriod(daysBack);
                await this.reloadRuns();

                // Re-render now that the DB has the full data for this period
                this.filterByPeriod(days);
            } finally {
                this.hideSyncIndicator();
                el.disabled = false;
            }
        });
    },

    /* ------------------------------------------------------------------ */
    /*  Summary Stats                                                      */
    /* ------------------------------------------------------------------ */
    renderSummary() {
        const runs = this.runs;
        const totalRuns     = runs.length;
        const totalKm       = runs.reduce((s, r) => s + (r.distance_km || 0), 0);
        const totalMinutes  = runs.reduce((s, r) => s + (r.duration_minutes || 0), 0);
        const paceRuns      = runs.filter(r => r.avg_pace_min_km && r.avg_pace_min_km > 0);
        const avgPace       = paceRuns.length ? paceRuns.reduce((s, r) => s + r.avg_pace_min_km, 0) / paceRuns.length : 0;
        const hrRuns        = runs.filter(r => r.avg_heart_rate && r.avg_heart_rate > 0);
        const avgHR         = hrRuns.length ? Math.round(hrRuns.reduce((s, r) => s + r.avg_heart_rate, 0) / hrRuns.length) : 0;
        const longestRun    = runs.length > 0 ? Math.max(...runs.map(r => r.distance_km || 0)) : 0;
        const totalHours    = totalMinutes / 60;

        this.setText('statTotalRuns', totalRuns);
        this.setText('statTotalKm', totalKm.toFixed(1));
        this.setText('statAvgPace', avgPace > 0 ? this.formatPace(avgPace) : '--');
        this.setText('statAvgHR', avgHR > 0 ? avgHR : '--');
        this.setText('statLongest', longestRun.toFixed(1));
        this.setText('statTotalHours', totalHours.toFixed(1));
    },

    /* ------------------------------------------------------------------ */
    /*  Grouping                                                           */
    /* ------------------------------------------------------------------ */
    groupByWeek(runs) {
        const buckets = {};
        for (const r of runs) {
            const d = new Date(r.date);
            const mon = this.startOfWeek(d);
            // Build the key from local date components so it isn't shifted by
            // the UTC offset when toISOString() is called on a midnight-local Date.
            const key = `${mon.getFullYear()}-${String(mon.getMonth() + 1).padStart(2, '0')}-${String(mon.getDate()).padStart(2, '0')}`;
            if (!buckets[key]) buckets[key] = [];
            buckets[key].push(r);
        }
        return this.aggregateBuckets(buckets, k => {
            const [y, m, day] = k.split('-').map(Number);
            // Use Date(y, m-1, d) so it's local time, not UTC-midnight which
            // would display as the previous day in UTC- timezones.
            return new Date(y, m - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        });
    },

    groupByMonth(runs) {
        const buckets = {};
        for (const r of runs) {
            const d = new Date(r.date);
            const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
            if (!buckets[key]) buckets[key] = [];
            buckets[key].push(r);
        }
        return this.aggregateBuckets(buckets, k => {
            const [y, m] = k.split('-');
            const d = new Date(parseInt(y), parseInt(m) - 1);
            return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
        });
    },

    aggregateBuckets(buckets, labelFn) {
        const sorted = Object.keys(buckets).sort();
        return sorted.map(key => {
            const group = buckets[key];
            const totalKm = group.reduce((s, r) => s + (r.distance_km || 0), 0);
            const paceRuns = group.filter(r => r.avg_pace_min_km && r.avg_pace_min_km > 0);
            const avgPace = paceRuns.length ? paceRuns.reduce((s, r) => s + r.avg_pace_min_km, 0) / paceRuns.length : null;
            const hrRuns = group.filter(r => r.avg_heart_rate && r.avg_heart_rate > 0);
            const avgHR = hrRuns.length ? Math.round(hrRuns.reduce((s, r) => s + r.avg_heart_rate, 0) / hrRuns.length) : null;
            const cadRuns = group.filter(r => r.avg_cadence && r.avg_cadence > 0);
            const avgCadence = cadRuns.length ? Math.round(cadRuns.reduce((s, r) => s + r.avg_cadence, 0) / cadRuns.length) : null;
            return { label: labelFn(key), totalKm, avgPace, avgHR, avgCadence, runCount: group.length };
        });
    },

    startOfWeek(d) {
        const dt = new Date(d);
        const day = dt.getDay();
        const diff = day === 0 ? 6 : day - 1; // Monday start
        dt.setDate(dt.getDate() - diff);
        dt.setHours(0, 0, 0, 0);
        return dt;
    },

    /* ------------------------------------------------------------------ */
    /*  Trend Line (linear regression)                                     */
    /* ------------------------------------------------------------------ */
    computeTrendLine(values) {
        const n = values.length;
        if (n < 2) return values;
        let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0, count = 0;
        for (let i = 0; i < n; i++) {
            if (values[i] == null) continue;
            sumX += i; sumY += values[i]; sumXY += i * values[i]; sumXX += i * i; count++;
        }
        if (count < 2) return values;
        const slope = (count * sumXY - sumX * sumY) / (count * sumXX - sumX * sumX);
        const intercept = (sumY - slope * sumX) / count;
        return values.map((_, i) => slope * i + intercept);
    },

    /* ------------------------------------------------------------------ */
    /*  Responsive Helpers                                                 */
    /* ------------------------------------------------------------------ */
    _mobileRatio(desktop, mobile) {
        return window.innerWidth < 768 ? (mobile || 1.5) : desktop;
    },

    _mobileTickOpts() {
        const isMobile = window.innerWidth < 768;
        return {
            maxRotation: isMobile ? 45 : 0,
            font: { size: isMobile ? 10 : 12 },
        };
    },

    /* ------------------------------------------------------------------ */
    /*  Chart Rendering                                                    */
    /* ------------------------------------------------------------------ */
    renderAllCharts() {
        this.renderPaceChart('weekly');
        this.renderDistanceChart('weekly');
        this.renderHRChart('weekly');
        this.renderWorkoutTypeChart();
        this.renderCadenceChart('weekly');
    },

    /** Re-render all charts respecting current grouping dropdown values. */
    renderCurrentCharts() {
        const g = id => { const el = document.getElementById(id); return el ? el.value : 'weekly'; };
        this.renderPaceChart(g('paceGrouping'));
        this.renderDistanceChart(g('distanceGrouping'));
        this.renderHRChart(g('hrGrouping'));
        this.renderWorkoutTypeChart();
        this.renderCadenceChart(g('cadenceGrouping'));
    },

    getGroupedData(grouping) {
        return grouping === 'monthly' ? this.groupByMonth(this.runs) : this.groupByWeek(this.runs);
    },

    renderPaceChart(grouping) {
        const data = this.getGroupedData(grouping);
        const labels = data.map(d => d.label);
        const values = data.map(d => d.avgPace);
        const validValues = values.filter(v => v != null);
        if (validValues.length === 0) {
            this.hideChart('paceChartCard');
            return;
        }
        this.showChart('paceChartCard');
        const trend = this.computeTrendLine(values);

        this.destroyChart('paceChart');
        const ctx = document.getElementById('paceChart').getContext('2d');
        this.charts.paceChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Avg Pace',
                        data: values,
                        borderColor: this.COLORS.primary,
                        backgroundColor: this.COLORS.primaryFill,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                    },
                    {
                        label: 'Trend',
                        data: trend,
                        borderColor: this.COLORS.trend,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: this._mobileRatio(2.5),
                onResize: (chart) => {
                    chart.options.aspectRatio = this._mobileRatio(2.5);
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.dataset.label + ': ' + this.formatPace(ctx.parsed.y),
                        },
                    },
                },
                scales: {
                    x: { ticks: this._mobileTickOpts() },
                    y: {
                        reverse: true,
                        ticks: { callback: v => this.formatPace(v) },
                        title: { display: true, text: 'min/km' },
                    },
                },
            },
        });
    },

    renderDistanceChart(grouping) {
        const data = this.getGroupedData(grouping);
        const labels = data.map(d => d.label);
        const values = data.map(d => d.totalKm);

        this.destroyChart('distanceChart');
        const ctx = document.getElementById('distanceChart').getContext('2d');
        this.charts.distanceChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Distance (km)',
                    data: values,
                    backgroundColor: this.COLORS.primaryFill,
                    borderColor: this.COLORS.primary,
                    borderWidth: 1.5,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: this._mobileRatio(2.5),
                onResize: (chart) => {
                    chart.options.aspectRatio = this._mobileRatio(2.5);
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.parsed.y.toFixed(1) + ' km',
                        },
                    },
                },
                scales: {
                    x: { ticks: this._mobileTickOpts() },
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: 'km' },
                    },
                },
            },
        });
    },

    renderHRChart(grouping) {
        const hasHR = this.runs.some(r => r.avg_heart_rate && r.avg_heart_rate > 0);
        if (!hasHR) {
            this.hideChart('hrChartCard');
            return;
        }
        this.showChart('hrChartCard');

        const data = this.getGroupedData(grouping);
        const labels = data.map(d => d.label);
        const values = data.map(d => d.avgHR);
        const trend = this.computeTrendLine(values);

        this.destroyChart('hrChart');
        const ctx = document.getElementById('hrChart').getContext('2d');
        this.charts.hrChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Avg HR',
                        data: values,
                        borderColor: this.COLORS.accent,
                        backgroundColor: this.COLORS.accentFill,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                    },
                    {
                        label: 'Trend',
                        data: trend,
                        borderColor: 'rgba(255, 98, 70, 0.5)',
                        borderDash: [5, 5],
                        pointRadius: 0,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: this._mobileRatio(2.5),
                onResize: (chart) => {
                    chart.options.aspectRatio = this._mobileRatio(2.5);
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.dataset.label + ': ' + Math.round(ctx.parsed.y) + ' bpm',
                        },
                    },
                },
                scales: {
                    x: { ticks: this._mobileTickOpts() },
                    y: {
                        title: { display: true, text: 'bpm' },
                    },
                },
            },
        });
    },

    renderWorkoutTypeChart() {
        const counts = {};
        for (const r of this.runs) {
            const type = r.workout_type || 'unknown';
            counts[type] = (counts[type] || 0) + 1;
        }
        const labels = Object.keys(counts);
        const values = Object.values(counts);

        if (labels.length === 0) {
            this.hideChart('workoutTypeChartCard');
            return;
        }
        this.showChart('workoutTypeChartCard');

        const palette = [
            this.COLORS.primary, this.COLORS.accent, this.COLORS.secondary,
            '#F59E0B', '#8B5CF6', '#EC4899', '#10B981',
        ];

        this.destroyChart('workoutTypeChart');
        const ctx = document.getElementById('workoutTypeChart').getContext('2d');
        this.charts.workoutTypeChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels.map(l => l.charAt(0).toUpperCase() + l.slice(1)),
                datasets: [{
                    data: values,
                    backgroundColor: palette.slice(0, labels.length),
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: this._mobileRatio(1.2, 1),
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { padding: 16, usePointStyle: true, pointStyle: 'circle' },
                    },
                },
            },
        });
    },

    renderCadenceChart(grouping) {
        const hasCadence = this.runs.some(r => r.avg_cadence && r.avg_cadence > 0);
        if (!hasCadence) {
            this.hideChart('cadenceChartCard');
            return;
        }
        this.showChart('cadenceChartCard');

        const data = this.getGroupedData(grouping);
        const labels = data.map(d => d.label);
        const values = data.map(d => d.avgCadence);

        this.destroyChart('cadenceChart');
        const ctx = document.getElementById('cadenceChart').getContext('2d');
        this.charts.cadenceChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Avg Cadence',
                    data: values,
                    borderColor: this.COLORS.secondary,
                    backgroundColor: this.COLORS.secondaryFill,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: this._mobileRatio(1.2, 1),
                onResize: (chart) => {
                    chart.options.aspectRatio = this._mobileRatio(1.2, 1);
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.parsed.y + ' spm',
                        },
                    },
                },
                scales: {
                    x: { ticks: this._mobileTickOpts() },
                    y: {
                        title: { display: true, text: 'spm' },
                    },
                },
            },
        });
    },

    /* ------------------------------------------------------------------ */
    /*  Grouping Controls                                                  */
    /* ------------------------------------------------------------------ */
    bindGroupingControls() {
        const mapping = {
            paceGrouping:    'renderPaceChart',
            distanceGrouping:'renderDistanceChart',
            hrGrouping:      'renderHRChart',
            cadenceGrouping: 'renderCadenceChart',
        };

        for (const [selectId, method] of Object.entries(mapping)) {
            const el = document.getElementById(selectId);
            if (el) {
                el.addEventListener('change', () => {
                    this[method](el.value);
                });
            }
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Helpers                                                            */
    /* ------------------------------------------------------------------ */
    destroyChart(name) {
        if (this.charts[name]) {
            this.charts[name].destroy();
            delete this.charts[name];
        }
    },

    hideChart(id) {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    },

    showChart(id) {
        const el = document.getElementById(id);
        if (el) el.style.display = '';
    },

    setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    },

    formatPace(pace) {
        if (!pace || pace <= 0) return '--';
        const mins = Math.floor(pace);
        const secs = Math.round((pace - mins) * 60);
        return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    },

    /* ------------------------------------------------------------------ */
    /*  Strava Integration                                                 */
    /* ------------------------------------------------------------------ */
    async checkStravaConnection() {
        try {
            const res = await fetch('/api/strava/status', { credentials: 'same-origin' });
            if (!res.ok) return false;
            const data = await res.json();
            return data.connected;
        } catch (err) {
            console.error('Failed to check Strava connection:', err);
            return false;
        }
    },

    async syncStravaPeriod(daysBack) {
        try {
            const params = daysBack !== null ? `?force_days=${daysBack}` : '?full_sync=true';
            const res = await fetch(`/api/strava/sync${params}`, {
                method: 'POST',
                credentials: 'same-origin'
            });

            if (!res.ok) {
                console.warn('Strava sync failed:', await res.text());
                return;
            }

            const data = await res.json();
            console.log(`Strava sync complete: ${data.synced} new, ${data.skipped} skipped`);
        } catch (err) {
            console.error('Strava sync error:', err);
        }
    },

    async reloadRuns() {
        try {
            const res = await fetch('/api/analytics/runs', { credentials: 'same-origin' });
            if (!res.ok) throw new Error('Failed to reload runs');
            const data = await res.json();
            this.allRuns = data.runs.filter(r => r.date);
        } catch (err) {
            console.error('Failed to reload runs:', err);
        }
    },

    showSyncIndicator() {
        const el = document.getElementById('stravaSyncIndicator');
        if (el) el.style.display = 'flex';
    },

    hideSyncIndicator() {
        const el = document.getElementById('stravaSyncIndicator');
        if (el) el.style.display = 'none';
    },
};

document.addEventListener('DOMContentLoaded', () => AnalyticsDashboard.init());
