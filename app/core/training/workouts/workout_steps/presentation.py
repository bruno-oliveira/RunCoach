"""Display model for a structured session: grouped blocks plus an effort profile.

The day card, the day drill-down and the PDF all show a session's steps. They
used to print the flat step list line by line, which hid the one thing a runner
needs at a glance — *what repeats, and how hard each part is* — and let each
surface drift from what the watch actually runs.

:func:`session_view` builds that picture once, from the same grouping
(:func:`~.structure.group_steps`) and the same pace resolution
(:func:`~.intervals_export.resolve_pace_bounds`) as the watch export, so what
the page shows is what the wrist will beep. The screens read this instead of
re-deriving structure in templates.

Pure — no I/O.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.core.training.workouts.workout_steps.intervals_export import (
    _parse_pace_bounds,
    is_hill,
    is_open_effort,
    is_walk,
    resolve_pace_bounds,
    zone_paces_of,
)
from app.core.training.workouts.workout_steps.metrics import _DEFAULT_PACES
from app.core.training.workouts.workout_steps.structure import (
    group_steps,
    is_recovery,
)
from app.utils import format_km

# Effort level 0 (standing) .. 5 (flat out). Drives the profile bar's height
# and colour, and the dot beside each step.
_ZONE_LEVELS = {
    "E": 2,
    "M": 3,
    "race": 3,
    "T": 4,
    "10K": 4,
    "I": 5,
    "5K": 5,
    "R": 5,
}

_ZONE_NAMES = {
    "E": "Easy",
    "M": "Marathon pace",
    "race": "Race pace",
    "T": "Threshold",
    "10K": "10K pace",
    "I": "Interval pace",
    "5K": "5K pace",
    "R": "Fast",
}

_REP_PREFIX = re.compile(r"^\s*\d+\s*[×x]\s*")
_BARE_AMOUNT = re.compile(r"^[\d.,:]+\s*(km|m|s|min)?$", re.IGNORECASE)
# "400 m jog recovery" -> "jog recovery": the amount already has its column.
_LEADING_AMOUNT = re.compile(r"^[\d.,:]+\s*(km|m|s|min)\s+(?=[a-z])")


def _level(step: dict[str, Any]) -> int:
    kind = step.get("kind")
    if kind == "rest":
        return 0
    if is_walk(step) or step.get("implied"):
        return 1
    if kind == "recovery":
        return 1
    if kind in ("warmup", "cooldown"):
        return 2
    if kind == "strides" or is_hill(step):
        return 5
    return _ZONE_LEVELS.get(step.get("pace_zone") or "", 2)


def _name(step: dict[str, Any]) -> str:
    kind = step.get("kind")
    if kind == "warmup":
        return "Warm-up"
    if kind == "cooldown":
        return "Cool-down"
    label = _REP_PREFIX.sub("", str(step.get("label") or "")).strip()
    label = _LEADING_AMOUNT.sub("", label)
    if label and not _BARE_AMOUNT.match(label):
        return label[0].upper() + label[1:]
    if kind == "rest":
        return "Rest"
    if kind == "recovery":
        return "Walk" if is_walk(step) else "Recovery jog"
    if kind == "walk":
        return "Walk"
    if kind == "strides":
        return "Stride"
    return _ZONE_NAMES.get(step.get("pace_zone") or "", "Run")


def _amount(step: dict[str, Any]) -> Optional[str]:
    distance_m = step.get("distance_m")
    if distance_m:
        if distance_m >= 1000:
            return f"{format_km(distance_m / 1000)} km"
        return f"{int(round(distance_m))} m"
    duration_s = step.get("duration_s")
    if duration_s:
        minutes, seconds = divmod(int(duration_s), 60)
        if not minutes:
            return f"{seconds} s"
        if not seconds:
            return f"{minutes} min"
        if minutes == 1:
            return f"{int(duration_s)} s"
        return f"{minutes}:{seconds:02d} min"
    return None


def _fmt_pace(min_per_km: float) -> str:
    total = int(round(min_per_km * 60))
    return f"{total // 60}:{total % 60:02d}"


def format_pace_range(pace_str: Optional[str]) -> Optional[str]:
    """Any stored pace string, fast-first: ``5:26/km–4:50/km`` -> ``4:50–5:26 /km``."""
    return _pace_text(_parse_pace_bounds(pace_str) or None)


def _pace_text(bounds: Optional[list[float]]) -> Optional[str]:
    if not bounds:
        return None
    if len(bounds) == 1:
        return f"{_fmt_pace(bounds[0])} /km"
    return f"{_fmt_pace(min(bounds))}–{_fmt_pace(max(bounds))} /km"


def _seconds(step: dict[str, Any], bounds: Optional[list[float]]) -> float:
    """Estimated seconds for one rep of a step (for proportions only)."""
    if step.get("duration_s"):
        return float(step["duration_s"])
    distance_m = step.get("distance_m") or 0
    if not distance_m:
        return 0.0
    if bounds:
        pace = sum(bounds) / len(bounds)
    elif is_walk(step):
        pace = _DEFAULT_PACES["WALK"]
    else:
        pace = _DEFAULT_PACES.get(step.get("pace_zone") or "", _DEFAULT_PACES["E"])
    return distance_m / 1000.0 * pace * 60.0


def _step_view(step: dict[str, Any], zone_paces: dict[str, str]) -> dict[str, Any]:
    bounds = resolve_pace_bounds(step, zone_paces, allow_default=False)
    return {
        "kind": step.get("kind"),
        "name": _name(step),
        "amount": _amount(step),
        "pace": _pace_text(bounds),
        "by_feel": is_open_effort(step),
        "zone": step.get("pace_zone") if step.get("pace_zone") != "WALK" else None,
        "effort": step.get("effort"),
        "note": step.get("note"),
        "level": _level(step),
        "is_recovery": is_recovery(step),
        "implied": bool(step.get("implied")),
        "seconds": _seconds(step, bounds),
    }


def _fmt_total(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d}"


def _formula(blocks: list[dict[str, Any]]) -> str:
    """The repeated sets in one line: ``5 × 400 m / 90 s · 4 × 200 m``."""
    parts = []
    for block in blocks:
        if block["repeat"] <= 1:
            continue
        work = [v["amount"] for v in block["steps"] if not v["is_recovery"]]
        rest = [v["amount"] for v in block["steps"] if v["is_recovery"]]
        text = f"{block['repeat']} × {' + '.join(a for a in work if a)}"
        if all(v["kind"] == "strides" for v in block["steps"] if not v["is_recovery"]):
            parts.append(f"{text} strides")
            continue
        if any(rest):
            text += f" / {' + '.join(a for a in rest if a)}"
        parts.append(text)
    return " · ".join(parts)


def session_view(steps: Optional[list[dict[str, Any]]]) -> Optional[dict[str, Any]]:
    """Grouped, display-ready view of a session, or None when there are no steps.

    Returns:
        ``{"blocks": [...], "profile": [...], "total": "52 min",
        "has_repeats": bool, "formula": "5 × 400 m / 90 s"}``. ``formula``
        is the main set in one line (None for a session with no repeats). Each block carries ``repeat``,
        ``skip_last_recovery`` and its display ``steps``; ``profile`` is the
        session expanded rep by rep into ``{"level", "share", "title"}``
        segments whose shares sum to ~100, for drawing the effort bar.
    """
    if not steps:
        return None
    zone_paces = zone_paces_of(steps)
    blocks: list[dict[str, Any]] = []
    profile: list[dict[str, Any]] = []
    total_s = 0.0

    for block in group_steps(steps):
        views = [_step_view(s, zone_paces) for s in block["steps"]]
        reps = block["repeat"]
        for rep in range(reps):
            last = rep == reps - 1
            for view in views:
                if last and block["skip_last_recovery"] and view["is_recovery"]:
                    continue
                if view["seconds"] <= 0:
                    continue
                total_s += view["seconds"]
                profile.append(
                    {
                        "level": view["level"],
                        "seconds": view["seconds"],
                        "title": " · ".join(
                            p for p in (view["amount"], view["name"], view["pace"]) if p
                        ),
                    }
                )
        blocks.append(
            {
                "repeat": reps,
                "skip_last_recovery": block["skip_last_recovery"],
                "steps": views,
            }
        )

    formula = _formula(blocks) if any(b["repeat"] > 1 for b in blocks) else None
    for seg in profile:
        seg["share"] = round(seg.pop("seconds") / total_s * 100, 2) if total_s else 0
    return {
        "blocks": blocks,
        "profile": profile,
        "total": _fmt_total(total_s) if total_s else None,
        "has_repeats": formula is not None,
        "formula": formula,
    }
