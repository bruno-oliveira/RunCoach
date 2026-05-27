/**
 * analytics_render.js - Dashboard rendering for AnalyticsDashboard
 *
 * Renders: Summary stats with trend indicators, Activity heatmap (52 weeks),
 * Recent runs feed, and quality labels.
 */
(function() {
    const AD = window.AnalyticsDashboard;

    /* ------------------------------------------------------------------ */
    /*  Summary Stats with Trend Indicators                                */
    /* ------------------------------------------------------------------ */
    AD.renderSummary = function() {
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
    };

    AD.pctChange = function(current, previous) {
        if (!previous || previous === 0) return null;
        return ((current - previous) / previous) * 100;
    };

    AD.setTrend = function(id, pct, invertedIsGood) {
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
    };

    /* ------------------------------------------------------------------ */
    /*  Activity Heatmap (52 weeks)                                        */
    /* ------------------------------------------------------------------ */
    AD.renderHeatmap = function() {
        const container = document.getElementById('activityHeatmap');
        const monthsEl  = document.getElementById('heatmapMonths');
        if (!container) return;

        // Build date -> distance map from ALL runs (all time)
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

        // Month labels — one span per month, width = span of columns x cellSize
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
    };

    /* ------------------------------------------------------------------ */
    /*  Recent Runs Feed                                                   */
    /* ------------------------------------------------------------------ */
    AD.renderRecentRuns = function() {
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
            const inferredMark = r.inferred
                ? '<span class="run-type-inferred" title="Auto-detected from pace &amp; heart rate">auto</span>'
                : '';
            const ql = this.qualityLabel(r);

            const runJson = JSON.stringify(r).replace(/"/g, '&quot;');

            return `
                <div class="run-row">
                    <span class="run-date">${date}</span>
                    <span class="run-distance">${dist}</span>
                    <span class="run-pace">${pace}</span>
                    <span class="run-hr">${hr}</span>
                    <span class="run-type-badge ${typeClass}">${typeLabel}</span>${inferredMark}
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
    };

    AD.qualityLabel = function(run) {
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
    };
})();
