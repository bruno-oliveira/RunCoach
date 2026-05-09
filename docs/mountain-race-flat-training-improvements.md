# Mountain Race + Flat Training Access Improvements

This document captures targeted improvements for runners training on flat terrain for a mountainous trail race (e.g. 1000m+ elevation gain).

## Problem Definition

- Race demands and training constraints are different realities.
- A runner may target a high-vert race while having no access to hills.
- Plans should preserve mountain race intent while prescribing executable flat-session substitutes.

## Product and Planning Principles

1. Keep `race_profile` and `training_constraints` separate.
2. Let race profile drive total training stimulus and periodization.
3. Let training constraints decide session execution variants.
4. Preserve race-specific nutrition demands even when local terrain is flat.

## Current Gaps

- Terrain can leak into race-profile distribution dispatch in some planning paths.
- Hill stimulus can be dropped instead of translated into flat executable work.
- Quality distance budgets can undercount when hill slots are substituted.
- Adaptation focuses on generic volume/effort but lacks mountain-from-flat proxy signals.

## What Should Improve

### 1) Plan Generation

- Keep race elevation class as the source of truth for phase distributions.
- When `training_terrain=flat`, substitute hill sessions into flat climb-simulation sessions (tempo/interval) instead of deleting quality load.
- Redistribute hill-quality distance budget to substituted flat sessions to keep total quality stress aligned with race demands.
- Expand flat-for-mountain key workouts over time (treadmill incline, stairs, power-hike simulation, eccentric descent prep).

### 2) Nutrition

- Fuel by race demand, not local terrain access.
- Add session-level fueling cards (pre/during/post) for key and long runs.
- Track gut-training compliance (planned vs actual carbs/h, sodium, fluid, GI tolerance).

### 3) Adaptation

- Add mountain-readiness proxy signals for flat-trained athletes:
  - climb-effort minutes completed,
  - hike-run transition completion,
  - eccentric-load completion,
  - fueling execution consistency.
- Use these signals in weekly suggestions and adaptation multipliers.

## Implemented in This Iteration

- Race profile now drives phase distribution category even when training terrain is flat.
- Quality distribution now substitutes hill slots into flat-executable tempo/interval sessions when race is non-flat and training terrain is flat.
- Quality distance allocation now redistributes hill percentage budget to substituted quality types in mountain-race + flat-training scenarios.
- Weekly plans now include `vertical_simulation` targets for flat-only prep to mountainous races, including simulated uphill meters, uphill-effort minutes, downhill eccentric minutes, and hike-run transition reps.
- Plan week cards now render a "Mountain Simulation Targets (Flat Access)" section when those targets are present.
- Added mountain-from-flat proxy scoring in fitness services (`score_mountain_simulation`) and surfaced it in readiness output (`mountain_simulation`) plus gap analysis (`mountain_simulation_gap`) and action prioritization.

## Next Steps

1. Add run-log fields for fueling execution and terrain/surface mix.
2. Feed fueling execution into adaptation multipliers (not just recommendations).
3. Add session-level fueling cards (pre/during/post) for key and long runs.
4. Add an in-UI "How this score is computed" explainer for mountain simulation metrics.
