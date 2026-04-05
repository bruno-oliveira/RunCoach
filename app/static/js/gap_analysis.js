/**
 * Gap Analysis Tab — loads data via API and renders the dashboard.
 */

let gapLoaded = false;

window.loadGapAnalysis = function () {
    if (gapLoaded) return;

    var planId = window.APP_CTX && window.APP_CTX.plan_id;
    if (!planId) return;

    var loading = document.getElementById('gap-loading');
    var content = document.getElementById('gap-content');
    var empty = document.getElementById('gap-empty');

    if (!loading || !content) return;

    loading.style.display = 'flex';

    fetch('/api/plan/' + planId + '/gaps', { headers: authHeaders(), credentials: 'same-origin' })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            loading.style.display = 'none';
            if (!data.available) {
                empty.style.display = '';
                var p = empty.querySelector('p');
                if (p) p.textContent = data.reason || 'Not enough data yet.';
                return;
            }
            content.style.display = '';
            content.innerHTML = renderGapAnalysis(data);
            gapLoaded = true;
        })
        .catch(function (err) {
            loading.style.display = 'none';
            content.style.display = '';
            content.innerHTML = '<p class="gap-error">Could not load gap analysis data.</p>';
            console.error('[gap-analysis]', err);
        });
};

var esc = escapeHtml;

function verdictLabel(verdict) {
    var labels = {
        'on_track': 'On Track',
        'close': 'Close',
        'behind': 'Behind',
        'far_behind': 'Far Behind',
        'needs_attention': 'Needs Attention',
        'insufficient_data': 'No Data'
    };
    return labels[verdict] || verdict;
}

function barColor(verdict) {
    var colors = {
        'on_track': 'var(--color-success, #16a34a)',
        'close': 'var(--color-warning, #ca8a04)',
        'behind': 'var(--color-warning-strong, #ea580c)',
        'far_behind': 'var(--color-error, #dc2626)',
        'needs_attention': 'var(--color-warning-strong, #ea580c)',
        'insufficient_data': 'var(--color-text-secondary)'
    };
    return colors[verdict] || 'var(--color-primary)';
}

function renderGapAnalysis(d) {
    var html = '';

    // ── Summary cards ──
    html += '<div class="gap-summary">';
    html += summaryCard('Volume', d.volume_gap.verdict, formatPct(d.volume_gap.deficit_pct) + ' deficit', d.volume_gap.actual_weekly_avg_km + ' / ' + d.volume_gap.planned_weekly_avg_km + ' km/wk');
    html += summaryCard('Long Run', d.long_run_gap.verdict, formatPct(d.long_run_gap.deficit_pct) + ' deficit', d.long_run_gap.longest_actual_km + ' / ' + d.long_run_gap.target_km + ' km');
    html += summaryCard('Consistency', d.consistency.verdict, d.consistency.completion_rate_pct + '% completion', d.consistency.skipped_workouts + ' skipped, ' + d.consistency.rescheduled_workouts + ' rescheduled');
    if (d.pace_gap.verdict !== 'insufficient_data') {
        html += summaryCard('Pace', d.pace_gap.verdict, '+' + d.pace_gap.gap_seconds + 's gap', formatPace(d.pace_gap.current_pace_min_km) + ' vs ' + formatPace(d.pace_gap.target_pace_min_km) + ' target');
    }
    html += '</div>';

    // ── Dimension bars ──
    html += '<div class="gap-dimensions">';
    html += dimensionBar('Weekly Volume', d.volume_gap);
    html += dimensionBar('Long Run Distance', d.long_run_gap);
    html += dimensionBar('Workout Consistency', d.consistency, true);
    if (d.pace_gap.verdict !== 'insufficient_data') {
        html += dimensionBar('Race Pace', d.pace_gap);
    }
    html += '</div>';

    // ── VDOT section ──
    if (d.fitness_trajectory.current_vdot) {
        html += renderVdot(d.fitness_trajectory);
    }

    // ── Action items ──
    if (d.top_actions && d.top_actions.length > 0) {
        html += '<div class="gap-actions">';
        html += '<div class="gap-actions-title">Top Actions</div>';
        html += '<ol class="gap-action-list">';
        for (var i = 0; i < d.top_actions.length; i++) {
            html += '<li class="gap-action-item">';
            html += '<span class="gap-action-number">' + (i + 1) + '</span>';
            html += '<span>' + esc(d.top_actions[i]) + '</span>';
            html += '</li>';
        }
        html += '</ol>';
        html += '</div>';
    }

    // ── Adjust plan button ──
    html += '<div class="gap-adjust-cta">';
    html += '<button class="btn btn-primary" onclick="adjustPlanFromGaps()">Adjust Plan</button>';
    html += '</div>';

    return html;
}

function summaryCard(label, verdict, value, detail) {
    var html = '<div class="gap-summary-card">';
    html += '<div class="gap-card-label">' + esc(label) + '</div>';
    html += '<div class="gap-card-value"><span class="gap-verdict gap-verdict-' + verdict + '">' + verdictLabel(verdict) + '</span></div>';
    html += '<div class="gap-card-detail">' + esc(value) + '</div>';
    html += '<div class="gap-card-detail">' + esc(detail) + '</div>';
    html += '</div>';
    return html;
}

function dimensionBar(label, gap, isConsistency) {
    var pct;
    if (isConsistency) {
        pct = gap.completion_rate_pct || 0;
    } else {
        pct = Math.max(0, 100 - (gap.deficit_pct || 0));
    }
    pct = Math.min(100, pct);

    var verdict = gap.verdict;
    var color = barColor(verdict);

    var valuesText = '';
    if (isConsistency) {
        valuesText = gap.completion_rate_pct + '% of planned workouts';
    } else if (gap.actual_weekly_avg_km !== undefined) {
        valuesText = gap.actual_weekly_avg_km + ' / ' + gap.planned_weekly_avg_km + ' km/wk';
    } else if (gap.longest_actual_km !== undefined) {
        valuesText = gap.longest_actual_km + ' / ' + gap.target_km + ' km';
    } else if (gap.current_pace_min_km !== undefined) {
        valuesText = formatPace(gap.current_pace_min_km) + ' / ' + formatPace(gap.target_pace_min_km) + ' min/km';
    }

    var html = '<div class="gap-dimension">';
    html += '<div class="gap-dim-header">';
    html += '<span class="gap-dim-label">' + esc(label) + '</span>';
    html += '<span class="gap-dim-values">' + esc(valuesText) + '</span>';
    html += '</div>';
    html += '<div class="gap-bar-track">';
    html += '<div class="gap-bar-fill" style="width:' + pct + '%;background:' + color + '"></div>';
    html += '</div>';
    html += '<span class="gap-verdict gap-verdict-' + verdict + '">' + verdictLabel(verdict) + '</span>';
    html += '</div>';
    return html;
}

function renderVdot(fitness) {
    var html = '<div class="gap-vdot-section">';
    html += '<div class="gap-vdot-value">' + fitness.current_vdot + '</div>';
    html += '<div class="gap-vdot-detail">';
    html += '<div>Current VDOT</div>';
    html += '<div class="gap-vdot-trend gap-vdot-trend-' + fitness.vdot_trend + '">Trend: ' + fitness.vdot_trend + '</div>';
    if (fitness.needed_vdot_for_goal) {
        html += '<div>Goal requires VDOT ' + fitness.needed_vdot_for_goal + '</div>';
        if (fitness.on_track === true) {
            html += '<div class="gap-verdict gap-verdict-on_track" style="margin-top:4px">On Track</div>';
        } else if (fitness.on_track === false) {
            html += '<div class="gap-verdict gap-verdict-behind" style="margin-top:4px">Behind</div>';
        }
    }
    html += '</div>';
    html += '</div>';
    return html;
}

function formatPct(val) {
    if (val === 0 || val === null || val === undefined) return '0%';
    return val.toFixed(1) + '%';
}

function formatPace(minPerKm) {
    if (!minPerKm) return '--:--';
    var mins = Math.floor(minPerKm);
    var secs = Math.round((minPerKm - mins) * 60);
    if (secs === 60) { mins++; secs = 0; }
    return mins + ':' + (secs < 10 ? '0' : '') + secs;
}

window.adjustPlanFromGaps = function () {
    var planId = window.APP_CTX && window.APP_CTX.plan_id;
    if (!planId) return;

    fetch('/api/plan/' + planId + '/adjust', {
        method: 'POST',
        headers: authHeaders({'Content-Type': 'application/json'}),
        credentials: 'same-origin'
    })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.adjusted_weeks || data.message) {
                gapLoaded = false;
                loadGapAnalysis();
                if (window.showToast) {
                    window.showToast('Plan adjusted based on your performance data');
                }
            }
        })
        .catch(function (err) {
            console.error('[gap-analysis] adjust failed:', err);
        });
};
