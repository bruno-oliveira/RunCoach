"""Apply adjustment multiplier to future weeks' workout distances."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.training import key_workout_library as _kwlib
from app.core.training import workout_steps as _steps_mod
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training.workout_registry import build_workout
from app.models import TrainingPlan, WeeklyPlan
from app.utils import persist_json

from . import change_reasons as _reasons
from ._helpers import ANNOTATION_RE, batch_workouts_by_week, parse_plan_data_lookups
from .change_plan_builder import snapshot_workouts
from .reconcile import (
    _PLAIN_QUALITY_TYPES,
    reconcile_plan_data_to_orm,
)
from .reconcile import (
    rebuild_plain_quality as _rebuild_plain_quality,
)
from .safety import enforce_future_growth_cap, enforce_week_structure
from .tuning import (
    PER_TYPE_MAX,
    PER_TYPE_MIN,
    QUALITY_HALF_SCALE,
    WORKOUT_CEILING,
)
from .vdot_recalibrator import check_vdot_recalibration

logger = logging.getLogger(__name__)

# Quality sessions move at half scale (see ``_tentative_distance``).
_QUALITY_TYPES = ("interval", "tempo", "hill", "vo2max", "race_pace", "fartlek")


@dataclass
class ApplyResult:
    """Outputs of the apply-mutation stage of ``_run_adjust``."""

    before: Dict[str, Dict[str, Any]]
    after: Dict[str, Dict[str, Any]]
    weeks_changed: int
    any_distance_changed: bool
    recorder: List[Dict[str, Any]] = field(default_factory=list)
    vdot_result: Optional[Dict[str, Any]] = None


def apply_adjustment_stage(
    training_plan: TrainingPlan,
    adjustable_weeks: List[WeeklyPlan],
    *,
    multiplier: float,
    per_type_ratios: Optional[Dict[str, float]],
    current_week: int,
    current_day_of_week: int,
    user_id: str,
    db: Session,
    week_numbers: List[int],
) -> ApplyResult:
    """Snapshot, apply the multiplier, optionally recalibrate VDOT, snapshot again.

    The VDOT recalibration is wrapped in a try/except so a pace-zone update
    failure cannot block a successful distance adjustment — matching the
    pre-refactor behaviour.

    This helper performs ORM mutations but does NOT commit; the orchestrator
    owns the transaction boundary so applied/preview modes can share the
    same flow and preview can ``db.rollback()`` cleanly.
    """
    before = snapshot_workouts(training_plan, db, week_numbers=week_numbers)

    recorder: List[Dict[str, Any]] = []
    weeks_changed, any_distance_changed, _counts = apply_adjustment_to_future_weeks(
        training_plan,
        adjustable_weeks,
        multiplier,
        db,
        current_week=current_week,
        current_day_of_week=current_day_of_week,
        per_type_ratios=per_type_ratios,
        recorder=recorder,
    )

    vdot_result: Optional[Dict[str, Any]] = None
    try:
        vdot_result = check_vdot_recalibration(training_plan, user_id, db)
    except Exception as e:
        logger.warning("VDOT recalibration failed (non-fatal): %s", e)

    after = snapshot_workouts(training_plan, db, week_numbers=week_numbers)

    return ApplyResult(
        before=before,
        after=after,
        weeks_changed=weeks_changed,
        any_distance_changed=any_distance_changed,
        recorder=recorder,
        vdot_result=vdot_result,
    )


def _resolve_pace_zones(training_plan: TrainingPlan) -> Optional[Dict[str, Any]]:
    """Pace zones for regenerating adapted key workouts with their paces.

    Falls back to ``None`` (generic labels) when VDOT is unknown or lookup
    fails — never blocks an adjustment.
    """
    if not training_plan.vdot:
        return None
    try:
        return VDOTCalculator.get_pace_zones(training_plan.vdot)
    except Exception:  # pragma: no cover - defensive; never block adjust
        return None


def _resolve_type_multiplier(
    workout_type: Optional[str],
    multiplier: float,
    per_type_ratios: Optional[Dict[str, float]],
    phase: str,
) -> float:
    """Per-type multiplier, clamped to bounds and never inflating a taper.

    Taper is sacrosanct: positive adaptation must never inflate it. A
    fatigue/overreach signal may still ease it (downward-only), but the
    multiplier can never scale a taper session above its prescribed distance
    (audit G2).
    """
    wtype = workout_type or "easy"
    type_mult = multiplier
    if per_type_ratios and wtype in per_type_ratios:
        type_ratio = per_type_ratios[wtype]
        type_mult = round(max(PER_TYPE_MIN, min(PER_TYPE_MAX, type_ratio)), 2)
    if phase == "taper":
        type_mult = min(type_mult, 1.0)
    return type_mult


def _tentative_distance(
    workout_type: Optional[str], base_distance: float, type_mult: float
) -> Tuple[float, Optional[str]]:
    """New distance + change reason before key/plain-quality rebuild.

    Long runs hold a floor (never scaled below baseline on a down-adjust),
    quality sessions move at half scale, everything else scales directly. The
    result is capped at ``base_distance × WORKOUT_CEILING`` — a belt-and-
    suspenders guard for when per-type ratios slip past the global clamp.
    """
    note_reason: Optional[str] = None
    if workout_type == "long" and type_mult < 1.0:
        new_distance = round(base_distance, 1)
        note_reason = _reasons.LONG_RUN_FLOOR
    elif workout_type in _QUALITY_TYPES:
        quality_mult = 1.0 + (type_mult - 1.0) * QUALITY_HALF_SCALE
        new_distance = max(1.0, round(base_distance * quality_mult, 1))
        note_reason = _reasons.QUALITY_HALF_SCALED
    else:
        new_distance = max(1.0, round(base_distance * type_mult, 1))

    ceiling = round(base_distance * WORKOUT_CEILING, 1)
    if new_distance > ceiling:
        new_distance = ceiling
    return new_distance, note_reason


def _rebuild_session_distance(
    workout,
    pd_wo: Optional[Dict[str, Any]],
    new_distance: float,
    *,
    week_number: int,
    phase: str,
    pace_zones: Optional[Dict[str, Any]],
    pd_week: Dict[int, Dict[str, Any]],
) -> Tuple[float, bool]:
    """Regenerate key / plain-quality sessions from a single distance.

    Key workouts rebuild prose, structure and steps at the tentative distance,
    then adopt the rebuilt steps total as authoritative. Builder-generated
    plain quality regenerates the same way (same builder, same day → same
    variant) so description, steps and distance stay in lockstep. Returns the
    (possibly adjusted) distance and whether a plain-quality session rebuilt.
    """
    if pd_wo is None:
        return new_distance, False
    if workout.key_workout_id:
        pd_wo["distance"] = new_distance
        if _kwlib.rebuild_key_workout(pd_wo, pace_zones):
            new_distance = round(pd_wo.get("distance", new_distance) or new_distance, 1)
        return new_distance, False
    if workout.workout_type in _PLAIN_QUALITY_TYPES:
        week_total = (pd_week.get(week_number) or {}).get("total_km") or 0.0
        old_distance = round(workout.distance_km or 0.0, 1)
        requested = new_distance
        new_distance = _rebuild_plain_quality(
            pd_wo,
            distance=requested,
            day=workout.day_of_week,
            total_km=week_total,
            phase=phase,
            pace_zones=pace_zones,
        )
        # Rep quantization can make the rebuilt card land back on (or below)
        # the pre-adaptation distance even though the adjuster asked for more —
        # the builder rounds the budget down to whole reps, so a small boost
        # rebuilds to the same rep count and the session never grows. Walk the
        # rebuild target upward past the quantization gap (bounded, so a
        # structurally fixed session like hill repeats just keeps its dose).
        if requested > old_distance > 0:
            bump = requested
            while new_distance <= old_distance and bump < requested + 2.0:
                bump = round(bump + 0.4, 1)
                new_distance = _rebuild_plain_quality(
                    pd_wo,
                    distance=bump,
                    day=workout.day_of_week,
                    total_km=week_total,
                    phase=phase,
                    pace_zones=pace_zones,
                )
        return new_distance, True
    return new_distance, False


def _record_workout(
    recorder: Optional[List[Dict[str, Any]]],
    week_number: int,
    workout,
    old_distance: float,
    new_distance: float,
    status: str,
    note_reason: Optional[str],
) -> None:
    """Append a per-workout change record (no-op when no recorder is supplied)."""
    if recorder is None:
        return
    delta = round(new_distance - old_distance, 2) if status == "changed" else 0.0
    recorder.append(
        {
            "week": week_number,
            "day": workout.day_of_week,
            "type": workout.workout_type,
            "old_distance_km": old_distance,
            "new_distance_km": new_distance,
            "delta_km": delta,
            "status": status,
            "reason": note_reason,
        }
    )


def _sync_workout_notes_and_steps(
    workout,
    pd_wo: Optional[Dict[str, Any]],
    *,
    old_distance: float,
    new_distance: float,
    type_mult: float,
    is_protected: bool,
    rebuilt_plain: bool,
    week_number: int,
    phase: str,
    pace_zones: Optional[Dict[str, Any]],
    pd_week: Dict[int, Dict[str, Any]],
) -> None:
    """Reconcile the ORM notes and plan_data steps/prose after a distance change."""
    # A rebuilt plain-quality session carries a fresh description; adopt it as
    # the note so the ORM text matches the regenerated card.
    if rebuilt_plain and pd_wo is not None:
        clean_notes = (pd_wo.get("description") or "").strip()
    else:
        clean_notes = ANNOTATION_RE.sub("", workout.notes or "").strip()
    if type_mult != 1.0 and not is_protected:
        adjust_note = f"(Adjusted: x{type_mult})"
        workout.notes = (
            f"{clean_notes} {adjust_note}".strip() if clean_notes else adjust_note
        )
    else:
        workout.notes = clean_notes or None

    if pd_wo is None:
        return

    pd_wo["distance"] = new_distance
    # Key workouts already had their steps regenerated by rebuild_key_workout;
    # only flexible workouts scale.
    if (
        not workout.key_workout_id
        and not rebuilt_plain
        and pd_wo.get("steps")
        and old_distance
        and old_distance > 0
    ):
        step_scale = new_distance / old_distance
        pd_wo["steps"] = _steps_mod.scale_steps(pd_wo["steps"], step_scale)
        # Refresh the card-visible prose so a long run's embedded distances
        # ("first X km / final Y km") track the new distance instead of going
        # stale. Easy descriptions are pace-only, so this is a no-op there.
        week_total = (pd_week.get(week_number) or {}).get("total_km") or 0.0
        rebuilt = build_workout(
            workout.workout_type or "easy",
            day=workout.day_of_week,
            distance=new_distance,
            total_km=week_total,
            phase=phase,
            pace_zones=pace_zones,
        )
        if rebuilt.get("description"):
            pd_wo["description"] = rebuilt["description"]
    pd_clean = ANNOTATION_RE.sub(
        "", pd_wo.get("notes", pd_wo.get("description", ""))
    ).strip()
    if type_mult != 1.0 and not is_protected:
        adjust_note = f"(Adjusted: x{type_mult})"
        pd_wo["notes"] = (
            f"{pd_clean} {adjust_note}".strip() if pd_clean else adjust_note
        )
    else:
        pd_wo["notes"] = pd_clean


def _adjust_one_workout(
    workout,
    *,
    multiplier: float,
    per_type_ratios: Optional[Dict[str, float]],
    phase: str,
    pace_zones: Optional[Dict[str, Any]],
    pd_week: Dict[int, Dict[str, Any]],
    pd_workout: Dict[Tuple[int, int], Dict[str, Any]],
    week_number: int,
    recorder: Optional[List[Dict[str, Any]]],
) -> bool:
    """Adjust a single workout's distance in place. Returns True if it changed."""
    if (
        workout.workout_type == "rest"
        or not workout.distance_km
        or workout.distance_km <= 0
    ):
        return False

    pd_wo = pd_workout.get((week_number, workout.day_of_week))
    # Fixed-structure sessions are whole units, not budgets. A backyard loop
    # simulation is "six loops, on the hour" — scaling it by 0.9 would leave
    # the card promising six loops while the distance describes five and a
    # bit, which is not a session anyone can go and run.
    if pd_wo is not None and pd_wo.get("fixed_structure"):
        _record_workout(
            recorder,
            week_number,
            workout,
            workout.distance_km,
            workout.distance_km,
            "protected",
            None,
        )
        return False

    base_distance = workout.baseline_distance_km or workout.distance_km
    type_mult = _resolve_type_multiplier(
        workout.workout_type, multiplier, per_type_ratios, phase
    )
    new_distance, note_reason = _tentative_distance(
        workout.workout_type, base_distance, type_mult
    )
    old_distance = workout.distance_km

    new_distance, rebuilt_plain = _rebuild_session_distance(
        workout,
        pd_wo,
        new_distance,
        week_number=week_number,
        phase=phase,
        pace_zones=pace_zones,
        pd_week=pd_week,
    )

    if new_distance == old_distance:
        _record_workout(
            recorder,
            week_number,
            workout,
            old_distance,
            new_distance,
            "unchanged",
            note_reason,
        )
        return False

    workout.distance_km = new_distance
    is_protected = workout.workout_type == "long" and type_mult < 1.0
    _record_workout(
        recorder,
        week_number,
        workout,
        old_distance,
        new_distance,
        "changed",
        note_reason,
    )
    _sync_workout_notes_and_steps(
        workout,
        pd_wo,
        old_distance=old_distance,
        new_distance=new_distance,
        type_mult=type_mult,
        is_protected=is_protected,
        rebuilt_plain=rebuilt_plain,
        week_number=week_number,
        phase=phase,
        pace_zones=pace_zones,
        pd_week=pd_week,
    )
    return True


def _finalize_week(
    week,
    workouts: List,
    *,
    week_changed: bool,
    phase: str,
    target_distance: float,
    training_plan: TrainingPlan,
    pd_week: Dict[int, Dict[str, Any]],
    pd_workout: Dict[Tuple[int, int], Dict[str, Any]],
) -> bool:
    """Enforce week structure and re-total a changed week. Returns whether changed."""
    if week_changed and target_distance > 0:
        enforce_week_structure(
            workouts,
            target_distance,
            phase,
            is_trail=bool(getattr(training_plan, "is_trail", False)),
            target_elevation_gain_m=getattr(
                training_plan, "target_elevation_gain_m", None
            ),
            training_terrain=getattr(training_plan, "training_terrain", None),
        )

    if not week_changed:
        return False

    new_total = round(sum(w.distance_km for w in workouts if w.distance_km), 1)
    week.total_km = new_total
    if week.week_number in pd_week:
        pd_week[week.week_number]["total_km"] = new_total
        for workout in workouts:
            pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
            if pd_wo is not None:
                pd_wo["distance"] = workout.distance_km
    return True


def _apply_future_growth_cap(
    training_plan: TrainingPlan,
    future_weeks: List,
    week_by_number: Dict[int, Any],
    workouts_by_week: Dict[Any, List],
    pd_week: Dict[int, Dict[str, Any]],
    db: Session,
) -> int:
    """Clamp week-over-week growth across the future weeks. Returns weeks changed."""
    if not future_weeks:
        return 0
    first_future_week = future_weeks[0].week_number
    prev_week = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == training_plan.id,
            WeeklyPlan.week_number < first_future_week,
        )
        .order_by(WeeklyPlan.week_number.desc())
        .first()
    )
    seed = (
        prev_week.total_km
        if prev_week and prev_week.total_km
        else training_plan.current_weekly_km or 0.0
    )
    return enforce_future_growth_cap(
        [w.week_number for w in future_weeks],
        week_by_number,
        workouts_by_week,
        pd_week,
        high_water_seed=seed,
    )


def apply_adjustment_to_future_weeks(
    training_plan: TrainingPlan,
    future_weeks: List,
    multiplier: float,
    db: Session,
    *,
    current_week: int | None = None,
    current_day_of_week: int | None = None,
    per_type_ratios: Optional[Dict[str, float]] = None,
    recorder: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[int, bool, Dict[str, int]]:
    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)
    target_distance = training_plan.target_distance_km
    pace_zones = _resolve_pace_zones(training_plan)

    workouts_by_week = batch_workouts_by_week([week.id for week in future_weeks], db)

    weeks_changed = 0
    any_distance_changed = False
    workouts_changed = 0

    future_weeks = sorted(future_weeks, key=lambda w: w.week_number)
    week_by_number = {w.week_number: w for w in future_weeks}

    for week in future_weeks:
        workouts = workouts_by_week.get(week.id, [])
        phase = pd_week.get(week.week_number, {}).get("phase", "build")
        week_changed = False

        for workout in workouts:
            if _adjust_one_workout(
                workout,
                multiplier=multiplier,
                per_type_ratios=per_type_ratios,
                phase=phase,
                pace_zones=pace_zones,
                pd_week=pd_week,
                pd_workout=pd_workout,
                week_number=week.week_number,
                recorder=recorder,
            ):
                week_changed = True
                any_distance_changed = True
                workouts_changed += 1

        if _finalize_week(
            week,
            workouts,
            week_changed=week_changed,
            phase=phase,
            target_distance=target_distance,
            training_plan=training_plan,
            pd_week=pd_week,
            pd_workout=pd_workout,
        ):
            weeks_changed += 1

    changed_weeks = _apply_future_growth_cap(
        training_plan, future_weeks, week_by_number, workouts_by_week, pd_week, db
    )
    if changed_weeks > 0:
        weeks_changed += changed_weeks
        any_distance_changed = True

    # Final ORM → JSON re-sync: make plan_data a deterministic projection of
    # the ORM regardless of which mutator last touched the workouts. Shared
    # with the missed-week / recalibration flows so they stay in lockstep.
    reconcile_plan_data_to_orm(
        future_weeks,
        workouts_by_week,
        pd_workout,
        pd_week,
        pace_zones,
    )

    training_plan.plan_data = plan_data
    persist_json(training_plan, "plan_data")
    if any_distance_changed:
        training_plan.adaptation_revision = (training_plan.adaptation_revision or 0) + 1
    counts = {
        "workouts_changed": workouts_changed,
        "workouts_skipped_protected": 0,
    }
    return weeks_changed, any_distance_changed, counts
