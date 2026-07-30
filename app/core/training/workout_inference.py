"""Pure run-type inference from pace, HR, distance, and per-km splits.

No I/O, no ORM. Imported activities arrive with ``workout_type`` unset and the
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

# An imported activity carries one of these only when the athlete tagged it
# deliberately. Anything else collapses to "easy" in the sync mapper and is NOT
# a reliable signal.
_MEANINGFUL_TAGS = frozenset({"race", "long", "interval"})

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

    Under the running-specific bands (Z3 Tempo = 80-88% of max) the tempo
    zone spans both steady/marathon effort (lower half) and true threshold
    effort (upper half), so Z3 splits at its midpoint into moderate vs
    tempo. Z4 (88-95%) and Z5 (95-100%) average HRs only occur in interval
    work. Returns None when HR or zones are missing (no HR signal).
    """
    if not avg_heart_rate or avg_heart_rate <= 0 or not hr_zones:
        return None
    zone = HRZoneCalculator.classify_hr(avg_heart_rate, hr_zones)
    if zone == 3:
        z3 = next((z for z in hr_zones if z.get("zone") == 3), None)
        if z3 is not None:
            mid = (z3["min_bpm"] + z3["max_bpm"]) / 2
            return MODERATE if avg_heart_rate < mid else TEMPO
        return MODERATE
    return {1: RECOVERY, 2: EASY, 4: INTERVAL, 5: INTERVAL}.get(zone, EASY)


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


# A run whose average pace lands in the easy band can still BE a quality
# session: a tempo or interval workout's warm-up and cool-down (run easy) drag
# the whole-run average down into easy territory even though a sustained block
# was run at threshold or faster. The average is the wrong lens for a session
# with an embedded quality block; the per-km splits are not. Marathon pace is
# the easy/quality boundary -- a split at or under it was NOT an easy-pace
# kilometre. When a meaningful share of the run's splits sit at the quality
# end, we lift the easy-looking average back to the tier the splits imply.
_QUALITY_SPLIT_MIN_FRACTION = 0.25  # >= 1/4 of splits at quality pace
_QUALITY_SPLIT_MIN_COUNT = 3  # ...and at least this many (a real block)


def quality_block_fraction(
    splits: Optional[list], pace_zones: Optional[dict]
) -> tuple[Optional[float], Optional[str]]:
    """Detect an embedded quality block from per-km splits.

    Returns ``(fraction, tier)`` where ``fraction`` is the share of usable
    splits run at marathon pace or faster (i.e. clearly not easy), and ``tier``
    is the intensity tier implied by the *fastest sustained* portion of the run
    -- ``TEMPO`` when those quality splits cluster at threshold effort,
    ``INTERVAL`` when a meaningful number reach interval pace. Returns
    ``(None, None)`` when there aren't enough splits or no pace zones, so the
    caller simply falls back to the average-pace read.

    This is the signal the whole-run average destroys: a 2 km easy + 4 km @ T +
    2 km easy tempo session averages out to an easy pace, but its splits show a
    clear cluster at threshold. We classify on that cluster, not the mean.
    """
    if not splits or not pace_zones:
        return None, None
    paces = [s["pace_min_km"] for s in splits if s.get("pace_min_km")]
    n = len(paces)
    if n < _QUALITY_SPLIT_MIN_COUNT:
        return None, None

    i_pace = pace_zones.get("I", {}).get("pace_min_km")
    t_pace = pace_zones.get("T", {}).get("pace_min_km")
    m_pace = pace_zones.get("M", {}).get("pace_min_km")
    # Quality = run faster than marathon pace (so genuinely above easy/steady).
    # Without an M pace we can't define the easy/quality boundary; bail.
    if not m_pace:
        return None, None

    quality_splits = [p for p in paces if p <= m_pace]
    q = len(quality_splits)
    if q < _QUALITY_SPLIT_MIN_COUNT:
        return None, None
    fraction = q / n

    # Tier from the quality cluster: interval if several splits reach I pace,
    # tempo if they sit at/under threshold, else a moderate (marathon-effort)
    # block that on its own doesn't make the session a quality day.
    if i_pace and sum(1 for p in quality_splits if p <= i_pace) >= 2:
        tier = INTERVAL
    elif t_pace and sum(1 for p in quality_splits if p <= t_pace) >= 2:
        tier = TEMPO
    else:
        tier = MODERATE
    return fraction, tier


def combine(
    pace_tier: Optional[str],
    hr_tier: Optional[str],
    *,
    splits_cv: Optional[float] = None,
    splits_quality: Optional[tuple[Optional[float], Optional[str]]] = None,
    is_long: bool = False,
    hilly: bool = False,
    perceived_effort: Optional[int] = None,
) -> Optional[tuple[str, float]]:
    """Fuse the available signals into ``(workout_type, confidence)``.

    workout_type is one of recovery / easy / long / tempo / interval.
    confidence is in [0, 1]. Returns None when neither pace nor HR is available
    (no basis to infer -- the caller keeps the raw tag).

    ``splits_quality`` is the ``(fraction, tier)`` from
    :func:`quality_block_fraction`: when a session's average pace reads easy but
    its splits expose a sustained block at threshold/interval pace (a tempo or
    interval workout whose warm-up + cool-down diluted the average), it lifts
    the classification to that block's tier rather than burying the quality
    work as "easy".
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

    # Embedded quality-block rescue. The tier so far comes from the WHOLE-RUN
    # average, which a tempo/interval session's easy warm-up + cool-down drag
    # down into the easy band. If the splits expose a sustained block at
    # threshold/interval pace, classify on that block -- but only lift upward,
    # and not on hilly runs where pace is already known-unreliable (the hilly
    # branch above deliberately took the gentler read). This only fires when
    # the average under-rated the run; it can never demote a session.
    if splits_quality is not None and not hilly:
        q_fraction, q_tier = splits_quality
        if (
            q_fraction is not None
            and q_tier is not None
            and q_fraction >= _QUALITY_SPLIT_MIN_FRACTION
            and _TIER_RANK[q_tier] > _TIER_RANK[tier]
        ):
            tier = q_tier
            rank = _TIER_RANK[tier]
            # A clear block we had to recover is a softer signal than pace+HR
            # agreeing outright, but still confident enough to displace the
            # unreliable raw "easy" tag.
            confidence = max(confidence, 0.7)

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
    is_imported: bool,
    confidence: Optional[float] = None,
) -> Optional[str]:
    """The workout type consumers should trust, reconciling tag vs inference.

    - Manually logged runs: the user's explicit choice wins; inference only
      fills a blank.
    - Imported runs: a deliberate race/long/interval tag wins; the unreliable
      "easy" default defers to a confident inference.
    """
    if not is_imported:
        return workout_type or inferred_workout_type
    if workout_type in _MEANINGFUL_TAGS:
        return workout_type
    if inferred_workout_type and (
        confidence is None or confidence >= _MIN_INFERENCE_CONFIDENCE
    ):
        return inferred_workout_type
    return workout_type
