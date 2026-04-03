# Adaptive Plans & Analytics Roadmap

This document maps out how to wire adaptive training plans into the current RunCoach app and enhance the analytics dashboard to focus on plan gap analysis.

## Current State (what we have)

### Existing adaptive infrastructure (live, wired to UI)

| Component | What it does |
|-----------|-------------|
| `AdaptationService.adjust_plan()` | Scales future workout distances up/down based on recent run performance. Triggered from plan.js and auto-runs after every Strava sync. |
| `AdaptationService.map_runs_to_plan()` | Retroactively links unlinked RunLog entries to plan DailyWorkouts by week (greedy matching on date proximity + distance). |
| `AdaptationService.analyze_performance()` | Read-only analysis: adherence rate, effort trend, pace consistency, recommendations. Used by `PlanService.get_plan_view_data()`. |
| `AdaptationService.detect_skipped_workouts()` | Classifies unlinked workouts as skipped vs rescheduled based on weekly volume. |
| `ReadinessService.compute_readiness()` | Synthesizes volume adherence, VDOT, long run coverage, consistency, and taper positioning into a 0-100 readiness score. Displayed via readiness.js on plan view. |
| `RacePredictorService` | Best-recent-VDOT lookup, race time predictions, gap analysis (current VDOT vs goal time). Called by analytics dashboard and run log creation. |
| `PerformanceService` | Creates pace-zone-based plans from VDOT, auto-calculates fitness from run logs, provides today's workout and plan progress. |
| `FeedbackService` | Per-run coaching feedback (pace, HR zone, effort, volume, pattern analysis). Generated on run creation, viewable per-plan. |

### Existing analytics dashboard (analytics_dashboard.js)

Currently shows:
- Weekly/monthly mileage chart (line)
- Pace trend chart
- Heart rate trend chart
- Effort distribution breakdown
- Run type distribution
- Race predictions (from VDOT)
- Race history (predicted vs actual)
- Strava sync + period filtering (7d / 30d / 90d / 1y / all)

### What was removed (dead code, never wired to UI)

The old `AdaptivePlanGenerator` and `/api/adaptive/*` endpoints were removed. They attempted a standalone adaptive plan generation flow disconnected from the existing plan infrastructure. The approach below integrates adaptation directly into the current plan lifecycle.

---

## Phase 1: Plan-Centric Gap Analysis Panel

**Goal:** Surface per-plan gap analysis directly on the plan view page, replacing the vague "recommendations" with actionable, data-driven insights.

### 1.1 Gap analysis API endpoint

Add `GET /api/plan/{plan_id}/gaps` to `plans.py`.

Combines data from existing services:
- `AdaptationService.analyze_performance()` for adherence & effort data
- `ReadinessService` component scores (volume, long run, consistency)
- `RacePredictorService` for VDOT-based gap (current fitness vs what the plan targets)
- `AdaptationService.detect_skipped_workouts()` for missed-workout count

Returns a structured gap report:
```json
{
  "volume_gap": {
    "planned_weekly_avg_km": 35.0,
    "actual_weekly_avg_km": 28.5,
    "deficit_pct": 18.6,
    "verdict": "behind"
  },
  "long_run_gap": {
    "target_km": 28.0,
    "longest_actual_km": 22.0,
    "deficit_pct": 21.4,
    "verdict": "behind"
  },
  "pace_gap": {
    "target_pace_min_km": 5.0,
    "current_pace_min_km": 5.35,
    "gap_seconds": 21,
    "verdict": "close"
  },
  "consistency": {
    "completion_rate_pct": 72,
    "skipped_workouts": 4,
    "rescheduled_workouts": 2,
    "verdict": "needs_attention"
  },
  "fitness_trajectory": {
    "current_vdot": 42.5,
    "needed_vdot_for_goal": 45.0,
    "vdot_trend": "improving",
    "on_track": false
  },
  "top_actions": [
    "Increase long run by ~1km/week to close the 6km gap before taper",
    "Add one tempo session per week to bring pace closer to target",
    "Focus on completing scheduled easy runs — consistency matters more than intensity right now"
  ]
}
```

### 1.2 Gap analysis UI panel on plan.html

Add a collapsible "Gap Analysis" section on the plan view (below the readiness panel). Renders the gap report with:
- Horizontal bar for each gap dimension (volume, long run, pace, consistency) showing planned vs actual
- Color-coded verdicts (green/amber/red)
- Numbered action items at the bottom
- "Adjust Plan" button triggers existing `adjust_plan()` flow

### 1.3 Files to create/modify

| File | Action |
|------|--------|
| `app/services/gap_analysis_service.py` | **New.** Orchestrates calls to existing services, computes verdicts and top actions. |
| `app/routers/plans.py` | Add `GET /api/plan/{plan_id}/gaps` endpoint. |
| `app/templates/components/gap_panel.html` | **New.** Jinja2 component for the gap UI. |
| `app/templates/plan.html` | Include gap panel component. |
| `app/static/js/plan.js` | Fetch `/api/plan/{id}/gaps` and render into the panel. |
| `app/static/css/plan-core.css` | Styles for gap bars and verdict badges. |

---

## Phase 2: Analytics Dashboard - Plan Gap Focus

**Goal:** Shift the analytics dashboard from a general run-stats page to a plan-aware training intelligence hub.

### 2.1 Plan-scoped analytics

Currently analytics fetches ALL runs (`/api/analytics/runs`). Add plan-scoping:

- `GET /api/analytics/runs?plan_id={id}` — filter runs to those mapped to a specific plan
- Dashboard gets a plan selector dropdown at the top (populated from `/my-plans` data or a lightweight `/api/plans/summary` endpoint)
- When a plan is selected, all charts and metrics scope to that plan's date range and mapped runs

### 2.2 New dashboard sections

#### Gap Trend Chart
Shows weekly gap progression over the plan's duration:
- X-axis: training weeks
- Y-axis: % of plan target achieved
- Lines: volume, long run distance, pace (each as % of target)
- Reveals whether gaps are closing or widening over time

Data source: extend `/api/plan/{plan_id}/gaps` to accept a `?weekly=true` param that returns per-week breakpoints, or add a dedicated `/api/analytics/gap-trend/{plan_id}` endpoint.

#### Workout Type Adherence Heatmap
Grid showing plan weeks (rows) x workout types (columns), with cells colored by completion:
- Green = completed & matched type
- Yellow = completed but different type (rescheduled)
- Red = skipped
- Gray = future / not yet due

Data source: `AdaptationService.map_runs_to_plan()` already links runs to workouts. Combine with `detect_skipped_workouts()`.

#### VDOT Progression vs Target
Line chart overlaying:
- Per-run VDOT (already stored on RunLog)
- Target VDOT needed for goal time (from `RacePredictorService.analyze_fitness_gap()`)
- Trend line showing projected VDOT at race date

### 2.3 Files to create/modify

| File | Action |
|------|--------|
| `app/routers/analytics.py` | Add `plan_id` query param to `/api/analytics/runs`. Add `/api/analytics/gap-trend/{plan_id}`. |
| `app/static/js/analytics_dashboard.js` | Plan selector, gap trend chart, adherence heatmap, VDOT progression chart. |
| `app/templates/analytics.html` | Plan selector UI, new chart containers. |
| `app/static/css/analytics.css` | Styles for heatmap and new chart sections. |

---

## Phase 3: In-Plan Adaptive Suggestions

**Goal:** Surface contextual adaptation suggestions within the plan view itself, not just as a global dashboard.

### 3.1 Weekly suggestion cards

For each upcoming week in the plan view, show a small suggestion card if the adaptation service detects a meaningful signal:

- "You've exceeded targets 3 weeks in a row — this week's distances have been bumped +8%"
- "Long run completion is behind — consider extending Sunday's run to 18km"
- "Effort trending high — this recovery week is well-timed"

These are generated from data already computed by `AdaptationService.adjust_plan()` and `analyze_performance()`. The key is surfacing them inline rather than behind a separate page.

### 3.2 One-tap week adjustments

Each suggestion card offers a one-tap action:
- "Accept adjustment" (already wired via `/api/plan/{id}/adjust`)
- "Skip this week's bump" (new: per-week override that preserves baseline)
- "I'm injured — reduce next 2 weeks by 30%" (new: targeted reduction)

### 3.3 Files to create/modify

| File | Action |
|------|--------|
| `app/services/adaptation_service.py` | Add `get_weekly_suggestions(plan_id, user_id, db)` method returning per-week suggestion objects. |
| `app/routers/plans.py` | Add `GET /api/plan/{plan_id}/suggestions` endpoint. |
| `app/routers/plans.py` | Add `POST /api/plan/{plan_id}/week/{week}/override` for per-week adjustments. |
| `app/templates/components/workout_item.html` | (recreate) Show suggestion badges on workout cards. |
| `app/static/js/plan.js` | Fetch and render suggestion cards per week. |

---

## Phase 4: Proactive Adaptation Triggers

**Goal:** Automatically detect and surface plan adjustments based on training signals, instead of waiting for the user to click "Adjust Plan."

### 4.1 Post-sync adaptation check

After every Strava sync (already runs `_auto_map_and_adjust` in `strava.py`), also generate a "needs attention" flag if:
- Weekly volume deficit > 25% for 2+ consecutive weeks
- Effort trending "increasing" for 3+ weeks
- No runs logged in 7+ days (potential injury/break)
- VDOT declining over 4+ week window

Store the flag on the TrainingPlan model (e.g., `adaptation_alert` JSON column). Surface it as a banner on plan view and a badge on the My Plans page.

### 4.2 Smart plan recalibration

When the user acknowledges an adaptation alert, offer specific recalibration options:
- **"I took time off"** — Rebuilds remaining weeks with a gentler ramp from current actual fitness
- **"I'm ahead of schedule"** — Bumps up remaining weeks' targets
- **"I want to change my race goal"** — Re-runs plan generation for remaining weeks with updated VDOT-based targets

This extends `AdaptationService.adjust_plan()` to support multi-strategy recalibration.

### 4.3 Files to create/modify

| File | Action |
|------|--------|
| `app/models/training_plan.py` | Add `adaptation_alert` TEXT column. |
| `app/services/adaptation_service.py` | Add `check_alerts(plan_id, user_id, db)` and `recalibrate(plan_id, strategy, db)`. |
| `app/routers/strava.py` | Call `check_alerts()` inside `_auto_map_and_adjust()`. |
| `app/routers/plans.py` | Add `POST /api/plan/{plan_id}/recalibrate` endpoint. |
| `app/templates/plan.html` | Adaptation alert banner + recalibration modal. |
| `app/templates/my_plans.html` | Badge on plan cards when alert is active. |

---

## Implementation Order

| Priority | Phase | Effort | Why this order |
|----------|-------|--------|----------------|
| 1 | Phase 1 (Gap Analysis Panel) | Medium | Highest value — puts actionable data where users already look (plan view). Reuses all existing services. |
| 2 | Phase 2.2 VDOT Progression chart only | Small | Quick win for analytics, uses existing `RunLog.vdot` data. |
| 3 | Phase 2.1 + 2.2 (Full analytics overhaul) | Large | Plan-scoped analytics is the foundation for everything else. |
| 4 | Phase 3 (In-plan suggestions) | Medium | Natural follow-on from gap analysis — same data, different presentation. |
| 5 | Phase 4 (Proactive triggers) | Large | Requires the most new logic and careful UX for alert fatigue. |

---

## Key Design Principles

1. **Reuse existing services.** `AdaptationService`, `ReadinessService`, `RacePredictorService`, and `FeedbackService` already compute most of what we need. The gap analysis layer orchestrates, not reimplements.

2. **Plan-centric, not global.** Every metric should be scoped to a specific plan. Global "fitness metrics" without plan context were the problem with the old adaptive router.

3. **Surface insights where users already are.** Plan view is the primary interaction surface. Analytics dashboard is secondary. Don't create new pages; enhance existing ones.

4. **Progressive disclosure.** Show the overall gap score prominently. Show per-dimension breakdowns on expand. Show weekly trends only in analytics. Avoid information overload.

5. **Actionable, not just informative.** Every insight should have a clear next step — adjust plan, extend a run, add a session, or trust the process.
