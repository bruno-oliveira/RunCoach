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
            this.bindPredictionsToggle();
            this.loadRacePredictions();
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
        const toggle = document.getElementById('predictionsToggle');
        const content = document.getElementById('predictionsContent');
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
        this.renderPersonalRecords();
        this.renderRecentRuns();
        this.renderCurrentCharts();
        this.renderEfficiencyChart('weekly');
        this.renderTrainingLoadChart('weekly');
        this.renderDistanceDistChart();
    },

    /** Re-render charts respecting current grouping dropdown values. */
    renderCurrentCharts() {
        const g = id => { const el = document.getElementById(id); return el ? el.value : 'weekly'; };
        this.renderPaceChart(g('paceGrouping'));
        this.renderDistanceChart(g('distanceGrouping'));
        this.renderHRChart(g('hrGrouping'));
        this.renderEfficiencyChart(g('efficiencyGrouping'));
        this.renderTrainingLoadChart(g('loadGrouping'));
        this.renderDistanceDistChart();
        this.renderCadenceChart(g('cadenceGrouping'));
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

        // 5. Run streak
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
    /*  Personal Records (all-time)                                        */
    /* ------------------------------------------------------------------ */
    renderPersonalRecords() {
        const el = document.getElementById('recordsList');
        const card = document.getElementById('recordsCard');
        if (!el) return;

        const all = this.allRuns;
        if (all.length === 0) {
            if (card) card.style.display = 'none';
            return;
        }
        if (card) card.style.display = '';

        const longestRun = all.reduce((best, r) =>
            (r.distance_km || 0) > (best.distance_km || 0) ? r : best, all[0]);

        const fastestRun = all
            .filter(r => r.avg_pace_min_km > 0 && r.distance_km >= 3)
            .reduce((best, r) => (!best || r.avg_pace_min_km < best.avg_pace_min_km) ? r : best, null);

        // Best week (by km)
        const weekBuckets = {};
        for (const r of all) {
            if (!r.date) continue;
            const d = new Date(r.date);
            const mon = this.startOfWeek(d);
            const key = `${mon.getFullYear()}-${String(mon.getMonth()+1).padStart(2,'0')}-${String(mon.getDate()).padStart(2,'0')}`;
            weekBuckets[key] = (weekBuckets[key] || 0) + (r.distance_km || 0);
        }
        const bestWeekKm = Object.values(weekBuckets).reduce((m, v) => Math.max(m, v), 0);

        const elevRuns = all.filter(r => r.elevation_gain_m > 0);
        const mostElev = elevRuns.length
            ? elevRuns.reduce((best, r) => r.elevation_gain_m > best.elevation_gain_m ? r : best, elevRuns[0])
            : null;

        const records = [
            { icon: '📏', label: 'Longest Run',   value: longestRun ? longestRun.distance_km.toFixed(1) : null, unit: 'km' },
            { icon: '⚡', label: 'Fastest Pace',  value: fastestRun ? this.formatPace(fastestRun.avg_pace_min_km) : null, unit: 'min/km' },
            { icon: '📅', label: 'Best Week',     value: bestWeekKm > 0 ? bestWeekKm.toFixed(1) : null, unit: 'km' },
            mostElev ? { icon: '⛰️', label: 'Most Elevation', value: mostElev.elevation_gain_m.toFixed(0), unit: 'm' } : null,
        ].filter(Boolean).filter(r => r.value !== null);

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

            return `
                <div class="run-row">
                    <span class="run-date">${date}</span>
                    <span class="run-distance">${dist}</span>
                    <span class="run-pace">${pace}</span>
                    <span class="run-hr">${hr}</span>
                    <span class="run-type-badge ${typeClass}">${typeLabel}</span>
                    ${ql ? `<span class="quality-badge ${ql.cls}">${ql.label}</span>` : ''}
                </div>
            `;
        }).join('');
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

        this.destroyChart('efficiencyChart');
        const ctx = document.getElementById('efficiencyChart').getContext('2d');
        const opts = this._baseChartOptions(2.2, {
            ticks: { callback: v => v != null ? v.toFixed(2) : '', font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.tooltip = {
            callbacks: {
                label: c => c.dataset.label === 'Trend' ? null
                    : `Efficiency: ${c.parsed.y != null ? c.parsed.y.toFixed(2) : '--'} (speed ÷ HR × 100)`,
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

    renderHRChart(grouping) {
        if (!this.runs.some(r => r.avg_heart_rate > 0)) { this.hideChart('hrChartCard'); return; }
        this.showChart('hrChartCard');

        const data   = this.getGroupedData(grouping);
        const labels = data.map(d => d.label);
        const values = data.map(d => d.avgHR);
        const trend  = this.computeTrendLine(values);

        this.destroyChart('hrChart');
        const ctx = document.getElementById('hrChart').getContext('2d');
        const opts = this._baseChartOptions(2.2, {
            ticks: { callback: v => `${v} bpm`, font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.tooltip = {
            callbacks: { label: c => `${c.dataset.label}: ${Math.round(c.parsed.y)} bpm` },
        };

        this.charts.hrChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Avg HR',
                        data: values,
                        borderColor: '#E84393',
                        backgroundColor: 'rgba(232,67,147,0.10)',
                        fill: true,
                        tension: 0.35,
                        pointRadius: 3,
                        pointBackgroundColor: '#E84393',
                        pointHoverRadius: 5,
                    },
                    {
                        label: 'Trend',
                        data: trend,
                        borderColor: 'rgba(232,67,147,0.35)',
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

    /* ------------------------------------------------------------------ */
    /*  Training Load Chart                                                */
    /* ------------------------------------------------------------------ */
    renderTrainingLoadChart(grouping) {
        const data = this.getGroupedData(grouping);
        if (data.length === 0) { this.hideChart('trainingLoadChartCard'); return; }
        this.showChart('trainingLoadChartCard');

        const labels = data.map(d => d.label);
        const loads  = data.map(d => parseFloat(d.load.toFixed(1)));

        // 4-period rolling average
        const rolling = loads.map((_, i) => {
            const window = loads.slice(Math.max(0, i - 3), i + 1).filter(v => v != null);
            return window.length ? parseFloat((window.reduce((a, b) => a + b, 0) / window.length).toFixed(1)) : null;
        });

        this.destroyChart('trainingLoadChart');
        const ctx = document.getElementById('trainingLoadChart').getContext('2d');
        const opts = this._baseChartOptions(2.2, {
            ticks: { font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.tooltip = {
            callbacks: {
                label: c => c.dataset.label === 'Rolling Avg'
                    ? `4-period avg: ${c.parsed.y}`
                    : `Load: ${c.parsed.y}`,
            },
        };

        this.charts.trainingLoadChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Training Load',
                        data: loads,
                        backgroundColor: this.COLORS.primaryFill,
                        borderColor: this.COLORS.primary,
                        borderWidth: 1.5,
                        borderRadius: 4,
                    },
                    {
                        label: 'Rolling Avg',
                        data: rolling,
                        type: 'line',
                        borderColor: this.COLORS.accent,
                        borderWidth: 2,
                        pointRadius: 0,
                        fill: false,
                        tension: 0.35,
                        spanGaps: true,
                    },
                ],
            },
            options: opts,
        });
    },

    /* ------------------------------------------------------------------ */
    /*  Distance Distribution Chart                                        */
    /* ------------------------------------------------------------------ */
    renderDistanceDistChart() {
        const buckets = [
            { label: '< 5 km',   min: 0,  max: 5  },
            { label: '5–10 km',  min: 5,  max: 10 },
            { label: '10–15 km', min: 10, max: 15 },
            { label: '15–20 km', min: 15, max: 20 },
            { label: '20–25 km', min: 20, max: 25 },
            { label: '25+ km',   min: 25, max: Infinity },
        ];
        const counts = buckets.map(b => this.runs.filter(r => {
            const d = r.distance_km || 0;
            return d >= b.min && d < b.max;
        }).length);

        if (!counts.some(c => c > 0)) { this.hideChart('distDistChartCard'); return; }
        this.showChart('distDistChartCard');

        this.destroyChart('distDistChart');
        const ctx = document.getElementById('distDistChart').getContext('2d');

        this.charts.distDistChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: buckets.map(b => b.label),
                datasets: [{
                    label: 'Runs',
                    data: counts,
                    backgroundColor: buckets.map((_, i) => [
                        'rgba(13,148,136,0.7)',
                        'rgba(29,78,216,0.7)',
                        'rgba(124,58,237,0.7)',
                        'rgba(245,158,11,0.7)',
                        'rgba(255,98,70,0.7)',
                        'rgba(220,38,38,0.7)',
                    ][i]),
                    borderWidth: 0,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: this._mobileRatio(2.2),
                indexAxis: 'y',
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: c => ` ${c.parsed.x} run${c.parsed.x !== 1 ? 's' : ''}` } },
                },
                scales: {
                    x: {
                        ticks: { stepSize: 1, font: { size: 11 }, color: this.COLORS.tick },
                        grid: { color: this.COLORS.grid },
                    },
                    y: {
                        ticks: { font: { size: 11 }, color: this.COLORS.tick },
                        grid: { display: false },
                    },
                },
            },
        });
    },

    renderCadenceChart(grouping) {
        if (!this.runs.some(r => r.avg_cadence > 0)) { this.hideChart('cadenceChartCard'); return; }
        this.showChart('cadenceChartCard');

        const data   = this.getGroupedData(grouping);
        const labels = data.map(d => d.label);
        const values = data.map(d => d.avgCadence);

        this.destroyChart('cadenceChart');
        const ctx = document.getElementById('cadenceChart').getContext('2d');
        const opts = this._baseChartOptions(2.2, {
            ticks: { callback: v => `${v} spm`, font: { size: 11 }, color: this.COLORS.tick },
            grid: { color: this.COLORS.grid },
        });
        opts.plugins.tooltip = {
            callbacks: { label: c => `${c.parsed.y} spm` },
        };

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
                    tension: 0.35,
                    pointRadius: 3,
                    pointBackgroundColor: this.COLORS.secondary,
                    pointHoverRadius: 5,
                }],
            },
            options: opts,
        });
    },

    /* ------------------------------------------------------------------ */
    /*  Grouping Controls                                                  */
    /* ------------------------------------------------------------------ */
    bindGroupingControls() {
        const mapping = {
            paceGrouping:       'renderPaceChart',
            distanceGrouping:   'renderDistanceChart',
            hrGrouping:         'renderHRChart',
            cadenceGrouping:    'renderCadenceChart',
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

    async reloadRuns() {
        try {
            const res = await fetch('/api/analytics/runs', { credentials: 'same-origin' });
            if (!res.ok) throw new Error('Failed to reload');
            const data = await res.json();
            this.allRuns = data.runs.filter(r => r.date);
        } catch (err) { console.error('Reload runs error:', err); }
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
