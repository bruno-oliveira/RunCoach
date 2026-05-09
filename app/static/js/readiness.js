/**
 * Race Readiness Tab — loads data via API and renders the dashboard.
 */

function escapeReadinessHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str == null ? '' : String(str)));
    return div.innerHTML;
}

let readinessLoaded = false;

window.loadReadiness = function () {
    if (readinessLoaded) return;

    const planId = window.APP_CTX && window.APP_CTX.plan_id;
    if (!planId) return;

    const loading = document.getElementById('readiness-loading');
    const content = document.getElementById('readiness-content');
    const empty = document.getElementById('readiness-empty');

    if (!loading || !content) return;

    fetch('/api/plan/' + planId + '/readiness', { credentials: 'same-origin' })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            loading.style.display = 'none';
            if (!data.available) {
                empty.style.display = '';
                empty.querySelector('p').textContent = data.reason || 'Not enough data yet.';
                return;
            }
            content.style.display = '';
            content.innerHTML = renderReadiness(data);
            readinessLoaded = true;
        })
        .catch(function (err) {
            loading.style.display = 'none';
            content.style.display = '';
            content.innerHTML = '<p class="readiness-error">Could not load readiness data.</p>';
            console.error('[readiness]', err);
        });
};

function renderReadiness(d) {
    var html = '';

    // ── Hero score ──
    var scoreClass = d.overall_score >= 75 ? 'score-strong' : d.overall_score >= 50 ? 'score-good' : 'score-developing';
    html += '<div class="readiness-hero">';
    html += '  <div class="readiness-score-ring ' + scoreClass + '">';
    html += '    <span class="readiness-score-number">' + d.overall_score + '</span>';
    html += '    <span class="readiness-score-label">/ 100</span>';
    html += '  </div>';
    html += '  <div class="readiness-hero-meta">';
    html += '    <h2>Race Readiness</h2>';
    html += '    <p class="readiness-hero-subtitle">' + escapeReadinessHtml(d.distance_label) + ' &mdash; ' + escapeReadinessHtml(d.overall_label) + '</p>';
    html += '    <div class="readiness-hero-stats">';
    html += '      <span>Week ' + d.current_week + ' / ' + d.total_weeks + '</span>';
    html += '      <span>' + d.days_to_race + ' days to race</span>';
    html += '      <span>' + d.total_runs + ' runs &middot; ' + d.total_km + ' km</span>';
    html += '    </div>';
    html += '  </div>';
    html += '</div>';

    // ── Component breakdown ──
    html += '<div class="readiness-components">';
    html += '  <h3>Readiness Breakdown</h3>';
    html += '  <div class="readiness-component-grid">';
    var compOrder = ['volume', 'fitness', 'long_run', 'consistency', 'taper'];
    var compLabels = { volume: 'Volume', fitness: 'Fitness (VDOT)', long_run: 'Long Run', consistency: 'Consistency', taper: 'Training Phase' };
    var compIcons = { volume: 'V', fitness: 'F', long_run: 'L', consistency: 'C', taper: 'T' };
    for (var i = 0; i < compOrder.length; i++) {
        var key = compOrder[i];
        var comp = d.components[key];
        if (!comp) continue;
        var cclass = comp.score >= 75 ? 'comp-strong' : comp.score >= 50 ? 'comp-good' : 'comp-developing';
        html += '<div class="readiness-component ' + cclass + '">';
        html += '  <div class="readiness-comp-header">';
        html += '    <span class="readiness-comp-name">' + compLabels[key] + '</span>';
        html += '    <span class="readiness-comp-score">' + comp.score + '</span>';
        html += '  </div>';
        html += '  <div class="readiness-comp-bar"><div class="readiness-comp-fill" style="width:' + comp.score + '%"></div></div>';
        html += '  <div class="readiness-comp-detail">' + escapeReadinessHtml(comp.detail) + '</div>';
        html += '</div>';
    }
    html += '  </div>';
    html += '</div>';

    // ── Mountain-from-flat simulation (trail race + flat training) ──
    if (d.mountain_simulation) {
        var sim = d.mountain_simulation;
        var simClass = sim.score >= 75 ? 'sim-strong' : sim.score >= 50 ? 'sim-good' : 'sim-developing';
        html += '<div class="readiness-mountain ' + simClass + '">';
        html += '  <h3>Mountain Simulation (Flat Access)</h3>';
        html += '  <div class="readiness-mountain-head">';
        html += '    <span class="readiness-mountain-score">' + sim.score + '</span>';
        html += '    <span class="readiness-mountain-label">/ 100</span>';
        html += '  </div>';
        html += '  <div class="readiness-mountain-detail">' + escapeReadinessHtml(sim.detail || '') + '</div>';
        html += '  <div class="readiness-mountain-grid">';
        html += '    <div class="mountain-metric"><span class="mountain-key">Uphill</span><span class="mountain-val">' + (sim.actual.uphill_effort_min || 0) + '/' + (sim.planned.uphill_effort_min || 0) + ' min</span><span class="mountain-pct">' + (sim.completion_pct.uphill || 0) + '%</span></div>';
        html += '    <div class="mountain-metric"><span class="mountain-key">Downhill</span><span class="mountain-val">' + (sim.actual.downhill_eccentric_min || 0) + '/' + (sim.planned.downhill_eccentric_min || 0) + ' min</span><span class="mountain-pct">' + (sim.completion_pct.downhill || 0) + '%</span></div>';
        html += '    <div class="mountain-metric"><span class="mountain-key">Transitions</span><span class="mountain-val">' + (sim.actual.hike_run_transition_reps || 0) + '/' + (sim.planned.hike_run_transition_reps || 0) + ' reps</span><span class="mountain-pct">' + (sim.completion_pct.transitions || 0) + '%</span></div>';
        html += '  </div>';
        html += '  <details class="readiness-mountain-explainer">';
        html += '    <summary>How this score is computed</summary>';
        html += '    <p>This score tracks how closely your logged runs match your weekly mountain-simulation targets while training on flat terrain. It combines uphill-effort minutes, downhill-eccentric minutes, and hike-run transitions. Higher completion means your flat training is better matching mountain race demands.</p>';
        html += '  </details>';
        html += '</div>';
    }

    // ── Race predictions ──
    if (d.vdot && d.vdot.current && d.predictions && Object.keys(d.predictions).length > 0) {
        html += '<div class="readiness-predictions">';
        html += '  <h3>Race Predictions <span class="readiness-vdot-badge">VDOT ' + escapeReadinessHtml(d.vdot.current) + ' &mdash; ' + escapeReadinessHtml(d.vdot.trend) + '</span></h3>';
        html += '  <div class="readiness-predictions-grid">';
        var predKeys = Object.keys(d.predictions);
        for (var j = 0; j < predKeys.length; j++) {
            var name = predKeys[j];
            var pred = d.predictions[name];
            var highlight = pred.is_target ? ' prediction-target' : '';
            html += '<div class="readiness-prediction-card' + highlight + '">';
            html += '  <div class="prediction-name">' + escapeReadinessHtml(name) + '</div>';
            html += '  <div class="prediction-time">' + escapeReadinessHtml(pred.time) + '</div>';
            if (pred.range && pred.range.fast && pred.range.slow) {
                html += '  <div class="prediction-range">' + escapeReadinessHtml(pred.range.fast) + ' &ndash; ' + escapeReadinessHtml(pred.range.slow) + '</div>';
            }
            html += '</div>';
        }
        html += '  </div>';
        html += '</div>';
    }

    // ── Scenarios ──
    if (d.scenarios && d.scenarios.length > 0) {
        html += '<div class="readiness-scenarios">';
        html += '  <h3>Race Scenarios</h3>';
        html += '  <div class="readiness-scenarios-table">';
        html += '    <div class="scenario-header">';
        html += '      <span>Scenario</span><span>Time</span><span>Pace</span><span>Prob.</span>';
        html += '    </div>';
        for (var k = 0; k < d.scenarios.length; k++) {
            var s = d.scenarios[k];
            var rowClass = 'scenario-' + s.name.toLowerCase();
            html += '<div class="scenario-row ' + rowClass + '">';
            html += '  <div class="scenario-name">';
            html += '    <strong>' + escapeReadinessHtml(s.name) + '</strong>';
            html += '    <span class="scenario-desc">' + escapeReadinessHtml(s.description) + '</span>';
            html += '  </div>';
            html += '  <span class="scenario-time">' + escapeReadinessHtml(s.time) + '</span>';
            html += '  <span class="scenario-pace">' + escapeReadinessHtml(s.pace) + '</span>';
            html += '  <span class="scenario-prob">' + s.probability + '%</span>';
            html += '</div>';
        }
        html += '  </div>';
        html += '</div>';
    }

    // ── Volume comparison ──
    if (d.volume_comparison && d.volume_comparison.length > 0) {
        html += '<div class="readiness-volume">';
        html += '  <h3>Weekly Volume: Planned vs Actual</h3>';
        html += '  <div class="readiness-volume-chart">';
        for (var w = 0; w < d.volume_comparison.length; w++) {
            var wk = d.volume_comparison[w];
            var maxKm = Math.max(wk.planned, wk.actual, 1);
            var plannedPct = Math.round((wk.planned / (d.peak_week_km || maxKm)) * 100);
            var actualPct = Math.round((wk.actual / (d.peak_week_km || maxKm)) * 100);
            var overUnder = wk.actual >= wk.planned ? 'vol-over' : 'vol-under';
            html += '<div class="readiness-vol-week ' + overUnder + '">';
            html += '  <div class="vol-bars">';
            html += '    <div class="vol-bar vol-planned" style="height:' + Math.max(plannedPct, 2) + '%"  title="Planned: ' + wk.planned + ' km"></div>';
            html += '    <div class="vol-bar vol-actual" style="height:' + Math.max(actualPct, 2) + '%"  title="Actual: ' + wk.actual + ' km"></div>';
            html += '  </div>';
            html += '  <span class="vol-label">W' + wk.week + '</span>';
            html += '</div>';
        }
        html += '  </div>';
        html += '  <div class="readiness-volume-legend">';
        html += '    <span class="legend-item"><span class="legend-dot vol-planned-dot"></span> Planned</span>';
        html += '    <span class="legend-item"><span class="legend-dot vol-actual-dot"></span> Actual</span>';
        html += '  </div>';
        html += '</div>';
    }

    return html;
}
