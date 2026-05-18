"""Compute volume, effort, completion, and trend signals for plan adjustment."""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import RunLog, RunFeedback
from app.services.adaptation.hr_zone_analyzer import HRZoneAnalyzer
from app.utils import to_date as _to_date

_PHASE_WEIGHTS = {
    "base":   (0.38, 0.18, 0.18, 0.11, 0.07, 0.08),
    "build":  (0.33, 0.20, 0.16, 0.14, 0.09, 0.08),
    "peak":   (0.28, 0.20, 0.16, 0.16, 0.10, 0.10),
    "taper":  (0.10, 0.20, 0.22, 0.22, 0.14, 0.12),
}

_MIN_RUNS_PER_TYPE = 3
_BAYESIAN_SHRINKAGE_PER_RUN = 0.30

_IMPORTANCE_WEIGHTS = {
    "long": 1.5,
    "tempo": 1.3,
    "interval": 1.3,
    "vo2max": 1.3,
    "race_pace": 1.3,
    "hill": 1.2,
    "fartlek": 1.1,
    "easy": 1.0,
    "recovery": 0.5,
}

_CONSECUTIVE_THRESHOLD = 3
_EXPANDED_MIN = 0.70
_EXPANDED_MAX = 1.25
_STANDARD_MIN = 0.85
_STANDARD_MAX = 1.15


def compute_adjustment_signals(
    all_plan_runs: List,
    past_workouts: List[Tuple],
    past_workout_ids: set,
    today,
    plan_id: str,
    db: Session,
    recency_weight_fn,
    *,
    current_phase: str = "build",
    adaptation_history: List[Dict[str, Any]] | None = None,
    hr_zones: Optional[list[dict]] = None,
    run_feedback_list: Optional[List] = None,
    vdot_trend: str = "stable",
    mountain_simulation: Optional[Dict[str, Any]] = None,
    readiness_logs: Optional[List] = None,
    training_load: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    (
        volume_weight,
        effort_weight,
        completion_weight,
        hr_zone_weight,
        feedback_weight,
        readiness_weight,
    ) = _PHASE_WEIGHTS.get(current_phase, _PHASE_WEIGHTS["build"])
    planned_weighted = 0.0
    planned_by_type: Dict[str, float] = defaultdict(float)
    for workout, sched_date in past_workouts:
        w = recency_weight_fn(sched_date)
        dist = workout.baseline_distance_km or workout.distance_km or 0
        wtype = workout.workout_type or "easy"
        importance = _IMPORTANCE_WEIGHTS.get(wtype, 1.0)
        planned_weighted += dist * w * importance
        planned_by_type[wtype] += dist * w * importance

    actual_weighted = 0.0
    actual_by_type: Dict[str, float] = defaultdict(float)
    for run in all_plan_runs:
        run_date = _to_date(run.date) if run.date else today
        w = recency_weight_fn(run_date)
        dist = run.distance_km or 0
        rtype = run.workout_type or "easy"
        importance = _IMPORTANCE_WEIGHTS.get(rtype, 1.0)
        actual_weighted += dist * w * importance
        actual_by_type[rtype] += dist * w * importance

    volume_ratio = max(0.5, min(1.5,
        actual_weighted / planned_weighted if planned_weighted > 0 else 1.0
    ))

    per_type_ratios: Dict[str, float] = {}
    per_type_run_counts: Dict[str, int] = defaultdict(int)
    for run in all_plan_runs:
        rtype = run.workout_type or "easy"
        per_type_run_counts[rtype] += 1

    for wtype in ("easy", "long", "tempo", "interval", "hill"):
        planned = planned_by_type.get(wtype, 0)
        actual = actual_by_type.get(wtype, 0)
        if planned > 0:
            raw_ratio = max(0.5, min(1.5, actual / planned))
            n_runs = per_type_run_counts.get(wtype, 0)
            confidence = min(1.0, n_runs * _BAYESIAN_SHRINKAGE_PER_RUN)
            per_type_ratios[wtype] = round(
                confidence * raw_ratio + (1.0 - confidence) * volume_ratio, 2,
            )

    effort_sum = 0.0
    effort_weight_sum = 0.0
    recent_efforts: List[float] = []
    for run in all_plan_runs:
        if run.perceived_effort is not None:
            run_date = _to_date(run.date) if run.date else today
            w = recency_weight_fn(run_date)
            effort_sum += run.perceived_effort * w
            effort_weight_sum += w
            recent_efforts.append(run.perceived_effort)

    if effort_weight_sum > 0:
        avg_effort = effort_sum / effort_weight_sum
        effort_factor = max(0.85, min(1.10, 1.10 - (avg_effort - 1.0) * (0.25 / 9.0)))
    else:
        effort_factor = 1.0
        avg_effort = None

    effort_trend = _compute_effort_trend(recent_efforts)
    trend_modifier = {
        "increasing": -0.03,
        "decreasing": +0.02,
        "stable": 0.0,
        "insufficient_data": 0.0,
    }.get(effort_trend, 0.0)

    quality_drift, quality_drift_modifier = _compute_quality_drift(all_plan_runs, today)

    recent_race_effort_count = _count_recent_race_efforts(all_plan_runs, today)

    # HR Zone Signal
    hr_result = HRZoneAnalyzer.analyze_runs(
        all_plan_runs,
        hr_zones,
        recency_weight_fn=recency_weight_fn,
        today=today,
    )

    avg_zone_deviation = hr_result["avg_deviation"]
    hr_zone_adherence = hr_result["adherence_rate"]
    hr_zone_trend = hr_result["trend"]

    # Map deviation to factor
    if avg_zone_deviation >= 1.5:
        hr_zone_factor = 0.90
    elif avg_zone_deviation >= 1.0:
        hr_zone_factor = 0.95
    elif avg_zone_deviation <= -1.0:
        hr_zone_factor = 1.05
    elif avg_zone_deviation <= -0.5:
        hr_zone_factor = 1.02
    else:
        hr_zone_factor = 1.0

    # If no HR data, distribute weight to other signals
    if hr_zones is None or hr_result["run_count"] == 0:
        hr_zone_factor = 1.0
        original_hr_weight = hr_zone_weight
        hr_zone_weight = 0.0
        total_other = volume_weight + effort_weight + completion_weight + feedback_weight + readiness_weight
        if total_other > 0:
            scale = 1.0 + original_hr_weight / total_other
            volume_weight *= scale
            effort_weight *= scale
            completion_weight *= scale
            feedback_weight *= scale
            readiness_weight *= scale

    # Feedback Sentiment Signal
    if run_feedback_list and len(run_feedback_list) > 0:
        warning_weighted = 0.0
        positive_weighted = 0.0
        total_weighted = 0.0

        for fb in run_feedback_list:
            run_date = None
            for run in all_plan_runs:
                if run.id == fb.run_log_id:
                    run_date = _to_date(run.date) if run.date else today
                    break

            if run_date:
                w = recency_weight_fn(run_date)
            else:
                w = 1.0

            total_weighted += w
            if fb.overall_sentiment == "warning":
                warning_weighted += w
            elif fb.overall_sentiment == "positive":
                positive_weighted += w

        if total_weighted > 0:
            warning_ratio = warning_weighted / total_weighted
            positive_ratio = positive_weighted / total_weighted

            if warning_ratio > 0.6:
                feedback_factor = 0.92
            elif warning_ratio > 0.4:
                feedback_factor = 0.96
            elif positive_ratio > 0.6:
                feedback_factor = 1.05
            elif positive_ratio > 0.4:
                feedback_factor = 1.02
            else:
                feedback_factor = 1.0
        else:
            feedback_factor = 1.0
            warning_ratio = 0.0
            positive_ratio = 0.0
    else:
        feedback_factor = 1.0
        warning_ratio = 0.0
        positive_ratio = 0.0

    # Readiness signal — blends daily morning check-ins into the multi-week pipeline.
    readiness_log_count = len(readiness_logs) if readiness_logs else 0
    if readiness_log_count >= 3:
        scores = [getattr(log, "score", 0) or 0 for log in readiness_logs]
        readiness_pct = (sum(scores) / len(scores)) / 100.0
        readiness_pct = max(0.0, min(1.0, readiness_pct))
        readiness_factor = 0.92 + readiness_pct * 0.13
    else:
        readiness_factor = 1.0
        original_readiness_weight = readiness_weight
        readiness_weight = 0.0
        total_other = (
            volume_weight + effort_weight + completion_weight
            + hr_zone_weight + feedback_weight
        )
        if total_other > 0 and original_readiness_weight > 0:
            scale = 1.0 + original_readiness_weight / total_other
            volume_weight *= scale
            effort_weight *= scale
            completion_weight *= scale
            hr_zone_weight *= scale
            feedback_weight *= scale

    # Mountain-from-flat simulation signal. Applies only when callers provide
    # the proxy score (trail race + flat training access).
    mountain_simulation_score = None
    mountain_simulation_factor = 1.0
    if mountain_simulation is not None:
        mountain_simulation_score = float(mountain_simulation.get("score", 0) or 0)
        if mountain_simulation_score >= 85:
            mountain_simulation_factor = 1.03
        elif mountain_simulation_score >= 70:
            mountain_simulation_factor = 1.00
        elif mountain_simulation_score >= 55:
            mountain_simulation_factor = 0.97
        else:
            mountain_simulation_factor = 0.93

    completed_ids = set()
    if past_workout_ids:
        completed_rows = (
            db.query(RunLog.daily_workout_id)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.daily_workout_id.in_(past_workout_ids),
            )
            .all()
        )
        completed_ids = {row[0] for row in completed_rows}

    scheduled_weighted = 0.0
    completed_weighted = 0.0
    for workout, sched_date in past_workouts:
        w = recency_weight_fn(sched_date)
        scheduled_weighted += w
        if workout.id in completed_ids:
            completed_weighted += w

    completion_rate = (
        completed_weighted / scheduled_weighted
        if scheduled_weighted > 0 else 0.0
    )

    completion_factor = 0.90 + 0.15 * completion_rate

    raw_multiplier = (
        (volume_ratio * volume_weight)
        + (effort_factor * effort_weight)
        + (completion_factor * completion_weight)
        + (hr_zone_factor * hr_zone_weight)
        + (feedback_factor * feedback_weight)
        + (readiness_factor * readiness_weight)
    )

    raw_multiplier += trend_modifier
    raw_multiplier += quality_drift_modifier

    # Execute the mountain simulation signal as an explicit final adjustment.
    # This keeps existing phase weights unchanged for non-trail plans and for
    # trail plans without flat-access simulation targets.
    raw_multiplier *= mountain_simulation_factor

    overreach_detected = False
    if volume_ratio > 1.2 and avg_effort is not None and avg_effort > 8.0:
        raw_multiplier = min(raw_multiplier, 0.88)
        overreach_detected = True

    # HR-based overreach detection
    if hr_zone_adherence < 0.3 and hr_result.get("avg_abs_deviation", 0) > 1.0:
        raw_multiplier = min(raw_multiplier, 0.85)
        overreach_detected = True

    # Repeated race-effort exposure raises overreach risk
    if recent_race_effort_count >= 2:
        raw_multiplier = min(raw_multiplier, 0.95)
        overreach_detected = True

    # Declining fitness: VDOT dropping despite maintained workload
    if vdot_trend == "declining":
        raw_multiplier = min(raw_multiplier, 0.92)

    # TSB / Form clamps — incorporate accumulated load from TrainingLoadService.
    tsb = None
    ctl = None
    atl = None
    tsb_form = None
    peak_primed = False
    if training_load and training_load.get("available"):
        current_load = training_load.get("current") or {}
        tsb = current_load.get("tsb")
        ctl = current_load.get("ctl")
        atl = current_load.get("atl")

    if tsb is not None:
        if tsb <= -25:
            raw_multiplier = min(raw_multiplier, 0.92)
            tsb_form = "overreached"
        elif tsb >= 10 and current_phase == "peak":
            tsb_form = "primed"
            peak_primed = True
        elif tsb >= 5:
            tsb_form = "fresh"
        elif tsb <= -10:
            tsb_form = "loaded"
        else:
            tsb_form = "neutral"

    consecutive_same_direction = _count_consecutive_direction(adaptation_history)
    if consecutive_same_direction >= _CONSECUTIVE_THRESHOLD or peak_primed:
        clamp_min = _EXPANDED_MIN
        clamp_max = _EXPANDED_MAX
    else:
        clamp_min = _STANDARD_MIN
        clamp_max = _STANDARD_MAX

    # Whenever overreach is flagged from any branch above, force the final
    # multiplier into "reduce or hold" territory. Without this, a strong
    # positive volume contribution could push the multiplier back above 1.0
    # even after overreach was detected — yielding a banner that says
    # "increase volume" alongside an overreach alert telling the user the
    # opposite.
    if overreach_detected:
        raw_multiplier = min(raw_multiplier, 0.95)

    multiplier = round(max(clamp_min, min(clamp_max, raw_multiplier)), 2)

    return {
        "multiplier": multiplier,
        "volume_ratio": round(volume_ratio, 2),
        "effort_factor": round(effort_factor, 2),
        "avg_effort": round(avg_effort, 1) if avg_effort is not None else None,
        "effort_trend": effort_trend,
        "completion_rate": round(completion_rate, 2),
        "completion_factor": round(completion_factor, 2),
        "raw_multiplier": round(raw_multiplier, 3),
        "trend_modifier": round(trend_modifier, 3),
        "overreach_detected": overreach_detected,
        "per_type_ratios": {k: round(v, 2) for k, v in per_type_ratios.items()},
        "phase_weights": {
            "volume": round(volume_weight, 2),
            "effort": round(effort_weight, 2),
            "completion": round(completion_weight, 2),
            "hr_zone": round(hr_zone_weight, 2),
            "feedback": round(feedback_weight, 2),
            "readiness": round(readiness_weight, 2),
        },
        "current_phase": current_phase,
        "consecutive_same_direction": consecutive_same_direction,
        "expanded_range": consecutive_same_direction >= _CONSECUTIVE_THRESHOLD or peak_primed,
        "hr_zone_adherence": hr_zone_adherence,
        "avg_zone_deviation": round(avg_zone_deviation, 2),
        "hr_zone_trend": hr_zone_trend,
        "hr_zone_factor": round(hr_zone_factor, 2),
        "warning_ratio": round(warning_ratio, 2),
        "positive_ratio": round(positive_ratio, 2),
        "feedback_factor": round(feedback_factor, 2),
        "mountain_simulation_score": (
            round(mountain_simulation_score, 1)
            if mountain_simulation_score is not None
            else None
        ),
        "mountain_simulation_factor": round(mountain_simulation_factor, 2),
        "vdot_trend": vdot_trend,
        "quality_drift": round(quality_drift, 2) if quality_drift is not None else None,
        "quality_drift_modifier": round(quality_drift_modifier, 3),
        "recent_race_effort_count": recent_race_effort_count,
        "readiness_factor": round(readiness_factor, 3),
        "readiness_weight": round(readiness_weight, 3),
        "readiness_log_count": readiness_log_count,
        "tsb": round(tsb, 1) if tsb is not None else None,
        "ctl": round(ctl, 1) if ctl is not None else None,
        "atl": round(atl, 1) if atl is not None else None,
        "tsb_form": tsb_form,
    }


def _compute_quality_drift(all_plan_runs: List, today) -> Tuple[Optional[float], float]:
    """Compare effort_quality_score across first/second half of last 8 runs.

    Returns (drift_delta, modifier). Modifier is in {-0.02, 0.0, +0.02}.
    """
    runs_with_score = []
    for run in all_plan_runs:
        score = getattr(run, "effort_quality_score", None)
        if score is None:
            continue
        run_date = _to_date(run.date) if run.date else today
        runs_with_score.append((run_date, score))

    if len(runs_with_score) < 4:
        return None, 0.0

    runs_with_score.sort(key=lambda t: t[0])
    recent = runs_with_score[-8:]
    if len(recent) < 4:
        return None, 0.0

    mid = len(recent) // 2
    first_half = [s for _, s in recent[:mid]]
    second_half = [s for _, s in recent[mid:]]
    if not first_half or not second_half:
        return None, 0.0

    delta = (sum(second_half) / len(second_half)) - (sum(first_half) / len(first_half))
    if delta < -10:
        return delta, -0.02
    if delta > 10:
        return delta, 0.02
    return delta, 0.0


def _count_recent_race_efforts(all_plan_runs: List, today) -> int:
    """Count runs classified as race_effort within the last 14 days."""
    from datetime import timedelta as _td
    cutoff = today - _td(days=14)
    count = 0
    for run in all_plan_runs:
        if getattr(run, "effort_class", None) != "race_effort":
            continue
        run_date = _to_date(run.date) if run.date else today
        if run_date >= cutoff:
            count += 1
    return count


def _compute_effort_trend(efforts: List[float]) -> str:
    if len(efforts) < 4:
        return "insufficient_data"
    mid_point = len(efforts) // 2
    first_half_avg = sum(efforts[:mid_point]) / mid_point
    second_half_avg = sum(efforts[mid_point:]) / (len(efforts) - mid_point)
    diff = second_half_avg - first_half_avg
    if diff > 1.0:
        return "increasing"
    elif diff < -1.0:
        return "decreasing"
    return "stable"


def _count_consecutive_direction(adaptation_history: List[Dict[str, Any]] | None) -> int:
    if not adaptation_history:
        return 0
    count = 0
    last_direction = None
    for event in reversed(adaptation_history):
        direction = event.get("direction")
        if direction in ("increased", "reduced"):
            if last_direction is None:
                last_direction = direction
                count = 1
            elif direction == last_direction:
                count += 1
            else:
                break
        elif direction == "kept":
            break
    return count
