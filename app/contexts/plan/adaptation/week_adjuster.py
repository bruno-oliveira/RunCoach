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

    # Pace zones for regenerating adapted key workouts with their specific
    # paces preserved (falls back to generic labels when VDOT is unknown).
    pace_zones: Optional[Dict[str, Any]] = None
    if training_plan.vdot:
        try:
            pace_zones = VDOTCalculator.get_pace_zones(training_plan.vdot)
        except Exception:  # pragma: no cover - defensive; never block adjust
            pace_zones = None

    workouts_by_week = batch_workouts_by_week([week.id for week in future_weeks], db)

    weeks_changed = 0
    any_distance_changed = False
    workouts_changed = 0
    workouts_skipped_protected = 0

    future_weeks = sorted(future_weeks, key=lambda w: w.week_number)
    week_by_number = {w.week_number: w for w in future_weeks}

    for week in future_weeks:
        workouts = workouts_by_week.get(week.id, [])
        week_changed = False
        phase = pd_week.get(week.week_number, {}).get("phase", "build")

        for workout in workouts:
            if (
                workout.workout_type == "rest"
                or not workout.distance_km
                or workout.distance_km <= 0
            ):
                continue

            base_distance = workout.baseline_distance_km or workout.distance_km
            rebuilt_plain = False

            wtype = workout.workout_type or "easy"
            type_mult = multiplier
            if per_type_ratios and wtype in per_type_ratios:
                type_ratio = per_type_ratios[wtype]
                type_mult = round(max(PER_TYPE_MIN, min(PER_TYPE_MAX, type_ratio)), 2)

            # Taper is sacrosanct: positive adaptation must never inflate it.
            # A fatigue/overreach signal may still ease it (downward-only), but
            # the multiplier can never scale a taper session above its
            # prescribed distance (audit G2).
            if phase == "taper":
                type_mult = min(type_mult, 1.0)

            note_reason = None
            if workout.workout_type == "long" and type_mult < 1.0:
                new_distance = round(base_distance, 1)
                note_reason = _reasons.LONG_RUN_FLOOR
            elif workout.workout_type in (
                "interval",
                "tempo",
                "hill",
                "vo2max",
                "race_pace",
                "fartlek",
            ):
                quality_mult = 1.0 + (type_mult - 1.0) * QUALITY_HALF_SCALE
                new_distance = max(1.0, round(base_distance * quality_mult, 1))
                note_reason = _reasons.QUALITY_HALF_SCALED
            else:
                new_distance = max(1.0, round(base_distance * type_mult, 1))

            # Belt-and-suspenders cap: even when per-type ratios + trend
            # modifiers slip past the global clamp, never push a single
            # workout above baseline × WORKOUT_CEILING.
            ceiling = round(base_distance * WORKOUT_CEILING, 1)
            if new_distance > ceiling:
                new_distance = ceiling
            old_distance = workout.distance_km

            # Key workouts regenerate from a single distance: rebuild prose,
            # structure and steps at the tentative distance, then adopt the
            # rebuilt steps total as the authoritative new distance. Distance-
            # based sessions track the change; duration-defined ones settle
            # back to their time total and simply won't move.
            pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
            if workout.key_workout_id and pd_wo is not None:
                pd_wo["distance"] = new_distance
                if _kwlib.rebuild_key_workout(pd_wo, pace_zones):
                    new_distance = round(
                        pd_wo.get("distance", new_distance) or new_distance, 1
                    )
            elif workout.workout_type in _PLAIN_QUALITY_TYPES and pd_wo is not None:
                # Builder-generated quality now adapts too: regenerate the
                # session from a single distance (same builder, same day → same
                # variant) so description, steps and distance stay in lockstep —
                # the property that lets key workouts adapt.
                week_total = (pd_week.get(week.week_number) or {}).get(
                    "total_km"
                ) or 0.0
                new_distance = _rebuild_plain_quality(
                    pd_wo,
                    distance=new_distance,
                    day=workout.day_of_week,
                    total_km=week_total,
                    phase=phase,
                    pace_zones=pace_zones,
                )
                rebuilt_plain = True

            if new_distance == old_distance:
                if recorder is not None:
                    recorder.append(
                        {
                            "week": week.week_number,
                            "day": workout.day_of_week,
                            "type": workout.workout_type,
                            "old_distance_km": old_distance,
                            "new_distance_km": new_distance,
                            "delta_km": 0.0,
                            "status": "unchanged",
                            "reason": note_reason,
                        }
                    )
                continue

            workout.distance_km = new_distance
            any_distance_changed = True
            week_changed = True
            workouts_changed += 1

            is_protected = workout.workout_type == "long" and type_mult < 1.0

            if recorder is not None:
                recorder.append(
                    {
                        "week": week.week_number,
                        "day": workout.day_of_week,
                        "type": workout.workout_type,
                        "old_distance_km": old_distance,
                        "new_distance_km": new_distance,
                        "delta_km": round(new_distance - old_distance, 2),
                        "status": "changed",
                        "reason": note_reason,
                    }
                )

            # A rebuilt plain-quality session carries a fresh description; adopt
            # it as the note so the ORM text matches the regenerated card.
            if rebuilt_plain and pd_wo is not None:
                clean_notes = (pd_wo.get("description") or "").strip()
            else:
                clean_notes = ANNOTATION_RE.sub("", workout.notes or "").strip()
            if type_mult != 1.0 and not is_protected:
                adjust_note = f"(Adjusted: x{type_mult})"
                workout.notes = (
                    f"{clean_notes} {adjust_note}".strip()
                    if clean_notes
                    else adjust_note
                )
            else:
                workout.notes = clean_notes or None

            if pd_wo is not None:
                pd_wo["distance"] = new_distance
                # Key workouts already had their steps regenerated by
                # rebuild_key_workout above; only flexible workouts scale.
                if (
                    not workout.key_workout_id
                    and not rebuilt_plain
                    and pd_wo.get("steps")
                    and old_distance
                    and old_distance > 0
                ):
                    step_scale = new_distance / old_distance
                    pd_wo["steps"] = _steps_mod.scale_steps(pd_wo["steps"], step_scale)
                    # Refresh the card-visible prose so a long run's embedded
                    # distances ("first X km / final Y km") track the new
                    # distance instead of going stale. Easy descriptions are
                    # pace-only, so this is a no-op there.
                    week_total = (pd_week.get(week.week_number) or {}).get(
                        "total_km"
                    ) or 0.0
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

        if week_changed and target_distance > 0:
            if enforce_week_structure(
                workouts,
                target_distance,
                phase,
                is_trail=bool(getattr(training_plan, "is_trail", False)),
                target_elevation_gain_m=getattr(
                    training_plan, "target_elevation_gain_m", None
                ),
                training_terrain=getattr(training_plan, "training_terrain", None),
            ):
                week_changed = True

        if week_changed:
            weeks_changed += 1
            new_total = round(sum(w.distance_km for w in workouts if w.distance_km), 1)
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total
                for workout in workouts:
                    pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                    if pd_wo is not None:
                        pd_wo["distance"] = workout.distance_km

    if future_weeks:
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
        changed_weeks = enforce_future_growth_cap(
            [w.week_number for w in future_weeks],
            week_by_number,
            workouts_by_week,
            pd_week,
            high_water_seed=seed,
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
        "workouts_skipped_protected": workouts_skipped_protected,
    }
    return weeks_changed, any_distance_changed, counts
