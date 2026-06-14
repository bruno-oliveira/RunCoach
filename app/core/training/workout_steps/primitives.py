"""Step primitives: the step dict factory and warm-up/cool-down helpers.

Pure building blocks shared by every workout-step builder. No I/O.
See the package ``__init__`` for the step-dict schema.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.utils import format_km

STEP_KINDS = (
    "warmup",
    "run",
    "recovery",
    "cooldown",
    "strides",
    "walk",
    "rest",
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


def _wucd_m(total_m: int) -> int:
    """Warm-up / cool-down distance (metres) that fits the workout.

    Snapped to whole 100 m increments so the value, shown as kilometres,
    already has at most one decimal place (e.g. 700 m -> 0.7 km) and survives
    one-decimal truncation unchanged. This keeps the executable step distance
    and the distance cited in the description identical: both are derived from
    this single helper, and neither can drift to a 3-decimal figure like
    0.775 km. Floors (rather than rounds) to the 100 m below so the warm-up
    never claims more distance than 25% of the workout.
    """
    raw = min(_WARMUP_M, max(500, int(total_m * 0.25)))
    return (raw // 100) * 100


def _warmup(pace_zones: Optional[Dict], distance_m: int = _WARMUP_M) -> Dict[str, Any]:
    label = f"{format_km(distance_m / 1000)} km warm-up"
    return _step(
        "warmup",
        label,
        distance_m=distance_m,
        pace_zone="E",
        pace_str=_pace_str("E", pace_zones),
        effort="easy",
    )


def _cooldown(
    pace_zones: Optional[Dict], distance_m: int = _COOLDOWN_M
) -> Dict[str, Any]:
    label = f"{format_km(distance_m / 1000)} km cool-down"
    return _step(
        "cooldown",
        label,
        distance_m=distance_m,
        pace_zone="E",
        pace_str=_pace_str("E", pace_zones),
        effort="easy",
    )
