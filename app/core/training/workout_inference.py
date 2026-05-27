"""Pure run-type inference from pace, HR, distance, and per-km splits.

No I/O, no ORM. Strava leaves ``workout_type`` unset on most activities and the
sync mapper defaults the blank to ``"easy"`` -- so tempo, interval, and long
sessions all masquerade as easy and poison every consumer that reads
``workout_type`` (adaptation volume ratios, coaching patterns, profile counts,
zone recalibration).

Given a run's signals already resolved against the runner's own VDOT pace zones
and HR zones, the functions here decide which workout type it most likely was.
The DB-aware orchestration (resolving the runner's VDOT, max HR, and distance
distribution) lives in
``app.contexts.runner.fitness.workout_type_classifier``; everything here is a
pure function of its inputs so it can be unit-tested exhaustively.
"""

from __future__ import annotations

import math
from typing import Optional

from app.core.training.hr_zone_calculator import HRZoneCalculator

# Intensity tiers, ordered easiest -> hardest. The classifier reasons in these
# tiers and only maps to the workout-type vocabulary at the very end.
RECOVERY = "recovery"
EASY = "easy"
MODERATE = "moderate"
TEMPO = "tempo"
INTERVAL = "interval"

_TIER_RANK = {RECOVERY: 0, EASY: 1, MODERATE: 2, TEMPO: 3, INTERVAL: 4}
_RANK_TIER = {rank: tier for tier, rank in _TIER_RANK.items()}

# Coefficient of variation of per-km pace above which a run reads as surging
# (rep work) rather than a steady continuous effort. A threshold/tempo run
# holds a near-constant pace (CV well under this); intervals and fartleks
# alternate hard reps with float/recovery, pushing the spread up.
_INTERVAL_PACE_CV = 0.12

# Strava sets workout_type to one of these only when the athlete tagged the
# activity deliberately (1=race, 2=long, 3=workout/interval). 0/None collapses
# to "easy" in the sync mapper and is NOT a reliable signal.
_MEANINGFUL_STRAVA_TAGS = frozenset({"race", "long", "interval"})

# Inference below this confidence does not displace the raw tag at read time.
_MIN_INFERENCE_CONFIDENCE = 0.5


def pace_to_tier(
    avg_pace_min_km: Optional[float], pace_zones: Optional[dict]
) -> Optional[str]:
    """Map an average pace to an intensity tier using Daniels' VDOT zones.

    ``pace_zones`` is the dict returned by ``VDOTCalculator.get_pace_zones``:
    zone "E" carries ``pace_min_km_slow`` / ``pace_min_km_fast``; zones M/T/I
    carry ``pace_min_km``. Smaller pace number = faster, so the zone paces sort
    as I < T < M < E_fast < E_slow. An average at or faster than interval pace
    is interval-grade, and so on down. Returns None when pace or zones are
    missing (no pace signal).
    """
    if not avg_pace_min_km or avg_pace_min_km <= 0 or not pace_zones:
        return None

    i_pace = pace_zones.get("I", {}).get("pace_min_km")
    t_pace = pace_zones.get("T", {}).get("pace_min_km")
    m_pace = pace_zones.get("M", {}).get("pace_min_km")
    e_slow = pace_zones.get("E", {}).get("pace_min_km_slow")

    p = avg_pace_min_km
    if i_pace and p <= i_pace:
        return INTERVAL
    if t_pace and p <= t_pace:
        return TEMPO
    if m_pace and p <= m_pace:
        return MODERATE
    if e_slow and p <= e_slow:
        return EASY
    return RECOVERY


def hr_to_tier(
    avg_heart_rate: Optional[int], hr_zones: Optional[list]
) -> Optional[str]:
    """Map an average HR to an intensity tier via the 5-zone HR model.

    Z5->interval, Z4->tempo, Z3->moderate, Z2->easy, Z1->recovery. Returns None
    when HR or zones are missing (no HR signal).
    """
    if not avg_heart_rate or avg_heart_rate <= 0 or not hr_zones:
        return None
    zone = HRZoneCalculator.classify_hr(avg_heart_rate, hr_zones)
    return {1: RECOVERY, 2: EASY, 3: MODERATE, 4: TEMPO, 5: INTERVAL}.get(zone, EASY)


def splits_variability(splits: Optional[list]) -> tuple[Optional[float], int]:
    """Return ``(pace_cv, n)`` over per-km splits.

    ``pace_cv`` is the coefficient of variation (stdev / mean) of per-km pace --
    high when the runner alternated hard reps with float/recovery
    (intervals/fartlek), low for a steady continuous effort (tempo/easy/long).
    Returns ``(None, n)`` when there aren't enough usable splits to be
    meaningful.
    """
    if not splits:
        return None, 0
    paces = [s["pace_min_km"] for s in splits if s.get("pace_min_km")]
    n = len(paces)
    if n < 3:
        return None, n
    mean = sum(paces) / n
    if mean <= 0:
        return None, n
    variance = sum((p - mean) ** 2 for p in paces) / n
    return math.sqrt(variance) / mean, n


def combine(
    pace_tier: Optional[str],
    hr_tier: Optional[str],
    *,
    splits_cv: Optional[float] = None,
    is_long: bool = False,
    hilly: bool = False,
    perceived_effort: Optional[int] = None,
) -> Optional[tuple[str, float]]:
    """Fuse the available signals into ``(workout_type, confidence)``.

    workout_type is one of recovery / easy / long / tempo / interval.
    confidence is in [0, 1]. Returns None when neither pace nor HR is available
    (no basis to infer -- the caller keeps the raw tag).
    """
    if pace_tier is None and hr_tier is None:
        return None

    if pace_tier is not None and hr_tier is not None:
        rank_pace, rank_hr = _TIER_RANK[pace_tier], _TIER_RANK[hr_tier]
        gap = abs(rank_pace - rank_hr)
        if hilly:
            # On climbs pace is slowed and HR is lifted, so the two disagree by
            # construction. Take the gentler read so a hilly easy run isn't
            # mistaken for a tempo, and keep confidence low.
            rank = min(rank_pace, rank_hr)
            confidence = 0.5
        else:
            rank = round((rank_pace + rank_hr) / 2)
            confidence = {0: 0.9, 1: 0.75}.get(gap, 0.55)
    else:
        # Exactly one signal is present (the both-None case returned above).
        single = pace_tier if pace_tier is not None else hr_tier
        assert single is not None
        rank = _TIER_RANK[single]
        confidence = 0.6
        if hilly and hr_tier is None:
            # Pace-only on a hill is unreliable; don't over-rate the intensity.
            rank = min(rank, _TIER_RANK[EASY])
            confidence = 0.45

    tier = _RANK_TIER[rank]

    # Splits refine the hard end: steady vs surging separates tempo and interval.
    if splits_cv is not None and rank >= _TIER_RANK[MODERATE]:
        if splits_cv >= _INTERVAL_PACE_CV:
            tier = INTERVAL
            confidence = min(0.95, confidence + 0.1)
        elif tier == INTERVAL:
            # Hard but steady -> a threshold/tempo effort, not reps.
            tier = TEMPO
            confidence = min(0.95, confidence + 0.05)

    workout_type = _tier_to_workout_type(tier, hr_tier)

    # A long run is defined by duration/distance, not pace: a slow long run is
    # still "long". It overrides easy/recovery/moderate but never a genuine
    # hard quality session (a long tempo stays tempo).
    if is_long and _TIER_RANK[tier] <= _TIER_RANK[MODERATE]:
        workout_type = "long"

    # Perceived effort corroborates rather than drives (the effort axis is
    # handled separately by effort_classifier); use it only to firm up
    # confidence when it agrees with the inferred intensity.
    if perceived_effort is not None:
        hard = _TIER_RANK[tier] >= _TIER_RANK[TEMPO]
        easyish = _TIER_RANK[tier] <= _TIER_RANK[EASY]
        if (perceived_effort >= 7 and hard) or (perceived_effort <= 3 and easyish):
            confidence = min(0.97, confidence + 0.05)

    return workout_type, round(confidence, 2)


def _tier_to_workout_type(tier: str, hr_tier: Optional[str]) -> str:
    """Collapse an intensity tier to the stored workout-type vocabulary."""
    if tier == INTERVAL:
        return "interval"
    if tier == TEMPO:
        return "tempo"
    if tier == MODERATE:
        # Marathon-pace steady running is a quality effort only when HR
        # confirms it; otherwise it's just a brisk easy run.
        return "tempo" if hr_tier in (TEMPO, INTERVAL) else "easy"
    if tier == EASY:
        return "easy"
    return "recovery"


def resolve_effective_workout_type(
    workout_type: Optional[str],
    inferred_workout_type: Optional[str],
    *,
    is_strava: bool,
    confidence: Optional[float] = None,
) -> Optional[str]:
    """The workout type consumers should trust, reconciling tag vs inference.

    - Manually logged runs: the user's explicit choice wins; inference only
      fills a blank.
    - Strava runs: a deliberate Strava tag (race/long/interval) wins; the
      unreliable "easy" default defers to a confident inference.
    """
    if not is_strava:
        return workout_type or inferred_workout_type
    if workout_type in _MEANINGFUL_STRAVA_TAGS:
        return workout_type
    if inferred_workout_type and (
        confidence is None or confidence >= _MIN_INFERENCE_CONFIDENCE
    ):
        return inferred_workout_type
    return workout_type
