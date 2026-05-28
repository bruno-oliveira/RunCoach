"""Completion stats, adjustment hints, and next-plan CTA."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan

if TYPE_CHECKING:
    from app.contexts.plan.adaptation import AdaptationService

logger = logging.getLogger(__name__)

_NEXT_PLAN_MAP: dict[float, dict[str, str]] = {
    5.0: {
        "label": "10K",
        "url": "/?target_distance=10",
        "message": "Ready to double the distance? Take on the 10K.",
    },
    10.0: {
        "label": "Half Marathon",
        "url": "/?target_distance=21.1",
        "message": "You've got the base. The Half Marathon is your next big step.",
    },
    21.1: {
        "label": "Marathon",
        "url": "/?target_distance=42.2",
        "message": "Go the full distance. You're ready for the Marathon.",
    },
    42.2: {
        "label": "Trail Running",
        "url": "/?target_distance=30",
        "message": "Take your fitness off-road with a Trail Running plan.",
    },
    30.0: {
        "label": "Marathon",
        "url": "/?target_distance=42.2",
        "message": "Bring your trail strength to the road with a Marathon plan.",
    },
}


def get_adjustment_hints(
    training_plan: TrainingPlan,
    performance_analysis: dict,
    db: Session,
    adaptation_service: AdaptationService | None = None,
) -> dict[str, Any]:
    if adaptation_service is None:
        from app.contexts.plan.adaptation import AdaptationService

        adaptation_service = AdaptationService()

    skipped_count = 0
    rescheduled_count = 0
    needs_adjustment = False
    avg_effort = performance_analysis.get("avg_effort")

    if training_plan.start_date:
        try:
            since = training_plan.last_adjusted_at
            skip_result = adaptation_service.detect_skipped_workouts(
                training_plan.id,
                db,
                since=since,
            )
            skipped_count = skip_result["skipped"]
            rescheduled_count = skip_result["rescheduled"]

            effort_extreme = False
            if avg_effort is not None and not since:
                effort_extreme = avg_effort >= 8 or avg_effort <= 3
            elif since:
                recent_runs = (
                    db.query(RunLog.perceived_effort)
                    .filter(
                        RunLog.training_plan_id == training_plan.id,
                        RunLog.perceived_effort.isnot(None),
                        RunLog.date > since,
                    )
                    .all()
                )
                if len(recent_runs) >= 3:
                    recent_avg = sum(r[0] for r in recent_runs) / len(recent_runs)
                    effort_extreme = recent_avg >= 8 or recent_avg <= 3

            needs_adjustment = skipped_count >= 2 or effort_extreme
        except Exception as e:
            logger.warning(f"Could not detect skipped workouts: {e}")

    return {
        "skipped_count": skipped_count,
        "rescheduled_count": rescheduled_count,
        "needs_adjustment": needs_adjustment,
    }


def get_completion_stats(
    training_plan: TrainingPlan,
    db: Session,
) -> dict[str, Any]:
    runs = db.query(RunLog).filter(RunLog.training_plan_id == training_plan.id).all()

    if not runs:
        return {"has_data": False}

    distances = [r.distance_km for r in runs if r.distance_km]
    total_km = sum(distances) if distances else 0
    longest_run = max(distances) if distances else 0

    paces = [r.avg_pace_min_km for r in runs if r.avg_pace_min_km]
    best_pace = min(paces) if paces else None

    efforts = [r.perceived_effort for r in runs if r.perceived_effort]
    avg_effort = round(sum(efforts) / len(efforts), 1) if efforts else None

    plan_data = training_plan.plan_data if training_plan.plan_data else []
    peak_km = max((w.get("total_km", 0) for w in plan_data), default=0)

    return {
        "has_data": bool(distances),
        "total_km": round(total_km, 1),
        "total_runs": len(runs),
        "longest_run_km": round(longest_run, 1),
        "best_pace_min_km": best_pace,
        "avg_effort": avg_effort,
        "start_km_per_week": training_plan.current_weekly_km,
        "peak_km_per_week": round(peak_km, 1),
    }


def get_next_plan_cta(target_distance_km: float) -> dict[str, str]:
    return _NEXT_PLAN_MAP.get(
        target_distance_km,
        {
            "label": "New Plan",
            "url": "/",
            "message": "Keep the momentum going -- start your next training plan.",
        },
    )
