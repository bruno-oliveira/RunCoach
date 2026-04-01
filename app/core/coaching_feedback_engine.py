"""Coaching feedback engine.

Generates automated post-run coaching feedback by comparing
a logged run against the planned workout, HR zones, and recent patterns.
"""

import logging
from datetime import timedelta
from typing import Optional

from app.core.hr_zone_calculator import HRZoneCalculator
from app.core.quality_scorer import calculate_quality_score

logger = logging.getLogger(__name__)


# Pace tolerance bands per workout type: (too_slow_fraction, too_fast_fraction)
# Positive = slower, negative = faster than planned
PACE_TOLERANCES: dict[str, tuple[float, float]] = {
    "easy": (0.10, -0.08),
    "recovery": (0.15, -0.05),
    "long": (0.10, -0.08),
    "tempo": (0.05, -0.05),
    "interval": (0.08, -0.08),
    "hill": (0.10, -0.10),
}


def _fmt_pace(pace: float) -> str:
    """Format decimal min/km as M:SS."""
    from app.utils import format_pace_bare
    return format_pace_bare(pace)


class CoachingFeedbackEngine:
    """Generate structured coaching feedback after a run is logged."""

    @classmethod
    def generate_feedback(
        cls,
        run_log,
        planned_workout,
        hr_zones: Optional[list[dict]],
        db,
    ) -> dict:
        """Master method — calls all sub-generators and aggregates results.

        Args:
            run_log:         RunLog instance (just committed).
            planned_workout: DailyWorkout instance, or None.
            hr_zones:        Zone list from HRZoneService, or None.
            db:              SQLAlchemy session for history queries.

        Returns:
            Dict with pace_feedback, hr_zone_feedback, effort_feedback,
            volume_feedback, pattern_feedback, and overall_sentiment.
        """
        fb: dict[str, Optional[str]] = {
            "pace_feedback": cls._pace_feedback(run_log, planned_workout),
            "hr_zone_feedback": cls._hr_zone_feedback(
                run_log, planned_workout, hr_zones
            ),
            "effort_feedback": cls._effort_feedback(run_log, planned_workout),
            "volume_feedback": cls._volume_feedback(run_log, db),
            "pattern_feedback": cls._pattern_feedback(run_log, db),
        }
        fb["overall_sentiment"] = cls._determine_sentiment(fb)
        return fb

    # -- Sub-generators -------------------------------------------------------

    @classmethod
    def _pace_feedback(cls, run_log, planned_workout) -> Optional[str]:
        """Compare actual pace vs planned pace."""
        if not planned_workout:
            return None

        planned_pace = getattr(planned_workout, "planned_pace_min_km", None)
        actual_pace = run_log.avg_pace_min_km
        if not planned_pace or not actual_pace:
            return None

        wtype = (
            planned_workout.workout_type
            or run_log.workout_type
            or "easy"
        ).lower()
        slow_tol, fast_tol = PACE_TOLERANCES.get(wtype, (0.10, -0.08))

        diff_pct = (actual_pace - planned_pace) / planned_pace

        actual_str = _fmt_pace(actual_pace)
        planned_str = _fmt_pace(planned_pace)

        if diff_pct > slow_tol:
            return (
                f"Pace was slower than target ({actual_str}/km vs "
                f"{planned_str}/km). Check if you were tired or "
                "if conditions were challenging."
            )
        elif diff_pct < fast_tol:
            if wtype in ("easy", "recovery", "long"):
                return (
                    f"Your {wtype} run was faster than planned "
                    f"({actual_str}/km vs {planned_str}/km). "
                    "Slow down to protect your aerobic base and recovery."
                )
            return (
                f"Pace was faster than target ({actual_str}/km vs "
                f"{planned_str}/km). Great speed — just make sure "
                "you can sustain this for the full workout."
            )
        else:
            return (
                f"Pace was right on target ({actual_str}/km vs "
                f"{planned_str}/km). Great execution!"
            )

    @classmethod
    def _hr_zone_feedback(cls, run_log, planned_workout, hr_zones) -> Optional[str]:
        """Compare actual HR zone vs target zone."""
        if not hr_zones or not run_log.avg_heart_rate:
            return None

        actual_zone = HRZoneCalculator.classify_hr(
            run_log.avg_heart_rate, hr_zones
        )

        # Determine target zone
        target_zone = None
        if planned_workout and hasattr(planned_workout, "hr_zone_target"):
            target_zone = planned_workout.hr_zone_target
        if not target_zone:
            wtype = (
                run_log.workout_type or "easy"
            ).lower()
            target_zone = HRZoneCalculator.get_workout_zone(wtype)

        target_label = HRZoneCalculator.zone_label(target_zone, hr_zones)
        actual_label = HRZoneCalculator.zone_label(actual_zone, hr_zones)

        diff = actual_zone - target_zone
        if diff == 0:
            return f"Heart rate was in the target zone ({actual_label}). Well paced!"
        elif diff >= 2:
            return (
                f"Heart rate averaged {actual_label} — that's {diff} zones above "
                f"the target ({target_label}). You're working harder than planned, "
                "which impairs recovery."
            )
        elif diff == 1:
            return (
                f"Heart rate was slightly high ({actual_label} vs target "
                f"{target_label}). Try to stay relaxed and ease into the effort."
            )
        elif diff == -1:
            return (
                f"Heart rate was a bit low ({actual_label} vs target "
                f"{target_label}). You could push a little harder next time."
            )
        else:
            return (
                f"Heart rate averaged {actual_label} — well below target "
                f"({target_label}). Increase intensity to get more benefit."
            )

    @classmethod
    def _effort_feedback(cls, run_log, planned_workout) -> Optional[str]:
        """Wrap quality scorer output into coaching narrative."""
        if not run_log.perceived_effort:
            return None

        wtype = (
            (planned_workout.workout_type if planned_workout else None)
            or run_log.workout_type
            or "easy"
        )
        planned_pace = (
            getattr(planned_workout, "planned_pace_min_km", None)
            if planned_workout
            else None
        )

        score, label = calculate_quality_score(
            actual_effort=run_log.perceived_effort,
            actual_pace_min_km=run_log.avg_pace_min_km,
            workout_type=wtype,
            planned_pace_min_km=planned_pace,
        )

        messages = {
            "Nailed it": (
                f"Nailed it! Effort and pace were spot-on for this {wtype} session "
                f"(quality score: {score:.0f}/100)."
            ),
            "On track": (
                f"On track — solid {wtype} session "
                f"(quality score: {score:.0f}/100)."
            ),
            "Too easy": (
                f"This {wtype} session felt too easy (effort {run_log.perceived_effort}/10). "
                "Push a bit harder next time to maximise training stimulus."
            ),
            "Too hard": (
                f"This {wtype} session felt too hard (effort {run_log.perceived_effort}/10). "
                "Consider backing off to prevent overtraining."
            ),
        }
        return messages.get(label, f"Quality score: {score:.0f}/100.")

    @classmethod
    def _volume_feedback(cls, run_log, db) -> Optional[str]:
        """Weekly mileage progress vs planned."""
        if not run_log.training_plan_id:
            return None

        from app.models import RunLog, TrainingPlan, WeeklyPlan, DailyWorkout

        plan = (
            db.query(TrainingPlan)
            .filter(TrainingPlan.id == run_log.training_plan_id)
            .first()
        )
        if not plan or not plan.start_date:
            return None

        # Determine which plan week this run falls in
        # Strip timezone info to avoid naive/aware mismatch
        run_date = run_log.date.replace(tzinfo=None) if hasattr(run_log.date, 'replace') and run_log.date.tzinfo else run_log.date
        plan_start = plan.start_date.replace(tzinfo=None) if hasattr(plan.start_date, 'replace') and plan.start_date.tzinfo else plan.start_date
        days_since_start = (run_date - plan_start).days
        if days_since_start < 0:
            return None
        current_week_num = (days_since_start // 7) + 1

        # Get planned km for this week
        wp = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number == current_week_num,
            )
            .first()
        )
        if not wp:
            return None

        planned_km = wp.total_km or 0
        if planned_km <= 0:
            return None

        # Sum logged km this week
        week_start = plan.start_date + timedelta(weeks=current_week_num - 1)
        week_end = week_start + timedelta(days=7)
        logged_km = sum(
            r.distance_km
            for r in db.query(RunLog)
            .filter(
                RunLog.training_plan_id == plan.id,
                RunLog.user_id == run_log.user_id,
                RunLog.date >= week_start,
                RunLog.date < week_end,
            )
            .all()
        )

        pct = (logged_km / planned_km) * 100
        if pct >= 100:
            return (
                f"Week {current_week_num} target reached! "
                f"{logged_km:.1f}/{planned_km:.1f} km ({pct:.0f}%)."
            )
        elif pct >= 75:
            return (
                f"Week {current_week_num} is on track: "
                f"{logged_km:.1f}/{planned_km:.1f} km ({pct:.0f}%)."
            )
        else:
            remaining = planned_km - logged_km
            return (
                f"Week {current_week_num}: {logged_km:.1f}/{planned_km:.1f} km "
                f"({pct:.0f}%). {remaining:.1f} km still to go."
            )

    @classmethod
    def _pattern_feedback(cls, run_log, db) -> Optional[str]:
        """Detect repeated pace patterns in same workout type over last 30 days."""
        if not run_log.avg_pace_min_km or not run_log.planned_pace_min_km:
            return None

        wtype = run_log.workout_type
        if not wtype:
            return None

        from app.models import RunLog

        cutoff = run_log.date - timedelta(days=30)
        recent = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == run_log.user_id,
                RunLog.workout_type == wtype,
                RunLog.avg_pace_min_km.isnot(None),
                RunLog.planned_pace_min_km.isnot(None),
                RunLog.date >= cutoff,
                RunLog.id != run_log.id,
            )
            .order_by(RunLog.date.desc())
            .limit(3)
            .all()
        )

        if len(recent) < 2:
            return None

        # Check if all recent runs were consistently too fast
        too_fast_count = sum(
            1
            for r in recent
            if (r.avg_pace_min_km - r.planned_pace_min_km) / r.planned_pace_min_km
            < -0.05
        )
        too_slow_count = sum(
            1
            for r in recent
            if (r.avg_pace_min_km - r.planned_pace_min_km) / r.planned_pace_min_km
            > 0.08
        )

        if too_fast_count >= 2 and wtype in ("easy", "recovery", "long"):
            return (
                f"Pattern detected: your last {too_fast_count + 1} {wtype} runs "
                "have been faster than planned. Running easy days too hard "
                "limits recovery and long-term improvement."
            )
        elif too_slow_count >= 2 and wtype in ("tempo", "interval"):
            return (
                f"Pattern detected: your last {too_slow_count + 1} {wtype} "
                "sessions have been slower than target. Consider whether the "
                "pace target is realistic or if you need more recovery."
            )
        return None

    @classmethod
    def _determine_sentiment(cls, feedback: dict) -> str:
        """Return overall_sentiment based on populated feedback fields."""
        texts = [
            v for k, v in feedback.items()
            if k != "overall_sentiment" and v
        ]
        if not texts:
            return "info"

        combined = " ".join(texts).lower()
        warning_signals = [
            "slower than",
            "faster than planned",
            "too hard",
            "too easy",
            "above target",
            "impairs recovery",
            "pattern detected",
        ]
        positive_signals = [
            "nailed it",
            "right on target",
            "great execution",
            "well paced",
            "target reached",
        ]

        has_warning = any(s in combined for s in warning_signals)
        has_positive = any(s in combined for s in positive_signals)

        if has_warning and not has_positive:
            return "warning"
        if has_positive and not has_warning:
            return "positive"
        return "info"
