/**
 * analytics_signal_chart.js — the "what your coach sees" radar.
 *
 * Renders the 6 adaptation signals (volume, effort, completion, HR zone,
 * feedback, readiness) as a Chart.js radar of their factors against a 1.0
 * baseline ring, plus a weight-aware legend. Attaches to AnalyticsDashboard.
 */
(function () {
    const AD = window.AnalyticsDashboard;

    const SIGNAL_ORDER = [
        ['volume', 'Volume'],
        ['effort', 'Effort'],
        ['completion', 'Completion'],
        ['hr_zone', 'HR Zone'],
        ['feedback', 'Feedback'],
        ['readiness', 'Readiness'],
    ];

    AD.renderSignalChart = function (signals) {
        const ctx = document.getElementById('coachSignalChart');
        if (!ctx) return;

        const labels = SIGNAL_ORDER.map(([, label]) => label);
        const factors = SIGNAL_ORDER.map(([key]) => {
            const s = signals[key] || {};
            // Dimmed/absent signals sit on the baseline so they don't skew the shape.
            return s.has_data === false ? 1.0 : (typeof s.factor === 'number' ? s.factor : 1.0);
        });

        // Tight, symmetric scale around 1.0 so small nudges stay legible.
        let min = Math.min(0.9, ...factors);
        let max = Math.max(1.1, ...factors);
        min = Math.floor((min - 0.05) * 10) / 10;
        max = Math.ceil((max + 0.05) * 10) / 10;

        this.destroyChart('coachSignal');
        this.charts.coachSignal = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Your signals',
                        data: factors,
                        borderColor: this.COLORS.primary,
                        backgroundColor: this.COLORS.primaryFill,
                        pointBackgroundColor: this.COLORS.primary,
                        pointRadius: 3,
                        borderWidth: 2,
                    },
                    {
                        label: 'Baseline',
                        data: labels.map(() => 1.0),
                        borderColor: 'rgba(28, 25, 23, 0.25)',
                        backgroundColor: 'transparent',
                        borderDash: [4, 4],
                        pointRadius: 0,
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (item) => {
                                if (item.datasetIndex === 1) return 'Baseline 1.00';
                                const key = SIGNAL_ORDER[item.dataIndex][0];
                                const s = signals[key] || {};
                                if (s.has_data === false) return 'No data yet';
                                const w = Math.round((s.weight || 0) * 100);
                                return `Factor ${Number(s.factor).toFixed(2)} · weight ${w}%`;
                            },
                        },
                    },
                },
                scales: {
                    r: {
                        min: min,
                        max: max,
                        ticks: {
                            stepSize: 0.1,
                            backdropColor: 'transparent',
                            color: this.COLORS.tick,
                            font: { size: 10 },
                        },
                        grid: { color: this.COLORS.grid },
                        angleLines: { color: this.COLORS.grid },
                        pointLabels: { font: { size: 12 }, color: '#57534E' },
                    },
                },
            },
        });

        this._renderSignalLegend(signals);
    };

    AD._renderSignalLegend = function (signals) {
        const wrap = document.getElementById('coachSignalLegend');
        if (!wrap) return;

        let html = '';
        for (const [key, label] of SIGNAL_ORDER) {
            const s = signals[key] || {};
            const hasData = s.has_data !== false;
            const factor = typeof s.factor === 'number' ? s.factor : null;
            const weight = Math.round((s.weight || 0) * 100);
            const dir = !hasData || factor == null ? 'none'
                : factor > 1.02 ? 'up' : factor < 0.98 ? 'down' : 'flat';
            const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : dir === 'flat' ? '—' : '';

            html += `<div class="coach-signal-legend-row${hasData ? '' : ' is-muted'}">`;
            html += `<span class="coach-signal-legend-name">${this._esc(label)}</span>`;
            if (hasData && factor != null) {
                html += `<span class="coach-signal-legend-factor coach-signal-dir--${dir}">${arrow} ${factor.toFixed(2)}</span>`;
            } else {
                html += `<span class="coach-signal-legend-factor coach-signal-legend-nodata">no data</span>`;
            }
            html += `<span class="coach-signal-legend-weight">${weight}%</span>`;
            html += '</div>';
        }
        wrap.innerHTML = html;
    };
})();
