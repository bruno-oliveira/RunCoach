"""Unified training-zone calculator.

Both `FitnessPlanGenerator` and `PerformancePlanGenerator` previously
maintained their own near-identical 5-zone tables (recovery, aerobic, tempo,
VO2max, race). The two diverged only in how zone 5 is anchored:

- Performance plans anchor zone 5 to the user's chosen `goal_pace`.
- Fitness plans anchor zone 5 to VDOT-derived marathon pace (or a 5.5 min/km
  fallback when no VDOT is available).

This module centralises the table so both generators delegate here.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.training.physiology.hr_zone_calculator import (
    TRAINING_ZONE_HR_PERCENTAGES,
    HRZoneCalculator,
)
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.utils import format_pace, format_pace_bare

_FALLBACK_PACE_MIN_KM = 5.5

# Slow edge of the recovery band when the VDOT zones carry no recovery
# sub-zone: about the gap between the recovery sub-zone's slow edge and E_slow.
_RECOVERY_SLOWDOWN = 1.08

# The pace-zone slugs in zone order (1-5). The keys of
# TRAINING_ZONE_HR_PERCENTAGES are these slugs in order, so canonical HR zones
# (a list, zone 1..5) map onto the pace-zone table 1:1.
_ZONE_SLUGS_ORDER = list(TRAINING_ZONE_HR_PERCENTAGES.keys())


def calculate_zones(
    *,
    vdot: Optional[float] = None,
    vdot_zones: Optional[Dict[str, Dict[str, Any]]] = None,
    goal_pace: Optional[float] = None,
    max_hr: Optional[int] = None,
    resting_hr: Optional[int] = None,
    lthr: Optional[int] = None,
    race_distance_km: Optional[float] = None,
) -> Dict[str, Dict[str, Any]]:
    """Build the 5-zone training table.

    Args:
        vdot: VDOT value used to derive pace zones via `VDOTCalculator`.
            Ignored if `vdot_zones` is provided directly.
        vdot_zones: Pre-fetched VDOT zone dict (keys "E", "T", "I", "M").
            Use this when the caller already has the dict to avoid recomputing.
        goal_pace: User's target race pace in min/km. If provided, anchors
            zone 5 to this pace and shifts the description to a race-target tone.
        max_hr: Maximum heart rate. If provided, attaches `hr_bpm_range` to
            each zone, sourced from the one HR-zone authority.
        resting_hr: Optional resting HR, threaded to the canonical calculator
            (raises only the Zone 1 floor).
        lthr: Optional lactate-threshold HR. Threaded to the canonical
            calculator so the BPM bands match the runner's real threshold —
            i.e. identical to the "Heart Rate Training Zones" panel. When absent
            the calculator falls back to the 88%-of-max default.
        race_distance_km: Target race distance. When given alongside
            `goal_pace`, the race-pace band's HR label is corrected to the
            effort that distance is actually run at (a marathon goal pace is a
            sustained aerobic effort, not the 95-100% the band would otherwise
            imply), rather than always reading as max effort.

    Returns:
        Dict keyed by zone slug, each value containing pace, pace_range,
        hr_range, description, color, and optionally hr_bpm_range.
    """
    if vdot_zones is None and vdot:
        vdot_zones = VDOTCalculator.get_pace_zones(vdot)

    zone_5_anchor: float
    zone_5_description: str
    if vdot_zones:
        e_slow = vdot_zones["E"]["pace_min_km_slow"]
        e_fast = vdot_zones["E"]["pace_min_km_fast"]
        t_pace = vdot_zones["T"]["pace_min_km"]
        i_pace = vdot_zones["I"]["pace_min_km"]
        r_pace = vdot_zones["R"]["pace_min_km"]
        recovery = vdot_zones["E"].get("sub_zones", {}).get("recovery", {})
        recovery_slow = recovery.get("pace_min_km_slow") or e_slow * _RECOVERY_SLOWDOWN

        if goal_pace is not None:
            zone_5_anchor = goal_pace
            zone_5_description = "Race pace: target effort for race day"
        else:
            # Zone 5 is the 95-100% HR / hardest band, so it must be strictly
            # faster than the zone-4 VO2max band. Anchor it to R-pace
            # (repetition / short fast reps), which truly sits at this
            # intensity. Anchoring to marathon pace (slower than I-pace)
            # inverted the displayed ladder.
            zone_5_anchor = r_pace
            zone_5_description = "Speed: short fast reps at near-max effort"

        # Each band's pace range is the pace that produces its HR band, so the
        # edges follow the HR model rather than the Daniels labels: threshold
        # pace is where HR reaches LTHR -- the Zone 3/4 line, and the very point
        # the LTHR estimate reads off the pace<->HR fit -- so T is the *fast*
        # edge of Zone 3, not its slow edge. Easy pace (E) is Zone 2, where
        # every easy run's HR target sits, and recovery pace is slower than it.
        # Every anchor (`pace`) is the fast edge of its own band; the workout
        # builders read those anchors, so prescribed paces are unchanged.
        zones: Dict[str, Dict[str, Any]] = {
            "zone_1_recovery": {
                "pace": e_slow,
                "pace_range": (recovery_slow, e_slow),
                "hr_range": "60-70%",
                "description": "Recovery: truly easy, conversational pace",
                "color": "#4ade80",
            },
            "zone_2_aerobic": {
                "pace": e_fast,
                "pace_range": (e_slow, e_fast),
                # The E band exactly as every E-paced step prints it, so an
                # easy run and a warm-up in the same week cannot differ by a
                # rounding second.
                "pace_str": vdot_zones["E"]["pace_str"],
                "hr_range": "70-80%",
                "description": "Aerobic: moderate effort, can still hold a conversation",
                "color": "#60a5fa",
            },
            "zone_3_tempo": {
                "pace": t_pace,
                # Spans the steady-to-threshold region (marathon pace sits
                # inside it) and ends on threshold pace -- a band, not the old
                # ~8 s sliver around T (G6).
                "pace_range": (e_fast, t_pace),
                "hr_range": "80-88%",
                "description": "Tempo: steady up to threshold, comfortably hard",
                "color": "#facc15",
            },
            "zone_4_vo2max": {
                "pace": i_pace,
                "pace_range": (t_pace, i_pace),
                "hr_range": "88-95%",
                "description": "VO2max: above threshold, 3-5 min intervals",
                "color": "#f97316",
            },
            "zone_5_race": {
                "pace": zone_5_anchor,
                "pace_range": (
                    (i_pace, r_pace)
                    if goal_pace is None
                    else (zone_5_anchor, zone_5_anchor * 0.98)
                ),
                "hr_range": "95-100%",
                "description": zone_5_description,
                "color": "#ef4444",
            },
        }
    else:
        ref = goal_pace if goal_pace is not None else _FALLBACK_PACE_MIN_KM
        # With an explicit goal pace, zone 5 is that race target. Without one,
        # zone 5 is the hardest (95-100% HR) band, so it must be faster than
        # the zone-4 VO2max anchor (ref * 0.95) rather than equal to ref.
        zone_5_anchor = ref if goal_pace is not None else ref * 0.90
        zone_5_description = (
            "Race pace: target effort for race day"
            if goal_pace is not None
            else "Speed: short fast reps at near-max effort"
        )
        # Adjacent bands share an edge so the table is a contiguous partition
        # of the pace continuum rather than leaving gaps between zones (G6).
        zones = {
            "zone_1_recovery": {
                "pace": ref * 1.30,
                "pace_range": (ref * 1.35, ref * 1.15),
                "hr_range": "60-70%",
                "description": "Recovery: truly easy, conversational pace",
                "color": "#4ade80",
            },
            "zone_2_aerobic": {
                "pace": ref * 1.15,
                "pace_range": (ref * 1.15, ref * 1.05),
                "hr_range": "70-80%",
                "description": "Aerobic: moderate effort, can still hold a conversation",
                "color": "#60a5fa",
            },
            "zone_3_tempo": {
                "pace": ref * 1.05,
                "pace_range": (ref * 1.05, ref * 0.95),
                "hr_range": "80-88%",
                "description": "Tempo: comfortably hard, threshold to cruise effort",
                "color": "#facc15",
            },
            "zone_4_vo2max": {
                "pace": ref * 0.95,
                "pace_range": (ref * 0.95, ref * 0.90),
                "hr_range": "88-95%",
                "description": "VO2max: hard effort, 3-5 min intervals",
                "color": "#f97316",
            },
            "zone_5_race": {
                "pace": zone_5_anchor,
                "pace_range": (zone_5_anchor, zone_5_anchor * 0.95),
                "hr_range": "95-100%",
                "description": zone_5_description,
                "color": "#ef4444",
            },
        }

    # Distance-aware race-pace effort: the zone-5 band is pinned to the goal
    # pace, but the *effort* that pace represents depends on the race. A 5K is
    # run near VO2max; a marathon at a sustained aerobic effort. Re-label the
    # band's HR/percentage to the matching training zone so the panel doesn't
    # claim every goal pace is a 95-100% max-HR effort. The pace itself is left
    # untouched (the runner's literal target).
    #
    # That holds once fitness has caught up with the goal. Early in a time-goal
    # block the goal pace can still be faster than the runner's VO2max pace, and
    # there it *is* a near-max effort: the band keeps its own 95-100% label
    # rather than borrowing a zone the pace sits outside of. Zones pinned to
    # the goal hold their interval pace *at* it until fitness passes it, so an
    # interval pace equal to the goal is that same early-block case.
    beyond_vo2max = bool(
        goal_pace is not None
        and vdot_zones
        and round(goal_pace, 2) <= vdot_zones["I"]["pace_min_km"]
    )
    if goal_pace is not None and race_distance_km and not beyond_vo2max:
        from app.core.training.physiology.goal_pace_model import race_pace_zone_label

        # Daniels pace zone closest to race pace -> the display band whose HR
        # range best describes that effort.
        _label_to_hr_slug = {
            "I": "zone_4_vo2max",
            "T": "zone_4_vo2max",
            "M": "zone_3_tempo",
            "E": "zone_2_aerobic",
        }
        hr_slug = _label_to_hr_slug.get(
            race_pace_zone_label(race_distance_km), "zone_4_vo2max"
        )
        zones["zone_5_race"]["hr_range"] = zones[hr_slug]["hr_range"]
        zones["zone_5_race"]["race_hr_slug"] = hr_slug

    if max_hr:
        # BPM bands come from the single HR-zone authority (LTHR-anchored),
        # never a second flat-%max computation. This is what makes the "your
        # training paces" panel's BPM band identical to the "Heart Rate Training
        # Zones" panel for the same runner — the divergence we set out to kill.
        canonical = HRZoneCalculator.calculate_zones(
            max_hr, resting_hr=resting_hr, lthr=lthr
        )
        slug_to_band = {
            slug: f"{z['min_bpm']}-{z['max_bpm']} BPM"
            for slug, z in zip(_ZONE_SLUGS_ORDER, canonical)
        }
        for slug, band in slug_to_band.items():
            zones[slug]["hr_bpm_range"] = band
        # The race-pace band borrows its effort cousin's BPM range too, so the
        # numeric band matches the corrected percentage label above.
        race = zones["zone_5_race"]
        if race.get("race_hr_slug"):
            race["hr_bpm_range"] = slug_to_band[race["race_hr_slug"]]

    # Attach display strings for the pace anchor and the pace band. The zone
    # table in the performance plan renders `pace_formatted` /
    # `pace_range_formatted`; without these the whole "your training paces"
    # panel showed blanks. Deriving them here (rather than in each zone literal
    # above) guarantees every zone — VDOT-based or fallback — carries them.
    for zone in zones.values():
        zone["pace_formatted"] = format_pace(zone["pace"])
        pace_range = zone.get("pace_range")
        if pace_range and len(pace_range) == 2:
            slow, fast = pace_range
            slow_str = format_pace_bare(slow)
            fast_str = format_pace_bare(fast)
            if slow_str == "--" or fast_str == "--":
                zone["pace_range_formatted"] = format_pace(zone["pace"])
            elif slow_str == fast_str:
                # A degenerate band (e.g. a pinned race-pace zone) reads as a
                # single pace rather than "5:00-5:00/km".
                zone["pace_range_formatted"] = f"{slow_str}/km"
            else:
                zone["pace_range_formatted"] = f"{fast_str}-{slow_str}/km"
        else:
            zone["pace_range_formatted"] = format_pace(zone["pace"])

    return zones
