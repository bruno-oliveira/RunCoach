/**
 * analytics_predictions.js - Race predictions for AnalyticsDashboard
 *
 * Loads and renders VDOT-based race predictions and the collapse toggle.
 */
(function() {
    const AD = window.AnalyticsDashboard;

    /* ------------------------------------------------------------------ */
    /*  Race Predictions                                                   */
    /* ------------------------------------------------------------------ */
    AD.loadRacePredictions = async function() {
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
    };

    AD.renderRacePredictions = function(data) {
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

        if (footerEl) {
            const tr = (key, fallback) => (window.RC_I18N ? RC_I18N.t(key) : fallback);
            const lines = [];

            if (data.best_effort) {
                const effort = data.best_effort;
                const date = effort.date ? new Date(effort.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
                const basedOn = tr('analytics.pred_based_on', 'Based on');
                lines.push(`${basedOn}: ${effort.distance_km}K run on ${date} (${effort.time})`);
            }

            // Surface the predicted-vs-actual feedback loop: when the runner's
            // own races have nudged predictions away from the raw VDOT estimate.
            const cal = data.calibration_factor;
            if (cal && Math.abs(cal - 1.0) >= 0.01) {
                const pct = Math.round(Math.abs(cal - 1.0) * 100);
                const dir = cal > 1.0
                    ? tr('analytics.calib_slower', 'slower')
                    : tr('analytics.calib_faster', 'faster');
                const label = tr('analytics.calibrated_from_races', 'Calibrated from your races');
                lines.push(`${label}: ${pct}% ${dir}`);
            }

            footerEl.innerHTML = lines.map((line) => `<div>${line}</div>`).join('');
        }
    };

    AD.bindPredictionsToggle = function() {
        this._bindCollapseToggle('predictionsToggle', 'predictionsContent');
        this._bindCollapseToggle('raceResultsToggle', 'raceResultsContent');
    };

    AD._bindCollapseToggle = function(toggleId, contentId) {
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
    };
})();
