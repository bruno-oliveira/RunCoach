/**
 * analytics_load.js - Training load and race results for AnalyticsDashboard
 *
 * Handles: Training Load + ACWR chart, and Predicted vs Actual (race results).
 * Race readiness and gap analysis live on the plan's Race Readiness tab.
 */
(function() {
    const AD = window.AnalyticsDashboard;

    /* ------------------------------------------------------------------ */
    /*  Predicted vs Actual                                                */
    /* ------------------------------------------------------------------ */
    AD.loadRaceResults = async function() {
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
    };

    AD.renderRaceResults = function(data) {
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
    };

    /* ------------------------------------------------------------------ */
    /*  Training Load + ACWR Chart                                         */
    /* ------------------------------------------------------------------ */
    AD.loadTrainingLoad = async function() {
        try {
            const res = await fetch('/api/analytics/training-load?days=90', { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();
            if (!data.available) return;

            this.acwrData = data;
            // Re-render chart with ACWR overlay
            const g = document.getElementById('loadGrouping');
            this.renderTrainingLoadChart(g ? g.value : 'weekly');
            // Fitness / fatigue / form card
            this.renderFitnessForm(data);
        } catch (err) {
            console.error('Failed to load training load:', err);
        }
    };

    AD.renderTrainingLoadChart = function(grouping) {
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
        const loadCanvas = document.getElementById('trainingLoadChart');
        if (!loadCanvas) return;
        const ctx = loadCanvas.getContext('2d');
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
    };

    AD._groupAcwrByPeriod = function(grouping, expectedLen) {
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
    };

    AD._acwrColor = function(v) {
        if (v == null) return '#999';
        if (v < 0.8)  return '#F59E0B';  // amber -- under-training
        if (v <= 1.3)  return '#10B981';  // green -- optimal
        if (v <= 1.5)  return '#F97316';  // orange -- caution
        return '#EF4444';                  // red -- danger
    };

    AD._acwrLabel = function(v) {
        if (v == null) return '';
        if (v < 0.8)  return 'Under-training';
        if (v <= 1.3)  return 'Optimal';
        if (v <= 1.5)  return 'Elevated risk';
        return 'Injury danger';
    };

    AD._renderAcwrBadge = function() {
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
    };

    /* ------------------------------------------------------------------ */
    /*  Fitness / Fatigue / Form (CTL / ATL / TSB)                         */
    /* ------------------------------------------------------------------ */
    AD._formLabel = function(form) {
        return ({
            fresh: 'Fresh',
            neutral: 'Neutral',
            fatigued: 'Fatigued',
            deep: 'Deep fatigue'
        })[form] || 'Neutral';
    };

    AD._formColor = function(form) {
        return ({
            fresh: '#10B981',     // green
            neutral: '#6366F1',   // indigo
            fatigued: '#F59E0B',  // amber
            deep: '#EF4444'       // red
        })[form] || '#6366F1';
    };

    AD.renderFitnessForm = function(data) {
        const card = document.getElementById('fitnessFormCard');
        if (!card) return;
        if (!data || !data.current || data.current.ctl == null) {
            card.style.display = 'none';
            return;
        }
        card.style.display = '';

        const cur = data.current;
        const ctlEl = document.getElementById('ffCtlValue');
        const atlEl = document.getElementById('ffAtlValue');
        const tsbEl = document.getElementById('ffTsbValue');
        const tsbSub = document.getElementById('ffTsbSub');
        const badge = document.getElementById('ffFormBadge');

        if (ctlEl) ctlEl.textContent = cur.ctl.toFixed(1);
        if (atlEl) atlEl.textContent = cur.atl.toFixed(1);
        if (tsbEl) {
            const sign = cur.tsb > 0 ? '+' : '';
            tsbEl.textContent = sign + cur.tsb.toFixed(1);
            tsbEl.style.color = this._formColor(cur.form);
        }
        if (tsbSub) {
            tsbSub.textContent = ({
                fresh: 'Rested — go race or PB',
                neutral: 'Balanced — keep building',
                fatigued: 'Productive load',
                deep: 'Back off before injury'
            })[cur.form] || 'Balanced';
        }
        if (badge) {
            badge.textContent = this._formLabel(cur.form);
            badge.className = 'ff-form-badge ff-form-badge--' + cur.form;
        }

        // Chart: two lines (CTL solid, ATL dashed) + TSB area, using recent 60 days
        const history = data.history.slice(-60);
        const labels = history.map(d => d.date.slice(5)); // mm-dd
        const ctl = history.map(d => d.ctl);
        const atl = history.map(d => d.atl);
        const tsb = history.map(d => d.tsb);

        this.destroyChart('fitnessFormChart');
        const canvas = document.getElementById('fitnessFormChart');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        this.charts.fitnessFormChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Form (TSB)',
                        data: tsb,
                        borderColor: 'rgba(99,102,241,0.45)',
                        backgroundColor: 'rgba(99,102,241,0.14)',
                        borderWidth: 1,
                        pointRadius: 0,
                        fill: 'origin',
                        tension: 0.35,
                        yAxisID: 'yTsb',
                    },
                    {
                        label: 'Fitness (CTL)',
                        data: ctl,
                        borderColor: '#10B981',
                        backgroundColor: 'transparent',
                        borderWidth: 3,
                        pointRadius: 0,
                        tension: 0.35,
                        yAxisID: 'y',
                    },
                    {
                        label: 'Fatigue (ATL)',
                        data: atl,
                        borderColor: '#F59E0B',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [6, 4],
                        pointRadius: 0,
                        tension: 0.35,
                        yAxisID: 'y',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { position: 'top', labels: { boxWidth: 14, font: { size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: c => `${c.dataset.label}: ${c.parsed.y.toFixed(1)}`,
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: { font: { size: 10 }, color: this.COLORS.tick, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 },
                        grid: { display: false },
                    },
                    y: {
                        position: 'left',
                        beginAtZero: true,
                        ticks: { font: { size: 10 }, color: this.COLORS.tick },
                        grid: { color: this.COLORS.grid },
                        title: { display: true, text: 'Load', font: { size: 11 }, color: this.COLORS.tick },
                    },
                    yTsb: {
                        position: 'right',
                        grid: { display: false },
                        ticks: { font: { size: 10 }, color: 'rgba(99,102,241,0.7)' },
                        title: { display: true, text: 'Form', font: { size: 11 }, color: 'rgba(99,102,241,0.7)' },
                    },
                },
            },
        });
    };

})();
