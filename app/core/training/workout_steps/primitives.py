"""Step primitives: the step dict factory and warm-up/cool-down helpers.

Pure building blocks shared by every workout-step builder. No I/O.
See the package ``__init__`` for the step-dict schema.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional

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

# Session types whose work is at interval intensity or faster (VO2max reps,
# hill repeats, race-pace efforts at 10K-or-faster). These earn the longer
# warm-up profile: starting 400 m reps off a 500 m jog is an injury risk, not
# a time saving.
HARD_SESSION_TYPES = frozenset({"interval", "hill", "vo2max", "race_pace"})

# Ambient warm-up/cool-down profile for the current workout. Key-workout
# entry points (overlay, reconcile, step building) set this from the
# workout's type so every helper that sizes a warm-up — the step builders
# AND the prose-rewrite arithmetic in rewrites.py — reads the same profile
# without threading a flag through every rep-count helper and lambda.
# Generic builders (tempo/interval/hill in quality.py) know their own type
# and pass ``hard`` explicitly instead.
_WUCD_HARD: ContextVar[bool] = ContextVar("wucd_hard", default=False)


@contextmanager
def wucd_profile(workout_type: Optional[str]) -> Iterator[None]:
    """Scope the warm-up/cool-down profile to ``workout_type``.

    Wrap any region that renders a key workout's prose or steps so
    :func:`_wucd_m` picks the hard or tempo profile matching the session.
    """
    token = _WUCD_HARD.set(workout_type in HARD_SESSION_TYPES)
    try:
        yield
    finally:
        _WUCD_HARD.reset(token)


# Warm-up/cool-down profiles: (floor_m, share_of_session, cap_m).
_WUCD_TEMPO_PROFILE = (800, 0.18, 1600)
_WUCD_HARD_PROFILE = (1000, 0.22, 2000)


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


def _wucd_m(total_m: int, hard: Optional[bool] = None) -> int:
    """Warm-up / cool-down distance (metres) that fits the workout.

    A warm-up and cool-down are bookends, not the session: at 25% each they
    consumed half of every sub-8 km quality workout, leaving a sub-Daniels
    working set (a 4 km tempo became 2 km of threshold, ~10 min). The share
    caps at 18% for tempo-grade work and 22% for hard sessions, with the
    absolute length bounded so bigger sessions' bookends stop scaling.

    Hard sessions (interval/hill/VO2max/race-pace — see
    :data:`HARD_SESSION_TYPES`) floor at 1 km: a runner should never open
    400 m reps at 5K pace off a 500 m jog. Tempo-grade sessions floor at
    800 m. Either way the two bookends combined never claim more than half
    the session, so the working set stays the majority of the day even on
    tiny slots. ``hard=None`` reads the ambient :func:`wucd_profile` scope
    (default: tempo profile).

    Snapped to whole 100 m increments so the value, shown as kilometres,
    already has at most one decimal place (e.g. 700 m -> 0.7 km) and survives
    one-decimal truncation unchanged. This keeps the executable step distance
    and the distance cited in the description identical: both are derived from
    this single helper, and neither can drift to a 3-decimal figure like
    0.775 km. Floors (rather than rounds) to the 100 m below so the warm-up
    never claims more distance than its share of the workout.
    """
    if hard is None:
        hard = _WUCD_HARD.get()
    floor_m, share, cap_m = _WUCD_HARD_PROFILE if hard else _WUCD_TEMPO_PROFILE
    raw = min(cap_m, max(floor_m, int(total_m * share)))
    raw = min(raw, total_m // 4)
    return max(0, (raw // 100) * 100)


def _wucd_m_for_work(work_m: int, hard: Optional[bool] = None) -> int:
    """Bookend length for a session defined bottom-up by its work size.

    The performance-family builders pick the work distance first (e.g. "8 km
    of threshold") and wrap bookends around it, so the session total isn't
    known yet. Estimate it by inverting the profile share (work is what's
    left after two bookends) and delegate to :func:`_wucd_m` so both
    construction directions apply the identical policy.
    """
    if hard is None:
        hard = _WUCD_HARD.get()
    _, share, _ = _WUCD_HARD_PROFILE if hard else _WUCD_TEMPO_PROFILE
    if work_m <= 0:
        return 0
    est_total = int(work_m / (1.0 - 2.0 * share))
    return _wucd_m(est_total, hard)


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
