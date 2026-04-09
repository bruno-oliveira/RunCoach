# Codebase Improvements Checklist

Issues found across security, correctness, and maintainability. Ordered by severity.

---

## Security

- [x] **IDOR on run creation** — `POST /api/runs` writes `training_plan_id` and `daily_workout_id` from the request body without verifying they belong to the authenticated user. An attacker can link their run to any user's plan, polluting that plan's analytics and adaptation data.
  - `app/routers/runs.py:72–103`
  - Fix: before saving, verify `TrainingPlan.user_id == current_user.id` and that the `DailyWorkout` belongs to a plan owned by the same user. Raise 403 on mismatch.

- [x] **Plan claim race condition** — `POST /api/plan/{plan_id}/save` uses `check_ownership=False` and then checks non-atomically whether the current owner is anonymous. Any authenticated user can claim a plan created by any anonymous session (not just theirs), since the `anonymous_user_id` cookie is not validated against `plan.user_id`.
  - `app/routers/plans.py:763–786`
  - Fix: verify the request's `anonymous_user_id` cookie matches `plan.user_id` before allowing the claim.

- [x] **PDF cache outside static tree** — `pdf_cache/` is written to a relative CWD-anchored path that sits alongside the static directory. If static file serving is ever misconfigured, plan PDFs could be publicly accessible by URL.
  - `app/core/export/pdf_generator.py:28–29`
  - Fix: write to an absolute path outside the web root, e.g. `/tmp/pdf_cache`.

- [x] **PII in INFO logs** — User email addresses are logged at `INFO` level on every login, which appears in Fly.io log streams.
  - `app/services/auth_service.py:78`, `app/routers/auth.py:48`
  - Fix: downgrade to `DEBUG` or log only a truncated/hashed identifier.

---

## Correctness

- [x] **Strava sync: unhandled `IntegrityError` on concurrent duplicate activities** — `sync_activities` checks for duplicates with a non-atomic `SELECT` before inserting. If two sync calls run concurrently, the second insert raises an unhandled `IntegrityError`, propagating as HTTP 502 and losing all progress from that batch.
  - `app/services/strava_service.py:254–289`
  - Fix: wrap `db.add` / `db.flush` in `try/except IntegrityError`, roll back the savepoint, increment `skipped`, and continue.

- [x] **`EncryptedType` returns ciphertext on key rotation instead of `None`** — When `SECRET_KEY` changes, `process_result_value` catches `InvalidToken` and returns the raw ciphertext as a plain string. For Strava tokens this means the app uses a garbled string as a refresh token, causing silent auth failure with no re-authorization prompt.
  - `app/models/encrypted_type.py:46–56`
  - Fix: return `None` on `InvalidToken`. When `strava_refresh_token` is `None` but `strava_athlete_id` is set, surface a "Reconnect Strava" prompt.

- [x] **Plan limit doesn't count `TriathlonPlan` rows** — `has_reached_plan_limit` only counts `TrainingPlan` rows. The triathlon router has no plan-limit check at all, allowing unlimited triathlon plan creation.
  - `app/services/plan_service.py:50–53`, `app/routers/triathlon.py`
  - Fix: if the limit applies to all plan types, sum both tables or add the same limit check to the triathlon router.

- [x] **Very low base mileage for long distances: long-run minimum exceeds weekly budget** — For a marathon with 1–3 km/week base, `target_distance * 0.25 = 10.5 km` minimum long run exceeds the total weekly volume.
  - `app/core/generators/plan_generator.py:975–979`
  - Fix: add a minimum base mileage check for longer distances, consistent with the constraints already in `config.py`.

- [x] **Datetime timezone handling is fragile** — `_resolve_user` calls `datetime.now(timezone.utc).replace(tzinfo=None)` to compare against `last_activity`. This works while everything is stored as naive UTC, but silently breaks if any path stores a non-UTC aware datetime and strips its tzinfo.
  - `app/dependencies.py:131–137`
  - Fix: standardise on one approach (naive UTC throughout) and add a comment explaining the choice.

---

## Bug Fixes Already Applied

- [x] **Favorite recipe DELETE returns 422** — `remove_favorite` declared `favorite_id: int` but `FavoriteRecipe.id` is a UUID string. Changed to `str`.
  - `app/routers/recipes.py:248`

- [x] **Favorite toggle breaks after adding on recipe detail page** — `{{ favorite_id }}` was server-rendered as `None` when the recipe wasn't yet favorited, so the subsequent DELETE went to `/api/recipes/favorite/None`. Introduced a `currentFavoriteId` JS variable that captures `data.id` from the POST response and added `response.ok` checks on both fetch paths.
  - `app/templates/recipe_detail.html`
