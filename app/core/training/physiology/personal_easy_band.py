"""The runner's own easy pace, in place of the one their VDOT implies.

Daniels' easy band is a fixed slice of VDOT, and a plan's VDOT is read off the
runner's hardest recent efforts — so the band says what easy *would* be for a
runner of that speed, not what it is for this one. The two disagree in both
directions: a runner who has not raced lately is scored from training runs
taken as races and is handed an easy band well slower than they jog, while a
runner with one good race is handed one faster than their heart rate allows.

What a runner actually does at an easy heart rate is a measurement, so it wins:
the band is the median pace of their recent runs whose average heart rate sat
in their own aerobic zones, fifteen seconds either side. Heart rate decides
*which* runs count; it never sets the pace. Only the easy band moves — the
quality paces stay on VDOT, because jogging faster at the same heart rate does
not show that threshold moved with it.

Pure: the caller gathers the runs and the heart-rate ceiling.
"""

import statistics
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from app.core.training.physiology.vdot_calculator import TRAIL_ELEVATION_M_PER_KM
from app.utils import format_pace

# How far back runs speak for the pace the runner jogs at today. Shorter than
# the 12 weeks fitness is read over: an easy pace drifts with the season, and
# a band built from spring would prescribe spring.
EASY_PACE_WINDOW_DAYS = 42
# Fewer easy runs than this and the median is one outing's weather.
MIN_EASY_RUNS = 4
# Below this a run is a warm-up or a shakeout, jogged slower than easy.
_MIN_DISTANCE_KM = 3.0

# The band is the measured pace this far either side (min/km): 15 s.
EASY_BAND_HALF_WIDTH = 0.25
# A stored band follows the runner only once their pace has moved this many
# seconds per km. Every re-pace deletes and re-creates watch events, so the
# calendar should not churn over a second or two of noise.
EASY_PACE_MIN_SHIFT_SEC = 5
# Easy must stay clear of threshold, whatever was measured: a band reaching
# tempo pace says the VDOT is wrong, not that the runner jogs at threshold.
_THRESHOLD_GAP = 10 / 60
# A band squeezed thinner than this by the threshold guard is not a band.
_MIN_BAND_WIDTH = EASY_BAND_HALF_WIDTH
# Recovery sits below easy; this is how far it reaches past the slow edge.
_RECOVERY_WIDTH = 0.5


@dataclass(frozen=True)
class EasyRunSample:
    """The four facts about a logged run that decide whether it was easy."""

    pace_min_km: Optional[float]
    avg_heart_rate: Optional[int]
    distance_km: Optional[float]
    elevation_gain_m: Optional[float]


def is_easy_run(sample: EasyRunSample, hr_ceiling: int) -> bool:
    """Whether a run was jogged, on the flat, at an aerobic heart rate.

    A run with no heart rate is never counted: without it there is nothing to
    tell an easy day from a steady one, and the band would drift toward
    whatever pace the runner happens to default to.
    """
    if not sample.pace_min_km or sample.pace_min_km <= 0:
        return False
    if not sample.avg_heart_rate or sample.avg_heart_rate > hr_ceiling:
        return False
    if not sample.distance_km or sample.distance_km < _MIN_DISTANCE_KM:
        return False
    gain_per_km = (sample.elevation_gain_m or 0.0) / sample.distance_km
    return gain_per_km <= TRAIL_ELEVATION_M_PER_KM


def personal_easy_pace(
    samples: Iterable[EasyRunSample], hr_ceiling: Optional[int]
) -> Optional[float]:
    """Median pace (min/km) of the easy runs among ``samples``, or ``None``.

    ``None`` when the runner's aerobic ceiling is unknown or too few runs sat
    under it — the plan then keeps the band its VDOT implies.
    """
    if not hr_ceiling:
        return None
    paces = [
        sample.pace_min_km
        for sample in samples
        if is_easy_run(sample, hr_ceiling) and sample.pace_min_km
    ]
    if len(paces) < MIN_EASY_RUNS:
        return None
    return round(statistics.median(paces), 3)


def easy_pace_moved(stored: Optional[float], observed: Optional[float]) -> bool:
    """Whether a plan paced from ``stored`` should be re-paced to ``observed``.

    Losing the measurement (a quiet month, a watch left at home) is not a move:
    the last pace the runner showed stays until they show another.
    """
    if observed is None:
        return False
    if stored is None:
        return True
    # In whole seconds, as the runner reads a pace: 6:18 to 6:13 is a move.
    return round(abs(observed - stored) * 60) >= EASY_PACE_MIN_SHIFT_SEC


def personal_easy_range(
    easy_pace: Optional[float], threshold_pace: Optional[float]
) -> Optional[tuple[float, float]]:
    """The ``(slow, fast)`` edges of the band around ``easy_pace``, or ``None``.

    The fast edge is held clear of ``threshold_pace``. When that leaves no
    real band — the measured pace is itself at threshold — there is nothing
    coherent to prescribe and the caller keeps the VDOT band.
    """
    if not easy_pace or easy_pace <= 0:
        return None
    slow = easy_pace + EASY_BAND_HALF_WIDTH
    fast = easy_pace - EASY_BAND_HALF_WIDTH
    if threshold_pace:
        fast = max(fast, threshold_pace + _THRESHOLD_GAP)
    if slow - fast < _MIN_BAND_WIDTH:
        return None
    return round(slow, 2), round(fast, 2)


def has_personal_easy_band(pace_zones: Optional[Dict[str, Any]]) -> bool:
    """Whether ``pace_zones`` carry a measured easy band rather than the VDOT's."""
    return bool(pace_zones and (pace_zones.get("E") or {}).get("personal"))


def _band(slow: float, fast: float, description: str) -> Dict[str, Any]:
    return {
        "pace_min_km_slow": slow,
        "pace_min_km_fast": fast,
        "pace_str": f"{format_pace(slow)}–{format_pace(fast)}",
        "description": description,
    }


def with_personal_easy_band(
    pace_zones: Optional[Dict[str, Any]], easy_pace: Optional[float]
) -> Optional[Dict[str, Any]]:
    """``pace_zones`` with the easy band moved onto the runner's own pace.

    Easy and long runs take the measured band; recovery is the stretch just
    slower than it. Every other zone is returned as it came. The input is not
    mutated, and it is returned untouched when there is no pace to apply or no
    coherent band to make of it.
    """
    if not pace_zones or "E" not in pace_zones:
        return pace_zones
    threshold = (pace_zones.get("T") or {}).get("pace_min_km")
    edges = personal_easy_range(easy_pace, threshold)
    if edges is None:
        return pace_zones
    slow, fast = edges
    recovery_slow = round(slow + _RECOVERY_WIDTH, 2)
    easy_zone = {
        **_band(slow, fast, "Easy — the pace you run at an easy heart rate"),
        "personal": True,
        "sub_zones": {
            "recovery": _band(
                recovery_slow, slow, "Recovery run — very easy, conversational"
            ),
            "easy": _band(slow, fast, "Standard easy run"),
            "long_run": _band(slow, fast, "Long run pace — your easy pace"),
        },
    }
    return {**pace_zones, "E": easy_zone}
