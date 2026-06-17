# RunCoach Plan Generator — Quality Evaluation

**Author's lens:** evaluated as a running coach / training-product perspective (Runna-style
periodization norms). This is an **analysis-only** document — no code was changed. It is meant
as the baseline reference for prioritizing improvements to the plan generators.

**Date:** 2026-06-17
**Branch:** `claude/plan-generator-quality-eval-05ldld`
**Scope:** the three plan families that produce week-by-week schedules:

| Family | Entry point | Driven by |
|--------|-------------|-----------|
| **Distance (road)** | `TrainingPlanGenerator.generate_plan` | race distance + base mileage |
| **Performance** | `PerformancePlanGenerator.generate_plan` | current pace → goal pace |
| **Fitness** | `FitnessPlanGenerator.generate_plan` | VDOT + focus area |
| *(Beginner)* | `BeginnerPlanGenerator` (auto when `current_km == 0` for 5K/10K) | C25K table |

---

## 1. Methodology

Plans were generated programmatically across a matrix of **base weekly mileage × runs-per-week ×
race distance × plan family**, then each plan was measured on objective signals and graded
against established coaching norms. The raw generation harness lived in `/tmp` (not committed);
the tables below reproduce its output.

### Quality axes & rubric (1–5)

| Axis | What it measures | "5" looks like |
|------|------------------|----------------|
| **Mileage** | Is peak/weekly volume appropriate for the runner's base and race? No forced detraining; no absurd peaks. | Peak scales sensibly with base, distance, frequency; never below the runner's established base. |
| **Weekly progression** | Smoothness & monotonicity of the week-to-week curve. | Gentle up-ramp, clean deload dips, no week below its own preceding recovery week, no dead plateaus. |
| **Long run** | Long-run distance, its share of weekly volume, and its progression. | LR is 25–35 % of the week (road), progresses through the build, caps at distance-appropriate ceiling. |
| **Ramping** | Adherence to the ~10 % week-over-week rule and overall load safety. | No non-recovery week jumps >~10 % over the prior loading week. |
| **Overall feel** | Would a coach hand this plan to a client unedited? | Reads as deliberate periodization. |

### Reference norms used for grading

- **Acute progression:** ≤10 % week-over-week on loading weeks ("10 % rule").
- **Long run share:** ~30–35 % of weekly volume on road plans (≤25 % at very high volume); a long
  run >40–45 % of the week is a recognized overuse-injury pattern.
- **Polarization:** ~80/20 easy/hard; 1 quality session at low volume, 2 in build/peak at higher volume.
- **Periodization:** base → build → peak → taper, with a deload roughly every 4th week (3:1).
- **Taper:** distance-scaled (5K ≈ 1–2 wk, marathon ≈ 3 wk).

---

## 2. Scorecard (the matrix)

Scores are per **family × training-frequency band**, because frequency turned out to be the single
biggest driver of quality variation.

### Distance / road plans

| Frequency | Mileage | Progression | Long run | Ramping | Overall | Verdict |
|-----------|:------:|:-----------:|:--------:|:-------:|:-------:|---------|
| **3 runs/wk** | 2 | 2 | 2 | 2 | **2.0** | ⚠️ Structurally weak — detraining for high-base runners, long-run-dominant, breaks the 10 % rule. |
| **4 runs/wk** | 4 | 4 | 4 | 5 | **4.0** | ✅ Solid, ships as-is. The reference design point. |
| **5 runs/wk** | 4.5 | 4.5 | 4 | 5 | **4.5** | ✅ Strong. Frequency→volume scaling works well. |
| **6 runs/wk** | 4.5 | 4.5 | 4 | 5 | **4.5** | ✅ Strong; marathon LR share improves as volume rises. |

### Performance plans

| Frequency | Mileage | Progression | Long run | Ramping | Overall | Verdict |
|-----------|:------:|:-----------:|:--------:|:-------:|:-------:|---------|
| **4–6 runs/wk** | 4.5 | 5 | 4.5 | 4.5 | **4.5** | ✅ Best of the three families. Smooth ramp, no detraining, sensible LR share, clean quality progression. |

### Fitness plans

| Frequency | Mileage | Progression | Long run | Ramping | Overall | Verdict |
|-----------|:------:|:-----------:|:--------:|:-------:|:-------:|---------|
| **3–6 runs/wk** | 4 | 3.5 | 3 | 4 | **3.6** | 🟡 Safe and gentle, but long run is frequency/-focus-insensitive (hard-capped at 18 km) and deload dips run deeper than intended. |

### Beginner (C25K) plans

| | Mileage | Progression | Long run | Ramping | Overall | Verdict |
|-|:------:|:-----------:|:--------:|:-------:|:-------:|---------|
| **5K / 10K from 0 km** | 4 | 3.5 | n/a | 4 | **3.8** | 🟡 Sound run/walk ramp; plateaus at the session cap and the 5K variant has no taper week. |

---

## 3. Findings by axis

### 3.1 Mileage

**Strong (4+ runs):** Peak mileage scales coherently with base, distance, and frequency. Examples:

- 10K, base 40 km: peak **42 / 54 / 62 / 62** km at 3/4/5/6 runs — the frequency→volume knob
  (`runs_per_week_volume_factor`) is doing real work.
- Marathon, base 60 km: peak **63 / 78 / 86 / 100** km at 3/4/5/6 runs, respecting the 100 km
  `MAX_PEAK_MILEAGE` ceiling.

**Weak — forced detraining at 3 runs/wk for higher-base runners.** The "distributable" cap
(`run_ceiling × runs + q_cap`) can pin total weekly volume *below the runner's own base* because
three runs cannot physically hold the volume:

| Case | Base | Peak | Loading weeks below base | Min loading week |
|------|:----:|:----:|:-----------------------:|:----------------:|
| 5K, base 35, 3 runs | 35 | **33 (−6 %)** | 5 / 5 | 30 |
| Half, base 50, 3 runs | 50 | 50 (±0 %) | 6 / 11 | 38 (−24 %) |
| Marathon, base 60, 3 runs | 60 | 63 (+5 %) | 4 / 12 | 44 (−27 %) |

The `peak = max(current_km * 0.90, peak)` "no-detraining" floor in `get_peak_mileage` is applied
*before* the distributable cap clamps the peak back down, so the floor does not actually protect
the runner. A 35 km/wk runner asking for a 3-day 5K plan is handed weeks as low as 30 km.

### 3.2 Weekly progression

**Strong (4+ runs):** Clean base→build→peak→taper shape, deload every ~4th week with the
high-water mark preserved across the dip, mild peak-phase oscillation so the ceiling isn't flat.

**Weak spots:**

- **Weeks dipping below their own recovery week.** 10K, base 20, 3 runs:
  `22 23 25 21(deload) 19 22 27 …` — week 5 (19) is *lower* than the deload it follows. The curve
  reads as a stumble, not a progression.
- **Plateaus / flat blocks at 3 runs.** 5K, base 35, 3 runs: `33 32 30 28(deload) 30 30 27 18`
  has `max_wow_inc = 0 %` — the plan never progresses at all.
- **Beginner plateau.** 5K-from-zero: `3 4 5 8 10 13 13 13 13 13` — the per-session beginner cap
  (`target_distance × 1.5`) freezes volume for the last five weeks, and there is **no taper week**
  (it ends *at* peak). The 10K beginner does taper (`… 13 13 7`).

### 3.3 Long run

**Strong:** Long run progresses through the build and caps at experience-tiered ceilings
(`ROAD_LONG_RUN_CAPS`), e.g. marathon LR tops out ~34 km, half ~18–24 km. Performance plans show
textbook LR progression (e.g. `19 20 20 17 21 23 25 22 28 30 …`).

**Weak — long-run dominance at low frequency.** With only three runs, the long run becomes an
outsized share of the week:

| Case | Peak week | Long run | LR as % of week |
|------|:---------:|:--------:|:---------------:|
| Marathon, base 30, 3 runs | 55 km | 34.8 km | **63 %** ⚠️ |
| Marathon, base 60, 3 runs | 63 km | 35.1 km | **56 %** ⚠️ |
| Half, base 25, 3 runs | 41 km | 22.5 km | **54 %** ⚠️ |
| 10K, base 20, 3 runs | 30 km | 13.9 km | 46 % |

A long run at 54–63 % of weekly volume is a classic overuse-injury setup. Even on **higher-frequency
marathon plans**, the LR share runs hot when total volume is modest (base 30, 5 runs → LR is ~49 %
of a 70 km peak week) because the absolute LR cap (~34 km) is large relative to the weekly volume;
it only normalizes (~36 %) once volume reaches ~100 km/wk.

**Fitness LR is too blunt.** Fitness long runs are `min(weekly × 0.25, 18)` regardless of focus
distance — a 42.2 km-focus, 60 km/wk plan still gets a 16.5 km long run, and a 5K-focus plan gets
nearly the same LR profile as a half-marathon focus. The focus distance changes the *quality* type
but barely touches the endurance dose.

### 3.4 Ramping (10 % rule)

**Strong (4+ runs):** Effectively flawless. 10K base 20 at 4 runs, half base 25 at 4 runs,
marathon base 30 at 3 *and* 4 runs — **0 violations**.

**Weak (3 runs):** The 10 % rule is regularly broken because prescriptive quality workouts keep
their authored distance (they are intentionally *not* rescaled), and with only one flexible easy
run there is no headroom to absorb the overage:

| Case | Violations | Worst jump |
|------|:----------:|:----------:|
| 10K, base 20, 3 runs | 3 | **+26 %** (22→27) |
| 10K, base 40, 3 runs | 3 | +15 % |
| Half, base 25, 3 runs | 2 | +16 % |

The same plans at 4 runs/wk have zero violations — additional flexible easy volume is exactly the
shock absorber the cap-enforcement logic needs.

### 3.5 Overall feel

- **Performance** plans feel coach-authored: deliberate phases, smooth load, quality that builds
  from 1→2 sessions into the peak, honest taper.
- **Distance** plans at **4–6 runs** feel right. At **3 runs** they feel like the model is fighting
  its own constraints — the volume target, the per-run ceiling, the long-run ratio, and the 10 %
  cap cannot all be satisfied with three runs, and something always gives (usually safety).
- **Fitness** plans feel safe but generic — the gentle 1.3× peak and 18 km LR cap make a 5K-focus
  and a marathon-focus plan look nearly identical in volume terms.

---

## 4. Empirical appendix (representative runs)

`r` = recovery/deload week. `LR` = long-run km. `q` = quality sessions that week.

### Distance / road

```
[10K]  base20 wk12 r4: peak36 total337 peakLR15  maxWoW10%  recov2
  km:  22 24 26 22r 28 30 34 29r 36 36 30 20
  LR:   7  7  8  6   9 10 12  9  13 14  9  7
  q:    1  1  1  0   1  1  1  0   1  1  1  1

[10K]  base40 wk12 r3: peak42 total434 peakLR22  maxWoW15%  recov2   << detraining + LR-heavy
  km:  40 40 40 34r 29 33 36 39r 36 36 42 29
  LR:  14 14 14 12  14 16 16 14  16 16 22 13

[Half] base50 wk16 r5: peak70 total957 peakLR24  maxWoW10%  recov3
  km:  51 53 54 46r 56 57 63 54r 64 67 70 70r 69 69 67 45
  LR:  15 16 17 13  19 19 19 16  21 23 24 21  24 24 20 16

[Mara] base30 wk18 r3: peak55 total759 peakLR35  maxWoW10%  recov3   << LR is 63% of peak week
  km:  33 36 39 33r 42 45 37 38r 41 42 45 46r 49 48 52 55 45 32
  LR:  11 12 14 12  16 17 17 13  20 22 24 18  27 27 32 35 26 15

[Mara] base60 wk18 r6: peak100 total1370 peakLR36 maxWoW9%  recov3   << clean, LR 36% of peak
  km:  62 64 66 56r 68 70 76 65r 82 87 93 80r 95 100 100 85 70 50
```

### Performance

```
[Half 21.1] cp5.5→gp5.0 wk16 base45 r4 vdot37.9: peak80 total957 peakLR22
  km:  43 49 48 44r 50 56 61 52r 63 74 80 68r 80 80 65 44
  LR:  14 15 15 13  16 17 18 16  20 22 22 20  22 22 20 13
  ph:  ba ba ba ba  ba ba bu bu  bu bu bu bu  pe pe ta ta

[Mara 42.2] cp6.0→gp5.5 wk16 base60 r5 vdot35.5: peak100 total1226 peakLR30
  km:  58 65 63 58r 66 77 85 72r 93 100 85r 100 100 85 70 50
  LR:  19 20 20 17  21 23 25 22  28  30 26  30  30 26 21 15
```

### Fitness

```
[base30 wk12 r4 vdot45 vo2max focus10K]: peak39 total403 peakLR9.8
  km:  30 30 31 21r 33 36 39 33r 37 38 36 39    << deload dips to ~70%, not the intended 85%
  LR:   8  8  8  6   8  9 10  8  10  9 10 10

[base60 wk12 r6 vdot55 threshold focus42.2]: peak67 total717 peakLR16.5  << LR tiny for a marathon focus
  km:  58 56 52 52r 62 64 66 56r 65 67 65 55
  LR:  15 15 15 13  15 16 16 14  16 16 16 16
```

### Beginner (from 0 km)

```
5K  (10 wk, 3 runs): 3 4 5 8 10 13 13 13 13 13   << plateaus at session cap; no taper week
10K (12 wk, 3 runs): 3 5 8 10 13 13 13 13 13 13 13 7
```

---

## 5. Prioritized recommendations (for a future change set)

Ordered by impact-to-effort. **No code is changed in this document.**

1. **Fix the 3-runs/week regime (highest priority).** It fails three axes at once. Options, in
   rough order of leverage:
   - Cap the **long run as a hard fraction of weekly volume** (e.g. ≤35–40 %) *before* filling the
     rest of the week — this is the root of both the LR-dominance and the detraining (the LR eats
     the volume the easy runs needed).
   - Let the **10 % cap-enforcement borrow from / re-shape the long run** when there is no flexible
     easy headroom (currently it can only trim easy/long *flexible* km, of which a 3-run week has
     almost none).
   - Apply the **no-detraining floor *after* the distributable cap**, or raise the per-run ceiling
     when frequency is low so three runs can legitimately hold the base.
   - Consider **steering very-high-base + short-race + low-frequency users toward a fitness plan**
     instead, since a 3-day 5K plan for a 35 km/wk runner is an ill-posed request.

2. **Normalize marathon long-run share at low/모derate volume.** Make the LR cap track *weekly
   volume* (e.g. `min(absolute_cap, 0.35 × week_km)` once volume is below ~80 km) so a 70 km peak
   week doesn't carry a 34 km long run (49 %).

3. **Make fitness long runs responsive to focus distance & frequency.** The flat
   `min(weekly × 0.25, 18)` makes every fitness plan look the same on the endurance axis. Scale the
   LR (and its cap) by `focus_distance` and let it grow on higher-frequency plans.

4. **Smooth the post-deload step-down.** Guarantee the first loading week after a deload is ≥ the
   deload week (the `19` after a `21` deload should not happen). A simple `max(week_km, prev_deload)`
   guard would remove the visible stumble.

5. **Give the 5K beginner plan a taper week** (the 10K variant already has one) and soften the
   beginner plateau by letting volume creep under the session cap rather than freezing flat.

6. **Audit the fitness deload depth.** Assembled deload weeks land near ~70 % of the high-water
   mark rather than the intended `RECOVERY_WEEK_RATIO = 0.85`; the easy-fill step appears to
   under-fill on recovery weeks.

### What's already good (keep)

- The **frequency→volume** model (`runs_per_week_volume_factor`) is a genuine improvement — same
  runner, different frequencies now land on different, sensible peaks.
- **Performance plans** are the quality benchmark the other two families should be measured against.
- **Deload cadence** (continuous 3:1, peak week preserved, no deload in taper) is well-designed.
- **Distance-aware tapers and phase splits** are sound.
- The **4–6 run road plans** are production-quality today.

---

## 6. One-line verdict per family

| Family | Verdict |
|--------|---------|
| **Distance, 4–6 runs/wk** | ✅ Ship-quality. The reference for the rest. |
| **Distance, 3 runs/wk** | ⚠️ Needs work — long-run-dominant, detraining for high-base runners, breaks the 10 % rule. |
| **Performance** | ✅ Best-in-class within RunCoach; use as the template. |
| **Fitness** | 🟡 Safe but generic; endurance dose is frequency/-focus-blind. |
| **Beginner** | 🟡 Sound ramp; fix the 5K taper and the late-plan plateau. |
