# Custom Plans — implementation plan

Status: implemented on `feat/custom-plans` · 2026-10-15 (see "As built" below)

## Goal

Let a runner build their own training plan by **choosing the sessions** that
fill a fixed weekly skeleton, and still get everything a generated plan gets:
VDOT / measured-easy-band paces, ramp and long-run safety caps, deloads and
taper, adaptation, watch mirroring, nutrition, and translation.

Plans are titled **"Custom Plan N · <distance>"** (backyard would use loops,
but backyard is out of scope for v1).

The skeleton comes from the *Flat to Mountain* method (Ch. 12): one long run,
one speed session, one threshold/climb session, easy running around them, up
to two strength sessions, at least one rest day, never two quality days
back-to-back, and about 80% of time easy. The engine already enforces every
one of those rules. This feature is about **choice**, not new periodisation.

## The one principle

> **The runner picks *what*. The engine decides *how much*.**

A chosen session goes through the same `overlay_key_workout` path an automatic
pick does. It is sized to the week's budget, capped against the long run
(`MAX_KEY_WORKOUT_VS_LONG_RUN`), trimmed by the Daniels share caps, and paced
from the plan's zones. Choosing a session never lets a runner prescribe
distance, reps or pace directly. That is what keeps the safety guarantees,
and it is why adaptation needs no special case: chosen sessions carry a
`key_workout_id`, so `week_adjuster` → `rebuild_key_workout` keeps them
through every re-pace (`week_adjuster.py:189`).

## Scope

**In (v1):** road distances (5K, 10K, Half, Marathon) and trail. 3–6 runs a
week. Weekly mileage above 0. Choice per phase × slot. A strength template and
sessions-per-week choice.

**Out (v1), and why:**

| Excluded | Reason |
|---|---|
| Backyard | Simulations own the weekend and carry `fixed_structure`, so there is nothing to choose |
| 0 km/week | Routes to `BeginnerPlanGenerator`, which installs no key workouts |
| ≤ 2 runs/week | `quality_stays_formulaic` skips the overlay on purpose: a fixed prescription cannot carry a 2-run week's volume (measured 20 km delivered vs a 48 km target) |
| Time-goal (performance) plans | Separate generator (`performance_plan_generator`); add later if wanted |
| Stair / incline / treadmill sessions | No GPS distance. They interact with weekly km, completion stats and the watch export. Deferred to Phase 5 |
| Per-week hand editing | Choice per phase is enough for v1; the existing adjust flow covers one-off changes |

## Product shape

1. **Basics**: the existing plan form fields (distance, current km, weeks,
   runs per week, recent race / goal, trail elevation).
2. **Choose sessions**: a grid of **phase × slot**. Each cell accepts 1–3
   catalog sessions, which the engine rotates through week to week. Each card
   shows the catalog's own `name`, `structure`, `rationale`, `intensity`.
   - Phases the runner can choose for: **Base, Build, Peak.** Taper and
     recovery weeks are engine-owned (they're structural, and the book treats
     them the same way). Recovery weeks still use the runner's choices, just
     trimmed.
   - Slots, by runs per week (measured in the Phase 0 spike, below):
     - 3–4 runs: Long, Quality (one quality day a week; the runner's menu
       may mix speed and threshold sessions, and the rotation decides that
       week's type)
     - 5–6 runs: Long, Speed, Threshold/Climb (easy runs fill the rest)
     - Base phase: Long only. The engine's base has no quality day (see
       the spike), and v1 doesn't add one
   - Easy runs are not selectable in v1 ("easy means easy").
3. **Strength**: 0, 1 or 2 sessions a week. Template: *Automatic* (today's
   rotation) or *Climb + Descent* (the book's Strength A heavy/slow and
   Strength B eccentric/plyometric).
4. **Preview**: the phase arc plus one representative build week, then Create.

A choice the engine cannot honour in a given week is **shown, not hidden**.
For example, a fixed long-run session in a week that cannot absorb it (the
`long_run_must_stay_flexible` guard) is kept as a plain long run, and the
week card says so.

---

## Phase 0 — Spike: the slot grid ✅ done 2026-10-15

Generated 5K/10K/Half/Marathon/Trail-30 plans at 3–6 runs (VDOT 45) and
counted each non-recovery week's quality/long days, plus whether a
key workout was installed (`*`). The scripts are throwaway (scratchpad).

| Runs | Base | Build / Peak | Taper |
|---|---|---|---|
| 3 | long only | **one** quality day: interval, tempo or hill, alternating week to week | tempo sharpener |
| 4 | long only (an occasional untimed hill day, never keyed) | **one** quality day, alternating type | tempo sharpener |
| 5 | as 4 | interval + tempo (sometimes hill for tempo, or 2 × tempo in peak) | tempo sharpener |
| 6 | as 4 | as 5 | tempo sharpener |

Findings that change the design:

1. **Base has no quality cell.** Base weeks are volume-first with no keyed
   quality day at any frequency. Grid cells exist only in build and peak.
   Base strides arrive with easy-run choices in v1.1.
2. **At 3–4 runs the week has one quality day whose type the engine
   alternates.** A custom plan sets that week's quality type from the rotated
   pick: `distribution` becomes `{pick.type: 1}` *before* `_quality_budgets`
   runs, so the budget, the per-type min dose and the caps are all computed
   for the session actually installed. At 5–6 runs, the Speed cell fills the
   `interval` day and the Threshold/Climb cell fills the `tempo` or `hill`
   day. A peak week with 2 × tempo uses the Threshold menu twice
   (`slot_index` already rotates it).
3. **A fixed long-run session is usually refused.** Of 28 build/peak long
   runs per frequency, the overlay was even attempted on only ~12 at 3 runs
   and ~12 at 5 runs (the `long_run_must_stay_flexible` volume guard), and on
   most weeks at 4 and 6. "No candidate" was rare (1–5). A runner who picks a
   long-run session would see it in well under half their weeks, which is
   not acceptable. This is fixed by **proportional long runs** (Phase 2,
   item 2).

## Phase 1 — Core: spec, eligibility, validation (pure, `app/core/`)

New module `app/core/training/custom_plan.py`, with no I/O, SQLAlchemy or
FastAPI imports (the layer test enforces this at every depth).

```python
class SlotKind(StrEnum):   # what the runner sees
    LONG = "long"
    SPEED = "speed"          # fills workout_type "interval"
    THRESHOLD = "threshold"  # fills "tempo" or "hill"
    QUALITY = "quality"      # the single quality slot at 3 runs/week

@dataclass(frozen=True)
class StrengthChoice:
    sessions_per_week: int           # 0..2
    template: Literal["auto", "climb_descent"]

@dataclass(frozen=True)
class CustomPlanSpec:
    menus: Mapping[str, Mapping[SlotKind, tuple[str, ...]]]  # phase -> slot -> ids
    strength: StrengthChoice

    def to_json(self) -> dict: ...
    @classmethod
    def from_json(cls, raw: dict) -> "CustomPlanSpec": ...
```

- `CUSTOM_SLOT_GRID` (from Phase 0) and `slot_grid(runs_per_week)`.
- `eligible_sessions(phase, slot, *, target_distance, is_trail)` returns the
  catalog entries that can go in a cell:
  - catalog `phases` contains the phase, and its `type` maps to the slot;
  - **ignore the `distances` gate** for universal zones (`E`, `T`, `I`, `R`).
    Sessions paced at `M` or at goal pace stay limited to their own distances,
    because their pace depends on that race;
  - `trail_*` entries only for trail plans;
  - never `_BACKYARD_ONLY_IDS`, taper sharpeners, or `time_trial_5k`.
- `validate_spec(spec, runs_per_week, target_distance, is_trail) -> list[Problem]`:
  - every cell in the grid has ≥ 1 and ≤ 3 sessions, and every id is eligible
    for its cell;
  - a phase's Speed and Threshold menus don't both contain VO2-dominant
    sessions (`pace_zone == "I"`). This is the book's "never two VO2 in a
    week" rule;
  - `runs_per_week >= 3`, distance not backyard.
- Problems are keys plus figures, not prose (the same pattern as
  `training_read` findings), so the web layer can word and translate them.

**Strength templates** in `periodization/strength_data.py`: add
`climb` (squat 3s down, walking lunge, step-up, single-leg RDL, calf raises)
and `descent` (5s eccentric squat, lateral lunge, slow box step-down,
squat/drop jumps, single-leg balance, plank set) for each experience level,
using the existing `_PHASE_MODIFIERS` for base/build/peak/taper dosing.

Tests (`tests/test_core/test_custom_plan.py`): spec round-trip, eligibility
per distance/trail, every validation rule, and the grid matching the
composers for the whole matrix. That last one guards against drift if a
composer changes.

## Phase 2 — Generator: honour the spec (`contexts/plan/generators/`)

Thread `custom_spec: CustomPlanSpec | None` through
`TrainingPlanGenerator.generate_plan` → weekly builder →
`generate_daily_workouts`.

1. **Rotation inside the runner's choices.** Add `allowed_ids:
   Sequence[str] | None` to `overlay_key_workout` and
   `KeyWorkoutLibrary.ordered_candidates`. When it's set, candidates are the
   menu (still filtered by type and phase, *not* by distance), and **all the
   existing variety logic still runs**: no-repeat window, per-plan use cap,
   peak work-floor walk. Prefer this to `force_id`: `force_id` bypasses the
   rotation state and the peak "don't regress below build" invariant.
   With a single-item menu, the no-repeat window must yield (repeating the
   only choice is the runner's call). Add a test for it.
2. **Proportional long runs.** Every long-run session in the book is a
   *shape* over whatever distance the day carries: thirds (negative split),
   the final 3–5 km (fast finish), 1-minute surges sprinkled through, quality
   blocks folded in (sandwich). Add a long-run *shape* to the catalog
   entries (`shape: {"segments": [(fraction, zone), …]}` or a builder id),
   and a builder in `core/training/workouts/workout_steps/` that lays the
   shape over the engine's flexible long-run distance **without pinning it**.
   The day carries `key_workout_id` (so the card, the rationale and adaptation
   all treat it as the runner's session), but `is_prescriptive` stays false,
   so `fill_shortfall` can still grow it and the volume guard has nothing to
   refuse. `rebuild_key_workout` re-lays the shape at the adapted distance
   instead of snapping back to a prescription. Shapes are validated by zone
   share (e.g. ≤ 25% of the run at T or faster), so a shaped long run is
   still mostly easy. Fixed-length long sessions (B2B day 2, time-on-feet by
   hours) stay prescriptive and keep the guard; when the guard wins on one,
   set `workout["custom_choice_deferred"] = "long_run_volume"` and the UI
   says why.
3. **Quality type from the pick** at 3–4 runs: see Phase 0, finding 2.
   Test that the budget for a week whose pick is an interval matches the
   engine's own interval week for the same inputs.
4. **Taper and engine-owned weeks** ignore the menus (`phase == "taper"`).
   Recovery weeks use them, with the usual trims.
5. **Strength**: extend `attach_strength_sessions` with
   `sessions_per_week` and `template`. For `climb_descent`, A goes on the
   first eligible easy day and B on the last. Add the book's rule that is
   missing today: **never on the day before the long run in peak weeks**.
   Custom plans only (decided), so existing plans don't change.
6. **Refuse before generating** (`engine_floors.py` style): spec invalid,
   ≤ 2 runs, 0 km, backyard. Raise a new `InvalidCustomPlanException`
   (`RunCoachException`, with `user_message` / `suggestion`).

Tests (`tests/test_core/` or `tests/test_services/`, following the generator
tests):
- Over a matrix of distance × runs 3–6 × min/max weeks: a custom plan passes
  `plan_validator` and `plan_structure_guard`, and its weekly totals match the
  automatic plan for the same inputs within a small tolerance (the budget is
  the engine's, so they should).
- Every build/peak quality/long day's `key_workout_id` is in that phase's
  menu, or the day is marked deferred.
- Shaped long runs: honoured in every build/peak week at 3–6 runs, weekly
  totals unchanged from the automatic plan, zone share within the cap.
- `test_free_weekdays.py`: add the custom generator path.
- The backtest harness (`adaptation/backtest.py`) replays a history against a
  custom plan, and the chosen ids survive adaptation.

## Phase 3 — Persistence, service, title

- **Migration `040_add_custom_plan_fields`** (via the migration-author flow,
  round-tripped on a scratch copy and never on `runcoach.db`):
  `training_plans.custom_spec JSON NULL`, `training_plans.custom_index INTEGER NULL`.
  Add a `Mapped[...]` on `TrainingPlan`.
- **`PlanRequest`** (`app/schemas/plan_request.py`): optional
  `custom: CustomPlanSpecIn | None`. A `@model_validator` converts it to
  `CustomPlanSpec` and runs `validate_spec`.
- **`PlanService`** (`plan_service.py:160`): pass `custom_spec` into
  `generate_plan` and persist `custom_spec` + `custom_index = max(user's) + 1`.
  Numbers are never reused, so "Custom Plan 3" never refers to two different
  plans in a runner's history.
- ⚠️ **`find_duplicate` must compare `custom_spec`.** Today it would return an
  existing *automatic* plan for a custom request with the same basics, so the
  runner would silently get a plan they didn't build.
- **Title**: new `CustomPlanHandler` in `plan_type_registry.py`.
  `matches` is `plan.custom_spec is not None`, and it is registered ahead of
  `DistancePlanHandler`. `display_label` → "Custom Plan {n} · {distance label}".
  `enrich_view_context` delegates to the distance handler, so zones and the
  trail extras still render. `plan_type` stays `"distance"`: it is read in too
  many places to fork.
- **i18n**: add `"Custom Plan {n:n} · {distance!}"` and every new string to
  `app/data/i18n/pt/*.json`. `test_phrase_catalogue.py` fails the build
  otherwise.

## Phase 4 — API and builder UI (`web/`)

- `GET /api/custom-plans/options?distance=&is_trail=&runs=` returns the slot
  grid plus eligible sessions per cell: `id, name, structure, rationale,
  intensity, type`, with a sensible default (the session the automatic plan
  would have chosen) pre-selected in each cell.
- `POST /api/custom-plans/preview` returns the phase arc plus one build week,
  generated and **not** persisted. Rate-limited like plan generation (there's
  precedent: the long-run warning endpoint already generates and discards).
- Create through the existing `/generate-plan` with the `custom` block. There
  is one creation path, so the anonymous plan → sign-in flow keeps working.
- Page `/plans/custom/new` (`templates/custom_plan.html`, server-rendered with
  a small script): step 1 reuses the plan form partial, step 2 the grid, step 3
  strength plus preview. The entry point sits next to "New plan" on
  `my_plans.html`.
- Week cards show `custom_choice_deferred` reasons. The plan header shows the
  title from the handler.
- Tests in `tests/test_routers/` (options, preview, create, invalid spec → the
  mapped error) and `tests/test_security/` (ownership, CSRF on the POSTs).
- Verify in the browser via `scripts/verify_ui.py` + `scripts/dev_verify.py`
  (a disposable DB copy).

## Phase 5 — Catalog growth (separate PRs)

Sessions from the book's library that the catalog lacks. The book is our own,
so entries may keep its names ("Kilometre Club", "Hour of Power"). Each has a
`structure` that
`build_key_workout_steps` can parse into executable steps, and has pt
translations. Each starts **custom-only** (a `_CUSTOM_ONLY_IDS` gate, modelled
on `_BACKYARD_ONLY_IDS`) so automatic plans don't change. They graduate into
the automatic rotation in a later, deliberate PR.

| Proposed id | Type | Structure |
|---|---|---|
| `flying_30s` | interval | 6–8 × 30 m near-max from a rolling build |
| `vo2_800s` | interval | 6–10 × 800 m @ I, 400 m jog |
| `effort_3min_repeats` | interval | 5–7 × 3:00 @ I by feel, 2:00 jog |
| `km_cutdowns` | interval | 6 × 1 km, T → I, 2:00 jog |
| `broken_tempo` | tempo | 2 × 15 min @ T, 3 min jog |
| `threshold_capstone` | tempo | 3 × 15 min @ T, 3 min jog (peak only, once per plan) |
| `minute_ladder` | interval | 1-2-3-4-3-2-1 min @ T–I, half-time jog |
| `kenyan_fartlek` | interval | 15–20 × (1 min hard / 1 min easy) |
| `sandwich_long` | long | long run with 3 × 15 min @ M–T folded in |
| `surge_long` | long | easy long run with 8–12 × 1 min @ T |

`test_key_workout_catalog.py`, `test_catalog_prose_sync.py` and
`test_phrase_catalogue.py` cover every addition.

Later, the **non-running sessions** (stairs power/endurance, weighted incline
hike, treadmill decline). They need a time-based, distance-0 session that
counts toward the week's *time* but not km. Completion stats, the run mapper
and the Intervals export (`intervals_export`) each need a decision, so this is
its own design.

---

## Risks and how each is handled

| Risk | Handling |
|---|---|
| Adaptation re-selects sessions and quietly undoes the choices | It doesn't: rebuilds keep `key_workout_id`. A hard day eased to easy clears it, which is correct. The Phase 2 backtest test pins this |
| `type_swapper` suggests swapping a chosen tempo | Swaps are runner-accepted suggestions, so acceptable. Revisit if feedback says otherwise |
| `find_duplicate` returns an automatic plan | Fixed in Phase 3 |
| Menus that are all VO2 sessions overload a week | `validate_spec` rule, plus the existing Daniels share caps |
| One-item menus repeat for 6 weeks | Allowed, it's the runner's choice. The preview shows it |
| Distance-agnostic sessions feel off for a race (e.g. 200 m reps in a marathon build) | Eligibility keeps universal zones only. Per-session distance hints are a later polish |
| Composer changes break the grid | The Phase 1 grid-vs-composer test |

## Decisions (settled 2026-10-15)

1. **Runs per week floor: 3.**
2. **Source:** *Flat to Mountain* is our own document, so its session names
   and text can be used directly in the catalog.
3. **"No strength the day before a peak long run" applies to custom plans
   only.** Automatic plans keep their current snapshots.
4. **Easy-run choices** (strides 0/1/2 a week, soft-surface) are **v1.1**.

## Sizing

| Phase | Size | Ships as |
|---|---|---|
| 0 spike | done | notes only |
| 1 core | S | PR 1 (with 2) |
| 2 generator (incl. proportional long runs) | M–L | PR 1 |
| 3 persistence + title | S | PR 2 |
| 4 API + UI | M–L | PR 2 |
| 5 catalog | S per batch | PRs 3+ |

## As built (deviations from the plan above)

- **Shaped long runs carry `long_shape_id`, not `key_workout_id`.** A
  `key_workout_id` makes a card prescriptive everywhere (`is_prescriptive`,
  `_resize_long_run` strips it), which is exactly what a shape must not be.
  The shape id travels on the card instead, and every rebuild path re-lays it.
- **Quality picks use `force_id`** with the rotation's own budget floor applied
  first (`fits_key_workout_budget`), and the runner's order as the rotation —
  `CustomRotation` walks each cell's menu one step per use.
- **Six Flat to Mountain quality sessions** landed (`ftm_800s`,
  `ftm_km_cutdowns`, `ftm_three_minute_repeats`, `ftm_kenyan_fartlek`,
  `ftm_broken_tempo`, `ftm_hour_of_power`), built on the catalog's existing rep
  families so prose and watch steps share one source. Not done: the minute
  ladder and the compound sessions (they need new step builders), and the
  stair/incline sessions (the non-running design is still open).
- **Long-run shapes:** steady, negative split, fast finish, sandwich, surges.
  Back-to-back weekends and time-on-feet were left out: one is two days, the
  other is defined by hours.
- Measured on the Phase 0 matrix: every build/peak quality day and every
  non-recovery long run is the runner's choice; weekly totals stay within a few
  km of the automatic plan for the same inputs.
