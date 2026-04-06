/**
 * Analytics Dashboard — Performance Hub
 * Full client-side aggregation + Chart.js rendering.
 */
const AnalyticsDashboard = {
    allRuns: [],
    runs: [],      // current period
    prevRuns: [],  // previous period (for trend comparison)
    charts: {},
    currentPeriodDays: 30,
    currentPlanId: null,
    planInfo: null,
    acwrData: null,
    prData: null,
    insightsData: null,
    activeTab: 'dashboard',

    COLORS: {
        primary:       '#1D4ED8',
        primaryFill:   'rgba(29, 78, 216, 0.12)',
        accent:        '#FF6246',
        accentFill:    'rgba(255, 98, 70, 0.12)',
        secondary:     '#0D9488',
        secondaryFill: 'rgba(13, 148, 136, 0.12)',
        purple:        '#7C3AED',
        purpleFill:    'rgba(124, 58, 237, 0.12)',
        trend:         'rgba(29, 78, 216, 0.4)',
        grid:          'rgba(28, 25, 23, 0.06)',
        tick:          '#A09A93',
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
            const stravaConnected = await this.checkStravaConnection();
            if (stravaConnected) {
                await this.syncStravaPeriod(30);
            }

            await this.loadRuns();

            loading.style.display = 'none';

            if (this.allRuns.length === 0) {
                empty.style.display = 'block';
                return;
            }

            const tabs = document.getElementById('analyticsTabs');
            if (tabs) tabs.style.display = 'flex';

            dashboard.style.display = 'block';
            this.filterByPeriod(30);
            this.bindGroupingControls();
            this.bindPeriodSelector();
            this.bindPlanSelector();
            this.bindPredictionsToggle();
            this.bindTabSwitching();
            this.loadRacePredictions();
            this.loadRaceResults();
            this.loadTrainingLoad();
            this.loadPersonalRecords();
            this.loadInsights();
        } catch (err) {
            console.error('Analytics load error:', err);
            loading.style.display = 'none';
            empty.style.display = 'block';
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Race Predictions                                                   */
    /* ------------------------------------------------------------------ */
    async loadRacePredictions() {
        const card = document.getElementById('predictionsCard');
        if (!card) return;

        try {
            const res = await fetch('/api/runs/predictions', { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();

            if (!data.has_sufficient_data) {
                card.style.display = 'none';
                return;
            }

            card.style.display = '';
            this.renderRacePredictions(data);
        } catch (err) {
            console.error('Failed to load race predictions:', err);
        }
    },

    renderRacePredictions(data) {
        const vdotEl = document.getElementById('predictionsVdot');
        const trendEl = document.getElementById('predictionsTrend');
        const gridEl = document.getElementById('predictionsGrid');
        const footerEl = document.getElementById('predictionsFooter');

        if (vdotEl) {
            vdotEl.textContent = `VDOT ${data.current_vdot}`;
        }

        if (trendEl) {
            const trendMap = {
                improving: { text: 'Improving', cls: 'trend-up' },
                stable: { text: 'Stable', cls: 'trend-neutral' },
                declining: { text: 'Declining', cls: 'trend-down' },
            };
            const trend = trendMap[data.vdot_trend] || trendMap.stable;
            trendEl.textContent = `${trend.text} ${data.vdot_trend === 'improving' ? '↑' : data.vdot_trend === 'declining' ? '↓' : '→'}`;
            trendEl.className = `predictions-trend ${trend.cls}`;
        }

        if (gridEl && data.predictions) {
            const distanceLabels = {
                '5K': { name: '5K', icon: '🎽' },
                '10K': { name: '10K', icon: '🏃' },
                'trail': { name: 'Trail', icon: '⛰️' },
                'half_marathon': { name: 'Half', icon: '🏅' },
                'marathon': { name: 'Marathon', icon: '🥇' },
            };

            gridEl.innerHTML = Object.entries(data.predictions).map(([key, pred]) => {
                const info = distanceLabels[key] || { name: key, icon: '🏃' };
                const range = pred.range || {};
                return `
                    <div class="prediction-item">
                        <div class="prediction-icon">${info.icon}</div>
                        <div class="prediction-name">${info.name}</div>
                        <div class="prediction-time">${pred.formatted}</div>
                        <div class="prediction-range">${range.fast || '--'} – ${range.slow || '--'}</div>
                    </div>
                `;
            }).join('');
        }

        if (footerEl && data.best_effort) {
            const effort = data.best_effort;
            const date = effort.date ? new Date(effort.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
            footerEl.textContent = `Based on: ${effort.distance_km}K run on ${date} (${effort.time})`;
        }
    },

    bindPredictionsToggle() {
        this._bindCollapseToggle('predictionsToggle', 'predictionsContent');
        this._bindCollapseToggle('raceResultsToggle', 'raceResultsContent');
    },

    _bindCollapseToggle(toggleId, contentId) {
        const toggle = document.getElementById(toggleId);
        const content = document.getElementById(contentId);
        if (!toggle || !content) return;

        toggle.addEventListener('click', () => {
            const isCollapsed = content.style.display === 'none';
            content.style.display = isCollapsed ? '' : 'none';
            toggle.innerHTML = isCollapsed
                ? `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 10l4-4 4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`
                : `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
        });
    },

    /* ------------------------------------------------------------------ */
    /*  Predicted vs Actual                                                 */
    /* ------------------------------------------------------------------ */
    async loadRaceResults() {
        const card = document.getElementById('raceResultsCard');
        if (!card) return;

        try {
            const res = await fetch('/api/runs/race-history', { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();

            if (!data.runs || data.runs.length === 0) {
                card.style.display = 'none';
                return;
            }

            // Only show the card if at least some runs have comparison data
            const hasComparisons = data.runs.some(r => r.comparison);
            if (!hasComparisons) {
                card.style.display = 'none';
                return;
            }

            card.style.display = '';
            this.renderRaceResults(data);
        } catch (err) {
            console.error('Failed to load race results:', err);
        }
    },

    renderRaceResults(data) {
        const listEl = document.getElementById('raceResultsList');
        const accuracyEl = document.getElementById('raceResultsAccuracy');
        const emptyEl = document.getElementById('raceResultsEmpty');

        if (accuracyEl && data.avg_prediction_accuracy != null) {
            accuracyEl.textContent = `${data.avg_prediction_accuracy}% accuracy`;
            accuracyEl.className = 'race-results-accuracy';
        }

        if (!listEl) return;

        // Only show runs that have comparison data
        const runs = (data.runs || []).filter(r => r.comparison);

        if (runs.length === 0) {
            if (emptyEl) emptyEl.style.display = 'block';
            return;
        }

        const typeLabels = {
            easy: 'Easy', tempo: 'Tempo', interval: 'Interval',
            long: 'Long', hill: 'Hill', race: 'Race', rest: 'Rest',
        };

        listEl.innerHTML = runs.map(run => {
            const date = run.date
                ? new Date(run.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                : '';
            const comp = run.comparison;
            const deltaClass = comp.faster_than_predicted ? 'race-delta-fast' : 'race-delta-slow';
            const deltaSign = comp.faster_than_predicted ? '-' : '+';
            const deltaIcon = comp.faster_than_predicted ? '&#9650;' : '&#9660;';
            const typeBadge = run.workout_type
                ? `<span class="race-result-type race-result-type--${run.workout_type}">${typeLabels[run.workout_type] || run.workout_type}</span>`
                : '';

            return `
                <div class="race-result-row">
                    <div class="race-result-header">
                        <div class="race-result-header-left">
                            <span class="race-result-distance">${run.distance_name}</span>
                            ${typeBadge}
                        </div>
                        <span class="race-result-date">${date}</span>
                    </div>
                    <div class="race-result-comparison">
                        <div class="race-result-times">
                            <div class="race-result-time-col">
                                <span class="race-time-label">Predicted</span>
                                <span class="race-time-value">${comp.predicted_formatted}</span>
                            </div>
                            <span class="race-result-arrow">&#8594;</span>
                            <div class="race-result-time-col">
                                <span class="race-time-label">Actual</span>
                                <span class="race-time-value race-time-actual">${comp.actual_formatted}</span>
                            </div>
                        </div>
                        <div class="race-result-delta ${deltaClass}">
                            <span class="race-delta-icon">${deltaIcon}</span>
                            ${deltaSign}${comp.delta_formatted}
                        </div>
                    </div>
                    ${run.vdot ? `<span class="race-result-vdot">VDOT ${run.vdot}</span>` : ''}
                </div>
            `;
        }).join('');
    },

    /* ------------------------------------------------------------------ */
    /*  Period Filtering                                                    */
    /* ------------------------------------------------------------------ */
    filterByPeriod(days) {
        this.currentPeriodDays = days;

        if (days === 'all') {
            this.runs = [...this.allRuns];
            this.prevRuns = [];
        } else {
            const n = Number(days);
            const now = new Date();
            const cutoffCurrent = new Date(now.getFullYear(), now.getMonth(), now.getDate() - n - 1);
            const cutoffPrev    = new Date(now.getFullYear(), now.getMonth(), now.getDate() - n * 2 - 1);
            this.runs     = this.allRuns.filter(r => new Date(r.date) >= cutoffCurrent);
            this.prevRuns = this.allRuns.filter(r => {
                const d = new Date(r.date);
                return d >= cutoffPrev && d < cutoffCurrent;
            });
        }

        this.renderAll();
    },

    bindPeriodSelector() {
        const el = document.getElementById('periodSelector');
        if (!el) return;

        const customWrap  = document.getElementById('customDaysWrap');
        const customInput = document.getElementById('customDaysInput');
        const customApply = document.getElementById('customDaysApply');

        const applyPeriod = async (days) => {
            this.filterByPeriod(days);

            const stravaConnected = await this.checkStravaConnection();
            if (!stravaConnected) return;

            this.showSyncIndicator();
            el.disabled = true;
            if (customApply) customApply.disabled = true;
            try {
                const daysBack = days !== 'all' ? parseInt(days) : null;
                const syncOk = await this.syncStravaPeriod(daysBack);
                await this.reloadRuns();
                this.filterByPeriod(days);
                if (!syncOk) this.showSyncError('Strava sync failed — showing cached data');
            } finally {
                this.hideSyncIndicator();
                el.disabled = false;
                if (customApply) customApply.disabled = false;
            }
        };

        el.addEventListener('change', async () => {
            const days = el.value;
            if (days === 'custom') {
                if (customWrap) customWrap.style.display = 'flex';
                if (customInput) customInput.focus();
                return;
            }
            if (customWrap) customWrap.style.display = 'none';
            await applyPeriod(days);
        });

        if (customApply) {
            customApply.addEventListener('click', async () => {
                const raw = parseInt(customInput.value, 10);
                if (!raw || raw < 1) { customInput.focus(); return; }
                const days = Math.min(raw, 366).toString();
                customInput.value = Math.min(raw, 366);
                await applyPeriod(days);
            });
        }

        if (customInput) {
            customInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') customApply && customApply.click();
            });
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Render All                                                         */
    /* ------------------------------------------------------------------ */
    renderAll() {
        this.renderSummary();
        this.renderHeatmap();
        this.renderInsights();
        this.renderRecentRuns();
        this.renderCurrentCharts();
        this.renderEfficiencyChart('weekly');
        this.renderTrainingLoadChart('weekly');
        this.renderPaceZonesChart();
        // PRs rendered once via loadPersonalRecords(); client fallback if API hasn't loaded
        if (!this.prData) this.renderPersonalRecordsFallback();
    },

    /** Re-render charts respecting current grouping dropdown values. */
    renderCurrentCharts() {
        const g = id => { const el = document.getElementById(id); return el ? el.value : 'weekly'; };
        this.renderPaceChart(g('paceGrouping'));
        this.renderDistanceChart(g('distanceGrouping'));
        this.renderEfficiencyChart(g('efficiencyGrouping'));
        this.renderTrainingLoadChart(g('loadGrouping'));
        this.renderPaceZonesChart();
    },

    /* ------------------------------------------------------------------ */
    /*  Summary Stats with Trend Indicators                                */
    /* ------------------------------------------------------------------ */
    renderSummary() {
        const runs = this.runs;
        const prev = this.prevRuns;

        const totalKm      = runs.reduce((s, r) => s + (r.distance_km || 0), 0);
        const prevTotalKm  = prev.reduce((s, r) => s + (r.distance_km || 0), 0);

        const paceRuns     = runs.filter(r => r.avg_pace_min_km && r.avg_pace_min_km > 0);
        const avgPace      = paceRuns.length ? paceRuns.reduce((s, r) => s + r.avg_pace_min_km, 0) / paceRuns.length : 0;
        const prevPaceRuns = prev.filter(r => r.avg_pace_min_km && r.avg_pace_min_km > 0);
        const prevAvgPace  = prevPaceRuns.length ? prevPaceRuns.reduce((s, r) => s + r.avg_pace_min_km, 0) / prevPaceRuns.length : 0;

        const totalRuns    = runs.length;
        const prevTotalRuns= prev.length;

        const totalMins    = runs.reduce((s, r) => s + (r.duration_minutes || 0), 0);
        const prevTotalMins= prev.reduce((s, r) => s + (r.duration_minutes || 0), 0);
        const totalHours   = totalMins / 60;
        const prevTotalHours = prevTotalMins / 60;

        this.setText('statTotalKm',    totalKm.toFixed(1));
        this.setText('statAvgPace',    avgPace > 0 ? this.formatPace(avgPace) : '--');
        this.setText('statTotalRuns',  totalRuns);
        this.setText('statTotalHours', totalHours.toFixed(1));

        // Trend badges — for pace, lower is better (faster)
        this.setTrend('trendTotalKm',    this.pctChange(totalKm, prevTotalKm),    false);
        this.setTrend('trendAvgPace',    this.pctChange(avgPace, prevAvgPace),    true); // inverted
        this.setTrend('trendTotalRuns',  this.pctChange(totalRuns, prevTotalRuns), false);
        this.setTrend('trendTotalHours', this.pctChange(totalHours, prevTotalHours), false);
    },

    pctChange(current, previous) {
        if (!previous || previous === 0) return null;
        return ((current - previous) / previous) * 100;
    },

    setTrend(id, pct, invertedIsGood) {
        const el = document.getElementById(id);
        if (!el) return;
        if (pct === null || this.currentPeriodDays === 'all') {
            el.textContent = '';
            el.className = 'hero-stat-trend';
            return;
        }
        const isPositive = invertedIsGood ? pct < 0 : pct > 0;
        const arrow = pct > 0 ? '↑' : pct < 0 ? '↓' : '→';
        const abs = Math.abs(pct).toFixed(1);
        el.textContent = `${arrow} ${abs}%`;
        el.className = 'hero-stat-trend ' + (
            Math.abs(pct) < 1 ? 'trend-neutral' :
            isPositive ? 'trend-up' : 'trend-down'
        );
    },

    /* ------------------------------------------------------------------ */
    /*  Activity Heatmap (52 weeks)                                        */
    /* ------------------------------------------------------------------ */
    renderHeatmap() {
        const container = document.getElementById('activityHeatmap');
        const monthsEl  = document.getElementById('heatmapMonths');
        if (!container) return;

        // Build date → distance map from ALL runs (all time)
        const dateMap = {};
        for (const r of this.allRuns) {
            if (!r.date) continue;
            const key = r.date.slice(0, 10);
            dateMap[key] = (dateMap[key] || 0) + (r.distance_km || 0);
        }

        const today = new Date();
        today.setHours(0, 0, 0, 0);

        // Start from Monday 52 weeks ago
        const startDate = new Date(today);
        startDate.setDate(startDate.getDate() - 364);
        const dayOfWeek = startDate.getDay(); // 0=Sun
        const diffToMon = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
        startDate.setDate(startDate.getDate() - diffToMon);

        // Intensity thresholds (km)
        const thresholds = [0, 3, 7, 12, 18];

        const cells = [];
        const monthLabels = [];
        let col = 0;
        const cur = new Date(startDate);
        let lastMonth = -1;

        while (cur <= today) {
            const key = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, '0')}-${String(cur.getDate()).padStart(2, '0')}`;
            const km = dateMap[key] || 0;
            const dow = cur.getDay(); // 0=Sun

            // Track month label position
            if (cur.getMonth() !== lastMonth && dow === 1) {
                monthLabels.push({ col, label: cur.toLocaleDateString('en-US', { month: 'short' }) });
                lastMonth = cur.getMonth();
            }

            const level = km === 0 ? 0 :
                          km < thresholds[1] ? 1 :
                          km < thresholds[2] ? 2 :
                          km < thresholds[3] ? 3 : 4;

            const cell = document.createElement('div');
            cell.className = `heatmap-cell${level > 0 ? ' heatmap-cell--' + level : ''}`;

            const dateLabel = cur.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            cell.title = km > 0 ? `${dateLabel}: ${km.toFixed(1)} km` : dateLabel;

            cells.push(cell);

            cur.setDate(cur.getDate() + 1);
            if (cur.getDay() === 1) col++;
        }

        container.innerHTML = '';
        cells.forEach(c => container.appendChild(c));

        // Month labels — one span per month, width = span of columns × cellSize
        if (monthsEl) {
            monthsEl.innerHTML = '';
            const totalCols = col + 1;
            const cellSize  = 15; // 12px cell + 3px gap
            for (let i = 0; i < monthLabels.length; i++) {
                const { col: c, label } = monthLabels[i];
                const nextCol = i + 1 < monthLabels.length ? monthLabels[i + 1].col : totalCols;
                const span = document.createElement('span');
                span.className = 'heatmap-month-label';
                span.textContent = label;
                span.style.width = ((nextCol - c) * cellSize) + 'px';
                span.style.flexShrink = '0';
                monthsEl.appendChild(span);
            }
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Insights                                                           */
    /* ------------------------------------------------------------------ */
    renderInsights() {
        const container = document.getElementById('analyticsInsights');
        if (!container) return;

        const insights = [];
        const runs = this.runs;
        const prev = this.prevRuns;

        if (runs.length === 0) {
            container.style.display = 'none';
            return;
        }

        // 1. Volume change
        const km    = runs.reduce((s, r) => s + (r.distance_km || 0), 0);
        const prevKm= prev.reduce((s, r) => s + (r.distance_km || 0), 0);
        if (prevKm > 0) {
            const pct = this.pctChange(km, prevKm);
            if (pct !== null) {
                const better = pct > 0;
                insights.push({
                    icon: better ? '📈' : '📉',
                    value: `${Math.abs(pct).toFixed(0)}%`,
                    title: better ? 'Volume Up' : 'Volume Down',
                    sub: `vs previous period (${prevKm.toFixed(0)} km → ${km.toFixed(0)} km)`,
                    type: better ? 'positive' : '',
                });
            }
        }

        // 2. Pace change
        const paceRuns = runs.filter(r => r.avg_pace_min_km > 0);
        const prevPaceRuns = prev.filter(r => r.avg_pace_min_km > 0);
        if (paceRuns.length && prevPaceRuns.length) {
            const ap = paceRuns.reduce((s, r) => s + r.avg_pace_min_km, 0) / paceRuns.length;
            const pp = prevPaceRuns.reduce((s, r) => s + r.avg_pace_min_km, 0) / prevPaceRuns.length;
            const diff = pp - ap; // positive = faster this period
            if (Math.abs(diff) > 0.05) {
                const faster = diff > 0;
                const absSecs = Math.round(Math.abs(diff) * 60);
                insights.push({
                    icon: faster ? '⚡' : '🐢',
                    value: `${absSecs}s/km`,
                    title: faster ? 'Running Faster' : 'Running Slower',
                    sub: `${this.formatPace(pp)} → ${this.formatPace(ap)} avg pace`,
                    type: faster ? 'positive' : 'warning',
                });
            }
        }

        // 3. Consistency: unique days with runs
        const runDays = new Set(runs.map(r => r.date ? r.date.slice(0, 10) : null)).size;
        const periodLen = this.currentPeriodDays === 'all' ? null : Number(this.currentPeriodDays);
        if (periodLen) {
            const weeks = Math.max(1, Math.floor(periodLen / 7));
            const runsPerWeek = (runs.length / weeks).toFixed(1);
            insights.push({
                icon: '🗓️',
                value: runsPerWeek,
                title: 'Runs/Week',
                sub: `${runDays} active days, ${runs.length} runs`,
                type: runsPerWeek >= 3 ? 'positive' : '',
            });
        }

        // 4. Longest run this period
        if (runs.length > 0) {
            const longest = Math.max(...runs.map(r => r.distance_km || 0));
            const longestRun = runs.find(r => r.distance_km === longest);
            if (longest > 0) {
                insights.push({
                    icon: '📏',
                    value: `${longest.toFixed(1)} km`,
                    title: 'Longest Run',
                    sub: longestRun && longestRun.date
                        ? new Date(longestRun.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                        : 'this period',
                    type: 'highlight',
                });
            }
        }

        // 5. ACWR status
        if (this.acwrData && this.acwrData.current) {
            const c = this.acwrData.current;
            const zoneMap = {
                low:       { icon: '🔻', title: 'Under-training', type: 'warning' },
                optimal:   { icon: '✅', title: 'Sweet Spot',     type: 'positive' },
                high:      { icon: '⚠️', title: 'Elevated Risk',  type: 'warning' },
                very_high: { icon: '🔴', title: 'Injury Danger',  type: 'negative' },
            };
            const zone = zoneMap[c.risk] || zoneMap.optimal;
            insights.push({
                icon: zone.icon,
                value: c.acwr.toFixed(2),
                title: zone.title,
                sub: `ACWR — acute/chronic load ratio`,
                type: zone.type,
            });
        }

        // 6. Run streak
        const streak = this.computeStreak();
        if (streak > 2) {
            insights.push({
                icon: '🔥',
                value: `${streak}d`,
                title: 'Current Streak',
                sub: `${streak} consecutive days with a run`,
                type: streak >= 7 ? 'positive' : 'highlight',
            });
        }

        if (insights.length === 0) {
            container.style.display = 'none';
            return;
        }

        container.style.display = 'flex';
        container.innerHTML = insights.map(i => `
            <div class="insight-card${i.type ? ' insight-card--' + i.type : ''}">
                <div class="insight-icon">${i.icon}</div>
                <div class="insight-value">${i.value}</div>
                <div class="insight-title">${i.title}</div>
                <div class="insight-sub">${i.sub}</div>
            </div>
        `).join('');
    },

    computeStreak() {
        const dateSet = new Set(this.allRuns.map(r => r.date ? r.date.slice(0, 10) : null));
        let streak = 0;
        const d = new Date();
        d.setHours(0, 0, 0, 0);
        while (true) {
            const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
            if (!dateSet.has(key)) break;
            streak++;
            d.setDate(d.getDate() - 1);
        }
        return streak;
    },

    /* ------------------------------------------------------------------ */
    /*  Personal Records — API-powered                                     */
    /* ------------------------------------------------------------------ */
    async loadPersonalRecords() {
        const el = document.getElementById('recordsList');
        const card = document.getElementById('recordsCard');
        if (!el || !card) return;

        try {
            const res = await fetch('/api/analytics/personal-records', { credentials: 'same-origin' });
            if (!res.ok) { this.renderPersonalRecordsFallback(); return; }
            const data = await res.json();
            if (!data.available) { this.renderPersonalRecordsFallback(); return; }

            this.prData = data;
            card.style.display = '';

            const distIcons = { sprint: '⚡', race: '🏃', medal: '🏅', trophy: '🏆' };
            const genIcons  = { longest_run: '📏', fastest_pace: '⚡', highest_vdot: '🧠', best_week: '📅' };

            let html = '';

            // Distance PRs
            if (data.distance_records && data.distance_records.length > 0) {
                html += '<div class="records-section"><div class="records-section-title">Race Distances</div>';
                html += data.distance_records.map(rec => {
                    const pr = rec.current_pr;
                    const icon = distIcons[rec.icon] || '🏃';
                    const dateStr = pr.date
                        ? new Date(pr.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                        : '';
                    const prCount = rec.pr_count > 1 ? `<span class="pr-count">${rec.pr_count} PRs</span>` : '';
                    const historyDots = rec.history.length > 1
                        ? `<div class="pr-history-dots">${rec.history.map((_, i) => `<span class="pr-dot${i === rec.history.length - 1 ? ' pr-dot--current' : ''}"></span>`).join('')}</div>`
                        : '';
                    const improvement = pr.improvement_seconds
                        ? `<span class="pr-improvement">-${Math.round(pr.improvement_seconds)}s</span>`
                        : '';

                    return `
                        <div class="record-item record-item--distance">
                            <span class="record-icon">${icon}</span>
                            <div class="record-info">
                                <span class="record-label">${rec.distance_name}</span>
                                <span class="record-meta">${dateStr} ${prCount}</span>
                                ${historyDots}
                            </div>
                            <div class="record-result">
                                <span class="record-value">${pr.duration_formatted}</span>
                                <span class="record-pace">${pr.pace_formatted}/km ${improvement}</span>
                            </div>
                        </div>
                    `;
                }).join('');
                html += '</div>';
            }

            // General records
            if (data.general && data.general.length > 0) {
                html += '<div class="records-section"><div class="records-section-title">All-Time</div>';
                html += data.general.map(rec => {
                    const icon = genIcons[rec.type] || '📊';
                    const dateStr = rec.date
                        ? new Date(rec.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                        : '';
                    return `
                        <div class="record-item">
                            <span class="record-icon">${icon}</span>
                            <span class="record-label">${rec.label}</span>
                            <div class="record-result">
                                <span class="record-value">${rec.formatted}<span class="record-unit">${rec.unit}</span></span>
                                ${dateStr ? `<span class="record-date">${dateStr}</span>` : ''}
                            </div>
                        </div>
                    `;
                }).join('');
                html += '</div>';
            }

            el.innerHTML = html;
        } catch (err) {
            console.error('Failed to load personal records:', err);
            this.renderPersonalRecordsFallback();
        }
    },

    /** Client-side fallback when API is unavailable. */
    renderPersonalRecordsFallback() {
        const el = document.getElementById('recordsList');
        const card = document.getElementById('recordsCard');
        if (!el) return;

        const all = this.allRuns;
        if (all.length === 0) { if (card) card.style.display = 'none'; return; }
        if (card) card.style.display = '';

        const longestRun = all.reduce((best, r) =>
            (r.distance_km || 0) > (best.distance_km || 0) ? r : best, all[0]);
        const fastestRun = all
            .filter(r => r.avg_pace_min_km > 0 && r.distance_km >= 3)
            .reduce((best, r) => (!best || r.avg_pace_min_km < best.avg_pace_min_km) ? r : best, null);

        const records = [
            { icon: '📏', label: 'Longest Run', value: longestRun ? longestRun.distance_km.toFixed(1) : null, unit: 'km' },
            { icon: '⚡', label: 'Fastest Pace', value: fastestRun ? this.formatPace(fastestRun.avg_pace_min_km) : null, unit: 'min/km' },
        ].filter(r => r.value !== null);

        el.innerHTML = records.map(r => `
            <div class="record-item">
                <span class="record-icon">${r.icon}</span>
                <span class="record-label">${r.label}</span>
                <span class="record-value">${r.value}<span class="record-unit">${r.unit}</span></span>
            </div>
        `).join('');
    },

    /* ------------------------------------------------------------------ */
    /*  Recent Runs Feed                                                   */
    /* ------------------------------------------------------------------ */
    renderRecentRuns() {
        const list = document.getElementById('recentRunsList');
        const count = document.getElementById('recentRunsCount');
        if (!list) return;

        const recent = [...this.runs]
            .sort((a, b) => new Date(b.date) - new Date(a.date))
            .slice(0, 8);

        if (count) count.textContent = `${this.runs.length} in this period`;

        if (recent.length === 0) {
            list.innerHTML = '<p style="color:var(--color-text-muted);font-size:var(--text-sm);padding:var(--space-3) 0">No runs in this period.</p>';
            return;
        }

        list.innerHTML = recent.map(r => {
            const date = r.date
                ? new Date(r.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                : '--';
            const dist = r.distance_km ? `${r.distance_km.toFixed(1)}<span class="run-distance-unit">km</span>` : '--';
            const pace = r.avg_pace_min_km > 0 ? `${this.formatPace(r.avg_pace_min_km)}/km` : '';
            const hr   = r.avg_heart_rate > 0  ? `${Math.round(r.avg_heart_rate)} bpm` : '';
            const type = r.workout_type || 'unknown';
            const typeClass = `badge-${type}`;
            const typeLabel = type.charAt(0).toUpperCase() + type.slice(1);
            const ql = this.qualityLabel(r);

            const runJson = JSON.stringify(r).replace(/"/g, '&quot;');

            return `
                <div class="run-row">
                    <span class="run-date">${date}</span>
                    <span class="run-distance">${dist}</span>
                    <span class="run-pace">${pace}</span>
                    <span class="run-hr">${hr}</span>
                    <span class="run-type-badge ${typeClass}">${typeLabel}</span>
                    ${ql ? `<span class="quality-badge ${ql.cls}">${ql.label}</span>` : ''}
                    <button class="share-run-btn" title="Share this run" data-run="${runJson}">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
                    </button>
                </div>
            `;
        }).join('');

        // Bind share buttons
        list.querySelectorAll('.share-run-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const run = JSON.parse(btn.dataset.run.replace(/&quot;/g, '"'));
                if (window.ShareCard) window.ShareCard.open(run);
            });
        });
    },

    qualityLabel(run) {
        // Prefer quality_label if set
        if (run.quality_label) {
            const map = {
                'Nailed it': { cls: 'quality-nailed', label: 'Nailed it' },
                'On track':  { cls: 'quality-track',  label: 'On track' },
                'Too easy':  { cls: 'quality-easy',   label: 'Too easy' },
                'Too hard':  { cls: 'quality-hard',   label: 'Too hard' },
            };
            return map[run.quality_label] || null;
        }
        // Fallback to perceived_effort
        const e = run.perceived_effort;
        if (!e || e <= 0) return null;
        if (e <= 3) return { cls: 'quality-easy',   label: 'Easy' };
        if (e <= 6) return { cls: 'quality-track',  label: 'Moderate' };
        if (e <= 8) return { cls: 'quality-nailed', label: 'Hard' };
        return { cls: 'quality-hard', label: 'Max' };
    },

    /* ------------------------------------------------------------------ */
    /*  Aerobic Efficiency Chart                                           */
    /* ------------------------------------------------------------------ */
    renderEfficiencyChart(grouping) {
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
    },

    _renderEfficiencyBadge(validValues) {
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
    },

    /* ------------------------------------------------------------------ */
    /*  Pace Zone Distribution                                             */
    /* ------------------------------------------------------------------ */
    paceZoneData: null,

    async renderPaceZonesChart() {
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
    },

    /* ------------------------------------------------------------------ */
    /*  Grouping Helpers                                                   */
    /* ------------------------------------------------------------------ */
    groupByWeek(runs) {
        const buckets = {};
        for (const r of runs) {
            const d = new Date(r.date);
            const mon = this.startOfWeek(d);
            const key = `${mon.getFullYear()}-${String(mon.getMonth()+1).padStart(2,'0')}-${String(mon.getDate()).padStart(2,'0')}`;
            if (!buckets[key]) buckets[key] = [];
            buckets[key].push(r);
        }
        return this.aggregateBuckets(buckets, k => {
            const [y, m, day] = k.split('-').map(Number);
            return new Date(y, m - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        });
    },

    groupByMonth(runs) {
        const buckets = {};
        for (const r of runs) {
            const d = new Date(r.date);
            const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
            if (!buckets[key]) buckets[key] = [];
            buckets[key].push(r);
        }
        return this.aggregateBuckets(buckets, k => {
            const [y, m] = k.split('-');
            return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
        });
    },

    aggregateBuckets(buckets, labelFn) {
        return Object.keys(buckets).sort().map(key => {
            const group = buckets[key];
            const totalKm   = group.reduce((s, r) => s + (r.distance_km || 0), 0);
            const paceRuns  = group.filter(r => r.avg_pace_min_km > 0);
            const avgPace   = paceRuns.length ? paceRuns.reduce((s, r) => s + r.avg_pace_min_km, 0) / paceRuns.length : null;
            const hrRuns    = group.filter(r => r.avg_heart_rate > 0);
            const avgHR     = hrRuns.length ? Math.round(hrRuns.reduce((s, r) => s + r.avg_heart_rate, 0) / hrRuns.length) : null;
            const cadRuns   = group.filter(r => r.avg_cadence > 0);
            const avgCadence= cadRuns.length ? Math.round(cadRuns.reduce((s, r) => s + r.avg_cadence, 0) / cadRuns.length) : null;

            const effortRuns = group.filter(r => r.perceived_effort > 0);
            const avgEffort  = effortRuns.length ? effortRuns.reduce((s, r) => s + r.perceived_effort, 0) / effortRuns.length : null;

            const effRuns = group.filter(r => r.avg_pace_min_km > 0 && r.avg_heart_rate > 0);
            const avgEfficiency = effRuns.length
                ? effRuns.reduce((s, r) => s + (60 / r.avg_pace_min_km) / r.avg_heart_rate * 100, 0) / effRuns.length
                : null;

            const load = group.reduce((s, r) => {
                const km = r.distance_km || 0;
                if (r.perceived_effort > 0) return s + km * r.perceived_effort;
                if (r.avg_heart_rate > 0)   return s + km * (r.avg_heart_rate / 150);
                return s + km;
            }, 0);

            return { label: labelFn(key), totalKm, avgPace, avgHR, avgCadence, runCount: group.length, avgEffort, avgEfficiency, load };
        });
    },

    startOfWeek(d) {
        const dt = new Date(d);
        const day = dt.getDay();
        dt.setDate(dt.getDate() - (day === 0 ? 6 : day - 1));
        dt.setHours(0, 0, 0, 0);
        return dt;
    },

    getGroupedData(grouping) {
        return grouping === 'monthly' ? this.groupByMonth(this.runs) : this.groupByWeek(this.runs);
    },

    /* ------------------------------------------------------------------ */
    /*  Trend Line                                                         */
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
        return values.map((_, i) => parseFloat((slope * i + intercept).toFixed(4)));
    },

    /* ------------------------------------------------------------------ */
    /*  Chart Config Helpers                                               */
    /* ------------------------------------------------------------------ */
    _mobileRatio(desktop, mobile) {
        return window.innerWidth < 768 ? (mobile || 1.5) : desktop;
    },

    _mobileTickOpts() {
        const isMobile = window.innerWidth < 768;
        return {
            maxRotation: isMobile ? 45 : 0,
            font: { size: isMobile ? 10 : 11 },
            color: this.COLORS.tick,
        };
    },

    _baseChartOptions(aspectRatio, yOptions = {}) {
        return {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: this._mobileRatio(aspectRatio),
            onResize: (chart) => { chart.options.aspectRatio = this._mobileRatio(aspectRatio); },
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: {
                    ticks: this._mobileTickOpts(),
                    grid: { color: this.COLORS.grid },
                },
                y: {
                    ticks: { font: { size: 11 }, color: this.COLORS.tick },
                    grid: { color: this.COLORS.grid },
                    ...yOptions,
                },
            },
        };
    },

    /* ------------------------------------------------------------------ */
    /*  Charts                                                             */
    /* ------------------------------------------------------------------ */
    renderPaceChart(grouping) {
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
    },

    renderDistanceChart(grouping) {
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
    },


    /* ------------------------------------------------------------------ */
    /*  Training Load + ACWR Chart                                         */
    /* ------------------------------------------------------------------ */
    async loadTrainingLoad() {
        try {
            const res = await fetch('/api/analytics/training-load?days=90', { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();
            if (!data.available) return;

            this.acwrData = data;
            // Re-render chart with ACWR overlay
            const g = document.getElementById('loadGrouping');
            this.renderTrainingLoadChart(g ? g.value : 'weekly');
        } catch (err) {
            console.error('Failed to load training load:', err);
        }
    },

    renderTrainingLoadChart(grouping) {
        const data = this.getGroupedData(grouping);
        if (data.length === 0) { this.hideChart('trainingLoadChartCard'); return; }
        this.showChart('trainingLoadChartCard');

        const labels = data.map(d => d.label);
        const loads  = data.map(d => parseFloat(d.load.toFixed(1)));

        const datasets = [
            {
                label: 'Training Load',
                data: loads,
                backgroundColor: this.COLORS.primaryFill,
                borderColor: this.COLORS.primary,
                borderWidth: 1.5,
                borderRadius: 4,
                yAxisID: 'y',
            },
        ];

        // Overlay ACWR line from server data
        const acwrValues = this._groupAcwrByPeriod(grouping, labels.length);
        const hasAcwr = acwrValues && acwrValues.some(v => v != null);

        if (hasAcwr) {
            datasets.push({
                label: 'ACWR',
                data: acwrValues,
                type: 'line',
                borderColor: this.COLORS.purple,
                backgroundColor: this.COLORS.purpleFill,
                borderWidth: 2.5,
                pointRadius: 4,
                pointBackgroundColor: acwrValues.map(v => this._acwrColor(v)),
                pointBorderColor: acwrValues.map(v => this._acwrColor(v)),
                fill: false,
                tension: 0.35,
                spanGaps: true,
                yAxisID: 'y1',
            });
        }

        this.destroyChart('trainingLoadChart');
        const ctx = document.getElementById('trainingLoadChart').getContext('2d');
        const opts = this._baseChartOptions(2.2, {
            ticks: { font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });

        if (hasAcwr) {
            opts.scales.y1 = {
                position: 'right',
                min: 0,
                max: 2.5,
                ticks: {
                    callback: v => v.toFixed(1),
                    font: { size: 10 },
                    color: this.COLORS.purple,
                    stepSize: 0.5,
                },
                grid: { display: false },
            };
            opts.plugins.legend = { display: true, position: 'top', labels: { boxWidth: 12, font: { size: 11 } } };
        }

        opts.plugins.tooltip = {
            callbacks: {
                label: c => {
                    if (c.dataset.label === 'ACWR') {
                        const v = c.parsed.y;
                        if (v == null) return null;
                        return `ACWR: ${v.toFixed(2)} (${this._acwrLabel(v)})`;
                    }
                    return `Load: ${c.parsed.y}`;
                },
            },
        };

        this.charts.trainingLoadChart = new Chart(ctx, {
            type: 'bar',
            data: { labels, datasets },
            options: opts,
        });

        // Render ACWR status badge on the card header
        this._renderAcwrBadge();
    },

    _groupAcwrByPeriod(grouping, expectedLen) {
        if (!this.acwrData || !this.acwrData.history) return null;

        const buckets = {};
        for (const d of this.acwrData.history) {
            const dt = new Date(d.date);
            let key;
            if (grouping === 'monthly') {
                key = `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}`;
            } else {
                const mon = this.startOfWeek(dt);
                key = `${mon.getFullYear()}-${String(mon.getMonth()+1).padStart(2,'0')}-${String(mon.getDate()).padStart(2,'0')}`;
            }
            if (!buckets[key]) buckets[key] = [];
            buckets[key].push(d.acwr);
        }

        const sorted = Object.keys(buckets).sort();
        const values = sorted.map(k => {
            const vals = buckets[k];
            return parseFloat((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2));
        });

        // Align: take last N to match chart labels
        if (values.length >= expectedLen) return values.slice(values.length - expectedLen);
        const padded = Array(expectedLen - values.length).fill(null).concat(values);
        return padded;
    },

    _acwrColor(v) {
        if (v == null) return '#999';
        if (v < 0.8)  return '#F59E0B';  // amber — under-training
        if (v <= 1.3)  return '#10B981';  // green — optimal
        if (v <= 1.5)  return '#F97316';  // orange — caution
        return '#EF4444';                  // red — danger
    },

    _acwrLabel(v) {
        if (v == null) return '';
        if (v < 0.8)  return 'Under-training';
        if (v <= 1.3)  return 'Optimal';
        if (v <= 1.5)  return 'Elevated risk';
        return 'Injury danger';
    },

    _renderAcwrBadge() {
        const header = document.querySelector('#trainingLoadChartCard .analytics-card-header');
        if (!header) return;
        // Remove old badge
        const old = header.querySelector('.acwr-badge');
        if (old) old.remove();

        if (!this.acwrData || !this.acwrData.current) return;
        const c = this.acwrData.current;
        const badge = document.createElement('span');
        badge.className = `acwr-badge acwr-badge--${c.risk}`;
        badge.textContent = `ACWR ${c.acwr.toFixed(2)}`;
        badge.title = this._acwrLabel(c.acwr);
        // Insert before the grouping select
        const select = header.querySelector('.grouping-select');
        if (select) header.insertBefore(badge, select);
        else header.appendChild(badge);
    },


    /* ------------------------------------------------------------------ */
    /*  Grouping Controls                                                  */
    /* ------------------------------------------------------------------ */
    bindGroupingControls() {
        const mapping = {
            paceGrouping:       'renderPaceChart',
            distanceGrouping:   'renderDistanceChart',
            efficiencyGrouping: 'renderEfficiencyChart',
            loadGrouping:       'renderTrainingLoadChart',
        };
        for (const [id, method] of Object.entries(mapping)) {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', () => this[method](el.value));
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Utility Helpers                                                    */
    /* ------------------------------------------------------------------ */
    destroyChart(name) {
        if (this.charts[name]) { this.charts[name].destroy(); delete this.charts[name]; }
    },
    hideChart(id) { const el = document.getElementById(id); if (el) el.style.display = 'none'; },
    showChart(id) { const el = document.getElementById(id); if (el) el.style.display = ''; },
    setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; },

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
            return (await res.json()).connected;
        } catch { return false; }
    },

    async syncStravaPeriod(daysBack) {
        try {
            const params = daysBack !== null ? `?force_days=${daysBack}` : '?full_sync=true';
            const res = await fetch(`/api/strava/sync${params}`, { method: 'POST', credentials: 'same-origin' });
            if (!res.ok) { console.warn('Strava sync failed:', await res.text()); return false; }
            const data = await res.json();
            console.log(`Strava sync: ${data.synced} new, ${data.skipped} skipped`);
            if (data.errors?.length) console.warn('Mapping errors:', data.errors);
            return true;
        } catch (err) { console.error('Strava sync error:', err); return false; }
    },

    async loadRuns() {
        let url = '/api/analytics/runs';
        if (this.currentPlanId) url += '?plan_id=' + encodeURIComponent(this.currentPlanId);
        const res = await fetch(url, { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Failed to fetch runs');
        const data = await res.json();
        this.allRuns = data.runs.filter(r => r.date);
        this.planInfo = data.plan || null;
    },

    async reloadRuns() {
        try {
            await this.loadRuns();
        } catch (err) { console.error('Reload runs error:', err); }
    },

    bindPlanSelector() {
        const el = document.getElementById('planSelector');
        if (!el) return;
        el.addEventListener('change', async () => {
            this.currentPlanId = el.value || null;
            const loading = document.getElementById('analyticsLoading');
            const dashboard = document.getElementById('analyticsDashboard');
            const empty = document.getElementById('analyticsEmpty');
            if (loading) loading.style.display = '';
            if (dashboard) dashboard.style.display = 'none';
            if (empty) empty.style.display = 'none';

            try {
                await this.loadRuns();
                if (loading) loading.style.display = 'none';
                if (this.allRuns.length === 0) {
                    if (empty) empty.style.display = 'block';
                    return;
                }
                if (dashboard) dashboard.style.display = 'block';
                this.filterByPeriod(this.currentPlanId ? 'all' : this.currentPeriodDays);
                if (this.currentPlanId) {
                    this.showPlanSection(this.currentPlanId);
                } else {
                    this.hidePlanSection();
                }
            } catch (err) {
                console.error('Plan switch error:', err);
                if (loading) loading.style.display = 'none';
                if (empty) empty.style.display = 'block';
            }
        });
    },

    showPlanSection(planId) {
        const section = document.getElementById('planScopedSection');
        if (section) section.style.display = '';
        this.loadReadiness(planId);
        this.loadGapAnalysis(planId);
        this.loadGapTrend(planId);
        this.loadAdherenceHeatmap(planId);
    },

    hidePlanSection() {
        const section = document.getElementById('planScopedSection');
        if (section) section.style.display = 'none';
    },

    /* ------------------------------------------------------------------ */
    /*  Race Readiness (plan-scoped)                                       */
    /* ------------------------------------------------------------------ */
    async loadReadiness(planId) {
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
    },

    _renderReadiness(d) {
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
    },

    /* ------------------------------------------------------------------ */
    /*  Gap Analysis (plan-scoped)                                         */
    /* ------------------------------------------------------------------ */
    async loadGapAnalysis(planId) {
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
    },

    _renderGapAnalysis(data) {
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
    },

    _esc(str) {
        if (str == null) return '';
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(String(str)));
        return div.innerHTML;
    },


    /* ------------------------------------------------------------------ */
    /*  Gap Trend Chart (plan-scoped)                                      */
    /* ------------------------------------------------------------------ */
    async loadGapTrend(planId) {
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
    },

    /* ------------------------------------------------------------------ */
    /*  Workout Adherence Heatmap (plan-scoped)                            */
    /* ------------------------------------------------------------------ */
    async loadAdherenceHeatmap(planId) {
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
    },

    /* ------------------------------------------------------------------ */
    /*  Tab Switching                                                      */
    /* ------------------------------------------------------------------ */
    bindTabSwitching() {
        const tabs = document.querySelectorAll('.analytics-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.tab;
                if (target === this.activeTab) return;
                this.switchTab(target);
            });
        });
    },

    switchTab(tabName) {
        this.activeTab = tabName;
        // Update tab buttons
        document.querySelectorAll('.analytics-tab').forEach(t => {
            t.classList.toggle('analytics-tab--active', t.dataset.tab === tabName);
        });
        // Show/hide panels
        const dashboard = document.getElementById('analyticsDashboard');
        const insights = document.getElementById('analyticsInsightsTab');
        if (dashboard) dashboard.style.display = tabName === 'dashboard' ? 'block' : 'none';
        if (insights) insights.style.display = tabName === 'insights' ? 'block' : 'none';
    },

    /* ------------------------------------------------------------------ */
    /*  Insights Tab                                                       */
    /* ------------------------------------------------------------------ */
    async loadInsights() {
        try {
            const res = await fetch('/api/analytics/insights', { credentials: 'same-origin' });
            if (!res.ok) return;
            this.insightsData = await res.json();
            this.renderInsights();
        } catch (err) {
            console.error('Insights load error:', err);
        }
    },

    renderInsights() {
        const data = this.insightsData;
        const list = document.getElementById('insightsList');
        const empty = document.getElementById('insightsEmpty');
        const loading = document.getElementById('insightsLoading');
        const badge = document.getElementById('insightsBadge');

        if (loading) loading.style.display = 'none';

        if (!data || !data.available) {
            if (empty) empty.style.display = 'block';
            if (list) list.style.display = 'none';
            return;
        }

        // Hide empty state, show list
        if (empty) empty.style.display = 'none';

        // Update badge with count of actionable insights (priority <= 3)
        const actionable = data.insights.filter(i => i.priority <= 3).length;
        if (badge) {
            badge.textContent = actionable;
            badge.style.display = actionable > 0 ? 'inline-flex' : 'none';
        }

        // Render profile summary
        this.renderProfileSummary(data.profile);

        // Render insight cards
        if (!list) return;
        list.innerHTML = data.insights.map(i => `
            <div class="insight-card insight-card--${this._esc(i.sentiment)}">
                <div class="insight-icon">${i.icon}</div>
                <div class="insight-content">
                    <div class="insight-header">
                        <span class="insight-title">${this._esc(i.title)}</span>
                        <span class="insight-category">${this._esc(i.category)}</span>
                    </div>
                    <p class="insight-body">${this._esc(i.body)}</p>
                </div>
            </div>
        `).join('');
        list.style.display = 'flex';
    },

    renderProfileSummary(profile) {
        const el = document.getElementById('profileSummary');
        if (!el || !profile) return;

        const set = (id, val) => {
            const s = document.getElementById(id);
            if (s) s.textContent = val;
        };

        set('profileVdot', profile.current_vdot || '--');
        set('profileWeeklyKm', profile.avg_weekly_km || '--');
        set('profileRunsWeek', profile.runs_per_week || '--');
        set('profileAcwr', profile.acwr != null ? profile.acwr.toFixed(2) : '--');
        set('profileEasyPct', profile.easy_pct ? `${Math.round(profile.easy_pct)}%` : '--');

        el.style.display = 'flex';
    },

    showSyncIndicator() {
        const el = document.getElementById('stravaSyncIndicator');
        if (el) el.style.display = 'flex';
    },
    hideSyncIndicator() {
        const el = document.getElementById('stravaSyncIndicator');
        if (el) el.style.display = 'none';
    },
    showSyncError(message) {
        const el = document.getElementById('stravaSyncIndicator');
        if (!el) return;
        const label = el.querySelector('.strava-sync-label');
        const spinner = el.querySelector('.strava-sync-spinner');
        if (spinner) spinner.style.display = 'none';
        if (label) label.textContent = message;
        el.style.display = 'flex';
        setTimeout(() => {
            el.style.display = 'none';
            if (label) label.textContent = 'Syncing\u2026';
            if (spinner) spinner.style.display = '';
        }, 4000);
    },
};

// Expose on window so nav.html's sync handler can reload the dashboard
window.AnalyticsDashboard = AnalyticsDashboard;

document.addEventListener('DOMContentLoaded', () => AnalyticsDashboard.init());
