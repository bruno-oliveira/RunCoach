/**
 * analytics_records.js - Personal records for AnalyticsDashboard
 *
 * Loads personal records from the API and renders distance PRs and
 * general all-time records, with a client-side fallback.
 */
(function() {
    const AD = window.AnalyticsDashboard;

    /* ------------------------------------------------------------------ */
    /*  Personal Records — API-powered                                     */
    /* ------------------------------------------------------------------ */
    AD.loadPersonalRecords = async function() {
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
    };

    /** Client-side fallback when API is unavailable. */
    AD.renderPersonalRecordsFallback = function() {
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
    };
})();
