/**
 * Analytics Dashboard — Performance Hub (Core)
 * Full client-side aggregation + Chart.js rendering.
 *
 * This is the core orchestrator. Chart rendering, predictions, records,
 * insights, evolution, and training-load modules are loaded separately
 * and attach their methods to this object via window.AnalyticsDashboard.
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
    activeTab: 'coach',
    // Declarative tab model. The Coach Hub is two surfaces: a narrated "Coach"
    // view and a "Progress" reference view. Adding/removing a surface is a
    // one-line change here — init, switchTab, persistence and plan-scoping all
    // derive from this table.
    //   planScoped   → panel renders its own prompt/empty per selected plan and
    //                  ignores the header period filter.
    //   headerPeriod → panel filters by the header period window.
    TABS: [
        { key: 'coach',    panel: 'analyticsCoach',    planScoped: true,  headerPeriod: false },
        { key: 'progress', panel: 'analyticsProgress', planScoped: false, headerPeriod: true  },
    ],
    // Legacy tab keys (pre-collapse) mapped onto the current surfaces so old
    // bookmarks and persisted state still land somewhere sensible.
    LEGACY_TAB_MAP: {
        today: 'coach', signals: 'coach', insights: 'coach',
        progress: 'progress', evolution: 'progress',
    },
    DEFAULT_TAB: 'coach',
    PERSIST_KEY: 'runcoach.coachHub.state',
    stravaConnected: false,

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
        const dashboard = document.getElementById('analyticsProgress');
        const loading   = document.getElementById('analyticsLoading');
        const empty     = document.getElementById('analyticsEmpty');
        if (!dashboard) return;

        try {
            this.stravaConnected = await this.checkStravaConnection();
            if (this.stravaConnected) {
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

            const persisted = this._readPersistedState();

            // Restore the period preference before any data-window calc so the
            // dropdown value and the actual filter agree on first paint.
            this._applyPersistedPeriod(persisted.period);

            // Plan selection: prefer the persisted plan when it still exists;
            // otherwise fall back to the most recent plan with logged runs, so
            // the Today tab lands with data. Never overwrite an explicit choice.
            const planSel = document.getElementById('planSelector');
            if (planSel) {
                const wantsAllRuns = persisted.plan === '';
                const persistedPlanExists = persisted.plan &&
                    Array.from(planSel.options).some(o => o.value === persisted.plan);
                if (persistedPlanExists) {
                    planSel.value = persisted.plan;
                    this.currentPlanId = persisted.plan;
                    await this.loadRuns();
                } else if (wantsAllRuns) {
                    planSel.value = '';
                    this.currentPlanId = null;
                } else if (planSel.options.length > 1) {
                    planSel.value = planSel.options[1].value;
                    this.currentPlanId = planSel.value || null;
                    await this.loadRuns();
                    if (this.allRuns.length === 0) {
                        planSel.value = '';
                        this.currentPlanId = null;
                        await this.loadRuns();
                    }
                }
            }

            dashboard.style.display = 'block';
            this.filterByPeriod(this.currentPeriodDays);
            this.bindGroupingControls();
            this.bindPeriodSelector();
            this.bindPlanSelector();
            this.bindPredictionsToggle();
            this.bindTabSwitching();
            this.loadTrainingLoad();
            this.loadPersonalRecords();
            this.loadInsights();
            if (this.currentPlanId) this.showPlanSection(this.currentPlanId);

            const wanted = this.LEGACY_TAB_MAP[persisted.tab] || persisted.tab;
            this.switchTab(this._tabConfig(wanted) ? wanted : this.DEFAULT_TAB);
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

    /* ------------------------------------------------------------------ */
    /*  State Persistence                                                  */
    /*                                                                     */
    /*  Coach Hub state (active tab, selected plan, period window) is      */
    /*  mirrored to the URL so reloads and shares land where the user      */
    /*  left off. localStorage backs the URL on a clean reload.            */
    /* ------------------------------------------------------------------ */
    _readPersistedState() {
        const params = new URLSearchParams(location.search);
        let tab = params.get('tab');
        let plan = params.get('plan');
        let period = params.get('period');
        if (tab === null && plan === null && period === null) {
            try {
                const stored = JSON.parse(localStorage.getItem(this.PERSIST_KEY) || 'null');
                if (stored) {
                    tab = stored.tab ?? null;
                    plan = stored.plan ?? null;
                    period = stored.period != null ? String(stored.period) : null;
                }
            } catch (_) { /* localStorage may be unavailable */ }
        }
        return { tab, plan, period };
    },

    _persistState() {
        const params = new URLSearchParams();
        if (this.activeTab && this.activeTab !== this.DEFAULT_TAB) params.set('tab', this.activeTab);
        if (this.currentPlanId) params.set('plan', String(this.currentPlanId));
        if (this.currentPeriodDays != null && this.currentPeriodDays !== 30) {
            params.set('period', String(this.currentPeriodDays));
        }
        const qs = params.toString();
        const url = qs ? `${location.pathname}?${qs}` : location.pathname;
        try { history.replaceState(null, '', url); } catch (_) { /* ignore */ }
        try {
            localStorage.setItem(this.PERSIST_KEY, JSON.stringify({
                tab: this.activeTab,
                plan: this.currentPlanId,
                period: this.currentPeriodDays,
            }));
        } catch (_) { /* ignore */ }
    },

    _applyPersistedPeriod(period) {
        if (!period) return;
        const sel = document.getElementById('periodSelector');
        const customWrap = document.getElementById('customDaysWrap');
        const customInput = document.getElementById('customDaysInput');
        if (!sel) return;
        const standard = ['30', '60', '90', '365', 'all'];
        if (standard.includes(period)) {
            sel.value = period;
            this.currentPeriodDays = period === 'all' ? 'all' : parseInt(period, 10);
        } else if (/^\d+$/.test(period)) {
            const n = Math.min(366, Math.max(1, parseInt(period, 10)));
            sel.value = 'custom';
            if (customWrap) customWrap.style.display = 'flex';
            if (customInput) customInput.value = n;
            this.currentPeriodDays = n;
        }
    },

    bindPeriodSelector() {
        const el = document.getElementById('periodSelector');
        if (!el) return;

        const customWrap  = document.getElementById('customDaysWrap');
        const customInput = document.getElementById('customDaysInput');
        const customApply = document.getElementById('customDaysApply');

        const applyPeriod = async (days) => {
            this.filterByPeriod(days);
            this._persistState();

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

    _esc(str) {
        if (str == null) return '';
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(String(str)));
        return div.innerHTML;
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
            this._persistState();
            const loading = document.getElementById('analyticsLoading');
            const dashboard = document.getElementById('analyticsProgress');
            const empty = document.getElementById('analyticsEmpty');
            if (loading) loading.style.display = '';
            if (dashboard) dashboard.style.display = 'none';
            if (empty) empty.style.display = 'none';

            // The Coach surface is plan-scoped: it renders its own prompt/empty
            // states, so it stays visible across a plan change.
            const cfg = this._tabConfig(this.activeTab);
            const planScopedTab = !!(cfg && cfg.planScoped);

            try {
                await this.loadRuns();
                if (loading) loading.style.display = 'none';

                // Refresh the active plan-scoped panel on every plan change.
                if (planScopedTab) {
                    if (dashboard) dashboard.style.display = 'none';
                    this.reloadPlanScopedTab();
                }

                if (this.allRuns.length === 0) {
                    if (!planScopedTab && empty) empty.style.display = 'block';
                    if (this.currentPlanId) this.showPlanSection(this.currentPlanId);
                    return;
                }
                if (!planScopedTab && dashboard) dashboard.style.display = 'block';
                this.filterByPeriod(this.currentPeriodDays);
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

    /** Re-fetch the plan-scoped Coach panel (today narrative + signals). */
    reloadPlanScopedTab() {
        if (this.activeTab !== 'coach') return;
        if (this.loadToday) this.loadToday(this.currentPlanId);
        if (this.loadSignals) this.loadSignals(this.currentPlanId);
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
    /*  Tab Switching                                                      */
    /* ------------------------------------------------------------------ */
    bindTabSwitching() {
        const tabs = Array.from(document.querySelectorAll('.analytics-tab'));
        tabs.forEach((tab, idx) => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.tab;
                if (target === this.activeTab) return;
                this.switchTab(target);
            });
            // Roving-tabindex keyboard support for the tablist (WAI-ARIA).
            tab.addEventListener('keydown', (e) => {
                let next = null;
                if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % tabs.length;
                else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx - 1 + tabs.length) % tabs.length;
                else if (e.key === 'Home') next = 0;
                else if (e.key === 'End') next = tabs.length - 1;
                if (next === null) return;
                e.preventDefault();
                tabs[next].focus();
                this.switchTab(tabs[next].dataset.tab);
            });
        });
    },

    _tabConfig(key) {
        return this.TABS.find(t => t.key === key) || null;
    },

    switchTab(tabName) {
        if (!this._tabConfig(tabName)) tabName = this.DEFAULT_TAB;
        this.activeTab = tabName;

        document.querySelectorAll('.analytics-tab').forEach(t => {
            const active = t.dataset.tab === tabName;
            t.classList.toggle('analytics-tab--active', active);
            t.setAttribute('aria-selected', active ? 'true' : 'false');
            t.tabIndex = active ? 0 : -1;
        });

        // Show the active panel, hide the rest — driven by the tab model.
        this.TABS.forEach(t => {
            const el = document.getElementById(t.panel);
            if (el) el.style.display = t.key === tabName ? 'block' : 'none';
        });

        // Scope the header period selector to tabs that filter by window. The
        // Coach surface is plan-scoped and ignores it.
        const showHeaderPeriod = !!(this._tabConfig(tabName) || {}).headerPeriod;
        const periodSel = document.getElementById('periodSelector');
        const customWrap = document.getElementById('customDaysWrap');
        if (periodSel) periodSel.style.display = showHeaderPeriod ? '' : 'none';
        if (customWrap) {
            const customActive = periodSel && periodSel.value === 'custom';
            customWrap.style.display = (showHeaderPeriod && customActive) ? 'flex' : 'none';
        }

        if (tabName === 'coach') this._activateCoach();

        this._persistState();
    },

    /** Lazy-load the plan-scoped Coach panels (today narrative + signals). */
    _activateCoach() {
        if (this.todayLoadedPlanId !== this.currentPlanId && this.loadToday) {
            this.loadToday(this.currentPlanId);
        }
        if (this.signalsLoadedPlanId !== this.currentPlanId && this.loadSignals) {
            this.loadSignals(this.currentPlanId);
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Sync Indicators                                                    */
    /* ------------------------------------------------------------------ */
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
