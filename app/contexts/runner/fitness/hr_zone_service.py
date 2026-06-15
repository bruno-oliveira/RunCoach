"""Heart rate zone service — orchestrates zone computation and persistence."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.training.hr_pace_calibration import (
    PaceHRSample,
    attach_calibrated_paces,
    fit_pace_hr_model,
)
from app.core.training.hr_zone_calculator import (
    DEFAULT_MAX_HR,
    HR_ZONES_VERSION,
    MAX_HR_SPIKE_TOLERANCE_BPM,
    MAX_RELIABLE_MAX_HR,
    MAX_RELIABLE_RESTING_HR,
    MIN_RELIABLE_MAX_HR,
    MIN_RELIABLE_RESTING_HR,
    HRZoneCalculator,
    _lthr_is_usable,
)
from app.models.training_plan import TrainingPlan
from app.models.user import User

logger = logging.getLogger(__name__)

# Easy-run average HR sits well above true resting HR. We approximate the gap
# with a fixed offset when estimating resting HR from the lowest easy-run
# average. Deliberately conservative (small) so an over-estimate keeps the
# Karvonen zones close to the %max-HR fallback rather than skewing them low.
EASY_RUN_TO_RESTING_OFFSET_BPM = 25
# Require at least this many easy-effort runs before trusting a derived value.
MIN_EASY_RUNS_FOR_RESTING = 5

# How many recent runs to sample when calibrating the pace<->HR relationship.
# Bounded so the fit reflects *current* fitness (the mapping shifts as the
# runner gets faster) and stays cheap; per-km splits within these runs supply
# the bulk of the intensity spread the fit needs.
MAX_RUNS_FOR_CALIBRATION = 60

# Effort types whose average HR sits at lactate threshold. Used to measure the
# runner's threshold HR (LTHR) for re-anchoring the zone boundaries.
THRESHOLD_WORKOUT_TYPES = ("tempo", "cruise_interval", "race_pace", "fartlek")
# Need a few threshold sessions before trusting a derived LTHR.
MIN_THRESHOLD_RUNS_FOR_LTHR = 3
# Only the most recent threshold runs, so LTHR tracks current fitness.
MAX_RUNS_FOR_LTHR = 60


def detect_max_hr_from_runs(user_id: str, db: Session) -> Optional[int]:
    """Estimate max HR from run data, robust to single-sensor spikes.

    Optical wrist sensors routinely glitch 15-30 BPM high (cadence lock,
    loose strap), and the old "take the single highest reading ever" picked
    those spikes up permanently, inflating every zone for every future plan.

    Strategy: take the top recorded per-run max values inside the plausible
    human band; accept the highest only if the second-highest run
    corroborates it (within MAX_HR_SPIKE_TOLERANCE_BPM), otherwise fall back
    to the corroborated second reading. A single qualifying run is still
    accepted - one data point beats an age formula.
    """
    from app.models import RunLog

    rows = (
        db.query(RunLog.max_heart_rate)
        .filter(
            RunLog.user_id == user_id,
            RunLog.max_heart_rate.isnot(None),
            RunLog.max_heart_rate >= MIN_RELIABLE_MAX_HR,
            RunLog.max_heart_rate <= MAX_RELIABLE_MAX_HR,
        )
        .order_by(RunLog.max_heart_rate.desc())
        .limit(5)
        .all()
    )
    readings = [r[0] for r in rows]
    if not readings:
        return None
    if len(readings) == 1:
        return readings[0]
    top, second = readings[0], readings[1]
    if top - second > MAX_HR_SPIKE_TOLERANCE_BPM:
        return second
    return top


def get_user_max_hr(
    user_id: str,
    db: Session,
    user_age: Optional[int] = None,
) -> tuple[int, str]:
    """Determine max HR from run data, age, or a safe default.

    Returns:
        (max_hr, source) where source is "detected", "estimated", or "default".
    """
    detected = detect_max_hr_from_runs(user_id, db)
    if detected:
        return detected, "detected"

    if user_age and user_age > 0:
        return HRZoneCalculator.estimate_max_hr_age_based(user_age), "estimated"

    return DEFAULT_MAX_HR, "default"


def detect_resting_hr_from_runs(user_id: str, db: Session) -> Optional[int]:
    """Estimate resting HR from the lowest easy-effort run averages.

    We don't ingest per-second streams, so true resting HR isn't directly
    available. The lowest *average* HR on genuinely easy/recovery runs is the
    best aerobic-floor proxy we have; subtracting a conservative offset
    approximates the gap down to true resting. Requires a handful of easy runs
    before trusting the estimate, and clamps to a plausible band. Returns None
    when there isn't enough data -- callers then fall back to %max HR.
    """
    from app.models import RunLog

    rows = (
        db.query(RunLog.avg_heart_rate)
        .filter(
            RunLog.user_id == user_id,
            RunLog.avg_heart_rate.isnot(None),
            RunLog.avg_heart_rate > 0,
            RunLog.workout_type.in_(("easy", "recovery", "long")),
        )
        .order_by(RunLog.avg_heart_rate.asc())
        .limit(MIN_EASY_RUNS_FOR_RESTING)
        .all()
    )
    readings = [r[0] for r in rows if r[0]]
    if len(readings) < MIN_EASY_RUNS_FOR_RESTING:
        return None

    easy_floor = min(readings)
    estimate = easy_floor - EASY_RUN_TO_RESTING_OFFSET_BPM
    estimate = max(MIN_RELIABLE_RESTING_HR, min(MAX_RELIABLE_RESTING_HR, estimate))
    return int(round(estimate))


def get_user_resting_hr(
    user: User,
    db: Session,
) -> tuple[Optional[int], str]:
    """Determine resting HR, preferring the user's own value over an estimate.

    Returns:
        (resting_hr, source) where source is "user", "estimated", or "none".
        ``resting_hr`` is None when nothing usable is available, in which case
        zones fall back to the %max HR model.
    """
    override = getattr(user, "resting_hr", None)
    if override and override > 0:
        return int(override), "user"

    estimated = detect_resting_hr_from_runs(user.id, db)
    if estimated:
        return estimated, "estimated"

    return None, "none"


def detect_threshold_hr_from_runs(user_id: str, db: Session) -> Optional[int]:
    """Estimate lactate-threshold HR from recent threshold-effort runs.

    A tempo / cruise-interval / race-pace run is run at (or very near) lactate
    threshold, so the average HR across a handful of them is a solid LTHR proxy
    -- and one measured from the runner's own physiology rather than assumed to
    be 88% of max. We read the *effective* workout type (so untagged Strava
    runs inferred as tempo count) and take the median to shrug off the odd hot
    or under-warmed-up session. Returns None below a minimum sample count.
    """
    from statistics import median

    from app.models import RunLog

    runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.avg_heart_rate.isnot(None),
        )
        .order_by(RunLog.date.desc())
        .limit(MAX_RUNS_FOR_LTHR)
        .all()
    )
    hrs = [
        run.avg_heart_rate
        for run in runs
        if run.avg_heart_rate and run.effective_workout_type in THRESHOLD_WORKOUT_TYPES
    ]
    if len(hrs) < MIN_THRESHOLD_RUNS_FOR_LTHR:
        return None
    return int(round(median(hrs)))


def get_user_threshold_hr(user: User, db: Session) -> tuple[Optional[int], str]:
    """Determine threshold HR, preferring a user override over an estimate.

    Returns:
        (lthr, source) where source is "user", "estimated", or "none".
        ``lthr`` is None when nothing usable is available, leaving zones on the
        max/resting-HR formula bands.
    """
    override = getattr(user, "threshold_hr", None)
    if override and override > 0:
        return int(override), "user"

    estimated = detect_threshold_hr_from_runs(user.id, db)
    if estimated:
        return estimated, "estimated"

    return None, "none"


def gather_pace_hr_samples(user_id: str, db: Session) -> list[PaceHRSample]:
    """Collect ``(pace, heart rate)`` observations from a user's recent runs.

    Per-km splits are preferred when present: a single run's splits span easy
    warm-up to hard reps, giving the intensity spread the linear fit needs. When
    a run has no usable splits we fall back to its overall average pace / HR.
    """
    from app.models import RunLog

    rows = (
        db.query(
            RunLog.avg_pace_min_km,
            RunLog.avg_heart_rate,
            RunLog.splits,
        )
        .filter(RunLog.user_id == user_id)
        .order_by(RunLog.date.desc())
        .limit(MAX_RUNS_FOR_CALIBRATION)
        .all()
    )

    samples: list[PaceHRSample] = []
    for avg_pace, avg_hr, splits in rows:
        used_splits = False
        if isinstance(splits, list):
            for split in splits:
                if not isinstance(split, dict):
                    continue
                pace = split.get("pace_min_km")
                hr = split.get("avg_hr")
                if pace and hr:
                    samples.append(PaceHRSample(pace_min_km=pace, hr=hr))
                    used_splits = True
        if not used_splits and avg_pace and avg_hr:
            samples.append(PaceHRSample(pace_min_km=avg_pace, hr=avg_hr))

    return samples


class HRZoneService:
    """Compute, persist, and inject HR zones into training plans."""

    @staticmethod
    def compute_and_store_zones(
        plan: TrainingPlan,
        user: User,
        db: Session,
    ) -> list[dict]:
        """Calculate HR zones for a user and store them on the plan.

        Args:
            plan: TrainingPlan to annotate.
            user: The plan owner (for age fallback).
            db:   SQLAlchemy session.

        Returns:
            List of zone dicts with BPM ranges.
        """
        max_hr, source = get_user_max_hr(user.id, db, user_age=user.age)
        resting_hr, resting_source = get_user_resting_hr(user, db)
        lthr, lthr_source = get_user_threshold_hr(user, db)
        zones = HRZoneCalculator.calculate_zones(
            max_hr, resting_hr=resting_hr, lthr=lthr
        )
        method = "hrr" if resting_hr is not None else "pct_max"
        lthr_anchored = lthr is not None and _lthr_is_usable(max_hr, lthr)

        # Calibrate each zone's BPM band to the pace this runner actually holds
        # there, fitted from their own logged pace<->HR data. Falls back
        # silently to the formula bands (no pace) when there isn't enough
        # consistent data to trust a fit.
        calibration = HRZoneService._calibrate_zone_paces(user.id, db, zones)

        plan.hr_zones_data = {
            "max_hr": max_hr,
            "source": source,
            "resting_hr": resting_hr,
            "resting_source": resting_source,
            "lthr": lthr if lthr_anchored else None,
            "lthr_source": lthr_source,
            "lthr_anchored": lthr_anchored,
            "method": method,
            "zones": zones,
            "pace_calibration": calibration,
            "version": HR_ZONES_VERSION,
        }
        plan.max_heart_rate = max_hr

        logger.info(
            f"HR zones computed for plan {plan.id}: max_hr={max_hr} ({source}), "
            f"resting_hr={resting_hr} ({resting_source}), method={method}, "
            f"lthr={lthr} ({lthr_source}), lthr_anchored={lthr_anchored}, "
            f"pace_calibrated={calibration is not None}"
        )
        return zones

    @staticmethod
    def _calibrate_zone_paces(
        user_id: str,
        db: Session,
        zones: list[dict],
    ) -> Optional[dict]:
        """Fit pace<->HR from run data and annotate ``zones`` with their paces.

        Returns calibration metadata (slope, correlation, sample count) when a
        trustworthy fit is found and the zones were annotated in place, else
        None. Never raises: a calibration failure must not block zone storage.
        """
        try:
            samples = gather_pace_hr_samples(user_id, db)
            model = fit_pace_hr_model(samples)
            if model is None:
                return None
            attach_calibrated_paces(zones, model)
            return {
                "slope_bpm_per_kmh": round(model.slope, 2),
                "correlation": round(model.r, 3),
                "samples": model.n,
            }
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Pace<->HR calibration failed: %s", e)
            return None

    @staticmethod
    def inject_hr_zones_into_plan_data(
        plan_data: list[dict],
        zones: list[dict],
    ) -> list[dict]:
        """Annotate each workout dict with its target HR zone info.

        Mutates plan_data in place and returns it for convenience.
        """
        for week in plan_data:
            for workout in week.get("daily_workouts", []):
                wtype = workout.get("type", "easy")
                target_zone = HRZoneCalculator.get_workout_zone(wtype)
                workout["hr_zone_target"] = target_zone
                workout["hr_zone_label"] = HRZoneCalculator.zone_label(
                    target_zone, zones
                )
        return plan_data

    @staticmethod
    def get_zones_for_plan(plan: TrainingPlan) -> Optional[dict]:
        """Deserialise stored HR zones from a plan.

        Returns:
            Dict with max_hr, source, and zones list — or None.
        """
        if not plan.hr_zones_data:
            return None
        return plan.hr_zones_data

    @staticmethod
    def zones_are_stale(plan: TrainingPlan) -> bool:
        """True when the plan carries zones from an older zone model."""
        data = plan.hr_zones_data
        if not data:
            return False  # nothing stored; the "missing" path handles this
        return data.get("version", 1) < HR_ZONES_VERSION
