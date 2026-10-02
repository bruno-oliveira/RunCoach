"""How much of a runner's recent running was easy.

A count of easy runs only ever goes up, so it cannot tell a runner anything to
do. The *share* can: endurance training works when most of the volume is easy
and a small part is hard, and the common way to get that wrong is not too
little hard running but easy days that drift into moderate ones.

The split is by **session**, weighted by distance: a tempo run counts as hard
in full, warm-up and cool-down included. That is the convention the "80/20"
rule of thumb is stated in, and it needs nothing finer than the workout type
every logged run already carries — no lap data, no heart-rate stream.
"""

from dataclasses import dataclass
from typing import Iterable, Optional

# Share of volume that should be easy. A rule of thumb, not a physiological
# constant, which is why the bands around it are wide.
TARGET_EASY_SHARE = 0.8
_TOO_HARD_BELOW = 0.7
_MOSTLY_EASY_ABOVE = 0.9

# Below this the share is noise: one tempo in three runs reads as "67% easy".
MIN_RUNS = 4
MIN_KM = 10.0

# Session types run at or above threshold effort. Everything else — easy,
# recovery, long, untyped — is easy volume.
HARD_TYPES = frozenset(
    {
        "tempo",
        "threshold",
        "cruise_interval",
        "interval",
        "vo2max",
        "vo2max_ladder",
        "hill",
        "hills",
        "fartlek",
        "progression",
        "race",
    }
)

TOO_HARD = "too_hard"
BALANCED = "balanced"
MOSTLY_EASY = "mostly_easy"


@dataclass(frozen=True)
class IntensitySplit:
    """Easy vs hard distance over a window of runs."""

    easy_km: float
    hard_km: float
    runs: int

    @property
    def easy_share(self) -> float:
        total = self.easy_km + self.hard_km
        return self.easy_km / total if total else 0.0

    @property
    def verdict(self) -> str:
        share = self.easy_share
        if share < _TOO_HARD_BELOW:
            return TOO_HARD
        if share > _MOSTLY_EASY_ABOVE:
            return MOSTLY_EASY
        return BALANCED


def is_hard_session(workout_type: Optional[str]) -> bool:
    """Whether a session of this type counts as hard volume."""
    return (workout_type or "") in HARD_TYPES


def intensity_split(
    runs: Iterable[tuple[Optional[str], Optional[float]]],
) -> Optional[IntensitySplit]:
    """Split ``(workout_type, distance_km)`` runs into easy and hard distance.

    Returns:
        None when there is too little running to say anything honest.
    """
    easy_km = hard_km = 0.0
    count = 0
    for workout_type, distance_km in runs:
        if not distance_km or distance_km <= 0:
            continue
        count += 1
        if is_hard_session(workout_type):
            hard_km += distance_km
        else:
            easy_km += distance_km
    if count < MIN_RUNS or easy_km + hard_km < MIN_KM:
        return None
    return IntensitySplit(
        easy_km=round(easy_km, 1), hard_km=round(hard_km, 1), runs=count
    )
