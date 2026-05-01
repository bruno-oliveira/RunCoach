"""Key-workout structure string parser.

Turns a key-workout `structure` text into a list of executable step dicts.
Extracted from workout_steps.py to separate text-parsing concerns from
step builders.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.training.workout_steps import (
    _step,
    _pace_str,
    _warmup,
    _cooldown,
    _wucd_m,
)

_PACE_ZONE_PATTERNS = [
    (r"\b5K pace\b|\bVO₂max\b|\bVO2max\b|\bI[- ]pace\b", "I"),
    (r"\b10[Kk] (?:goal )?pace\b", "10K"),
    (r"\bthreshold\b|\btempo pace\b|\bT[- ]pace\b", "T"),
    (r"\bmarathon (?:goal )?pace\b|\bMP\b|\bM[- ]pace\b", "M"),
    (r"\beasy(?:\s+(?:pace|effort))\b|\bE[- ]pace\b|\bconversational\b", "E"),
    (r"\brepetition\b|\bR[- ]pace\b|\b5K[- ]?10K sprint\b", "R"),
]


def _infer_zone(text: str) -> Optional[str]:
    for pattern, zone in _PACE_ZONE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return zone
    return None


def _parse_distance_to_m(value: str, unit: str) -> int:
    num = float(value)
    return int(round(num * 1000)) if unit.lower() == "km" else int(round(num))


def _parse_duration_to_s(value: str, unit: str) -> int:
    num = float(value)
    unit = unit.lower()
    if unit.startswith("min"):
        return int(round(num * 60))
    return int(round(num))


def _try_progression_pattern(structure: str, pace_zones: Optional[Dict]) -> Optional[List[Dict[str, Any]]]:
    """Pattern A: "Nkm: first Xkm easy, last Ykm at ... pace" (progression runs)."""
    m = re.search(
        r"(\d+(?:-\d+)?)\s*km[^:]*:\s*first\s+(\d+(?:\.\d+)?)\s*km\s+(\w+)[^,]*,\s*(?:last|final)\s+(\d+(?:-\d+)?)\s*km\s+at\s+([^.]+)",
        structure,
        re.IGNORECASE,
    )
    if not m:
        return None
    easy_m = _parse_distance_to_m(m.group(2), "km")
    last_km = m.group(4).split("-")[-1]
    finish_m = _parse_distance_to_m(last_km, "km")
    finish_zone = _infer_zone(m.group(5)) or "M"
    return [
        _step("run", "Easy start", distance_m=easy_m, pace_zone="E",
              pace_str=_pace_str("E", pace_zones), effort="conversational"),
        _step("run", "Faster finish", distance_m=finish_m, pace_zone=finish_zone,
              pace_str=_pace_str(finish_zone, pace_zones), effort="comfortably hard"),
    ]


def _try_as_progression_pattern(
    structure: str, pace_zones: Optional[Dict],
    has_wcd: bool, warmup_steps: List, cd_m: Optional[int] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Pattern A2: "Nkm as a progression: ..." (tempo progression runs)."""
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*km\s+as\s+a\s+progression",
        structure,
        re.IGNORECASE,
    )
    if not m:
        return None
    dist_m = _parse_distance_to_m(m.group(1), "km")
    zone = _infer_zone(structure) or "T"
    steps = list(warmup_steps)
    steps.append(
        _step("run", "Tempo progression", distance_m=dist_m, pace_zone=zone,
              pace_str=_pace_str(zone, pace_zones), effort="build to tempo")
    )
    if has_wcd:
        steps.append(_cooldown(pace_zones, cd_m) if cd_m else _cooldown(pace_zones))
    return steps


def _try_distance_reps_pattern(
    structure: str, pace_zones: Optional[Dict], workout_type: str,
    has_wcd: bool, warmup_steps: List, cd_m: Optional[int] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Pattern B: "N x Dm/km at ... with Y recovery"."""
    m = re.search(
        r"(\d+)(?:-\d+)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(km|m)\s+at\s+([^,]+?)(?:\s+with\s+(\d+(?:\.\d+)?)\s*(min|sec|s)\s+(?:easy\s+jog\s+)?recovery)?(?:\s*\.|$)",
        structure,
        re.IGNORECASE,
    )
    if not m:
        return None
    reps = int(m.group(1))
    rep_m = _parse_distance_to_m(m.group(2), m.group(3))
    zone = _infer_zone(m.group(4)) or ("T" if workout_type == "tempo" else "I")
    rep_label = f"{reps} × {rep_m / 1000:.1f} km" if rep_m >= 1000 else f"{reps} × {rep_m} m"
    steps = list(warmup_steps)
    steps.append(
        _step("run", rep_label, distance_m=rep_m, repeat=reps, pace_zone=zone,
              pace_str=_pace_str(zone, pace_zones),
              effort="hard" if zone in ("I", "R") else "comfortably hard")
    )
    if m.group(5):
        rec_s = _parse_duration_to_s(m.group(5), m.group(6))
        steps.append(_step("recovery", f"{rec_s} s jog between reps",
                           duration_s=rec_s, repeat=reps - 1, effort="jog"))
    if has_wcd:
        steps.append(_cooldown(pace_zones, cd_m) if cd_m else _cooldown(pace_zones))
    return steps


def _try_duration_reps_pattern(
    structure: str, pace_zones: Optional[Dict],
    has_wcd: bool, warmup_steps: List, cd_m: Optional[int] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Pattern C: "N x Dsec/min uphill/at ..."."""
    m = re.search(
        r"(\d+)(?:-\d+)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(sec|min|s)\s+([^.]+?)(?:\.|$)",
        structure,
        re.IGNORECASE,
    )
    if not m:
        return None
    reps = int(m.group(1))
    dur_s = _parse_duration_to_s(m.group(2), m.group(3))
    desc = m.group(4).strip()
    zone = _infer_zone(desc) or "I"
    cue = desc.split(" ")[0].lower()
    steps = list(warmup_steps)
    steps.append(
        _step("run", f"{reps} × {dur_s} s {cue}" if cue else f"{reps} × {dur_s} s",
              duration_s=dur_s, repeat=reps, pace_zone=zone,
              pace_str=_pace_str(zone, pace_zones), effort="hard")
    )
    if has_wcd:
        steps.append(_cooldown(pace_zones, cd_m) if cd_m else _cooldown(pace_zones))
    return steps


def _try_fartlek_pattern(
    structure: str, pace_zones: Optional[Dict],
    has_wcd: bool, warmup_steps: List, cd_m: Optional[int] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Pattern C2: fartlek "N x (Dmin hard / Dmin easy)"."""
    m = re.search(
        r"(\d+)\s*[x\xd7]\s*\(\s*(\d+)\s*(min|sec|s)\s+(?:at\s+)?([^/]+?)\s*/\s*(\d+)\s*(min|sec|s)\s+([^)]+?)\s*\)",
        structure,
        re.IGNORECASE,
    )
    if not m:
        return None
    reps = int(m.group(1))
    on_s = _parse_duration_to_s(m.group(2), m.group(3))
    on_desc = m.group(4).strip()
    off_s = _parse_duration_to_s(m.group(5), m.group(6))
    zone = _infer_zone(on_desc) or "T"
    on_label = f"{on_s // 60} min" if on_s >= 60 else f"{on_s} s"
    off_label = f"{off_s // 60} min" if off_s >= 60 else f"{off_s} s"
    steps = list(warmup_steps)
    steps.append(
        _step("run", f"{reps} × {on_label} on / {off_label} off",
              duration_s=on_s, repeat=reps, pace_zone=zone,
              pace_str=_pace_str(zone, pace_zones), effort="hard")
    )
    if has_wcd:
        steps.append(_cooldown(pace_zones, cd_m) if cd_m else _cooldown(pace_zones))
    return steps


def _try_continuous_pattern(
    structure: str, pace_zones: Optional[Dict], workout_type: str,
    has_wcd: bool, warmup_steps: List, cd_m: Optional[int] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Pattern D: "Xkm continuous at X pace"."""
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*km\s+continuous\s+at\s+([^,.]+)",
        structure,
        re.IGNORECASE,
    )
    if not m:
        return None
    dist_m = _parse_distance_to_m(m.group(1), "km")
    zone = _infer_zone(m.group(2)) or ("T" if workout_type == "tempo" else "M")
    steps = list(warmup_steps)
    steps.append(
        _step("run", f"{dist_m / 1000:.1f} km continuous", distance_m=dist_m,
              pace_zone=zone, pace_str=_pace_str(zone, pace_zones), effort="comfortably hard")
    )
    if has_wcd:
        steps.append(_cooldown(pace_zones, cd_m) if cd_m else _cooldown(pace_zones))
    return steps


def parse_key_workout_steps(
    structure: str,
    pace_zones: Optional[Dict] = None,
    workout_type: str = "interval",
    default_zone: Optional[str] = None,
    total_distance_km: float = 0,
) -> List[Dict[str, Any]]:
    """Best-effort parser turning a key-workout `structure` into steps.

    Falls back to a single main block labelled with the structure text if
    no pattern matches.
    """
    structure = structure.strip()
    has_wcd = workout_type in ("interval", "tempo", "hill")
    if has_wcd and total_distance_km > 0:
        wu_m = _wucd_m(int(round(total_distance_km * 1000)))
        warmup_steps = [_warmup(pace_zones, wu_m)]
    else:
        wu_m = None
        warmup_steps = [_warmup(pace_zones)] if has_wcd else []

    result = _try_progression_pattern(structure, pace_zones)
    if result is not None:
        return result

    result = _try_as_progression_pattern(structure, pace_zones, has_wcd, warmup_steps, wu_m)
    if result is not None:
        return result

    result = _try_distance_reps_pattern(structure, pace_zones, workout_type, has_wcd, warmup_steps, wu_m)
    if result is not None:
        return result

    result = _try_duration_reps_pattern(structure, pace_zones, has_wcd, warmup_steps, wu_m)
    if result is not None:
        return result

    result = _try_fartlek_pattern(structure, pace_zones, has_wcd, warmup_steps, wu_m)
    if result is not None:
        return result

    result = _try_continuous_pattern(structure, pace_zones, workout_type, has_wcd, warmup_steps, wu_m)
    if result is not None:
        return result

    fallback = "T" if workout_type == "tempo" else "I"
    zone = _infer_zone(structure) or default_zone or fallback
    effort = "easy" if zone == "E" else "see description"
    steps = list(warmup_steps)
    steps.append(
        _step("run", structure[:60], pace_zone=zone,
              pace_str=_pace_str(zone, pace_zones), effort=effort)
    )
    if has_wcd:
        cd_m = wu_m if wu_m else None
        steps.append(_cooldown(pace_zones, cd_m) if cd_m else _cooldown(pace_zones))
    return steps
