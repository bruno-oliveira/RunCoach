# RunCoach — Plan Generator Quality Evaluation

> **Author's framing:** written from the perspective of a coach/algorithm designer
> who has shipped training-plan engines at scale (Runna). This is an *audit*, not a
> code change — the goal is to give RunCoach a defensible, prioritised improvement
> backlog grounded in the generator's actual output, not in how the code reads.
>
> **Method:** every plan family (`TrainingPlanGenerator` "distance", `PerformancePlanGenerator`,
> `FitnessPlanGenerator`) was generated across a matrix of weekly mileage and runs/week,
> and each plan was scored on six axes. Metrics were computed directly from the emitted
> weekly dicts (`total_km`, `is_recovery`, `daily_workouts`). 5K/10K/Half ran at 12 weeks,
> Marathon at 16, Fitness at 10 (its hard cap). VDOT 45 where applicable.
>
> **Date:** 2026-06-17 · **Scope:** analysis only, no code modified.

---

## 1. What "good" means (the six axes)

| Axis | What a strong plan does | How it was measured |
|------|-------------------------|---------------------|
| **Mileage** | Peak volume is race- and base-appropriate; high-base runners aren't detrained; low-base runners are pulled up to a productive load | Peak weekly km vs ideal; start vs current base |
| **Weekly progression** | No abrupt jumps; ~10% rule respected *week-over-week*, not just vs a high-water mark | Max consecutive week-over-week % change |
| **Long run** | Race-specific share of the week and of race distance; grows smoothly; doesn't spawn a second long "easy" run | Peak long-run km, % of week, % of race distance, max week-over-week growth |
| **Ramping** | Monotone-ish build, real deloads on a 3:1-ish cadence, a taper that actually descends | Deload count, down-step count, taper ratio (race week ÷ peak) |
| **Polarisation / feel** | ~80/20 easy:hard for endurance, more quality for speed/5K; run count honoured; each session has a job | Easy-km %, hard-session %, run-count stability |
| **Overall** | Would I hand this to an athlete unedited? | Holistic, per cell |

---

## 2. Results matrix (per family, per axis)

Grades: **A** excellent · **B** good, minor nits · **C** usable but flawed · **D** wrong in common cases · **F** broken.

### 2.1 Distance plans — `TrainingPlanGenerator`

| Distance | Mileage | Progression | Long run | Ramping | Polarisation | Overall |
|----------|:------:|:-----------:|:--------:|:-------:|:------------:|:------:|
| 5K | B | A (runs≥4) / C (runs 3) | **D** | B | C (too easy) | **C+** |
| 10K | A | A (runs≥4) / C (runs 3) | B | A | C (too easy) | **B** |
| Half | A | A (runs≥4) / **D** (runs 3) | A | B | B | **B** |
| Marathon | A | A (runs≥4) / C (runs 3) | A | A | B | **A−** |

**What works (runs ≥ 4):** week-over-week max jump sits right on 10.0–10.3% across the
board — the high-water-mark cap is doing its job. Frequency scaling is real: a 10K at
base 40 goes 53→62→62 km peak as runs go 4→5→6. Marathon long run scales beautifully
(32–36 km cap, ~78% of race distance at sensible bases). Deloads land on a clean 3:1
cadence (2 for 12-week, 3 for 16-week). High-base runners targeting short races are held,
not crashed (base 60 → 5K peaks at the 50 km `MAX_PEAK_MILEAGE` ceiling).

### 2.2 Performance plans — `PerformancePlanGenerator`

| Distance | Mileage | Progression | Long run | Ramping | Polarisation | Overall |
|----------|:------:|:-----------:|:--------:|:-------:|:------------:|:------:|
| 5K | B | A (runs≥4) / C (3) | A | B | **A** | **B+** |
| 10K | A | C (jumps 15–18%) | B | B | **A** | **B** |
| Half | A | **D** (jumps 18–27%) | A | B | **A** | **B−** |
| Marathon | A | C (jumps 16–24%) | A | A | **A** | **B** |

**Standout:** polarisation is *much* better than the distance family — easy-km share
60–82% and hard-session share 26–35%, which is what a goal-pace plan should look like.
**Weakness:** the performance generator calls `calculate_weekly_progression` but **does
not apply the post-hoc week-level 10% cap** that the distance orchestrator does in
`plan_generator.py`. Result: consecutive week-over-week jumps of 15–27% appear on
Half/Marathon and higher-frequency 10K (e.g. Half base 25 runs 6: a 27.5% week-to-week
jump). Safe vs the high-water mark, jarring vs last week.

### 2.3 Fitness plans — `FitnessPlanGenerator`

| Focus | Mileage | Progression | Long run | Ramping | Polarisation | Overall |
|-------|:------:|:-----------:|:--------:|:-------:|:------------:|:------:|
| vo2max | B | **D** (jumps 12–34%) | **F** | **D** (no taper) | A | **C−** |
| threshold | B | **D** (jumps 12–28%) | **F** | **D** (no taper) | A | **C−** |
| balanced | B | **D** (jumps 9–24%) | **F** | **D** (no taper) | A | **C−** |

The fitness family is the weakest. Three structural defects (long-run collapse, jagged
ramp, broken taper — detailed in §4) keep it at C− regardless of focus.

---

## 3. Axis-by-axis read

### 3.1 Mileage — **strong overall**
- Peak targets are race-appropriate for runs ≥ 4 and scale with both base and frequency.
- The absolute `MAX_PEAK_MILEAGE` ceilings (5K 50 / 10K 64 / Half 82 / M 100) are sane
  recreational caps and bind correctly for high-base runners.
- **Issue — low-frequency forced detraining.** At runs = 3 the per-run "distributable"
  ceiling dominates, so a 60 km/wk runner who picks 3 runs is *started at 33 km* and
  peaked at 33–50 depending on distance. `base 40 runs 3` and `base 60 runs 3` produce
  **identical** plans — the established base above ~33 km is simply discarded. Physically
  unavoidable (you can't pack 60 km into 3 runs without 20 km easy days), but the engine
  neither warns the user nor nudges them to add a day. A coach would say "you can't do
  this volume on 3 runs — add a day or accept a big cut."

### 3.2 Weekly progression — **excellent at runs ≥ 4 in the distance family, leaky elsewhere**
- Distance family runs ≥ 4: max jump 9.6–10.3%. Textbook.
- **The cap is anchored to the high-water mark, not the previous week.** This is the root
  of every >10% number in the matrix: after a week dips below the high-water mark (common
  on 3-run plans where the long-run floor makes weeks lumpy, and at phase boundaries), the
  next week can rebound up to 110% of the *earlier* high — which can be 17–27% above the
  *immediately preceding* week. Examples: Half/3-run hits 19–23%; Performance Half/6-run
  hits 27.5%; Fitness routinely 20–34%. Runners and coaches judge ramps week-over-week, so
  these read as spikes even though the code's invariant holds.
- Performance and fitness families don't get the distance orchestrator's second-pass cap
  at all, so they're the worst offenders.

### 3.3 Long run — **good for 10K+/runs≥4, broken at the extremes**
- Distance Marathon/Half: long run 24–36 km, 30–48% of week, ~78%/100%+ of race distance.
  Exactly right.
- **5K long-run blow-up (D).** On 3-run 5K plans the low-frequency long-run *floor*
  overrides the 10 km experience cap: peak long run = **14 km = 280% of race distance**,
  46% of the week. Concretely, the 5K/base-20/3-run peak week is *long 14.0 km + "easy"
  13.3 km + interval 2.6 km* — **two ~14 km runs and one token interval for a 5K**. That
  is not a 5K week; it's a poorly-specified half base. The `MAX_EASY_RUN_KM = 14` cap is
  the only thing stopping a third long run.
- **Fitness long-run collapse (F).** `_fitness_long_run_km` caps the long run at
  `max(8, min(focus_distance·0.7, 26))`. For a 10 km focus that's a hard **8 km ceiling**,
  so a 50 km/wk fitness runner's "long run" is 8 km = **13% of the week** — there is no
  endurance session. The cap should track *weekly volume*, not (only) a short focus
  distance.

### 3.4 Ramping & taper — **distance family clean, fitness taper inverted**
- Distance/performance: deloads on a 3:1 cadence, monotone-ish builds, tapers that descend.
- **Shallow tapers in a few capped cells.** Because the taper scales from the progression's
  high-water mark while the displayed peak weeks were scaled down by the second-pass cap,
  race week can land at ~71% of the *shown* peak (e.g. Half base-40 runs-4) — a weak drawdown.
- **Fitness taper is inverted (F).** In `_calculate_fitness_mileage` the
  `MIN_NON_RECOVERY_BUMP` floor (`max(week_km, high_water·1.01)`) is applied to taper weeks
  too, overriding the 0.55 taper factor. Verified: fitness vo2max base-35 ends
  **peak 41.4 → 41.8 → taper 45.4 km** — the taper week is the *single biggest week of the
  plan*. Every fitness plan effectively ships with no taper.

### 3.5 Polarisation / feel
- **Distance family is too easy for the short races.** Easy-km share is 87–94% almost
  everywhere. For Marathon that's fine; for **5K/10K an 88–93% easy split under-doses
  threshold/VO2** — a 5K block should be nearer 80/20 by volume and feel sharper. Session
  count looks polarised (~20% hard) but the *volume* is heavily easy because quality
  sessions are short.
- **Performance family nails it** (60–82% easy-km, 26–35% hard sessions).
- **Run-count instability (fitness only).** Requested 6-run weeks intermittently render as
  4–5 runs when a time-trial or recovery week reshuffles slots (`[6,6,5,6,6,6,6,6,4,6]`).

---

## 4. Defects ranked by severity

| # | Severity | Family | Defect | Evidence |
|---|----------|--------|--------|----------|
| 1 | **High** | Fitness | Taper inverted — `MIN_NON_RECOVERY_BUMP` floor overrides taper reduction; final week is the plan's peak | vo2max base-35: 41.4→41.8→**45.4** |
| 2 | **High** | Fitness | Long run hard-capped at `focus·0.7` (≈8 km for a 10 km focus) regardless of volume → 13% of week at base 50 | LR stuck at 8.0 km for all base ≥ 35 |
| 3 | **High** | Distance | 3-run 5K long-run floor overrides 10 km cap → 14 km long run (280% of race) + 13 km "easy" | 5K base-20 runs-3 peak week |
| 4 | **Med** | Performance, Fitness | No week-over-week cap (only high-water cap) → 15–34% consecutive jumps | Perf Half runs-6: 27.5%; Fitness: 34% |
| 5 | **Med** | All | 10% rule is enforced vs high-water mark, not previous week; spikes after sub-peak weeks | Half/3-run: 19–23% |
| 6 | **Med** | Distance | runs=3 with high base silently discards established volume (base 40 ≡ base 60) | identical plans, start 33 km from 60 km base |
| 7 | **Low** | Distance | 5K/10K too easy by volume (88–93% easy-km) | polarisation column |
| 8 | **Low** | Distance | Taper scales from unrealised high-water → shallow (71%) drawdown in capped cells | Half base-40 runs-4 |
| 9 | **Low** | Fitness | Run count not stable across weeks | `[6,6,5,6,…,4,6]` |

---

## 5. Overall verdict

| Family | Verdict | One-line |
|--------|---------|----------|
| **Distance (`TrainingPlanGenerator`)** | **B / B+** — ship-quality for runs ≥ 4 | The mature engine: clean 10% ramps, real deloads, excellent marathon/half long runs. Falls down on **3-run plans** (long-run blow-up, discarded base) and is **too easy for 5K/10K**. |
| **Performance (`PerformancePlanGenerator`)** | **B** — best *feel*, leaky *ramp* | Polarisation is exactly right for goal-pace training, but it skips the second-pass 10% cap, so Half/Marathon show 15–27% week-over-week spikes. Closest to "great" with the smallest fix. |
| **Fitness (`FitnessPlanGenerator`)** | **C−** — needs structural work | Good zone/quality logic wrapped around three real defects: **no taper**, a **collapsed long run**, and a **jagged ramp**. Currently the weakest artifact RunCoach ships. |

**If I could change three things first (highest ROI):**
1. **Fix the fitness taper** (defect #1) — one-line floor exclusion; turns every fitness plan from "no taper" to correct. Biggest credibility win per unit effort.
2. **Make the long run track weekly volume**, with a hard race-distance ceiling, in *both* the fitness cap (#2) and the 3-run distance floor (#3) — kills the two most visible "this isn't a real plan for my race" artifacts.
3. **Add the week-over-week cap to performance & fitness** and re-anchor the rule to the previous loading week, not the high-water mark (#4, #5) — makes every family's ramp read as smooth to a runner, not just safe to the algorithm.

**Secondary:** nudge 5K/10K toward 80/20 by volume (#7); when runs = 3 can't hold the
base, surface a "add a training day" prompt rather than silently cutting (#6); anchor the
taper to the realised peak (#8).

---

## 6. Reproducing this evaluation

The numbers above came from a throwaway harness that swept the matrix and computed the
six-axis metrics per cell (peak/avg/start km, max week-over-week %, deload & down-step
counts, peak long run with its %-of-week and %-of-race, max long-run growth %, hard-session
% and easy-km %, taper ratio, and the full weekly-total + run-count vectors). It exercised:

- **Distance:** 5K/10K/Half (12 wk) + Marathon (16 wk) × base {15,25,40,60} × runs {3,4,5,6}, VDOT 45
- **Performance:** same distances × base {25,40,60} × runs {3,4,5,6}, current 5:30/km → goal 5:09/km
- **Fitness:** focus {vo2max, threshold, balanced} (10 wk) × base {20,35,50} × runs {3,4,5,6}, VDOT 45, focus_distance 10 km

To regenerate, instantiate the three generators and call `generate_plan(...)` over those
parameter grids, then read `total_km` / `daily_workouts[*].{type,distance,quality}` /
`is_recovery` off each weekly dict (distance returns a list of weeks; performance/fitness
return a dict with `weekly_plans`).
