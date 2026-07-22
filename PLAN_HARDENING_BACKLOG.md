# Hardening & Onboarding Backlog

Deferred items from the 2026-07-22 review of rate limiting, plan-generation
robustness, and first-run onboarding. The items marked **Shipped** in that same
pass are recorded here so they aren't re-investigated; the **Deferred** items are
the actual backlog.

---

## Shipped 2026-07-22 (context, not backlog)

- **`/api/intervals/sync` rate limiter** — `intervals_sync_limiter`
  (12 req / 60 s per IP) in `app/rate_limit.py`, applied in
  `app/web/routers/intervals.py`. Each sync is only ~2 Intervals.icu API calls,
  so this guards against accidental polling loops / abuse, not volume.
- **Plan-gen fix #1 — VDOT/pace floors.** `VDOTCalculator.get_pace_zones` now
  clamps its input to `[VDOT_FLOOR, VDOT_CEILING]` (25–85), so a degenerate VDOT
  from a non-calculator source (predictor, HR-pace calibration) can't produce
  nonsensical training paces.
- **Plan-gen fix #2 — plan-level structure guard.**
  `app/contexts/plan/generators/plan_structure_guard.py` runs after all smoothing
  in `generate_plan`; fatal issues (unrunnable week, collapsed non-recovery week)
  raise `PlanGenerationException`, softer ones log a warning for telemetry.
- **Plan-gen fix #3 — run-frequency floor.** `_viable_run_frequency` drops
  running days rather than shattering a low weekly budget into sub-2.5 km/run
  sessions (floored at `MIN_RUNNING_DAYS = 3`). Aligned with the plan grid's own
  "unrealistic below 2.5 km/run" line. Note: the *min-weeks* interpolation was
  investigated and found sound — the low-end artifact was min-*base*, not
  min-*weeks*, so the original "snap shortest-weeks plans to a skeleton" framing
  was redirected to the frequency floor.
- **Plan-gen fix #4 — already in production.** Deloads fire on ≥8-week plans
  (continuous 3:1 cadence in `phase_calculator.recovery_week_set`), and taper is
  protected from upward adaptation (`week_adjuster._resolve_type_multiplier`
  caps taper at `min(type_mult, 1.0)`, audit G2). This pass added a deload
  regression test; the taper cap was already tested
  (`test_positive_adaptation_never_inflates_taper`). The stale
  memory/audit note ("≤12-week plans get no deload; taper unprotected") is
  superseded — both are done.
- **Plan-gen fix #5 — grid invariant tests** in
  `tests/test_core/test_plan_structure_invariants.py`. Chose durable *structural
  invariants* over exact golden snapshots: a continuously pace/tuning-tuned
  generator makes exact snapshots brittle (they'd break on every intended
  change) while giving weak signal. The invariants (no fatal structure, every
  week runnable, no trivial runs, deload present, taper non-increasing) catch
  the degenerate-week regressions the golden idea was meant to catch.

---

## Deferred — Rate limiting / cost

### 1. Per-IP limiter on `/api/analytics/coach-note/{plan_id}`
- **Why:** the endpoint is auth-gated and the *Anthropic spend* is already
  bounded (cache keyed by run signature + hard once-per-plan-per-day cap in
  `coach_narrative_service.build_coach_note`), but the endpoint itself has no
  `RateLimiter`. Each call still runs the full fact-assembly (several DB queries)
  even when it returns cache, so a client can hammer it.
- **Do:** add a `coach_note_limiter` (e.g. 20 / 60 s) in `app/rate_limit.py` and
  `.check(request)` it in the route (add a `Request` param like the sync route).
- **Size:** small.

### 2. Global / monthly AI spend ceiling
- **Why:** the current bound is *per-plan-per-day*. Total spend scales with
  (users × plans). Fine at demo scale; want a ceiling before any real launch.
- **Do:** a coarse global counter (daily/monthly call budget) checked in
  `build_coach_note` before invoking the narrator; fall back to the deterministic
  rules note when exhausted. Persist the counter (DB row or cache) so it survives
  machine wakes on Fly.io's scale-to-zero.
- **Size:** small–medium. Decide the budget number with the user.

---

## Deferred — Onboarding / product

### 3. Re-surface Strava as a connect option on the landing page
- **Why:** a friend who has never heard of Intervals.icu hits a real wall — the
  connect flow assumes she *already has an Intervals.icu account with her runs in
  it* (Intervals.icu is itself a Garmin/Strava aggregator). A full Strava backend
  already exists (`/api/strava/connect`, callback, sync) but is **not exposed**
  anywhere on the landing page — only Intervals.icu is. Strava is far more
  familiar to a newcomer.
- **Do:** add a Strava connect affordance to the connect card in
  `app/web/templates/index.html` (+ `auth.js` chained-connect intent, mirroring
  the Intervals path). Decide whether Strava becomes the primary "connect" CTA
  for first-time users or a secondary option.
- **Size:** medium. Product call on primary vs secondary.

### 4. Honest onboarding copy for the Intervals.icu prerequisite chain
- **Why:** the landing copy ("Connects through a free Intervals.icu account — one
  minute, one time") undersells the real chain for a true newcomer: create
  Intervals.icu account → connect Garmin/Strava *inside* Intervals.icu → wait for
  runs to sync there → *then* OAuth into RunCoach. RunCoach shows nothing useful
  until her runs already exist in Intervals.icu.
- **Do:** either (a) set expectations honestly in the connect card for
  first-timers, or (b) steer newcomers to "Build a plan without connecting" (the
  friction-free anonymous 3-question path) first, and only walk Garmin users
  through Intervals.icu setup when they want adaptive + send-to-watch.
- **Size:** small (copy) but depends on the #3 decision.

---

## Demo note (for showing the app to a friend)

The friction-free path today is **"Build a plan without connecting"** — anonymous
cookie, no account, a real plan in ~30 seconds. Use that for the demo; only walk a
Garmin user through Intervals.icu setup if they want the adaptive / send-to-watch
experience. See #3/#4 to make the connect path itself newcomer-friendly.
