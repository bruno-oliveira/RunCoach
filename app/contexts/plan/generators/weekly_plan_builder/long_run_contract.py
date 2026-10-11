"""The road long run's final contract, settled once the week is fitted.

By the time this runs the week has been scaled to its budget and its long run
clamped to the ratio and time ceilings. What is left is the long run's
*contract* — the promises it makes across weeks and within its own — and the
order they are settled in is the order of their authority:

1. the cross-week **progression floor** and the **contract cap**;
2. the cross-week **growth clamp**;
3. at ≤ 2 runs, the **low-frequency fill**, which may grow the long run and
   the single quality session back toward a target the caps left unmet;
4. the **share cap**, the true last word on the long run's share of its week;
5. the **contract cap** again, at the volume the passes above finally left.

Road only. A trail plan's long days are governed by the bracket cap and the
ITW, a backyard's by its simulation ladder.
"""

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.workout_scaler import (
    _floor_to_100m,
    _resizable_long_run,
    _resize_long_run,
    enforce_contract_long_run_cap,
    enforce_long_run_progression_floor,
    enforce_long_run_share_cap,
    reclamp_quality_to_long_run,
    set_distance,
)
from app.core.training.periodization import long_run_calculator
from app.core.training.tuning import (
    LONG_RUN_GROWTH_ABS_KM,
    LONG_RUN_GROWTH_PCT,
    MAX_WORK_ABS_KM_BY_ZONE,
    MAX_WORK_SHARE_BY_ZONE,
    WORK_ZONE_GROUP,
)

# How far a formulaic quality session may be scaled up in one step when the
# low-frequency fill grows it toward its work-set cap.
MAX_QUALITY_GROWTH_SCALE = 1.4

# At ≤ 3 runs the final contract cap never takes the long run below this
# fraction of the previous loading week's: a 10 %+ single-step drop is the
# worse fault there.
MATERIAL_LONG_RUN_DROP = 0.90


def settle_road_long_run(
    workouts: List[Dict[str, Any]],
    *,
    phase: str,
    terrain: Optional[str],
    target_distance: float,
    total_km: float,
    experience_level: str,
    max_runs_per_week: int,
    is_recovery: bool,
    prev_long_run_km: Optional[float],
    pace_zones: Optional[Dict],
) -> None:
    """Settle the long run against every cross-week and in-week promise (in place).

    Restores the cross-week progression shape first, then re-asserts the
    ceilings the fitting passes cannot guarantee on their own — and which
    ``reclamp_quality_to_long_run`` has just perturbed by shrinking the
    quality day.
    """
    if not is_recovery:
        enforce_long_run_progression_floor(
            workouts, prev_long_run_km, pace_zones=pace_zones
        )
    enforce_contract_long_run_cap(
        workouts,
        target_distance,
        experience_level,
        pace_zones=pace_zones,
        max_runs=max_runs_per_week,
    )

    growth_ceiling_km = _long_run_growth_ceiling(prev_long_run_km, is_recovery)
    _clamp_long_run_growth(workouts, growth_ceiling_km, pace_zones)

    if max_runs_per_week is not None and max_runs_per_week <= 2 and not is_recovery:
        _fill_low_frequency_long_run(
            workouts,
            phase=phase,
            target_distance=target_distance,
            total_km=total_km,
            experience_level=experience_level,
            max_runs_per_week=max_runs_per_week,
            growth_ceiling_km=growth_ceiling_km,
            pace_zones=pace_zones,
        )
        _grow_low_frequency_quality(workouts, total_km, pace_zones)

    # The share cap is the true last word: it runs after the progression
    # floor, the contract cap, the growth clamp and the low-frequency fill,
    # so no pass above can leave the long run over its share of the week.
    enforce_long_run_share_cap(
        workouts,
        phase,
        terrain,
        max_runs=max_runs_per_week,
        pace_zones=pace_zones,
        target_km=total_km,
        target_distance=target_distance,
        experience_level=experience_level,
    )
    # ... and the contract cap re-asserts itself after that: the reclamps
    # above shrink the quality day, which lowers the week's delivered
    # volume and with it the volume-aware cap the contract solves for —
    # a long run legal at the pre-clamp volume can sit past the cap at
    # the final one (measured: 12.9 km against a 12.2 cap on a 5K week).
    # It runs after the final reclamp (so no later pass shrinks the week
    # under it). At ≤ 3 runs it never takes the long run below the previous
    # loading week's minus the material-drop tolerance: there the volume
    # cap and the cross-week progression floor genuinely conflict (a 2-run
    # week's volume swings with its single partner), and a 10 %+ single-
    # step long-run drop is the worse fault. At 4+ runs the volume cap
    # rules — protecting the long there let loading-week longs ratchet
    # past the published band (a 19 km long run for a 10K).
    contract_floor_km = (
        round(prev_long_run_km * MATERIAL_LONG_RUN_DROP, 1)
        if (
            not is_recovery
            and prev_long_run_km
            and max_runs_per_week is not None
            and max_runs_per_week <= 3
        )
        else None
    )
    reclamp_quality_to_long_run(workouts)
    enforce_contract_long_run_cap(
        workouts,
        target_distance,
        experience_level,
        pace_zones=pace_zones,
        max_runs=max_runs_per_week,
        floor_km=contract_floor_km,
    )
    # The contract pass may have shrunk the long run below what the
    # quality sessions were fitted against — refit them so the step list
    # never promises more than the card says.
    reclamp_quality_to_long_run(workouts)


def _long_run_growth_ceiling(
    prev_long_run_km: Optional[float], is_recovery: bool
) -> Optional[float]:
    """The furthest this week's long run may step past the previous one.

    ``max(+18%, +3 km)`` over the previous loading week's long run — the same
    ceiling ``calculate_long_run_distance`` enforces at sizing time. ``None``
    on a deload, or when there is no previous long run to step from.
    """
    if is_recovery or not prev_long_run_km:
        return None
    return max(
        prev_long_run_km * LONG_RUN_GROWTH_PCT,
        prev_long_run_km + LONG_RUN_GROWTH_ABS_KM,
    )


def _clamp_long_run_growth(
    workouts: List[Dict[str, Any]],
    growth_ceiling_km: Optional[float],
    pace_zones: Optional[Dict],
) -> None:
    """Long-run growth clamp (audit G3).

    ``fill_shortfall`` and the fitting passes can grow the long run past the
    cross-week growth ceiling that was enforced at sizing time — a +31-41%
    single-step jump in the longest, highest-risk session. Clamped before the
    low-frequency fill, so the fill's growth is bounded by the same ceiling
    instead of being cut by it after the fact.
    """
    if growth_ceiling_km is None:
        return
    long_run = _resizable_long_run(workouts)
    if long_run is None:
        return
    if (long_run.get("distance") or 0) > growth_ceiling_km + 0.05:
        _resize_long_run(long_run, growth_ceiling_km, pace_zones)


def _fill_low_frequency_long_run(
    workouts: List[Dict[str, Any]],
    *,
    phase: str,
    target_distance: float,
    total_km: float,
    experience_level: str,
    max_runs_per_week: int,
    growth_ceiling_km: Optional[float],
    pace_zones: Optional[Dict],
) -> None:
    """Low-frequency final fill: let the long run take what its partner left.

    After every cap has had its word, a ≤2-run week may still sit below its
    target because the single quality partner is physiologically capped
    (Daniels work-share, per-distance caps) and nothing re-grows the long run
    *after* the caps spoke. The long run takes what the capped partner leaves
    of the target, bounded by its contracted cap and — so the fill never
    manufactures the very session-spike the growth clamp exists to prevent —
    by the cross-week growth ceiling when one applies. The plan-level 10% pass
    still bounds the week-over-week total.
    """
    long_run = _resizable_long_run(workouts)
    if long_run is None:
        return
    rest_km = round(
        sum(
            w.get("distance", 0) or 0
            for w in workouts
            if w.get("type") not in ("rest", "recovery", "long")
        ),
        1,
    )
    volume_bound = _floor_to_100m(
        long_run_calculator.long_run_cap(
            target_distance,
            experience_level,
            weekly_km=total_km,
            max_runs=max_runs_per_week,
        )
    )
    # The share ceiling still rules: the grown pair must satisfy
    # long / (long + rest) <= the frequency ceiling, i.e.
    # long <= ceiling * rest / (1 - ceiling).
    share_ceiling = long_run_calculator.get_weekly_long_run_ratio_cap(
        phase, max_runs=max_runs_per_week
    )
    share_bound = (
        _floor_to_100m(share_ceiling * rest_km / (1 - share_ceiling))
        if share_ceiling < 1
        else rest_km
    )
    desired = min(total_km - rest_km, volume_bound, share_bound)
    if growth_ceiling_km is not None:
        desired = min(desired, growth_ceiling_km)
    current = long_run.get("distance") or 0
    if desired > current + 0.1:
        _resize_long_run(long_run, desired, pace_zones)
        # The quality day must stay subordinate to the grown long run (its
        # phys caps were computed against the old value).
        reclamp_quality_to_long_run(workouts)


def _grow_low_frequency_quality(
    workouts: List[Dict[str, Any]], total_km: float, pace_zones: Optional[Dict]
) -> None:
    """Grow a collapsed week's formulaic quality session toward its work cap.

    The transition into build at 2 runs swaps the easy slot for a quality
    slot, and the formulaic quality session is sized from the week's
    (reachable-capped) target through the Daniels work-share — which is
    computed against the week's *volume*. A collapsed week therefore permits
    only a tiny interval, which keeps the week collapsed: a self-reinforcing
    fixed point (measured: 11.4 km in a 16.5 km week at the base→build
    boundary). Grow the single formulaic quality slot toward its physiological
    cap computed at the week's TARGET volume, breaking the loop; the
    plan-level 10% pass still bounds the weekly total.
    """
    for workout in workouts:
        if workout.get("type") not in ("tempo", "interval", "hill"):
            continue
        if workout.get("key_workout_id") or workout.get("fixed_structure"):
            continue
        distance = workout.get("distance") or 0
        if distance <= 0:
            continue

        steps = workout.get("steps") or []
        work_km = (
            sum(
                (s.get("distance_m") or 0) * s.get("repeat", 1)
                for s in steps
                if s.get("kind") in ("run", "walk", "strides")
                and s.get("pace_zone") in WORK_ZONE_GROUP
            )
            / 1000.0
        )
        zone = next(
            (
                s.get("pace_zone")
                for s in steps
                if s.get("pace_zone") in WORK_ZONE_GROUP
            ),
            None,
        )
        if zone is None or work_km <= 0:
            continue
        group = WORK_ZONE_GROUP[zone]
        work_cap_target = min(
            MAX_WORK_ABS_KM_BY_ZONE.get(group, 99.0),
            MAX_WORK_SHARE_BY_ZONE.get(group, 1.0) * total_km,
        )
        if work_km >= work_cap_target - 0.05:
            continue
        # Scale the session up so its work set reaches the cap the target
        # volume allows; bookends grow proportionally.
        scale = min(MAX_QUALITY_GROWTH_SCALE, work_cap_target / work_km)
        set_distance(workout, round(distance * scale, 1), pace_zones)
