# Code Review: Maintainability & Cleanliness Improvements

## ~~Priority 1 — Dead Code Removal~~ ✅ DONE

### Top-level recipe scripts (507 KB, 15 files)

The `add_*.py`, `enhance_recipes.py`, and `clean_recipes.py` scripts are one-shot data seeding utilities that ran once and now clutter the repository root. They are committed to git but serve no runtime or development purpose.

**Files:**
- `add_bean_recipes.py` (478 lines)
- `add_extra_bean_recipes.py` (1030 lines)
- `add_international_recipes.py` (880 lines)
- `add_mediterranean_performance_recipes.py` (1353 lines)
- `add_more_beef_chicken_recipes.py` (610 lines)
- `add_more_mediterranean_recipes.py` (1016 lines)
- `add_more_recipes.py` (687 lines)
- `add_more_stew_recipes.py` (392 lines)
- `add_nl_mediterranean_recipes.py` (687 lines)
- `add_performance_recipes.py` (600 lines)
- `add_stew_recipes.py` (568 lines)
- `add_unique_healthy_recipes.py` (500 lines)
- `add_unique_recipes.py` (471 lines)
- `clean_recipes.py` (72 lines)
- `enhance_recipes.py` (1616 lines)

**Recommendation:** ~~Delete all of them. The data they produced is already in `app/data/`. If ever needed again, the scripts are preserved in git history.~~ Done.

---

### Dead router: `app/routers/plans_pages.py` (490 lines)

A near-copy of `app/routers/plans.py` (491 lines). It is not imported or registered anywhere — completely unreachable dead code from an incomplete refactor.

**Recommendation:** ~~Delete it.~~ Done.

---

### Dead JavaScript files (4,297 lines)

Old monolith JS that was split into modular files in subdirectories but the originals were never cleaned up:

| Dead file | Lines | Replaced by |
|-----------|-------|-------------|
| `app/static/js/analytics_dashboard.js` | 2,252 | `app/static/js/analytics/*.js` (9 files) |
| `app/static/js/plan.js` | 1,265 | `app/static/js/plan/*.js` (5 files) |
| `app/static/js/share_card.js` | 780 | `app/static/js/share/share_card.js` (227 lines) |

None of these are referenced in any template.

**Recommendation:** ~~Delete all three.~~ Done.

---

## Priority 2 — Long Functions (partially done)

Functions over 100 lines hurt readability. Progress:

| Lines | Location | Function | Status |
|-------|----------|----------|--------|
| 173 | `app/services/readiness_service.py` | `compute_readiness` | ✅ Extracted `_parse_plan_targets` + `_build_component_dict` |
| 161 | `app/services/adaptation/plan_adjuster.py` | `adjust_plan` | ✅ Already well-decomposed (+ fixed stale datetime import) |
| 158 | `app/core/training/workout_steps.py` | `parse_key_workout_steps` | ✅ Each regex pattern extracted to own function |
| 144 | `app/routers/runs.py` | `create_run_log` | ✅ Extracted `_enrich_vdot_and_prediction` + `_build_race_comparison` |
| 143 | `app/core/export/triathlon_pdf_generator.py` | `_week_page` | Acceptable (PDF layout logic) |
| 132 | `app/services/adaptation/type_swapper.py` | `get_swap_proposals` | Acceptable (linear logic) |
| 131 | `app/services/adaptation/run_mapper.py` | `map_runs_to_plan` | Acceptable (orchestration) |
| 127 | `app/routers/plans.py` | `generate_plan` | Acceptable (endpoint handler) |
| 120 | `app/routers/readiness.py` | `adapt_todays_workout` | Acceptable (endpoint handler) |

---

## ~~Priority 3 — Excessive Lazy Imports~~ ✅ DONE

Moved unnecessary lazy imports to module level:

- ~~`app/routers/runs.py` — `FeedbackService` (3 sites) and `WeeklyPlan` moved to top~~ Done.
- ~~`app/core/generators/plan_generator.py` — `VDOTCalculator` moved to top~~ Done.
- ~~`app/services/performance_service.py` — `performance_progress` imports consolidated at module level~~ Done.
- ~~`app/core/training/workout_builders.py` — `VDOTCalculator` (2 sites) moved to top~~ Done.
- ~~`app/services/strava_service.py` — `VDOTCalculator` and `FeedbackService` moved to top~~ Done.

Remaining lazy imports are genuinely breaking circular dependencies (e.g., `insights_service` ↔ `insight_generators`).

---

## Priority 4 — Large Files

Files over 500 lines that could benefit from splitting:

| Lines | File | Notes |
|-------|------|-------|
| 670 | `app/core/training/workout_steps.py` | `parse_key_workout_steps` (158 lines) is self-contained; extract to its own module |
| 587 | `app/services/adaptation/plan_adjuster.py` | Already well-decomposed into functions; acceptable |
| 576 | `app/core/training/key_workout_data_long.py` | Pure data — acceptable |
| 551 | `app/core/generators/plan_generator.py` | Thin orchestrator with many small methods — acceptable |
| 545 | `app/services/gap_analysis_service.py` | Mix of class + free functions; could split internal computations into `_gap_computations.py` |
| 523 | `app/schemas.py` | 12 schema classes; split into `schemas/plans.py`, `schemas/runs.py`, `schemas/auth.py` if it grows further |

---

## Priority 5 — Minor Issues

### Duplicated logic in `plans.py` vs `plans_pages.py`
Even though `plans_pages.py` is dead code now, the fact it existed suggests the split between "API" and "page" routers was never completed cleanly. The remaining `plans.py` mixes HTML-returning endpoints (`/generate-plan`, POST returning `HTMLResponse`) with plan management. Consider the existing pattern used elsewhere (`performance.py` API + `performance_pages.py` pages) for consistency.

### `app/main.py` `create_app` (116 lines)
Contains inline route handlers (`/health`, `/`, `/debug/*`). Extract the home page and debug routes to a `routers/pages.py` or similar.

### `app/static/js/analytics/analytics_dashboard.js` (514 lines) vs root (2252 lines)
The refactored `analytics/` version is already modular and fine. Just delete the root monolith.

---

## Summary

| Category | Lines removable | Effort | Status |
|----------|----------------|--------|--------|
| Top-level recipe scripts | ~10,962 | Low (just delete) | ✅ Done |
| Dead router (`plans_pages.py`) | 490 | Low (just delete) | ✅ Done |
| Dead JS monoliths | 4,297 | Low (just delete) | ✅ Done |
| **Total dead code** | **~15,749** | | **Done** |
| Long function refactors | — | Medium | ✅ Top 4 refactored |
| Lazy import cleanup | — | Low-Medium | ✅ Done |
