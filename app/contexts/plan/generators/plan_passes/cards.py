"""What the plan-level passes agree a card *is*, and the two things they all do.

Every pass that resizes a week has to answer the same questions — which cards
ask the runner to run, how small a session may get before it stops being one —
and has to leave the week in the same state afterwards (a fresh total, fresh
duration hints). They used to answer and tidy up separately, one copy per
pass.
"""

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.weekly_plan_builder import attach_duration_hints

# Card types that ask the runner to run. A card of one of these types whose
# distance has drained to 0 is not a session — it renders as an easy run with
# no distance on it — and every pass that tidies a week should be allowed to
# turn it into the rest day it effectively is.
RUNNING_CARD_TYPES = ("easy", "medium_long", "tempo", "interval", "hill")

# Card types whose distance is a prescription, not a share of the week.
QUALITY_CARD_TYPES = ("tempo", "interval", "hill")

# Floors for the trivial-session sweep. A *quality* card below this dose
# cannot hold warm-up, work, and cool-down and is relabelled as the easy run
# it effectively was. An *easy* card below the coherence floor is not a run by
# any measure (worst case observed: 0.3 km) and is rendered as rest. Between
# the coherence floor and a real session sits honest territory — a 1.5 km jog
# in a small week — which the sweep must leave alone: converting it erodes
# frequency and deflates the ramp baseline for no coaching gain.
MIN_VIABLE_QUALITY_KM = 2.5
MIN_COHERENT_RUN_KM = 1.0

# How far the 10 % weekly cap may shrink a flexible session before it stops.
# A ratio rather than an absolute distance: an absolute floor disables the cap
# on the low-base high-frequency plans that sit *at* that floor, while a ratio
# can never reach zero — so the cap keeps working and no session is ever
# deleted into a 0.0 km card.
FLEXIBLE_TRIM_FLOOR_RATIO = 0.5


def week_total_km(workouts: List[Dict[str, Any]]) -> float:
    """The week's card total, to the one decimal every surface displays."""
    return round(sum(w.get("distance", 0) or 0 for w in workouts), 1)


def is_running_session(workout: Dict[str, Any]) -> bool:
    """A card the runner actually runs: not rest, and with distance on it."""
    return (
        workout.get("type") not in ("rest", "recovery")
        and (workout.get("distance", 0) or 0) > 0
    )


def refresh_duration_hints(
    workouts: List[Dict[str, Any]], pace_zones: Optional[Dict]
) -> None:
    """Recompute the display-only duration hints from the final distances.

    A resize can move a workout across the 3 km display boundary, so a hint
    written before it is stale. They are cleared first because
    ``attach_duration_hints`` only writes the short cards: one that grew past
    the boundary would otherwise keep the hint it no longer earns.
    """
    clear_duration_hints(workouts)
    attach_duration_hints(workouts, pace_zones)


def clear_duration_hints(workouts: List[Dict[str, Any]]) -> None:
    """Drop the duration hints ahead of a drawdown.

    ``scale_down`` skips workouts carrying a display-only ``duration_min``
    hint, so they must be cleared before the drawdown is distributed.
    """
    for w in workouts:
        w.pop("duration_min", None)
