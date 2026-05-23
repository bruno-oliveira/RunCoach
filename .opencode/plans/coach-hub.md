# Coach Hub — Design & Implementation Plan

> Transform the current "Analytics" page into a **Coach Hub** that exposes RunCoach's unique adaptation engine, personalization signals, and training intelligence in a way no other running app does.

---

## 1. Vision

RunCoach already has a sophisticated coaching brain — a multi-signal adaptation engine that weighs volume, effort, completion, HR zone adherence, automated feedback sentiment, and daily readiness to dynamically adjust training plans. It computes CTL/ATL/TSB (fitness/fatigue/form), ACWR injury risk, VDOT trends, quality drift, pace patterns, race readiness with scenario planning, and mountain simulation for trail runners.

**The problem:** Almost none of this is visible to the user. The current Analytics page shows generic charts (pace, volume, HR) that any fitness tracker provides. The unique "coach" intelligence is buried behind a tab that requires a plan selection and only surfaces a fraction of what's computed.

**The goal:** Make the Coach Hub the **centerpiece** of RunCoach — a rich, plan-scoped dashboard that shows not just *what* the coach decided, but *why*, with transparent signal breakdowns, trend visualizations, and actionable intelligence.

---

## 2. Deep Data Inventory

### 2.1 What We Already Have (Data Layer)

| Model | Key Fields | Usage |
|-------|-----------|-------|
| **RunLog** | `distance_km`, `duration_minutes`, `avg_pace_min_km`, `avg_heart_rate`, `max_heart_rate`, `avg_cadence`, `elevation_gain_m`, `workout_type`, `perceived_effort`, `vdot`, `effort_quality_score`, `quality_label`, `planned_pace_min_km`, `predicted_time_seconds`, `hr_zone_deviation`, `effort_class` | Core training data |
| **RunFeedback** | `pace_feedback`, `hr_zone_feedback`, `effort_feedback`, `volume_feedback`, `pattern_feedback`, `overall_sentiment` | Automated coaching feedback per run |
| **ReadinessLog** | `sleep`, `soreness`, `energy`, `stress`, `score`, `status` (ready/caution/rest) | Daily wellness check-in |
| **TrainingPlan** | `adaptation_alert`, `adaptation_history`, `adjustment_multiplier`, `pending_recommendation`, `last_change_plan`, `adaptation_revision`, `vdot`, `hr_zones_data`, `race_protocol_data`, `nutrition_phases_data` | Plan state + adaptation history |
| **DailyWorkout** | `baseline_distance_km`, `coaching_rationale`, `hr_zone_target`, `key_workout_id`, `distance_km` (current/adapted) | Individual workout with coaching context |
| **WeeklyPlan** | `week_number`, `total_km`, `workout_types` | Weekly structure |

### 2.2 Computed Signals (Already Exist, Under-Exposed)

| Signal | Source | What It Measures | Current Exposure |
|--------|--------|-----------------|------------------|
| **Volume Ratio** | `signal_computer._volume_signal` | Actual vs planned km (recency-weighted, per-type) | Coach summary only (raw number) |
| **Effort Factor** | `signal_computer._effort_signal` | Perceived effort trend + quality drift | Coach summary only |
| **Completion Rate** | `signal_computer._completion_signal` | % of scheduled workouts completed | Coach summary only |
| **HR Zone Adherence** | `signal_computer._hr_signal` | How well runner stays in target HR zones | Coach summary only |
| **Feedback Factor** | `signal_computer._feedback_signal` | Sentiment ratio from automated coaching feedback | Coach summary only |
| **Readiness Factor** | `signal_computer._readiness_signal` | Aggregated wellness score trend | Coach summary only |
| **CTL (Fitness)** | `training_load_service` | 42-day EWMA of daily training load | Chart on Performance tab |
| **ATL (Fatigue)** | `training_load_service` | 7-day EWMA of daily training load | Chart on Performance tab |
| **TSB (Form)** | `training_load_service` | CTL − ATL (freshness for racing) | Badge + chart |
| **ACWR** | `training_load_service` | Acute:Chronic workload ratio (injury risk) | Insights tab only |
| **VDOT Trend** | `race_predictor_service` | Fitness trajectory (improving/stable/declining) | Evolution tab + predictions |
| **Quality Drift** | `adaptation_math.compute_quality_drift` | `effort_quality_score` change over last 8 runs | Used in multiplier, not shown |
| **Per-Type Ratios** | `signal_computer._volume_signal` | Volume ratio per workout type (Bayesian-shrunk) | Not shown to user |
| **Pace Patterns** | `pattern_analyzer.pattern_feedback` | Recency-weighted deviation from planned pace | Text-only in Coach tab |
| **Week Pulse** | `week_pulse_generator.get_week_pulse` | Current week mood + execution summary | Text-only in Coach tab |
| **Race Readiness** | `readiness_service.compute_readiness` | 5-component readiness score (volume/VDOT/long-run/consistency/taper) | Rendered but not fully explorable |
| **Gap Analysis** | `gap_analysis_service.analyze_gaps` | Volume/long-run/pace/consistency/fitness/elevation gaps + top actions | Rendered but not prominent |
| **Mountain Simulation** | `readiness_scoring.score_mountain_simulation` | Trail-specific vertical prep execution | Only for trail/flat plans |
| **Adaptation Events** | `plan.adaptation_history` | Timeline of plan adjustments with reasons | Shown as timeline |
| **Phase Weights** | `tuning.PHASE_WEIGHTS` | How much each signal matters in current phase | Not shown |
| **Endurance Factor** | `race_predictor_service.compute_endurance_factor` | Long-run calibration of VDOT predictions | Not shown |
| **Predicted vs Actual** | `race_predictor_service.get_race_history` | Accuracy of fitness predictions | Shown as list |

### 2.3 Data We Could Compute But Don't Yet

| Signal | Description | Value |
|--------|-------------|-------|
| **Readiness Trend** | 7/14/30-day rolling average of readiness scores | Show if wellness is improving or declining |
| **HR Zone Distribution Over Time** | % of time spent in each HR zone by week | Show polarization adherence |
| **Cadence Trend** | Running cadence evolution over time | Biomechanical efficiency signal |
| **Elevation Profile** | Weekly elevation gain vs plan target | Trail readiness |
| **Workout Completion Streak** | Consecutive completed workouts | Motivation metric |
| **Recovery Index** | Composite of TSB + readiness + sleep quality | Holistic recovery state |
| **Training Age** | Total weeks of logged training | Context for expectations |
| **Best Recent Efforts** | Top 3 VDOT performances with context | Confidence builder |
| **Plan Fidelity Score** | How closely actual training matches the plan's workout distribution | Overall adherence |
| **Fatigue Accumulation** | Multi-week ATL trend (not just current) | Overtraining early warning |

---

## 3. Current UI Audit

### 3.1 What Exists

**Page:** `/analytics` — "Performance" title, "Your running data at a glance" subtitle

**Tabs:**
1. **Coach** — Plan-scoped. Shows: adaptation banner, CTL/ATL/TSB form strip, race readiness, 6-signal radar chart, "why your plan is evolving" text, pace patterns (text), week pulse (text), adaptation history timeline
2. **Performance** — Global (or plan-scoped). Shows: hero stats (total km, avg pace, activities, hours), activity heatmap, insights strip, race predictions, predicted vs actual, weekly volume chart, personal records, pace trend, aerobic efficiency, training load/ACWR chart, fitness/fatigue/form chart, pace zones, plan-scoped readiness/gap analysis/gap trend/adherence heatmap, recent runs list
3. **Evolution** — Global. Shows: period selector, pace/VDOT/efficiency/volume change stats with trend badges, 4 evolution charts
4. **Insights** — Global. Shows: profile summary strip (VDOT, km/week, runs/week, ACWR, easy%), prioritized insight cards

### 3.2 Problems

1. **"Performance" is the default tab** — The unique coaching intelligence is hidden behind the "Coach" tab, which itself requires selecting a plan first
2. **Generic first impression** — Hero stats + heatmap + pace chart look like any Strava/Garmin dashboard
3. **Signals are opaque** — The 6-signal radar shows factors but not trends, not historical context, not phase weights
4. **Text-heavy coaching** — Pace patterns and week pulse are plain text strings, not visualized
5. **No "why" trail** — Adaptation history shows events but not the signal state at each decision point
6. **Readiness is siloed** — Daily check-in data is used in the multiplier but the trend isn't shown
7. **Gap analysis is buried** — Actionable recommendations are in a sub-section of the Performance tab
8. **No unified "coach narrative"** — All signals are computed independently; the user doesn't see the synthesized story

---

## 4. Coach Hub Design

### 4.1 Information Architecture

**Rename:** "Analytics" → "Coach Hub"
**Page title:** "Coach Hub" (was "Performance")
**Subtitle:** "Your personalized training intelligence" (was "Your running data at a glance")

**New Tab Structure:**

| Tab | Scope | Purpose |
|-----|-------|---------|
| **Today** | Plan-scoped (or prompt) | What's happening right now — today's workout, readiness, form, coach's current stance |
| **Signals** | Plan-scoped | Deep dive into the 6 adaptation signals with trends, phase weights, and per-type breakdowns |
| **Progress** | Plan-scoped | Gap analysis, race readiness, VDOT trajectory, adherence heatmap, week-by-week execution |
| **Insights** | Global (all plans) | Personalized training insights, profile summary, patterns across all training |
| **Evolution** | Global | Long-term trends (pace, VDOT, efficiency, volume) across months/years |

### 4.2 Tab-by-Tab Design

#### Tab 1: "Today" (New — replaces Coach as the lead tab)

**Purpose:** The single most important view. Answers: "What does my coach think about my training right now?"

**Layout:**

```
┌──────────────────────────────────────────────────────────────────┐
│  COACH STANCE BANNER (prominent, full-width)                     │
│  [icon] "Ready to step up" / "On track" / "Ease back"           │
│  "Your coach would increase remaining workouts (×1.12)"         │
│  [Build phase · Week 5 of 8]  [Form: Fresh (TSB +8)]            │
└──────────────────────────────────────────────────────────────────┘

┌─────────────────────┐  ┌─────────────────────────────────────────┐
│  TODAY'S WORKOUT    │  │  READINESS & FORM                       │
│  Tue · Tempo        │  │                                         │
│  5.0 km @ 5:30/km   │  │  ┌──────┬──────┬──────┬──────┐         │
│  HR Zone: 4 (Threshold)  │  │ CTL  │ ATL  │ TSB  │ ACWR │         │
│  [View details]     │  │  │ 42.3 │ 38.1 │ +4.2 │ 1.12 │         │
│                     │  │  │Fitness│Fatigue│ Form │ Risk │         │
│  Readiness today:   │  │  └──────┴──────┴──────┴──────┘         │
│  Score 72/100       │  │                                         │
│  [Log check-in]     │  │  ┌─ Readiness Trend (7 days) ─────────┐ │
│                     │  │  │  ████ ████ ████ ███ ███ ██ █       │ │
│                     │  │  │  78   72   68   75  80  65 72      │ │
│                     │  │  └────────────────────────────────────┘ │
└─────────────────────┘  └─────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  THIS WEEK'S EXECUTION                                          │
│  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐             │
│  │ Mon  │ Tue  │ Wed  │ Thu  │ Fri  │ Sat  │ Sun  │             │
│  │ Easy │Tempo │ Rest │Interval│Rest │ Long │ Rest │             │
│  │  ✓   │  →   │      │       │      │      │      │             │
│  │ 6.0km│5.0km │      │       │      │      │      │             │
│  └──────┴──────┴──────┴──────┴──────┴──────┴──────┘             │
│  8.0 / 22.0 km this week (36%)                                  │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  COACH'S NOTE (from week pulse + patterns)                      │
│  "You're on track this week — strong execution. Runs are        │
│   feeling easier compared to last week — your fitness is        │
│   adapting! One pattern to watch: your easy runs have been      │
│   consistently faster than planned."                            │
└──────────────────────────────────────────────────────────────────┘
```

**Data sources:**
- Coach stance: `build_coach_summary()` → `direction`, `multiplier`, `headline_reason`, `current_phase`, `form.tsb_form`
- Today's workout: `plan.plan_data` → current week → today's day
- Readiness: `ReadinessService.compute_readiness()` + recent readiness logs
- Form metrics: `build_coach_summary()` → `form.ctl/atl/tsb`
- Week execution: `plan.plan_data` + runs for current week
- Coach's note: `build_coach_patterns()` → `week_pulse.message` + `patterns`

#### Tab 2: "Signals" (New — deep dive into adaptation engine)

**Purpose:** Show exactly what the coach sees — the 6 signals, their trends, their weights, and how they combine.

**Layout:**

```
┌──────────────────────────────────────────────────────────────────┐
│  SIGNAL OVERVIEW                                                 │
│  Current phase: Build (Week 5 of 8)                             │
│  Multiplier: ×1.12 (+12%) → Increase                            │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Signal        │ Factor │ Weight │ Trend  │ Status          │ │
│  │  ──────────────│────────│────────│────────│──────────────── │ │
│  │  Volume        │  1.08  │  33%   │  ↗     │ Above plan      │ │
│  │  Effort        │  0.97  │  20%   │  →     │ Slightly high   │ │
│  │  Completion    │  1.05  │  16%   │  ↗     │ 85% complete    │ │
│  │  HR Zone       │  1.00  │  14%   │  →     │ On target       │ │
│  │  Feedback      │  1.02  │   9%   │  ↗     │ Mostly positive │ │
│  │  Readiness     │  0.98  │   8%   │  ↘     │ Below average   │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  SIGNAL DETAIL CARDS (expandable)                                │
│                                                                  │
│  ┌─ VOLUME ────────────────────────────────────────────────────┐ │
│  │  Ratio: 1.08 (actual 24.3 km vs planned 22.5 km)            │ │
│  │  ┌─ Per-Type Breakdown ───────────────────────────────────┐ │ │
│  │  │  Easy:     1.12 (6 runs, high confidence)              │ │ │
│  │  │  Long:     1.05 (2 runs, high confidence)              │ │ │
│  │  │  Tempo:    0.95 (1 run, medium confidence)             │ │ │
│  │  │  Interval: 1.00 (1 run, low confidence)                │ │ │
│  │  └────────────────────────────────────────────────────────┘ │ │
│  │  ┌─ Volume Trend (8 weeks) ───────────────────────────────┐ │ │
│  │  │  ██████ ████████ ██████ █████ ████████ ████ ████████   │ │ │
│  │  │  18.2   22.5   20.1   19.8  24.3   21.0  22.5         │ │ │
│  │  └────────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─ EFFORT ────────────────────────────────────────────────────┐ │
│  │  Factor: 0.97 (avg perceived effort: 6.8/10)                │ │
│  │  Trend: Stable │ Quality drift: +5 (improving)              │ │
│  │  ┌─ Effort Trend (last 12 runs) ──────────────────────────┐ │ │
│  │  │  ●    ●     ●    ●     ●    ●     ●    ●     ●    ●   │ │ │
│  │  │  7    6     8    7     6    7     8    6     7    7   │ │ │
│  │  └────────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─ HR ZONE ───────────────────────────────────────────────────┐ │
│  │  Adherence: 72% │ Avg deviation: +0.8 zones                 │ │
│  │  Trend: Improving                                          │ │
│  │  ┌─ Zone Distribution (this week) ────────────────────────┐ │ │
│  │  │  Z1: ████ 15%  Z2: ████████ 30%  Z3: ██████ 25%       │ │ │
│  │  │  Z4: ████ 15%  Z5: ██ 5%   Off: ██ 10%                │ │ │
│  │  └────────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─ READINESS ─────────────────────────────────────────────────┐ │
│  │  Factor: 0.98 (avg score: 68/100, 5 logs)                   │ │
│  │  ┌─ Component Breakdown ──────────────────────────────────┐ │ │
│  │  │  Sleep:    3.5/5  ████████░░                            │ │ │
│  │  │  Soreness: 2/5    ████░░░░░░  (higher = worse)         │ │ │
│  │  │  Energy:   4/5    ████████░░                            │ │ │
│  │  │  Stress:   2/5    ████░░░░░░  (higher = worse)         │ │ │
│  │  └────────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  HOW THE COACH DECIDES                                           │
│  "In the Build phase, volume matters most (33%), followed by    │
│   effort (20%) and completion (16%). As you approach Peak,      │
│   effort and HR zone adherence gain importance. In Taper,       │
│   readiness and completion dominate."                           │
│  ┌─ Phase Weight Comparison ──────────────────────────────────┐ │
│  │           │ Base │ Build │ Peak │ Taper                    │ │
│  │  Volume   │ ████ │ ███   │ ███  │ █                        │ │
│  │  Effort   │ ██   │ ██    │ ██   │ ██                       │ │
│  │  Complete │ ██   │ ██    │ ██   │ ███                      │ │
│  │  HR Zone  │ █    │ ██    │ ██   │ ███                      │ │
│  │  Feedback │ █    │ █     │ █    │ ██                       │ │
│  │  Readiness│ █    │ █     │ █    │ ██                       │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

**Data sources:**
- Signal table: `build_coach_summary()` → `signals` + `phase_weights`
- Volume detail: `signals.volume.factor` + `per_type_ratios` + historical runs
- Effort detail: `signals.effort.factor` + `effort_trend` + `quality_drift` + run history
- HR Zone detail: `signals.hr_zone.factor` + `hr_zone_adherence` + `hr_zone_trend`
- Readiness detail: `signals.readiness.factor` + recent readiness logs
- Phase weights: `tuning.PHASE_WEIGHTS`

#### Tab 3: "Progress" (Enhanced — combines existing plan-scoped views)

**Purpose:** Show where the runner stands relative to their plan targets and race goals.

**Layout:**

```
┌──────────────────────────────────────────────────────────────────┐
│  RACE READINESS GAUGE                                            │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  [████████████████████████████████░░░░░░░░] 72/100         │ │
│  │  Good — Half Marathon · 3 weeks to go                       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐       │
│  │ Volume   │ Fitness  │ Long Run │ Consist. │  Taper   │       │
│  │  78/100  │  82/100  │  65/100  │  85/100  │  55/100  │       │
│  │  Good    │  Strong  │ Moderate │  Strong  │  Build   │       │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘       │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  GAP ANALYSIS — TOP ACTIONS                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  ⚠️  Increase long run by ~2 km/week to close the 5 km     │ │
│  │      gap before taper                          [Extend]     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  ℹ️  Weekly volume is 18% below plan — add short easy runs │ │
│  │      or extend existing ones                   [Bump]       │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  VDOT TRAJECTORY                                                 │
│  Current: 42.3 (improving ↗) │ Needed for goal: 44.0           │
│  Gap: 1.7 VDOT units — on track with current trend              │
│  ┌─ VDOT vs Needed (8 weeks) ─────────────────────────────────┐ │
│  │  ●─────────────────────────── 44.0 (needed)                │ │
│  │     ●  ●     ●    ●    ●                                   │ │
│  │  38.5 39.2  40.1  41.0 42.3                                │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  WEEK-BY-WEEK EXECUTION                                          │
│  ┌─ Volume & Long Run vs Plan ────────────────────────────────┐ │
│  │  W1: ████████░░ 92% │ W2: ███████░░░ 85% │ W3: █████████░  │ │
│  │  W4: ██████░░░░ 72% │ W5: ████░░░░░░ 36% (in progress)    │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌─ Workout Adherence Heatmap ────────────────────────────────┐ │
│  │         Easy  Tempo  Interval  Long                        │ │
│  │  W1      ✓     ✓      ✓        ✓                          │ │
│  │  W2      ✓     →      ✓        ✓                          │ │
│  │  W3      ✓     ✗      ✓        ✓                          │ │
│  │  W4      →     ✓               ✓                          │ │
│  │  W5      ✓     (today)                                     │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  RACE SCENARIOS (if race date is set)                            │
│  ┌──────────┬──────────┬──────────┬──────────┐                  │
│  │  Dream   │  Solid   │  Tough   │ Survival │                  │
│  │  1:28:30 │ 1:32:15  │ 1:36:45  │ 1:42:00  │                  │
│  │  15%     │  50%     │  25%     │  10%     │                  │
│  └──────────┴──────────┴──────────┴──────────┘                  │
└──────────────────────────────────────────────────────────────────┘
```

**Data sources:**
- Readiness gauge: `ReadinessService.compute_readiness()` → `overall_score`, `components`
- Gap actions: `GapAnalysisService.analyze_gaps()` → `top_actions`
- VDOT trajectory: `race_predictor_service.get_predictions_for_user()` + `gap_analysis_service._compute_fitness_trajectory()`
- Week execution: `GapAnalysisService.analyze_gaps_weekly()`
- Adherence heatmap: `compute_adherence_heatmap()`
- Race scenarios: `readiness_scoring.build_scenarios()`

#### Tab 4: "Insights" (Enhanced — keep global scope)

**Purpose:** Cross-plan, long-term training intelligence.

**Enhancements:**
- Add **Training Age** (total weeks since first logged run)
- Add **Consistency Streak** (consecutive weeks with ≥X runs)
- Add **Personal Records timeline** — not just current PRs, but when they were set and which runs
- Add **Workout Type Distribution** pie chart — shows balance of easy/hard/long
- Keep existing insight cards but add **dismiss/snooze** functionality
- Add **"Coach's Assessment"** — a synthesized paragraph from all signals

**New data:**
- Training age: `RunLog` min date → today
- Consistency streak: count consecutive weeks with runs
- PR timeline: `PersonalRecordsService` + run dates
- Workout distribution: aggregate `RunLog.workout_type`

#### Tab 5: "Evolution" (Keep mostly as-is)

**Purpose:** Long-term trends across months/years.

**Minor enhancements:**
- Add **cadence trend** chart (if data available)
- Add **elevation gain trend** chart
- Add **training load trend** (CTL overlay)
- Keep existing pace/VDOT/efficiency/volume charts

---

## 5. Implementation Plan

### Phase 1: Restructure & Rename (Foundation)

| Task | Files | Effort |
|------|-------|--------|
| Rename page title/subtitle in `analytics_pages.py` | `analytics_pages.py`, `analytics.html` | Low |
| Rename tab labels (Coach→Today, add Signals, rename Performance→Progress) | `analytics.html`, `analytics_dashboard.js` | Low |
| Reorder tabs: Today first, then Signals, Progress, Insights, Evolution | `analytics.html` | Low |
| Add `data-tab="signals"` tab button and panel | `analytics.html` | Low |
| Create `analytics_signals.js` for new Signals tab | New file | Medium |
| Create `analytics_today.js` for new Today tab | New file | Medium |

### Phase 2: Today Tab (Highest Impact)

| Task | Files | Effort |
|------|-------|--------|
| Build `loadToday()` JS function fetching coach summary + plan data | `analytics_today.js` | Medium |
| Render coach stance banner (reuse existing banner logic) | `analytics_today.js`, `coach.css` | Medium |
| Render today's workout from `plan.plan_data` | `analytics_today.js` | Medium |
| Render readiness + form strip (reuse existing) | `analytics_today.js`, `analytics_coach.js` | Low |
| Add readiness trend sparkline (new endpoint or computed client-side) | `readiness.py` (new endpoint), `analytics_today.js` | Medium |
| Render week execution strip (7-day grid) | `analytics_today.js` | Medium |
| Render coach's note (combine week pulse + patterns) | `analytics_today.js` | Low |

### Phase 3: Signals Tab (Unique Differentiator)

| Task | Files | Effort |
|------|-------|--------|
| Build `loadSignals()` JS function | `analytics_signals.js` | Medium |
| Render signal overview table (factor, weight, trend, status) | `analytics_signals.js`, `coach.css` | Medium |
| Render expandable signal detail cards | `analytics_signals.js`, `coach.css` | High |
| Add per-type volume ratio breakdown | `analytics_signals.js` | Medium |
| Add effort trend mini-chart (last 12 runs) | `analytics_signals.js` | Medium |
| Add HR zone distribution bar chart | `analytics_signals.js` | Medium |
| Add readiness component breakdown (sleep/soreness/energy/stress) | `analytics_signals.js` | Medium |
| Render "How the Coach Decides" phase weight comparison | `analytics_signals.js` | Medium |
| **New endpoint:** `GET /api/analytics/signal-history/{plan_id}` — returns last N signal snapshots | `analytics.py` | High |

### Phase 4: Progress Tab (Enhance Existing)

| Task | Files | Effort |
|------|-------|--------|
| Move readiness card to top as gauge | `analytics.html`, `analytics_plan.js` | Medium |
| Move gap analysis actions to prominent position | `analytics.html`, `analytics_plan.js` | Medium |
| Add VDOT trajectory chart with "needed" line | `analytics_charts.js` | Medium |
| Enhance week-by-week execution visualization | `analytics.html`, `analytics_plan.js` | Medium |
| Add race scenarios visualization | `analytics.html`, `analytics_plan.js` | Medium |

### Phase 5: Insights Tab (Enhance)

| Task | Files | Effort |
|------|-------|--------|
| Add training age stat to profile summary | `analytics_insights.js`, `profile_builder.py` | Low |
| Add consistency streak stat | `analytics_insights.js`, `profile_builder.py` | Low |
| Add workout type distribution pie chart | `analytics_insights.js` | Medium |
| Add dismiss/snooze to insight cards | `analytics_insights.js`, `insights.css` | Medium |
| Add "Coach's Assessment" synthesized paragraph | New service or client-side | Medium |

### Phase 6: CSS & Polish

| Task | Files | Effort |
|------|-------|--------|
| Create `css/analytics/today.css` for Today tab styles | New file | Medium |
| Create `css/analytics/signals.css` for Signals tab styles | New file | Medium |
| Update `coach.css` for expanded signal cards | `coach.css` | Medium |
| Ensure responsive design for all new components | All CSS files | High |
| Add loading skeletons for new sections | All JS files | Medium |

---

## 6. New API Endpoints

### 6.1 `GET /api/analytics/signal-history/{plan_id}`

Returns the last N adaptation signal snapshots for trend visualization.

```json
{
  "available": true,
  "snapshots": [
    {
      "date": "2025-01-15",
      "multiplier": 1.05,
      "direction": "increase",
      "signals": {
        "volume": { "factor": 1.08, "weight": 0.33 },
        "effort": { "factor": 0.97, "weight": 0.20 },
        "completion": { "factor": 1.05, "weight": 0.16 },
        "hr_zone": { "factor": 1.00, "weight": 0.14 },
        "feedback": { "factor": 1.02, "weight": 0.09 },
        "readiness": { "factor": 0.98, "weight": 0.08 }
      },
      "form": { "ctl": 42.3, "atl": 38.1, "tsb": 4.2 },
      "phase": "build"
    }
  ]
}
```

**Implementation:** Read from `plan.adaptation_history` — each event already stores multiplier and direction. Enrich with signal recomputation for historical accuracy, or store signal snapshots on each adaptation event (recommended for future-proofing).

### 6.2 `GET /api/analytics/readiness-trend`

Returns recent readiness scores for trend visualization.

```json
{
  "available": true,
  "logs": [
    { "date": "2025-01-20", "score": 72, "status": "ready", "components": { "sleep": 4, "soreness": 2, "energy": 4, "stress": 2 } },
    { "date": "2025-01-19", "score": 65, "status": "caution", "components": { "sleep": 3, "soreness": 3, "energy": 3, "stress": 3 } }
  ],
  "avg_7d": 70,
  "avg_14d": 68,
  "trend": "improving"
}
```

**Implementation:** Query `ReadinessLog` for last 30 days, compute rolling averages.

### 6.3 `GET /api/analytics/training-age`

Returns training age and consistency metrics.

```json
{
  "weeks_since_first_run": 24,
  "total_runs": 87,
  "total_km": 542.3,
  "current_streak_weeks": 6,
  "longest_streak_weeks": 12,
  "avg_runs_per_week": 3.6
}
```

**Implementation:** Aggregate from `RunLog` min date, count consecutive weeks.

---

## 7. What Makes This Unique

Most running apps show:
- Pace charts
- Distance totals
- Heart rate zones
- Personal records

RunCoach's Coach Hub will show:
1. **Transparent adaptation reasoning** — "Your coach would increase load ×1.12 because your volume is 8% above plan, effort is manageable, and you're completing 85% of workouts"
2. **Phase-aware signal weighting** — "In Build phase, volume matters most. In Taper, readiness dominates"
3. **Per-type volume tracking** — "Your easy runs are 12% above plan but tempo sessions are 5% below"
4. **Quality drift detection** — "Your effort quality scores are improving (+5 points over last 8 runs)"
5. **Readiness integration** — Daily wellness check-ins directly influence training adjustments, with visible trends
6. **Race scenario planning** — Dream/Solid/Tough/Survival time ranges with probabilities
7. **Mountain simulation tracking** — For trail runners, vertical prep execution score
8. **Automated coaching feedback loop** — Sentiment from per-run feedback influences plan adjustments
9. **Endurance factor calibration** — VDOT predictions adjusted based on actual long-run performance
10. **Bayesian-shrunk confidence** — Per-type ratios show confidence levels based on sample size

---

## 8. Technical Considerations

### 8.1 Performance

- Signal history endpoint should be cached (signals don't change between runs)
- Today tab should batch all 3 API calls (coach-summary, coach-patterns, readiness-trend)
- Use `Promise.all` for parallel fetching (already pattern in `analytics_coach.js`)
- Lazy-load Signals tab content only when tab is activated

### 8.2 Backward Compatibility

- Existing endpoints remain unchanged
- New endpoints are additive
- Tab renaming is UI-only; `data-tab` values change but JS can handle both old and new during transition

### 8.3 Data Persistence

- **Recommended:** Store signal snapshots in `adaptation_history` entries during each adaptation event. This gives free historical signal trends without recomputation.
- **Alternative:** Recompute signals on-demand from run history. More accurate but slower.

### 8.4 Mobile Responsiveness

- All new components must work on mobile (320px+)
- Signal detail cards should stack vertically on small screens
- Week execution strip should scroll horizontally on mobile
- Phase weight comparison should use a compact table on mobile

---

## 9. Success Metrics

| Metric | Target |
|--------|--------|
| Coach Hub page views per user per week | > 3 |
| Time spent on Coach Hub per session | > 2 minutes |
| % of users who view Signals tab | > 40% |
| % of users who log readiness check-ins | > 30% (up from current) |
| User retention (return within 7 days) | > 60% |

---

## 10. Future Enhancements (Post-MVP)

1. **Push notifications** — "Your coach recommends an easy day today — readiness score is low"
2. **Coach chat** — Natural language Q&A about training decisions ("Why did my plan change last week?")
3. **Social sharing** — Share readiness score, VDOT progression, or race scenarios
4. **Training plan comparison** — Compare how different plans would have adapted the same training
5. **Injury risk dashboard** — Combine ACWR, TSB, readiness, and pace consistency into a single risk score
6. **Nutrition integration** — Show how meal plan adherence correlates with performance
7. **Strava segment analysis** — Compare segment times across training phases
8. **Weather correlation** — Show how weather conditions affect pace and effort
