# RunCoach Improvements

Tracking document for code quality, maintainability, and correctness improvements identified during codebase review (2026-03-28).

## Bugs

- [x] 1. **ISO week grouping ignores year boundaries** — `performance_service.py:174` — Runs grouped by week number only, inflating mileage across year boundaries
- [x] 2. **`_apply_ai_suggestions` subtracts 0 from `total_km`** — `plan_service.py:631-638` — `more_rest` branch zeroes distance before reading it
- [x] 3. **`more_endurance` overstates `total_km`** — `plan_service.py:651-661` — Uses new distance instead of original to compute delta
- [x] 4. **`UnboundLocalError` on unknown `workout_type`** — `plan_generator.py:422-438` — No `else` branch in if/elif chain
- [x] 5. **`NameError` in `_get_workout_distribution_simple`** — `plan_generator.py:331-334` — `else` branch uses `quality_workouts` before defining it
- [x] 6. **`KeyError` on `training_tips`** — `adaptive_plan_generator.py:255-268` — Key may not exist in base plan dict
- [x] 7. **Shallow copy causes shared state mutation** — `adaptive_plan_generator.py:211` — `week.copy()` shares nested lists
- [x] 8. **`"training_plan" in dir()` is unreliable** — `plans.py:254, 258` — Not a safe variable-existence check
- [x] 9. **Mid-method `commit()` leaves partial state** — `performance_service.py:337-339` — Weekly plans committed before nutrition attached
- [x] 10. **`Session(bind=engine)` deprecated** — `main.py:148` — Crashes on SQLAlchemy 2.0+

## Safety & Correctness

- [ ] 11. **Fragile naive/aware datetime pattern** — `dependencies.py:127`, `auth_service.py` — `replace(tzinfo=None)` will TypeError if DB returns aware datetimes
- [ ] 12. **`except Exception: pass` swallows migration errors** — `main.py:130-136` — Narrow to `OperationalError`
- [ ] 13. **Cert cache race condition** — `auth_service.py:19-21, 59-60` — Non-atomic updates to class-level mutable state
- [ ] 14. **`adherence_rate` can exceed 100%** — `adaptation_service.py:160` — Cap with `min(100.0, ...)`
- [ ] 15. **Blanket `except` in `create_run_log`** — `runs.py:162-168` — Catch `IntegrityError` specifically
- [ ] 16. **`update_user_activity` commits on every request** — `dependencies.py:130` — Throttle to once per 5 minutes

## Dead Code & Unused Artifacts

- [ ] 17. `_select_optimal_meal` — defined, never called — `nutrition_engine.py:212-276`
- [ ] 18. `_format_time` — defined, never called — `performance.py:64-73`
- [ ] 19. Unused `vdot` param on `_generate_tempo_run` / `_generate_interval_run` — `plan_generator.py:708, 740`
- [ ] 20. Lambda `wt=workout_type` capture never used — `performance_plan_generator.py:721-727`
- [ ] 21. Duplicate `import json` inside method — `pdf_generator.py:737`
- [ ] 22. `import shutil` deferred inside method — `pdf_generator.py:198`

## Cross-File Duplication

- [ ] 23. **Pace formatting implemented 3 times** — `utils.py:60`, `vdot_calculator.py:56`, `coaching_feedback_engine.py:29`
- [ ] 24. **Time parsing implemented twice** — `utils.py:92`, `vdot_calculator.py:167`
- [ ] 25. **`_to_date` is private but imported externally** — `adaptation_service.py:21` → `strava.py`

## Missing Indexes

- [ ] 26. `plan_customizations.training_plan_id`
- [ ] 27. `triathlon_plans.user_id`

## Deferred Imports (move to module level)

- [ ] 28. `plan_generator.py:442` — `KeyWorkoutLibrary` inside per-day loop
- [ ] 29. `plan_generator.py:466` — `generate_coaching_note` inside per-day loop
- [ ] 30. `performance_plan_generator.py:809` — `VDOTCalculator`
- [ ] 31. `key_workout_library.py:514` — `VDOTCalculator`
- [ ] 32. `main.py:64` — `uuid` inside middleware

## Architecture

- [ ] 33. **`adjust_plan` is 350 lines** — `adaptation_service.py:616-968` — Extract signal computation and mutation loop
- [ ] 34. **`get_plan_view_data` does too much** — `plan_service.py:454-538` — Split into independently callable pieces
- [ ] 35. **Duplicated plan-limit check** — `plans.py` and `performance.py` — Extract to `PlanService`
- [ ] 36. **Three near-identical error template blocks** — `performance.py:243-323` — Extract helper
- [ ] 37. **`_add_nutrition_guidance` monolith** — `pdf_generator.py:620-733` — Extract per-section methods + `_add_bullet_list` helper
- [ ] 38. **`FavoriteRecipe` relationship bypass** — Defines own `relationship("User")` outside centralized `models/__init__.py`
- [ ] 39. **Deprecated `@app.on_event`** — `main.py:261, 283` — Migrate to `lifespan` context manager

## Minor

- [ ] 40. `Dict[str, any]` → `Dict[str, Any]` — `adaptation_service.py:123, 377, 621, 975`
- [ ] 41. `>{15}%` redundant f-string — `schemas.py:484`
- [ ] 42. `_select_varied_meal` scoring dominated by random noise — `nutrition_engine.py:293-323`
- [ ] 43. Return type `-> float` but returns `None` — `adaptation_service.py:206`
