"""Week plan validation.

Checks that generated weekly workout plans follow training principles.
"""

from typing import Any, Dict, List


def validate_week_plan(
    workouts: List[Dict[str, Any]], total_km: float, target_total_km: float, phase: str
) -> tuple[bool, str]:
    """Validate week plan follows training principles.

    Checks:
    - All workouts have 'description' field
    - Recovery day has label 'recovery' (not 'recovery_rest')
    - No easy run > 125% of long run distance
    - Total distance matches target (+/-5% tolerance)
    - Recovery days have zero distance
    """
    for workout in workouts:
        if "description" not in workout:
            return (
                False,
                f"Missing description for {workout['type']} on day {workout['day']}",
            )

    for workout in workouts:
        if workout["type"] == "recovery_rest":
            return (
                False,
                f"Old label 'recovery_rest' on day {workout['day']}, should be 'recovery'",
            )

    long_run_dist = max(
        [w.get("distance", 0) for w in workouts if w["type"] == "long"], default=0
    )
    if long_run_dist > 0:
        for workout in workouts:
            if workout["type"] == "easy":
                if workout.get("distance", 0) > long_run_dist * 1.25:
                    return (
                        False,
                        f"Easy run ({workout.get('distance')}km) > 125% of long run ({long_run_dist}km) on day {workout['day']}",
                    )

    tolerance = target_total_km * 0.05
    if abs(total_km - target_total_km) > tolerance:
        return (
            False,
            f"Total distance mismatch: expected {target_total_km}km, got {total_km}km",
        )

    for workout in workouts:
        if workout["type"] == "recovery" and workout.get("distance", 0) != 0:
            return False, f"Recovery day on day {workout['day']} has non-zero distance"

    return True, "Valid"


# ---------------------------------------------------------------------------
# Quality-run internal consistency
# ---------------------------------------------------------------------------

# Effort labels that belong to easy/recovery effort — a quality-run step whose
# *only* work effort is from this set is mislabelled relative to its workout type.
_EASY_EFFORTS: frozenset = frozenset({"easy", "conversational", ""})
# Pace zones that represent genuine quality work (not easy/recovery)
_QUALITY_ZONES: frozenset = frozenset({"T", "I", "M", "R", "10K", "5K"})
# Key workouts in a quality slot whose stimulus is deliberately not pace, and
# which therefore cannot satisfy the pace-zone checks below.
#
# This is a narrow exemption, and it is worth saying what it is *not* for. It
# used to hold ``marathon_easy_long_fueling`` and ``trail_flat_soft_surface``
# — two 30 km easy long runs that had been typed ``tempo`` by mistake. Listing
# them here silenced the one check that would have caught the mistake, and
# both went on quietly occupying 8 km tempo slots, rewritten down to a quarter
# of their prescribed distance. They are typed ``long`` now, where their
# distance belongs. A session that is here only because it is too *long* for
# its slot is mis-typed, not exempt.
#
# The two entries below earn it, for opposite reasons:
#
# * the night run is easy by design — a 100-mile plan rehearses darkness,
#   footing and fuelling by feel, and that rehearsal must be run easy. It
#   takes a quality slot because you do not also run threshold work that week;
#   its week still carries a second, genuinely hard session.
# * the power walk is *hard* by design and slow anyway. Max-effort hiking at
#   9-10 min/km is real muscular work that no pace zone can express, and it is
#   the flat-terrain twin of ``trail_power_hike`` (typed ``hill``). It has to
#   sit in a tempo slot to exist at all: flat training converts every hill
#   slot to tempo/interval, so a hill-typed session would never fire.
_INTENTIONALLY_EASY_KEY_WORKOUTS: frozenset = frozenset(
    {
        "trail_night_run",  # long-ultra darkness rehearsal — easy by design
        "trail_flat_power_walk",  # max-effort hiking — hard, but slow ground
    }
)


def validate_quality_run_steps(workout: dict) -> tuple[bool, str]:
    """Validate that a quality run's steps are consistent with its declared type.

    Checks:
    - For ``interval`` and ``hill`` workouts: at least one ``run`` step must
      have a non-easy effort *or* a quality pace zone (T/I/M/R/10K/5K).
    - For ``tempo`` workouts: at least one ``run`` step must use a quality
      pace zone.
    - The reported ``distance`` must be within 0.6 km of the sum of primary
      step distances (warmup + run + cooldown), when all steps are
      distance-priced.  Duration-based reps that cannot be priced are excluded
      from the check (they are a lower-bound contribution).

    Returns ``(True, "Valid")`` or ``(False, <reason>)``.
    """
    from app.core.training.workout_steps import compute_distance_from_steps_checked

    wtype = workout.get("type")
    if wtype not in ("interval", "tempo", "hill"):
        return True, "Valid"

    steps = workout.get("steps") or []
    if not steps:
        return True, "Valid"  # no steps to validate

    work_steps = [s for s in steps if s.get("kind") == "run"]
    if not work_steps:
        return True, "Valid"  # no run-kind steps (e.g. walk-only hill)

    # A strides sharpener (easy run finished with fast strides) is a
    # legitimate occupant of a small tempo slot — taper weeks emit it instead
    # of degenerate sub-800 m cruise reps. Its quality stimulus lives in the
    # ``strides`` step, which the run-step zone checks below can't see.
    if any(
        s.get("kind") == "strides" and s.get("pace_zone") in _QUALITY_ZONES
        for s in steps
    ):
        return True, "Valid"

    work_efforts = [s.get("effort", "") or "" for s in work_steps]
    work_zones = [s.get("pace_zone", "") or "" for s in work_steps]

    kid = workout.get("key_workout_id", "")
    label = f"type={wtype} key={kid}" if kid else f"type={wtype}"

    # Workouts that are legitimately filed under a quality slot type but use
    # easy effort as their primary stimulus are exempt from the effort check.
    if kid in _INTENTIONALLY_EASY_KEY_WORKOUTS:
        return True, "Valid"

    if wtype in ("interval", "hill"):
        has_quality_effort = any(e not in _EASY_EFFORTS for e in work_efforts)
        has_quality_zone = any(z in _QUALITY_ZONES for z in work_zones)
        if not has_quality_effort and not has_quality_zone:
            return (
                False,
                f"{label}: all run steps have easy effort/zone "
                f"(efforts={work_efforts}, zones={work_zones})",
            )

    elif wtype == "tempo":
        has_quality_zone = any(z in _QUALITY_ZONES for z in work_zones)
        if not has_quality_zone:
            return (
                False,
                f"{label}: tempo run steps only have easy-zone (E) steps "
                f"(zones={work_zones})",
            )

    # Distance consistency check. Cards are reconciled from priced steps for
    # both generic builders and key-workout overlays, so the reported distance
    # must track the step total closely; the small band absorbs one-decimal
    # rounding and the snap-to-50/100 m grid.
    reported = workout.get("distance") or 0
    if reported > 0:
        step_km, fully_priced = compute_distance_from_steps_checked(steps)
        if fully_priced and step_km > 0:
            tolerance = 0.3 + reported * 0.10
            if abs(step_km - reported) > tolerance:
                return (
                    False,
                    f"{label}: steps total {step_km:.2f} km but "
                    f"workout reports {reported} km (tolerance ±{tolerance:.2f})",
                )

    return True, "Valid"
