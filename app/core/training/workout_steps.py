"""Structured workout steps.

Turns a workout into a sequence of concrete, executable blocks. Each step
is a dict with:

    kind       : 'warmup' | 'run' | 'recovery' | 'cooldown' | 'strides' |
                 'walk' | 'rest'
    label      : short human-readable label ("Warm up", "5 × 400 m")
    distance_m : target distance per rep in meters (None if duration-based)
    duration_s : target duration per rep in seconds (None if distance-based)
    repeat     : how many times to perform this block (default 1)
    pace_zone  : 'E' | 'M' | 'T' | 'I' | 'R' | None
    pace_str   : injected pace string ("4:22/km"), or None
    effort     : short effort cue ("conversational", "hard", "jog", "walk")
    note       : optional tip

Watches, UI, PDF, and adaptation can all operate on this structure rather
than parsing prose descriptions. Builders here are pure functions — they
accept numbers and pace-zones, and return a list of step dicts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

STEP_KINDS = (
    "warmup", "run", "recovery", "cooldown", "strides", "walk", "rest",
)

# Default warm-up / cool-down length for quality sessions (meters).
_WARMUP_M = 2000
_COOLDOWN_M = 2000


def _pace_str(zone_key: Optional[str], pace_zones: Optional[Dict]) -> Optional[str]:
    if not pace_zones or not zone_key or zone_key not in pace_zones:
        return None
    return pace_zones[zone_key].get("pace_str")


def _step(
    kind: str,
    label: str,
    *,
    distance_m: Optional[int] = None,
    duration_s: Optional[int] = None,
    repeat: int = 1,
    pace_zone: Optional[str] = None,
    pace_str: Optional[str] = None,
    effort: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "repeat": repeat,
        "pace_zone": pace_zone,
        "pace_str": pace_str,
        "effort": effort,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Non-quality builders
# ---------------------------------------------------------------------------


def build_easy_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    with_strides: bool = False,
) -> List[Dict[str, Any]]:
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    steps = [
        _step(
            "run",
            "Easy run",
            distance_m=total_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
        )
    ]
    if with_strides:
        steps.append(
            _step(
                "strides",
                "6 × 100 m strides",
                distance_m=100,
                repeat=6,
                pace_zone="R",
                pace_str=_pace_str("R", pace_zones),
                effort="fast, controlled",
                note="Walk/jog back full recovery",
            )
        )
    return steps


def build_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    variant: str = "easy",
) -> List[Dict[str, Any]]:
    """Long run steps.

    variant: 'easy' (steady E), 'mp_finish' (80% E + 20% M), 'progression'
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    if variant == "mp_finish":
        easy_m = int(round(total_m * 0.8))
        mp_m = total_m - easy_m
        return [
            _step(
                "run",
                "Easy aerobic",
                distance_m=easy_m,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="conversational",
                note="Fuel every 45 min",
            ),
            _step(
                "run",
                "Marathon-pace finish",
                distance_m=mp_m,
                pace_zone="M",
                pace_str=_pace_str("M", pace_zones),
                effort="comfortably hard",
            ),
        ]
    if variant == "progression":
        thirds = total_m // 3
        return [
            _step(
                "run",
                "Easy start",
                distance_m=thirds,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="conversational",
            ),
            _step(
                "run",
                "Steady middle",
                distance_m=thirds,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="moderate",
                note="15 s/km faster than start",
            ),
            _step(
                "run",
                "Marathon-pace finish",
                distance_m=total_m - 2 * thirds,
                pace_zone="M",
                pace_str=_pace_str("M", pace_zones),
                effort="strong finish",
            ),
        ]
    if variant == "alternating_mp":
        return build_alternating_mp_long_steps(distance_km, pace_zones)
    if variant == "fast_finish":
        return build_fast_finish_long_steps(distance_km, pace_zones)
    if variant == "rolling_hills":
        return build_rolling_hills_long_steps(distance_km, pace_zones)
    if variant == "depletion":
        return build_depletion_long_steps(distance_km, pace_zones)
    return [
        _step(
            "run",
            "Long run",
            distance_m=total_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
            note="Fuel every 45-60 min",
        )
    ]


def build_alternating_mp_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    block_km: float = 2.0,
) -> List[Dict[str, Any]]:
    """Long run alternating easy and marathon-pace blocks.

    Example: 16 km → 4 × (2 km easy / 2 km MP).
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    block_m = int(round(block_km * 1000))
    pair_m = block_m * 2
    full_pairs = total_m // pair_m
    if full_pairs < 1:
        full_pairs = 1
        block_m = total_m // 2
    steps: List[Dict[str, Any]] = [
        _step(
            "run",
            f"Easy {block_m // 1000} km",
            distance_m=block_m,
            repeat=full_pairs,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
        ),
        _step(
            "run",
            f"Marathon-pace {block_m // 1000} km",
            distance_m=block_m,
            repeat=full_pairs,
            pace_zone="M",
            pace_str=_pace_str("M", pace_zones),
            effort="comfortably hard",
            note="Alternate easy → MP blocks. No rest.",
        ),
    ]
    remainder_m = total_m - (full_pairs * pair_m)
    if remainder_m >= 500:
        steps.append(
            _step(
                "run",
                "Easy cool",
                distance_m=remainder_m,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="easy",
            )
        )
    return steps


def build_fast_finish_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    finish_km: float = 3.0,
) -> List[Dict[str, Any]]:
    """Long run with a hard (T-pace) final segment."""
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    finish_m = min(int(round(finish_km * 1000)), max(1000, total_m // 4))
    easy_m = total_m - finish_m
    return [
        _step(
            "run",
            "Easy aerobic base",
            distance_m=easy_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
            note="Relax, save legs for the finish",
        ),
        _step(
            "run",
            f"{finish_m / 1000:.0f} km fast finish",
            distance_m=finish_m,
            pace_zone="T",
            pace_str=_pace_str("T", pace_zones),
            effort="comfortably hard → hard",
            note="Build effort through the last km",
        ),
    ]


def build_rolling_hills_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Long run on a rolling hills route at steady easy effort."""
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    return [
        _step(
            "run",
            "Rolling hills — steady",
            distance_m=total_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="by effort, not pace",
            note="Keep effort even — push up, float down.",
        )
    ]


def build_depletion_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Fasted / low-carb long run for mitochondrial adaptation (marathon)."""
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    return [
        _step(
            "run",
            "Fasted long run",
            distance_m=total_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="easy, conservative",
            note="No carbs pre-run. Water only during. Drives fat-adaptation.",
        )
    ]


# ---------------------------------------------------------------------------
# Quality builders (fallback when no key workout is selected)
# ---------------------------------------------------------------------------


def _wucd_m(total_m: int) -> int:
    """Warmup/cooldown distance that fits within the total workout distance."""
    return min(_WARMUP_M, max(500, int(round(total_m * 0.25))))


def _warmup(pace_zones: Optional[Dict], distance_m: int = _WARMUP_M) -> Dict[str, Any]:
    label = f"{distance_m / 1000:g} km warm-up"
    return _step(
        "warmup",
        label,
        distance_m=distance_m,
        pace_zone="E",
        pace_str=_pace_str("E", pace_zones),
        effort="easy",
    )


def _cooldown(pace_zones: Optional[Dict], distance_m: int = _COOLDOWN_M) -> Dict[str, Any]:
    label = f"{distance_m / 1000:g} km cool-down"
    return _step(
        "cooldown",
        label,
        distance_m=distance_m,
        pace_zone="E",
        pace_str=_pace_str("E", pace_zones),
        effort="easy",
    )


def build_tempo_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    variant: int = 0,
) -> List[Dict[str, Any]]:
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    cd_m = wu_m
    main_m = max(500, total_m - wu_m - cd_m)

    if variant == 1:
        rep_m = main_m // 3
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                f"3 × {rep_m / 1000:.1f} km",
                distance_m=rep_m,
                repeat=3,
                pace_zone="T",
                pace_str=_pace_str("T", pace_zones),
                effort="comfortably hard",
            ),
            _step(
                "recovery",
                "3 min jog recovery",
                duration_s=180,
                repeat=2,
                pace_zone="E",
                effort="jog",
            ),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 2:
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                f"{main_m / 1000:.1f} km tempo with surges",
                distance_m=main_m,
                pace_zone="T",
                pace_str=_pace_str("T", pace_zones),
                effort="comfortably hard",
                note="4 × 30 s faster surges within the tempo block",
            ),
            _cooldown(pace_zones, cd_m),
        ]

    return [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            f"{main_m / 1000:.1f} km tempo",
            distance_m=main_m,
            pace_zone="T",
            pace_str=_pace_str("T", pace_zones),
            effort="comfortably hard",
            note="Relaxed rhythm, not a race",
        ),
        _cooldown(pace_zones, cd_m),
    ]


def build_interval_steps(
    distance_km: float,
    total_km: float,
    pace_zones: Optional[Dict] = None,
    variant: int = 0,
    reps_400: int = 0,
    reps_800: int = 0,
    reps_1000: int = 0,
    reps_200: int = 0,
) -> List[Dict[str, Any]]:
    """Interval session — step structure matches the selected description variant.

    The 50 km/week threshold matches ``generate_interval_run`` so the
    description variant table and the step variant table are sized
    identically. Below that, 400 m reps are the default.
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    cd_m = wu_m
    work_m = max(1600, total_m - wu_m - cd_m)

    if total_km >= 50:
        default_rep_m = 800
    else:
        default_rep_m = 400

    default_reps = max(4, work_m // default_rep_m)

    if total_km >= 50:
        return _build_interval_steps_high_base(
            variant, pace_zones, reps_400 or default_reps,
            reps_800 or default_reps, reps_1000 or max(3, work_m // 2000),
            wu_m, cd_m,
        )
    return _build_interval_steps_low_base(
        variant, pace_zones, default_reps,
        reps_400 or default_reps, reps_800 or max(3, work_m // 1600),
        reps_200 or max(6, work_m // 400),
        wu_m, cd_m,
    )


def _build_interval_steps_high_base(
    variant: int,
    pace_zones: Optional[Dict],
    reps_400: int,
    reps_800: int,
    reps_1000: int,
    wu_m: int = _WARMUP_M,
    cd_m: int = _COOLDOWN_M,
) -> List[Dict[str, Any]]:
    if variant == 1:
        return [
            _warmup(pace_zones, wu_m),
            _step("run", "400 m", distance_m=400, pace_zone="I",
                  pace_str=_pace_str("I", pace_zones), effort="hard"),
            _step("run", "800 m", distance_m=800, pace_zone="I",
                  pace_str=_pace_str("I", pace_zones), effort="hard"),
            _step("run", "1200 m", distance_m=1200, pace_zone="I",
                  pace_str=_pace_str("I", pace_zones), effort="hard"),
            _step("run", "800 m", distance_m=800, pace_zone="I",
                  pace_str=_pace_str("I", pace_zones), effort="hard"),
            _step("run", "400 m", distance_m=400, pace_zone="I",
                  pace_str=_pace_str("I", pace_zones), effort="hard"),
            _step("recovery", "Equal-distance recovery jog", effort="jog"),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 2:
        return [
            _warmup(pace_zones, wu_m),
            _step("run", "8 × 45 s hill repeats", duration_s=45, repeat=8,
                  pace_zone="T", pace_str=_pace_str("T", pace_zones),
                  effort="hard uphill"),
            _step("recovery", "Jog-down recovery", duration_s=90, repeat=8,
                  effort="jog"),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 3:
        return [
            _warmup(pace_zones, wu_m),
            _step("run", f"{reps_800} × 800 m (Yasso)", distance_m=800,
                  repeat=reps_800, pace_zone="M",
                  pace_str=_pace_str("M", pace_zones), effort="hard"),
            _step("recovery", "Equal-time jog recovery", duration_s=180,
                  repeat=reps_800 - 1, pace_zone="E", effort="jog"),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 4:
        return [
            _warmup(pace_zones, wu_m),
            _step("run", f"{reps_1000} × 1000 m", distance_m=1000,
                  repeat=reps_1000, pace_zone="I",
                  pace_str=_pace_str("I", pace_zones), effort="hard"),
            _step("recovery", "400 m jog recovery", distance_m=400,
                  repeat=reps_1000 - 1, pace_zone="E", effort="jog"),
            _cooldown(pace_zones, cd_m),
        ]

    return [
        _warmup(pace_zones, wu_m),
        _step("run", f"{reps_400} × 400 m", distance_m=400, repeat=reps_400,
              pace_zone="I", pace_str=_pace_str("I", pace_zones), effort="hard"),
        _step("recovery", "400 m jog recovery", distance_m=400,
              repeat=reps_400 - 1, pace_zone="E", effort="jog"),
        _cooldown(pace_zones, cd_m),
    ]


def _build_interval_steps_low_base(
    variant: int,
    pace_zones: Optional[Dict],
    default_reps: int,
    reps_400: int,
    reps_800: int,
    reps_200: int,
    wu_m: int = _WARMUP_M,
    cd_m: int = _COOLDOWN_M,
) -> List[Dict[str, Any]]:
    if variant == 1:
        return [
            _warmup(pace_zones, wu_m),
            _step("run", f"{reps_800} × 800 m", distance_m=800, repeat=reps_800,
                  pace_zone="T", pace_str=_pace_str("T", pace_zones),
                  effort="comfortably hard"),
            _step("recovery", "90 s rest", duration_s=90,
                  repeat=reps_800 - 1, pace_zone="E", effort="jog"),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 2:
        return [
            _warmup(pace_zones, wu_m),
            _step("run", f"{reps_200} × 200 m", distance_m=200, repeat=reps_200,
                  pace_zone="R", pace_str=_pace_str("R", pace_zones), effort="fast"),
            _step("recovery", "200 m jog recovery", distance_m=200,
                  repeat=reps_200 - 1, pace_zone="E", effort="jog"),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 3:
        return [
            _warmup(pace_zones, wu_m),
            _step("run", "8 × 30 s hill repeats", duration_s=30, repeat=8,
                  pace_zone="R", effort="hard uphill"),
            _step("recovery", "Walk-down recovery", duration_s=60, repeat=8,
                  effort="walk"),
            _cooldown(pace_zones, cd_m),
        ]

    return [
        _warmup(pace_zones, wu_m),
        _step("run", f"{reps_400} × 400 m", distance_m=400, repeat=reps_400,
              pace_zone="I", pace_str=_pace_str("I", pace_zones), effort="hard"),
        _step("recovery", "90 s jog recovery", duration_s=90,
              repeat=reps_400 - 1, pace_zone="E", effort="jog"),
        _cooldown(pace_zones, cd_m),
    ]


def build_hill_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    total_m = max(0, int(round(distance_km * 1000)))
    wu_m = _wucd_m(total_m) if total_m > 0 else _WARMUP_M
    cd_m = wu_m
    return [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            "10 × 30 s hill",
            duration_s=30,
            repeat=10,
            pace_zone="R",
            effort="hard uphill",
            note="Strong arms, quick turnover",
        ),
        _step(
            "recovery",
            "Walk down recovery",
            duration_s=60,
            repeat=10,
            effort="walk",
        ),
        _cooldown(pace_zones, cd_m),
    ]


# ---------------------------------------------------------------------------
# Key-workout parser — delegated to key_workout_parser module
# ---------------------------------------------------------------------------

from app.core.training.key_workout_parser import parse_key_workout_steps  # noqa: F401


# Default pace estimates (min/km) for time-based workouts when no VDOT data.
_DEFAULT_PACES = {
    "E": 8.0,   # Easy pace
    "T": 6.5,   # Tempo/threshold pace
    "I": 5.5,   # Interval/VO2max pace
    "M": 6.0,   # Marathon pace
    "R": 5.0,   # Repetition/speed pace
}


def _parse_pace_str_to_min_per_km(pace_str: Optional[str], pace_zone: Optional[str] = None) -> Optional[float]:
    """Parse pace string like '6:22/km' or '7:05-7:55/km' to min/km float.

    For ranges like '5:54-5:16/km' (slow-fast format), uses the slower pace
    (first value) for conservative distance estimates.
    """
    if pace_str:
        pace_str = pace_str.replace("/km", "").strip()
        # Handle both en-dash (–) and regular hyphen (-)
        if "–" in pace_str:
            pace_str = pace_str.split("–")[0].strip()
        elif "-" in pace_str:
            pace_str = pace_str.split("-")[0].strip()
        parts = pace_str.split(":")
        if len(parts) == 2:
            try:
                return int(parts[0]) + int(parts[1]) / 60.0
            except ValueError:
                pass
    if pace_zone and pace_zone in _DEFAULT_PACES:
        return _DEFAULT_PACES[pace_zone]
    return None


def _compute_distance_from_steps(steps: List[Dict[str, Any]]) -> float:
    """Compute total distance in km from workout steps.

    For distance-based steps, uses distance_m directly.
    For duration-based steps, calculates distance from duration and pace.
    """
    total_m = 0
    for s in steps:
        if s.get("distance_m"):
            total_m += s["distance_m"] * s.get("repeat", 1)
        elif s.get("duration_s"):
            pace_min_km = _parse_pace_str_to_min_per_km(
                s.get("pace_str"), s.get("pace_zone")
            )
            if pace_min_km and pace_min_km > 0:
                duration_min = s["duration_s"] / 60.0
                distance_km = duration_min / pace_min_km
                total_m += distance_km * 1000 * s.get("repeat", 1)
    return total_m / 1000.0


# ---------------------------------------------------------------------------
# Scaling — for adaptation
# ---------------------------------------------------------------------------


def scale_steps(
    steps: List[Dict[str, Any]], multiplier: float
) -> List[Dict[str, Any]]:
    """Scale distance/duration of each step by a multiplier.

    Used by adaptation when a week's total distance is adjusted — keeps
    step proportions intact rather than blanket-scaling the whole workout.
    Warm-up and cool-down are NOT scaled (they're absolute).
    """
    if not steps or multiplier == 1.0:
        return steps
    scaled = []
    for s in steps:
        if s["kind"] in ("warmup", "cooldown", "rest"):
            scaled.append(dict(s))
            continue
        new = dict(s)
        if s.get("distance_m"):
            new["distance_m"] = int(round(s["distance_m"] * multiplier))
        if s.get("duration_s"):
            new["duration_s"] = int(round(s["duration_s"] * multiplier))
        scaled.append(new)
    return scaled


def total_distance_m(steps: List[Dict[str, Any]]) -> int:
    """Sum total meters across all step reps (for validation)."""
    total = 0
    for s in steps:
        if s.get("distance_m"):
            total += s["distance_m"] * s.get("repeat", 1)
    return total
