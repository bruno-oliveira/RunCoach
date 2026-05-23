/**
 * analytics_insights.js - Insights for AnalyticsDashboard
 *
 * Handles two separate concerns:
 *   1. Dashboard insights strip (inline summary cards)
 *   2. Insights tab (full insight cards + profile summary)
 */
(function() {
    const AD = window.AnalyticsDashboard;

    /* ------------------------------------------------------------------ */
    /*  Dashboard Insights Strip                                           */
    /* ------------------------------------------------------------------ */
    AD.renderInsightsStrip = function() {
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
    };

    AD.computeStreak = function() {
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
    };

    /* ------------------------------------------------------------------ */
    /*  Insights Tab                                                       */
    /* ------------------------------------------------------------------ */
    AD.loadInsights = async function() {
        try {
            const [insightsRes, ageRes] = await Promise.all([
                fetch('/api/analytics/insights', { credentials: 'same-origin' }),
                fetch('/api/analytics/training-age', { credentials: 'same-origin' }),
            ]);
            if (insightsRes.ok) this.insightsData = await insightsRes.json();
            if (ageRes.ok) this.trainingAge = await ageRes.json();
            this.renderInsightsTab();
        } catch (err) {
            console.error('Insights load error:', err);
        }
    };

    AD.renderInsightsTab = function() {
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

        // Render profile summary + the new meta sections
        this.renderProfileSummary(data.profile);
        this.renderCoachAssessment(data);
        this.renderTrainingAge();
        this.renderWorkoutMix();

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
    };

    AD.renderProfileSummary = function(profile) {
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
    };

    /* ------------------------------------------------------------------ */
    /*  Coach's Assessment — synthesized paragraph                         */
    /* ------------------------------------------------------------------ */
    AD.renderCoachAssessment = function(data) {
        const card = document.getElementById('coachAssessmentCard');
        const el = document.getElementById('coachAssessment');
        if (!el) return;

        const p = (data && data.profile) || {};
        const ta = this.trainingAge;
        const parts = [];

        if (ta && ta.available) {
            parts.push(`You've been training for ${ta.weeks_since_first_run} week${ta.weeks_since_first_run === 1 ? '' : 's'} — ${ta.total_runs} runs and ${ta.total_km.toLocaleString()} km logged, averaging ${ta.avg_runs_per_week} runs a week.`);
            if (ta.current_streak_weeks >= 2) {
                parts.push(`You're on a ${ta.current_streak_weeks}-week consistency streak${ta.longest_streak_weeks > ta.current_streak_weeks ? ` (your best is ${ta.longest_streak_weeks})` : ' — your longest yet'}.`);
            }
        }
        if (p.current_vdot) parts.push(`Current fitness sits around VDOT ${p.current_vdot}.`);
        if (p.easy_pct != null) {
            const easy = Math.round(p.easy_pct);
            const aerobicNote = easy >= 75 ? 'a healthy aerobic base' : easy >= 60 ? 'a reasonable easy/hard balance' : 'a fairly hard-skewed mix — protect your easy days';
            parts.push(`About ${easy}% of your running is easy-paced — ${aerobicNote}.`);
        }
        const top = (data && data.insights ? data.insights.slice() : [])
            .sort((a, b) => (a.priority || 9) - (b.priority || 9))[0];
        if (top && top.body) parts.push(top.body);

        if (parts.length === 0) {
            if (card) card.style.display = 'none';
            return;
        }
        el.textContent = parts.join(' ');
        if (card) card.style.display = '';
    };

    /* ------------------------------------------------------------------ */
    /*  Training age strip                                                 */
    /* ------------------------------------------------------------------ */
    AD.renderTrainingAge = function() {
        const grid = document.getElementById('insightsMetaGrid');
        const strip = document.getElementById('trainingAgeStrip');
        const ta = this.trainingAge;
        if (!strip) return;
        if (!ta || !ta.available) {
            if (grid) grid.style.display = 'none';
            return;
        }
        const cell = (value, label) =>
            `<div class="training-age-cell"><span class="training-age-value">${value}</span>` +
            `<span class="training-age-label">${label}</span></div>`;
        strip.innerHTML =
            cell(ta.weeks_since_first_run, 'weeks training') +
            cell(ta.total_runs, 'total runs') +
            cell(Math.round(ta.total_km).toLocaleString(), 'total km') +
            cell(`${ta.longest_streak_weeks}w`, 'longest streak');
        if (grid) grid.style.display = 'grid';
    };

    /* ------------------------------------------------------------------ */
    /*  Workout-type distribution                                          */
    /* ------------------------------------------------------------------ */
    AD.WORKOUT_MIX_COLORS = {
        easy: '#0D9488', recovery: '#5EEAD4', long: '#1D4ED8', tempo: '#F59E0B',
        threshold: '#F59E0B', interval: '#EF4444', vo2max: '#EF4444',
        fartlek: '#7C3AED', hill: '#B45309', race_pace: '#DB2777', race: '#DB2777',
        run_walk: '#0D9488',
    };

    AD.renderWorkoutMix = function() {
        const el = document.getElementById('workoutMix');
        if (!el) return;
        const counts = {};
        let total = 0;
        for (const r of this.allRuns) {
            const t = r.workout_type;
            if (!t || t === 'rest') continue;
            counts[t] = (counts[t] || 0) + 1;
            total++;
        }
        if (total === 0) {
            el.innerHTML = '<p class="analytics-empty-text">Log runs with a workout type to see your training mix.</p>';
            return;
        }
        const ordered = Object.entries(counts).sort((a, b) => b[1] - a[1]);
        const seg = ordered.map(([t, n]) => {
            const pct = (n / total) * 100;
            const color = this.WORKOUT_MIX_COLORS[t] || '#A09A93';
            return `<span class="workout-mix-seg" style="width:${pct}%;background:${color}" title="${this._esc(t)}: ${n}"></span>`;
        }).join('');
        const legend = ordered.map(([t, n]) => {
            const pct = Math.round((n / total) * 100);
            const color = this.WORKOUT_MIX_COLORS[t] || '#A09A93';
            const label = t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, ' ');
            return (
                '<div class="workout-mix-legend-row">' +
                `<span class="workout-mix-dot" style="background:${color}"></span>` +
                `<span class="workout-mix-legend-label">${this._esc(label)}</span>` +
                `<span class="workout-mix-legend-val">${n} · ${pct}%</span></div>`
            );
        }).join('');
        el.innerHTML = `<div class="workout-mix-bar">${seg}</div><div class="workout-mix-legend">${legend}</div>`;
    };

    /* ------------------------------------------------------------------ */
    /*  Dispatcher: renderInsights()                                       */
    /*                                                                     */
    /*  The core calls this.renderInsights() from renderAll(). We need     */
    /*  it to call the strip renderer for the dashboard tab AND the        */
    /*  tab renderer for the insights tab.                                 */
    /* ------------------------------------------------------------------ */
    AD.renderInsights = function() {
        this.renderInsightsStrip();
        if (this.insightsData) this.renderInsightsTab();
    };
})();
