"""Workout-scaling primitives extracted from weekly_plan_builder.

Each week's distance budget can disagree with the sum of its generated
workouts. The functions here close that gap by:

- shrinking flexible (easy / long) workouts when the week is over budget
  (`scale_down`),
- expanding flexible workouts when the week is under budget, with a hard
  ceiling on the long run (`fill_shortfall`),
- capping long-run dominance against the rest of the week
  (`enforce_long_run_ratio_cap`).

Prescriptive workouts — key-workout overlays and tempo/interval/hill builds
that embed distance fragments in their description / step list — are
never silently rescaled, because changing `distance` would leave the
description and steps describing a different session than the runner is
asked to do.

The lower-level helpers (`set_distance`, `rebuild_long_run`,
`rescale_steps`, `is_prescriptive`) are exported too so callers in
`plan_generator` can apply the same invariant-preserving rules when
they do their own scaling passes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.training import long_run_calculator, workout_builders
from app.core.training.key_workout_library import rebuild_key_workout
from app.core.training.quality_caps import (
    MAX_EASY_VS_LONG_RUN,
    MIN_EASY_PER_RUN_KM,
    easy_run_cap,
    volume_scaled_easy_cap,
)
from app.core.training.training_constants import get_hard_ceiling


def long_run_pace_min_km(pace_zones: Optional[Dict]) -> Optional[float]:
    """Long-run pace (min/km) from VDOT zones, for the long-run time cap.

    Returns None when no VDOT-derived zones are available so the time cap is
    skipped rather than guessed (audit E7 time cap).
    """
    if not pace_zones:
        return None
    e_zone = pace_zones.get("E")
    if not isinstance(e_zone, dict):
        return None
    long_sub = e_zone.get("sub_zones", {}).get("long_run")
    src = long_sub if isinstance(long_sub, dict) else e_zone
    # E-zone bands expose slow/fast bounds rather than a single pace_min_km;
    # the slow bound is the more conservative (longer-time) estimate.
    return (
        src.get("pace_min_km")
        or src.get("pace_min_km_slow")
        or src.get("pace_min_km_fast")
    )


def enforce_long_run_time_cap(
    workouts: List[Dict[str, Any]],
    pace_zones: Optional[Dict] = None,
    trail_profile=None,
) -> None:
    """Final clamp keeping a road long run under ``MAX_LONG_RUN_HOURS``.

    ``fill_shortfall`` can spill capped-easy volume back into the long run, so
    this runs last: a slow runner's long run never exceeds the time ceiling,
    even if the week falls a little short as a result. Trail/ultra and
    prescriptive key long runs are left untouched (audit E7 time cap).
    """
    if trail_profile is not None:
        return
    pace = long_run_pace_min_km(pace_zones)
    if not pace or pace <= 0:
        return
    time_cap_km = round((long_run_calculator.MAX_LONG_RUN_HOURS * 60.0) / pace, 1)
    for w in workouts:
        if (
            w.get("type") == "long"
            and not w.get("key_workout_id")
            and w.get("distance", 0) > time_cap_km
        ):
            rebuild_long_run(w, time_cap_km, pace_zones)


def reclamp_quality_to_long_run(workouts: List[Dict[str, Any]]) -> None:
    """Re-fit key quality sessions against the *final* long-run distance.

    ``overlay_key_workout`` fits a session under the long run known at overlay
    time, but ``fill_shortfall`` / the ratio and time caps can shrink the long
    run afterwards — leaving a quality day above the ceiling it was fitted to.
    Runs after the long-run clamps as the last word: reps are dropped (never
    shortened) until the session fits, and the card re-adopts the priced step
    total. A session whose steps can't be priced is clamped to the ceiling
    directly.
    """
    from app.core.training import workout_steps as _steps_mod
    from app.core.training.tuning import MAX_KEY_WORKOUT_VS_LONG_RUN

    long_km = max(
        (w.get("distance") or 0 for w in workouts if w.get("type") == "long"),
        default=0,
    )
    ceiling = round(long_km * MAX_KEY_WORKOUT_VS_LONG_RUN, 1)
    if ceiling <= 0:
        return
    for w in workouts:
        if (
            w.get("type") in ("tempo", "interval", "hill")
            and w.get("key_workout_id")
            and not w.get("fixed_structure")
            and (w.get("distance") or 0) > ceiling
            and w.get("steps")
        ):
            w["steps"] = _steps_mod.fit_steps_to_distance(w["steps"], ceiling)
            km, priced = _steps_mod.compute_distance_from_steps_checked(w["steps"])
            if priced and km > 0:
                w["distance"] = round(km, 1)
            else:
                w["distance"] = min(w["distance"], ceiling)


def is_prescriptive(workout: Dict[str, Any]) -> bool:
    """Workouts whose ``distance``, ``description`` and ``steps`` are tightly
    coupled and must not be rescaled by week-level budget arithmetic.

    Key workouts (``key_workout_id``) are authored prescriptions. The
    standard quality builders (tempo / interval / hill) likewise embed
    distance fragments in the description (warm-up split, rep count,
    main_km), so silently changing ``workout['distance']`` would leave the
    description lying about what the runner is asked to do. Only easy and
    long runs are flexible enough to absorb week-budget drift.

    Race day is the hardest prescription of all: its distance is set by the
    event, so no budget arithmetic — generation *or* adaptation — may move it.
    A marathon does not become 38 km because the week ran over.
    """
    if workout.get("key_workout_id"):
        return True
    return workout.get("type") in ("tempo", "interval", "hill", "race")


def rescale_steps(workout: Dict[str, Any], multiplier: float) -> None:
    """Scale every step's distance_m / duration_s by ``multiplier`` so the
    step list stays in sync with the workout's distance.

    Skipped for prescriptive sessions — their structure is authored to a
    specific dose and shouldn't be rubber-banded to fit budget.
    """
    if multiplier == 1.0 or not workout.get("steps"):
        return
    if is_prescriptive(workout):
        return
    new_steps = []
    for s in workout["steps"]:
        ns = dict(s)
        if ns.get("distance_m"):
            ns["distance_m"] = max(1, int(round(ns["distance_m"] * multiplier)))
        if ns.get("duration_s"):
            ns["duration_s"] = max(1, int(round(ns["duration_s"] * multiplier)))
        new_steps.append(ns)
    workout["steps"] = new_steps


def rebuild_long_run(
    workout: Dict[str, Any], new_distance: float, pace_zones: Optional[Dict]
) -> None:
    """Rebuild a long-run workout so its description and steps reflect the
    new distance.

    ``generate_long_run`` is the single source of truth for the description
    template (including the ``mp_finish`` split that references distance
    fragments) and the matching step list. Calling it with the new distance
    keeps description ↔ steps ↔ distance aligned. Caller-attached fields
    (``coaching_rationale``, ``strength_session``, …) are preserved.
    """
    rounded = round(new_distance, 1)
    rebuilt = workout_builders.generate_long_run(
        workout.get("day", 0),
        rounded,
        rounded,
        pace_zones,
    )
    for key in ("distance", "description", "steps", "intensity", "type"):
        if key in rebuilt:
            workout[key] = rebuilt[key]


def set_distance(
    workout: Dict[str, Any], new_distance: float, pace_zones: Optional[Dict] = None
) -> None:
    """Update ``distance`` and keep the workout's text/steps in lockstep.

    For non-prescriptive workouts, steps are rescaled proportionally. Long
    runs additionally have their description re-rendered (the ``mp_finish``
    variant cites distance splits). Prescriptive non-key workouts (tempo /
    interval / hill) are not expected to flow through here; if they do,
    ``distance`` is updated alone — the caller is responsible for honouring
    the prescription's invariants.

    Key workouts are regenerated end to end via ``rebuild_key_workout``.
    Reconciling only the *prose* is not enough: ``rescale_steps`` refuses
    prescriptive sessions, so the step list — the executable half of the
    card, and what the watch export ships — would keep the dose it was
    built at while the description and the distance moved to the new one.
    A 30.7 km race-rehearsal capped to 28.8 km displayed "17.2 km easy +
    11.5 km at goal pace" over steps that still read 18.4 + 12.3.
    Rebuilding re-derives prose, structure and steps from the new distance
    and snaps ``distance`` onto the executable total, so all three agree.
    """
    old = workout.get("distance", 0) or 0
    rounded = round(new_distance, 1)
    if rounded == old:
        return
    # Race day is set by the event, not by any budget. Callers are expected to
    # filter it out via ``is_prescriptive``, but this is the one distance where
    # a missed filter would be actively harmful — a marathon quietly becoming
    # 38 km — so it is refused here as well as declared there.
    if workout.get("type") == "race":
        return
    if workout.get("type") == "long" and not workout.get("key_workout_id"):
        rebuild_long_run(workout, rounded, pace_zones)
        return
    workout["distance"] = rounded
    if workout.get("key_workout_id"):
        rebuild_key_workout(workout, pace_zones)
        return
    if old > 0 and rounded > 0:
        rescale_steps(workout, rounded / old)


def scale_down(
    workouts: List[Dict[str, Any]],
    total_km: float,
    pace_zones: Optional[Dict] = None,
    protect_long: bool = True,
) -> float:
    """Bring the week's total down to budget by shrinking flexible workouts.

    Prescriptive workouts (key overlays + tempo / interval / hill) stay at
    their prescribed distance — scaling them would silently invalidate the
    description and step list. Easy and (non-key) long runs absorb the
    overage; long runs are rebuilt via the long-run generator so their
    description and steps stay in lockstep with the new distance. If the
    flexible budget is exhausted, the small overage is accepted rather
    than corrupting a prescription.

    With ``protect_long`` (the default), the long run is the week's anchor and is
    protected: the overage is drained from the easy runs first (down to a per-run
    floor) and the long run is only shrunk when the easy budget cannot absorb it.
    This keeps a large prescriptive quality day from eating into the long run —
    trim the filler, keep the anchor — rather than scaling every run down in
    lockstep. Taper weeks pass ``protect_long=False`` so the long run tapers down
    in proportion with the rest of the week rather than being held large while
    the easy runs collapse (which would leave the long run dominating a
    deliberately light week).
    """
    actual_total_km = round(sum(w.get("distance", 0) for w in workouts), 1)
    if actual_total_km <= total_km * 1.01 or actual_total_km <= 0:
        return actual_total_km

    flexible = [
        w
        for w in workouts
        if w.get("type") in ("easy", "long")
        and not is_prescriptive(w)
        and w.get("distance", 0) > 0
        and not w.get("duration_min")
    ]
    if not flexible:
        return actual_total_km

    fixed_km = sum(w.get("distance", 0) for w in workouts if w not in flexible)
    target_flexible = total_km - fixed_km
    flexible_km = sum(w["distance"] for w in flexible)
    if flexible_km <= 0 or target_flexible >= flexible_km:
        return actual_total_km
    target_flexible = max(target_flexible, 0)

    overage = flexible_km - target_flexible
    easy_runs = [w for w in flexible if w.get("type") == "easy"]
    has_long = any(w.get("type") == "long" for w in flexible)
    easy_km = sum(w["distance"] for w in easy_runs)
    easy_absorbable = max(0.0, easy_km - len(easy_runs) * MIN_EASY_PER_RUN_KM)

    if protect_long and has_long and easy_runs and overage <= easy_absorbable:
        # Protect the long run: the easy runs alone can soak up the overage
        # while staying above their per-run floor, so leave the long run intact.
        scale_easy = (easy_km - overage) / easy_km
        for w in easy_runs:
            set_distance(w, w["distance"] * scale_easy, pace_zones)
    else:
        # The easy budget can't absorb it (or there's no long run to protect):
        # scale every flexible run proportionally rather than decimating one.
        scale = target_flexible / flexible_km
        for w in flexible:
            set_distance(w, w["distance"] * scale, pace_zones)
    return round(sum(w.get("distance", 0) for w in workouts), 1)


def fill_shortfall(
    workouts: List[Dict[str, Any]],
    total_km: float,
    actual_total_km: float,
    target_distance: float,
    pace_zones: Optional[Dict] = None,
    trail_profile=None,
    easy_vs_long_ratio: float = MAX_EASY_VS_LONG_RUN,
    experience_level: Optional[str] = None,
) -> float:
    """Fill shortfall by expanding easy runs; reshape long run when its
    distance must change for safety (its cap) or balance against easy.

    Prescriptive workouts are never expanded — their distance is the
    prescription. Long-run mutations rebuild description + steps via
    ``rebuild_long_run`` so the workout stays internally consistent.

    ``easy_vs_long_ratio`` bounds each easy run as a fraction of the long run.
    Low-frequency road plans pass a tighter ratio than the default so the
    single easy slot can't grow into a *second* long effort alongside the long
    run (the documented 3-run artifact: long 14 km + "easy" 13 km for a 5K).
    The long run keeps carrying the week's volume; the overflow the tighter
    easy cap can't hold is dropped, so the week falls slightly short rather
    than prescribing two near-equal long runs (audit G3).

    ``experience_level`` selects the long-run cap the overflow spills into.
    Without it the looser ``get_hard_ceiling`` is used, which is only a safety
    net: spilling to it let a 5K plan prescribe a 14 km long run (2.8x race
    distance) and a marathon plan 40 km, both past the tier the runner's own
    base puts them in.
    """
    if actual_total_km >= total_km * 0.97 or actual_total_km <= 0:
        actual_total_km = round(sum(w.get("distance", 0) for w in workouts), 1)
    else:
        deficit = total_km - actual_total_km
        easy_ws = [
            w
            for w in workouts
            if w.get("type") == "easy"
            and not is_prescriptive(w)
            and w.get("distance", 0) > 0
            and not w.get("duration_min")
        ]
        long_ws = [
            w
            for w in workouts
            if w.get("type") == "long"
            and not is_prescriptive(w)
            and w.get("distance", 0) > 0
            and not w.get("duration_min")
        ]
        # Distribute deficit to easy runs first — the long run was sized by
        # its ratio for a reason, and inflating it to fill a volume gap creates
        # oversized long runs (e.g. 42% of weekly volume in base phase).
        if easy_ws:
            total_easy = sum(w["distance"] for w in easy_ws)
            if total_easy > 0:
                per_easy = deficit / len(easy_ws)
                for w in easy_ws:
                    set_distance(w, w["distance"] + per_easy, pace_zones)
            deficit = round(total_km - sum(w.get("distance", 0) for w in workouts), 1)
        # Only spill to the long run what easy runs could not absorb, and
        # never inflate it past 45% of the weekly target — beyond that the
        # week should fall short rather than concentrate risk in one session.
        if deficit > 0.1 and long_ws:
            max_long_share = 0.45
            for w in long_ws:
                headroom = max(0, total_km * max_long_share - w["distance"])
                spill = min(deficit, headroom)
                if spill > 0.1:
                    set_distance(w, w["distance"] + spill, pace_zones)

    hard_ceiling = get_hard_ceiling(target_distance, trail_profile=trail_profile)
    # The cap the plan is contracted to respect. ``get_hard_ceiling`` is only an
    # absolute safety net; spilling to it made a 5K plan prescribe a 14 km long
    # run and a marathon 40 km. Keep the hard ceiling as the outer bound so a
    # mis-derived tier can never loosen it.
    spill_cap = hard_ceiling
    if experience_level:
        spill_cap = min(
            hard_ceiling,
            long_run_calculator.long_run_cap(
                target_distance,
                experience_level,
                weekly_km=total_km,
                trail_profile=trail_profile,
            ),
        )
    long_ws = [
        w for w in workouts if w.get("type") == "long" and w.get("distance", 0) > 0
    ]
    long_w = long_ws[0] if long_ws else None
    long_is_prescriptive = bool(long_w and long_w.get("key_workout_id"))

    if long_w and long_w["distance"] > spill_cap and not long_is_prescriptive:
        excess = round(long_w["distance"] - spill_cap, 1)
        set_distance(long_w, spill_cap, pace_zones)
        easy_ws = [
            w for w in workouts if w.get("type") == "easy" and w.get("distance", 0) > 0
        ]
        if easy_ws:
            per_easy = excess / len(easy_ws)
            for w in easy_ws:
                set_distance(w, w["distance"] + per_easy, pace_zones)

    if long_w:
        long_d = long_w["distance"]

        # On road plans easy runs are capped at an absolute ceiling so they
        # don't become second long runs; excess volume above the cap spills
        # into the long run (up to its contracted cap) and anything beyond that
        # is dropped — the week falls short rather than prescribing a second
        # long effort (audit G3). Trail back-to-back days are intentionally
        # long, so there the easy run is only bounded by the long run itself.
        def _easy_cap(_long_d: float) -> float:
            if trail_profile is not None:
                return _long_d
            abs_cap = volume_scaled_easy_cap(total_km)
            return easy_run_cap(_long_d, abs_cap, max_vs_long=easy_vs_long_ratio)

        cap = _easy_cap(long_d)
        for w in workouts:
            if w.get("type") == "easy" and w.get("distance", 0) > cap + 0.05:
                set_distance(w, cap, pace_zones)

    # Low-frequency weeks (≤3 runs) have no easy run to receive the volume the
    # distribution budgets for one: the layout is a long run plus a quality
    # session, so the share allocated to types with no slot is dropped and the
    # week lands well under its target (measured: a 2-run half marathon delivered
    # 18.5 km of a 27.5 km week, with the deficit simply unplaced). The two caps
    # that bound such a week — ``long_run_share_ceiling`` (0.60) plus
    # ``MAX_QUALITY_DAY_SHARE`` (0.25) — sum to 0.85, exactly the floor the
    # envelope harness reconciles against, so the remainder must go somewhere.
    # Let the quality day carry it, bounded by the same
    # ``MAX_KEY_WORKOUT_VS_LONG_RUN`` ceiling the key-workout overlay fits
    # sessions to, so quality work still never reaches the long run. The session
    # is grown through ``set_distance`` → ``rebuild_key_workout``, which
    # re-derives prose, steps and distance together.
    #
    # ``easy_vs_long_ratio`` is how the caller encodes a low-frequency schedule
    # (``low_freq_easy_vs_long_ratio``): no other input produces a tighter easy
    # ceiling than the default.
    low_frequency_schedule = (
        trail_profile is None
        and long_w is not None
        and easy_vs_long_ratio <= MAX_EASY_VS_LONG_RUN - 0.01
    )
    if low_frequency_schedule:
        from app.core.training.tuning import MAX_KEY_WORKOUT_VS_LONG_RUN

        deficit = round(total_km - sum(w.get("distance", 0) for w in workouts), 1)
        quality_ceiling = round(
            long_w.get("distance", 0) * MAX_KEY_WORKOUT_VS_LONG_RUN, 1
        )
        carriers = [
            w
            for w in workouts
            if w.get("type") in ("tempo", "interval", "hill")
            and w.get("key_workout_id")
            and not w.get("fixed_structure")
            and 0 < (w.get("distance") or 0) < quality_ceiling
        ]
        if deficit > 0 and carriers:
            per_carrier = deficit / len(carriers)
            for w in carriers:
                set_distance(
                    w, min(w["distance"] + per_carrier, quality_ceiling), pace_zones
                )

    return round(sum(w.get("distance", 0) for w in workouts), 1)


def enforce_long_run_ratio_cap(
    workouts: List[Dict[str, Any]],
    phase: str,
    training_terrain: Optional[str] = None,
    trail_profile=None,
    max_ratio: float = 0.55,
    min_runs_for_cap: int = 2,
    pace_zones: Optional[Dict] = None,
    max_runs: Optional[int] = None,
) -> float:
    """Cap long-run dominance for practical weekly distribution.

    Applies on 2+ running-day weeks. On 4+ run weeks excess long-run distance
    is redistributed to the (capped) easy runs. On low-frequency weeks (2-3
    runs) there is often no easy run to receive it — the week is one long plus
    one quality session — so the excess is simply trimmed: the week falls a
    little short of its volume target rather than carrying a long run that is
    85-90 % of the week. The frequency-aware ceiling (looser for 2-run weeks,
    which are inherently long-run-centric) comes from
    ``get_weekly_long_run_ratio_cap``.
    """
    running = [
        w
        for w in workouts
        if w.get("type") not in ("rest", "recovery") and (w.get("distance", 0) or 0) > 0
    ]
    if len(running) < min_runs_for_cap:
        return round(sum(w.get("distance", 0) for w in workouts), 1)

    long_ws = [w for w in running if w.get("type") == "long"]
    if not long_ws:
        return round(sum(w.get("distance", 0) for w in workouts), 1)
    long_w = long_ws[0]

    # A fixed-structure long slot — a backyard loop simulation — is a whole
    # number of hourly loops, not a share of the week. It is *meant* to
    # dominate its week; trimming it to a ratio would leave the card promising
    # six loops while the distance describes five and a half.
    if long_w.get("fixed_structure"):
        return round(sum(w.get("distance", 0) for w in workouts), 1)

    total = sum(w.get("distance", 0) for w in running)
    if total <= 0:
        return round(sum(w.get("distance", 0) for w in workouts), 1)

    effective_max_ratio = max_ratio
    if trail_profile is not None:
        effective_max_ratio = long_run_calculator.get_weekly_long_run_ratio_cap(
            phase,
            trail_profile=trail_profile,
            training_terrain=training_terrain,
        )
    elif max_runs is not None:
        effective_max_ratio = long_run_calculator.get_weekly_long_run_ratio_cap(
            phase,
            training_terrain=training_terrain,
            max_runs=max_runs,
        )

    max_long = total * effective_max_ratio
    long_d = long_w.get("distance", 0)
    if long_d <= max_long + 0.05:
        return round(sum(w.get("distance", 0) for w in workouts), 1)

    excess = long_d - max_long
    set_distance(long_w, max_long, pace_zones)

    recipients = [w for w in running if w is not long_w and w.get("type") == "easy"]
    if not recipients:
        recipients = [w for w in running if w is not long_w]
    if recipients:
        per = excess / len(recipients)
        for w in recipients:
            set_distance(w, w.get("distance", 0) + per, pace_zones)

    long_after = long_w.get("distance", 0)
    for w in workouts:
        if w.get("type") == "easy" and w.get("distance", 0) > long_after:
            set_distance(w, long_after, pace_zones)

    return round(sum(w.get("distance", 0) for w in workouts), 1)


# --- Final long-run contract passes -----------------------------------------
#
# These run after every other budget pass, so the ceilings below are the last
# word on the week's long run. They are needed because three independent
# mechanisms move it *after* ``enforce_long_run_ratio_cap`` has capped it:
#
# * ``fill_shortfall`` inflates a *flexible* long run to place the week's
#   volume — but only in weeks whose flexible slots fall below 97 % of target,
#   so a week that happens to clear that threshold keeps a ratio-sized long run
#   while its neighbour is inflated (measured: 17.8 km then 15.8 km on a 50 km
#   base half marathon, an 11 % regression between loading weeks);
# * ``set_distance`` routes a *pinned* long run through ``rebuild_key_workout``,
#   which restores the prescription — silently undoing the cap;
# * ``reclamp_quality_to_long_run`` shrinks the quality day, which *raises* the
#   long run's share of the week.
#
# Road only: a trail plan's back-to-back long days are governed by the bracket
# cap and the Intensive Training Weekend, and these passes are written for the
# road per-run ceilings.


def _resizable_long_run(
    workouts: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """The week's long run, or ``None`` when it must not be resized.

    A ``fixed_structure`` long slot is a backyard loop simulation: a whole
    number of hourly loops, not a share of the week (see
    ``enforce_long_run_ratio_cap``).
    """
    for w in workouts:
        if w.get("type") == "long" and (w.get("distance") or 0) > 0:
            if w.get("fixed_structure"):
                return None
            return w
    return None


def _running_total_km(workouts: List[Dict[str, Any]]) -> float:
    """The week's running volume, on the same basis the ratio cap uses."""
    return round(
        sum(
            w.get("distance", 0)
            for w in workouts
            if w.get("type") not in ("rest", "recovery")
        ),
        1,
    )


def _resize_long_run(
    workout: Dict[str, Any],
    distance: float,
    pace_zones: Optional[Dict],
) -> None:
    """Resize a long run, including one that a key-workout overlay pins.

    ``set_distance`` deliberately routes a key-workout long run through
    ``rebuild_key_workout``, whose job is to re-derive the prescription from the
    new distance — so a cap that *shrinks* it comes back at its original length
    (measured: a half-marathon plan's peak week held a 15.3 km long run where
    the 55 % share ceiling allowed 14.85 km). Clearing the overlay first is what
    makes the cap take effect; the session becomes a plain long run at the
    capped distance, which is the session the runner is actually being asked to
    run.
    """
    if workout.get("key_workout_id") or workout.get("fixed_structure"):
        for key in [k for k in workout if k.startswith("key_workout")]:
            workout.pop(key, None)
        workout.pop("fixed_structure", None)
    rebuild_long_run(workout, distance, pace_zones)


def enforce_long_run_progression_floor(
    workouts: List[Dict[str, Any]],
    prev_long_run_km: Optional[float],
    pace_zones: Optional[Dict] = None,
    tolerance: float = 0.02,
) -> float:
    """Stop a loading week's long run regressing below the previous one.

    ``calculate_long_run_distance`` bounds how fast the long run may *grow* but
    nothing bounds how far it may *fall*, and two mechanisms drop it mid-block
    (see the section comment above). Neither drop is a legitimate drawdown: the
    weekly total is still ramping up, so a shrinking long run is a shape fault,
    not a deload — which is why the envelope harness reads it as a progression
    fault. The contract and share caps that run after this one still win.
    """
    long_w = _resizable_long_run(workouts)
    if not prev_long_run_km or prev_long_run_km <= 0 or long_w is None:
        return _running_total_km(workouts)
    floor = round(prev_long_run_km * (1 - tolerance), 1)
    if (long_w.get("distance") or 0) < floor:
        _resize_long_run(long_w, floor, pace_zones)
    return _running_total_km(workouts)


def enforce_contract_long_run_cap(
    workouts: List[Dict[str, Any]],
    target_distance: float,
    experience_level: str,
    trail_profile=None,
    pace_zones: Optional[Dict] = None,
) -> float:
    """Hold the long run to its contracted cap at the volume actually delivered.

    ``fill_shortfall`` sizes its spill cap from the week's *target*
    (``weekly_km=total_km``), and ``long_run_cap`` is volume-aware — so a target
    the layout cannot reach inflates the cap that then governs the delivered
    long run. Measured: a half-marathon plan targeting 66 km a week delivered 55
    and carried a 19.8 km long run against a contract cap of 19.0 at the volume
    it delivered. The surplus is spilled to the easy runs while they have
    headroom and dropped otherwise, exactly as ``fill_shortfall`` does.
    """
    long_w = _resizable_long_run(workouts)
    if long_w is None:
        return _running_total_km(workouts)
    cap = long_run_calculator.long_run_cap(
        target_distance,
        experience_level,
        weekly_km=_running_total_km(workouts),
        trail_profile=trail_profile,
    )
    current = long_w.get("distance") or 0
    if cap <= 0 or current <= cap + 0.05:
        return _running_total_km(workouts)

    excess = round(current - cap, 1)
    _resize_long_run(long_w, cap, pace_zones)
    easy_runs = [
        w for w in workouts if w.get("type") == "easy" and (w.get("distance") or 0) > 0
    ]
    if easy_runs:
        wk_km = _running_total_km(workouts)
        limit = easy_run_cap(cap, volume_scaled_easy_cap(wk_km))
        per_easy = excess / len(easy_runs)
        for w in easy_runs:
            set_distance(w, min((w.get("distance") or 0) + per_easy, limit), pace_zones)
    return _running_total_km(workouts)


def enforce_long_run_share_cap(
    workouts: List[Dict[str, Any]],
    phase: str,
    training_terrain: Optional[str] = None,
    trail_profile=None,
    max_runs: Optional[int] = None,
    pace_zones: Optional[Dict] = None,
) -> float:
    """Last word on the long run's share of its own week.

    ``enforce_long_run_ratio_cap`` applies the same ceiling earlier, but a
    pinned long run escapes it (``set_distance`` → ``rebuild_key_workout``
    restores the prescription) and ``reclamp_quality_to_long_run`` can raise the
    share afterwards by shrinking the quality day. Applying the ceiling last is
    what makes it hold. As at low frequency, the excess is *dropped* rather than
    redistributed: a slightly short week is a better answer than a second long
    effort.
    """
    long_w = _resizable_long_run(workouts)
    if long_w is None:
        return _running_total_km(workouts)
    total = _running_total_km(workouts)
    if total <= 0:
        return total
    ceiling = long_run_calculator.get_weekly_long_run_ratio_cap(
        phase,
        trail_profile=trail_profile,
        training_terrain=training_terrain,
        max_runs=max_runs,
    )
    # Solve against the *rest* of the week, not the pre-clamp total. The excess
    # is dropped rather than redistributed, so shrinking the long run shrinks the
    # denominator too: capping the long run at ``ceiling * total`` leaves the
    # share above the ceiling (measured: 12.4 km against a 6.1 km quality day is
    # a 0.67 share where 0.60 was asked for). ``L / (L + rest) <= ceiling``
    # rearranges to ``L <= ceiling * rest / (1 - ceiling)``. The result is
    # floored to the 0.1 km plans are stored in, because rounding *up* breaches
    # the ceiling on small weeks (3.7 / 6.1 = 0.607 against 0.60).
    rest = round(
        sum(
            w.get("distance", 0)
            for w in workouts
            if w.get("type") not in ("rest", "recovery", "long")
        ),
        1,
    )
    max_long = _floor_to_100m(ceiling * rest / (1 - ceiling)) if ceiling < 1 else rest
    if (long_w.get("distance") or 0) > max_long + 0.05:
        _resize_long_run(long_w, max_long, pace_zones)
    return _running_total_km(workouts)


def _floor_to_100m(value: float) -> float:
    """Round a distance *down* to the 0.1 km granularity plans are stored in.

    Used for ceilings, not targets: rounding a cap to the nearest 0.1 km can
    push the result back over it on small weeks (a 2-run week's 3.66 km cap
    rounds to 3.7, which is 0.607 of a 6.1 km week against a 0.60 ceiling).
    """
    return int(value * 10) / 10
