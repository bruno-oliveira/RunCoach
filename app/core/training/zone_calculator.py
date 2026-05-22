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

from app.core.training.vdot_calculator import VDOTCalculator

_HR_PERCENTAGES = {
    "zone_1_recovery": (0.60, 0.70),
    "zone_2_aerobic": (0.70, 0.80),
    "zone_3_tempo": (0.80, 0.88),
    "zone_4_vo2max": (0.88, 0.95),
    "zone_5_race": (0.95, 1.00),
}

_FALLBACK_PACE_MIN_KM = 5.5


def calculate_zones(
    *,
    vdot: Optional[float] = None,
    vdot_zones: Optional[Dict[str, Dict[str, Any]]] = None,
    goal_pace: Optional[float] = None,
    max_hr: Optional[int] = None,
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
            each zone.

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
        m_pace = vdot_zones["M"]["pace_min_km"]

        if goal_pace is not None:
            zone_5_anchor = goal_pace
            zone_5_description = "Race pace: target effort for race day"
        else:
            zone_5_anchor = m_pace
            zone_5_description = "Race pace: all-out benchmark effort"

        zones: Dict[str, Dict[str, Any]] = {
            "zone_1_recovery": {
                "pace": e_slow,
                "pace_range": (e_slow, e_fast),
                "hr_range": "60-70%",
                "description": "Recovery: truly easy, conversational pace",
                "color": "#4ade80",
            },
            "zone_2_aerobic": {
                "pace": e_fast,
                "pace_range": (e_fast, t_pace),
                "hr_range": "70-80%",
                "description": "Aerobic: moderate effort, can still hold a conversation",
                "color": "#60a5fa",
            },
            "zone_3_tempo": {
                "pace": t_pace,
                "pace_range": (t_pace, t_pace * 0.97),
                "hr_range": "80-88%",
                "description": "Tempo: comfortably hard, sustainable for 20-40 min",
                "color": "#facc15",
            },
            "zone_4_vo2max": {
                "pace": i_pace,
                "pace_range": (i_pace, i_pace * 0.95),
                "hr_range": "88-95%",
                "description": "VO2max: hard effort, 3-5 min intervals",
                "color": "#f97316",
            },
            "zone_5_race": {
                "pace": zone_5_anchor,
                "pace_range": (zone_5_anchor, zone_5_anchor * 0.98),
                "hr_range": "95-100%",
                "description": zone_5_description,
                "color": "#ef4444",
            },
        }
    else:
        ref = goal_pace if goal_pace is not None else _FALLBACK_PACE_MIN_KM
        zone_5_description = (
            "Race pace: target effort for race day"
            if goal_pace is not None
            else "Race pace: all-out benchmark effort"
        )
        zones = {
            "zone_1_recovery": {
                "pace": ref * 1.30,
                "pace_range": (ref * 1.35, ref * 1.25),
                "hr_range": "60-70%",
                "description": "Recovery: truly easy, conversational pace",
                "color": "#4ade80",
            },
            "zone_2_aerobic": {
                "pace": ref * 1.15,
                "pace_range": (ref * 1.25, ref * 1.10),
                "hr_range": "70-80%",
                "description": "Aerobic: moderate effort, can still hold a conversation",
                "color": "#60a5fa",
            },
            "zone_3_tempo": {
                "pace": ref * 1.05,
                "pace_range": (ref * 1.10, ref * 1.02),
                "hr_range": "80-88%",
                "description": "Tempo: comfortably hard, sustainable for 20-40 min",
                "color": "#facc15",
            },
            "zone_4_vo2max": {
                "pace": ref * 0.95,
                "pace_range": (ref * 1.00, ref * 0.92),
                "hr_range": "88-95%",
                "description": "VO2max: hard effort, 3-5 min intervals",
                "color": "#f97316",
            },
            "zone_5_race": {
                "pace": ref,
                "pace_range": (ref * 1.02, ref * 0.98),
                "hr_range": "95-100%",
                "description": zone_5_description,
                "color": "#ef4444",
            },
        }

    if max_hr:
        for zone_name, (low_pct, high_pct) in _HR_PERCENTAGES.items():
            low_bpm = int(max_hr * low_pct)
            high_bpm = int(max_hr * high_pct)
            zones[zone_name]["hr_bpm_range"] = f"{low_bpm}-{high_bpm} BPM"

    return zones
