"""Race-day protocol generator.

Produces a structured race-day guide covering:
- Week-before checklist
- Race-morning timeline
- Km-by-km pacing splits
- Nutrition & hydration timing
- Mental checkpoints

Per-distance content lives in `app.core.race.race_profiles.RACE_PROFILES`.
This module orchestrates the pieces and handles distance-agnostic logic
(pacing splits, predicted finish, trail-specific procedural builders).
"""

from typing import Any, Dict, List, Optional

from app.core.race.race_profiles import RACE_PROFILES, lookup_profile


# Week-before checklist (universal across all distances)
_WEEK_BEFORE = [
    "Confirm race start time, location, and parking/transport",
    "Pick up race bib and packet if pre-collection is available",
    "Study the course map and identify key hills or turns",
    "Prepare and test your race-day outfit (including socks)",
    "Check the weather forecast and plan layers accordingly",
    "Charge GPS watch and earphones",
    "Prepare race nutrition: count gels, tabs, food",
    "Taper your training — trust the process, resist extra sessions",
    "Prioritise sleep: aim for 8+ hrs the night before the night before (Friday often matters more than Saturday)",
    "Avoid new foods, alcohol, and strenuous non-running activity",
]


def _seconds_to_hhmmss(total_seconds: int) -> str:
    """Convert integer seconds to H:MM:SS or MM:SS string."""
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _generate_pacing_splits(
    target_distance: float,
    goal_pace_min_km: Optional[float],
) -> List[Dict[str, str]]:
    """Generate km-by-km (or key checkpoint) pacing splits."""
    if not goal_pace_min_km:
        return []

    splits = []

    # Determine split checkpoints based on distance
    if target_distance <= 5.0:
        checkpoints = [1, 2, 3, 4, 5]
    elif target_distance <= 10.0:
        checkpoints = [2, 5, 8, 10]
    elif target_distance <= 21.1:
        checkpoints = [5, 10, 15, 20, 21.1]
    elif target_distance <= 30.0:
        checkpoints = [5, 10, 15, 20, 25, 30]
    else:
        checkpoints = [5, 10, 15, 21.1, 25, 30, 35, 40, 42.2]

    cumulative_seconds = 0.0
    prev_km = 0.0

    for km in checkpoints:
        segment_km = km - prev_km
        segment_seconds = segment_km * goal_pace_min_km * 60
        cumulative_seconds += segment_seconds

        split_seconds = round(segment_seconds)
        cum_seconds = round(cumulative_seconds)

        is_finish = abs(km - target_distance) < 0.2
        is_halfway = abs(km - target_distance / 2) < 0.3

        splits.append({
            "distance": f"{km:.1f}" if km != int(km) else str(int(km)),
            "split_time": _seconds_to_hhmmss(split_seconds),
            "target_pace": f"{int(goal_pace_min_km)}:{round((goal_pace_min_km % 1) * 60):02d}/km",
            "cumulative": _seconds_to_hhmmss(cum_seconds),
            "highlight": is_finish or is_halfway,
        })

        prev_km = km

    return splits


def _trail_dist_name(profile) -> str:
    bracket_label = {
        "short":      "Short Trail",
        "standard":   "Trail",
        "ultra":      "Ultra Trail",
        "long_ultra": "Ultra Trail",
    }[profile.bracket]
    return f"{profile.distance_km:g}km {bracket_label}"


def _trail_mental_checkpoints(distance_km: float) -> List[Dict[str, str]]:
    """Generate mental anchors at 10% / 33% / 50% / 75% / 90% of race distance."""
    anchors = [
        (0.10, "First climb. Power hike if needed — no shame in that. Settle in."),
        (0.33, "One third in. How is fueling going? Eat now if not in the last 30 min."),
        (0.50, "Halfway. Check in: legs, stomach, head. Adjust pace, don't fight it."),
        (0.75, "The hardest part. Run your own race, not someone else's. Stay present."),
        (0.90, "The finish line is real now. Put your head down — every step counts."),
    ]
    return [
        {"distance": f"{distance_km * pct:.1f} km", "message": msg}
        for pct, msg in anchors
    ]


def _trail_nutrition(distance_km: float, predicted_seconds: Optional[int]) -> List[Dict[str, str]]:
    """Bracket-aware nutrition: in-race carbs/h, electrolyte cadence, real food for ultras."""
    items = [
        {"icon": "🍌", "when": "3 hrs before",
         "what": "Larger carb-rich meal — you'll be burning glycogen for hours"},
    ]

    duration_h = (predicted_seconds / 3600) if predicted_seconds else None

    # Carb intake target scales with predicted duration.
    # 2-6h → 60 g/h gels/chews; >6h → 50 g/h with real food alongside.
    if duration_h and duration_h > 6:
        items.append({"icon": "🍬", "when": "Every 30–40 min",
                      "what": "≈50 g carbs/h via gels, chews, dates, banana — alternate sweet and savoury"})
    else:
        items.append({"icon": "🍬", "when": "Every 30–45 min from km 8",
                      "what": "60–90 g carbs/h via gels or chews — start fueling early"})

    # Hydration.
    items.append({"icon": "💧", "when": "Every aid station / 3–4 km",
                  "what": "Sip — climbs and exposed sections sweat harder than they feel"})

    # Electrolytes — denser cadence for longer races.
    if distance_km >= 50:
        items.append({"icon": "🧂", "when": "Every 60–90 min",
                      "what": "Electrolyte capsule or tab — cramps end races at this distance"})
    else:
        items.append({"icon": "🧂", "when": "Every 10 km",
                      "what": "Electrolytes — cramps on trails are race-ending"})

    # Real food for ultras.
    if distance_km >= 50:
        items.append({"icon": "🥪", "when": "From hour 3 onward",
                      "what": "Switch in real food at aid stations — boiled potato, rice balls, broth"})

    items.append({"icon": "🍫", "when": "Within 30 min after",
                  "what": "Real food: protein + substantial carbs"})
    return items


def _trail_morning(distance_km: float, is_ultra: bool, is_long_ultra: bool) -> List[tuple]:
    """Morning timeline. Ultras start earlier and gear-check more."""
    if is_long_ultra:
        return [
            ("4 hrs before", "Wake; tested breakfast (oats + banana + nut butter)"),
            ("3 hrs before", "Arrive at venue; full kit-check (mandatory gear if required)"),
            ("90 min before", "Drop bags handed in; confirm crew/pacer plan and aid-station ETAs"),
            ("60 min before", "Easy 10-min walk; small snack and start sipping electrolytes"),
            ("20 min before", "Final headlamp / poles check; calm breathing, mindset reset"),
        ]
    if is_ultra:
        return [
            ("3.5 hrs before", "Wake; tested breakfast"),
            ("2.5 hrs before", "Arrive at venue, gear check (vest, poles, mandatory items)"),
            ("75 min before", "Easy hike or jog 10 min to warm legs"),
            ("30 min before", "Confirm nutrition plan, pre-race gel and electrolyte"),
            ("10 min before", "Stay calm — the first 10 km should feel slow"),
        ]
    return [
        ("3 hrs before", "Larger pre-race breakfast — you'll burn more than any road race"),
        ("2 hrs before", "Arrive at venue, gear check (poles if used, hydration vest)"),
        ("60 min before", "Easy hike or jog to warm legs"),
        ("30 min before", "Confirm nutrition plan, take an early gel if long start queue"),
        ("10 min before", "Arrive at start, stay calm"),
    ]


def _trail_extras(distance_km: float, elevation_gain_m: float, is_ultra: bool, is_long_ultra: bool) -> List[str]:
    extras = list(RACE_PROFILES[30.0].week_before_extras)  # base trail extras
    if is_ultra:
        extras += [
            "Plan crew / pacer hand-offs; print aid-station ETAs",
            "Pack drop bags with: spare socks, lube, headlamp batteries, jacket, real food",
            "Test poles on rough terrain — don't introduce them on race day",
        ]
    if is_long_ultra:
        extras += [
            "Plan a sleep strategy: brief naps at major aid stations are normal",
            "Pack two headlamps + spare batteries — assume one fails",
            "Brief crew on warning signs (slurred speech, hypothermia, wobble) and the abort plan",
        ]
    if elevation_gain_m and elevation_gain_m / max(distance_km, 1.0) >= 50.0:
        extras += [
            "Sharpen / replace deep-lug shoe outsoles for descent grip",
            "Test a windproof jacket and gloves — exposed ridges get cold quickly",
        ]
    return extras


def _trail_pacing_strategy(profile) -> str:
    """Base trail pacing copy + ultra-specific add-ons."""
    base = RACE_PROFILES[30.0].pacing_strategy
    if profile.bracket in ("ultra", "long_ultra"):
        base += (
            " Walk every uphill steeper than ~10% from the start — at this distance "
            "you cannot bank time, only debt. Eat and drink to a clock, not to thirst."
        )
    if profile.bracket == "long_ultra":
        base += (
            " Plan for a low patch around hour 6–10 and another in the dark — these "
            "pass if you keep moving, eating, and changing one small thing (socks, "
            "music, a friend on the phone)."
        )
    return base


def generate_race_protocol(
    target_distance: float,
    goal_pace_min_km: Optional[float],
    trail_profile=None,
) -> Dict[str, Any]:
    """Generate a complete race-day protocol.

    Args:
        target_distance: Race distance in km (5.0, 10.0, 21.1, 30.0, 42.2 for
            road; arbitrary in [8, 163] for trail when ``trail_profile`` is set).
        goal_pace_min_km: Target pace in min/km (from VDOT or user input), optional.
        trail_profile: Optional ``TrailProfile`` — when present, the protocol
            scales mental checkpoints to actual race distance, generates
            duration-aware fueling, and adds ultra-only sections (drop bags,
            pacer plan, night-running gear).

    Returns:
        Dict with all protocol sections for template rendering.
    """
    # Predicted finish time
    predicted_finish = None
    predicted_seconds: Optional[int] = None
    if goal_pace_min_km:
        predicted_seconds = int(target_distance * goal_pace_min_km * 60)
        predicted_finish = _seconds_to_hhmmss(predicted_seconds)

    if trail_profile is not None:
        is_ultra = trail_profile.is_ultra
        is_long_ultra = trail_profile.is_long_ultra
        return {
            "distance_name": _trail_dist_name(trail_profile),
            "predicted_finish_time": predicted_finish,
            "week_before_checklist": list(_WEEK_BEFORE) + _trail_extras(
                trail_profile.distance_km, trail_profile.elevation_gain_m,
                is_ultra, is_long_ultra,
            ),
            "race_morning_timeline": [
                {"time": t, "activity": a}
                for t, a in _trail_morning(trail_profile.distance_km, is_ultra, is_long_ultra)
            ],
            "pacing_strategy": _trail_pacing_strategy(trail_profile),
            "pacing_splits": _generate_pacing_splits(target_distance, goal_pace_min_km),
            "nutrition_timing": _trail_nutrition(trail_profile.distance_km, predicted_seconds),
            "mental_checkpoints": _trail_mental_checkpoints(trail_profile.distance_km),
            "is_trail": True,
            "elevation_gain_m": trail_profile.elevation_gain_m,
        }

    # Road path: snap to a known distance via the registry.
    profile = lookup_profile(target_distance)

    return {
        "distance_name": profile.display_name,
        "predicted_finish_time": predicted_finish,
        "week_before_checklist": list(_WEEK_BEFORE) + list(profile.week_before_extras),
        "race_morning_timeline": [
            {"time": t, "activity": a}
            for t, a in profile.morning_timeline
        ],
        "pacing_strategy": profile.pacing_strategy,
        "pacing_splits": _generate_pacing_splits(target_distance, goal_pace_min_km),
        "nutrition_timing": profile.nutrition_timing,
        "mental_checkpoints": profile.mental_checkpoints,
        "is_trail": False,
    }
