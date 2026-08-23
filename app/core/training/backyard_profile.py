"""Backyard Ultra profile: a race measured in loops, not kilometres.

A backyard ultra ("last one standing") runs a fixed ~6.7 km loop starting on
the hour, every hour, until one runner remains. Two consequences of that
format are why the road/trail machinery cannot model it unchanged:

* **The loop is not the goal — the hour is.** Covering a loop in 42 minutes
  and covering it in 55 both count the same; the difference is 13 minutes of
  sitting down. Pace here is a *rest budget*, so running faster than the
  budget needs is not a virtue, and running slower than it is how people
  fail — not from the legs, but from never getting to eat.
* **The distance is repetition, not duration.** 24 loops is 161 km, but it
  is 161 km run as 24 separate 6.7 km efforts, each started cold, stiff,
  under-fuelled and eventually sleep-deprived. Preparing for it is about
  repeatability and the turnaround, not about covering the distance once.

A note on vocabulary, because it runs through this whole subsystem: the sport
itself calls a completed loop a **"yard"** (results read "24 yards"; the
winner is "last yard standing"). We say *loops* everywhere the runner can see,
because "yard" collides with the imperial distance unit and every other number
on the page is metric — a plan that mixes "24 yards" with "6.7 km" reads as a
unit error to anyone who doesn't already know the format. The term is
introduced once, in the goal form, so a runner still recognises it on race day.

This module is pure classification and arithmetic: it turns a runner's stated
goal (loops, loop length, loop climb) into the numbers the plan generator,
the schema validators, and the coaching copy all read.

The engine downstream still thinks in "target distance + elevation", so
:meth:`BackyardProfile.as_trail_profile` projects a backyard goal onto the
existing :class:`~app.core.training.trail_profile.TrailProfile`: it preserves
m/km so terrain-specific sessions are still selected correctly, and clamps
the distance to the trail engine's ceiling, because a 40-loop goal is 268 km
and no weekly mileage progression should be built backwards from that number.

Range validation is the caller's responsibility (PlanRequest validators).
Any non-negative input here produces a profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal

from app.core.training.trail_profile import (
    TRAIL_DISTANCE_MAX_KM,
    TRAIL_ELEVATION_MAX_M,
    TrailProfile,
    classify_trail,
)
from app.utils import format_pace

# The standard loop: 4.167 miles, sized so that 24 loops is exactly 100 miles
# in 24 hours. Every backyard race in the world uses this distance.
BACKYARD_LOOP_KM = 6.706
# Every loop starts on the hour, whistle to whistle. This is the only clock
# in the sport.
BACKYARD_CORRAL_MINUTES = 60.0

# Directors do vary the loop a little (trail loops measure long, some races
# switch to a road loop after dark), but an hourly lap that isn't roughly
# 6.7 km is a different event, not a backyard.
BACKYARD_LOOP_MIN_KM = 5.5
BACKYARD_LOOP_MAX_KM = 8.0
BACKYARD_LOOP_MAX_ELEVATION_M = 400.0

# Below 6 loops there is nothing to periodise — that is a long run with
# breaks in it. Above 48 the goal stops being a training target and becomes a
# duel with whoever else is left, so we cap it and keep the arithmetic honest.
MIN_TARGET_LOOPS = 6
MAX_TARGET_LOOPS = 48

Tier = Literal["first_timer", "day", "night", "multi_day"]

# Tier cutoffs in loops. They track what the *race* asks of the runner rather
# than the distance: the jump that matters is not 80 km to 100 km, it is the
# first hour run in the dark, and then the first hour run without sleep.
_TIER_DAY_MIN_LOOPS = 12
_TIER_NIGHT_MIN_LOOPS = 18
_TIER_MULTI_DAY_MIN_LOOPS = 30

# Minutes of turnaround the runner should be able to bank every hour at their
# goal. It rises with ambition because rest is the only place food, foot
# care, dry socks and (eventually) sleep can come from: at 6 loops a
# runner can afford to jog the loop, at 36 they cannot.
_TIER_TURNAROUND_MIN: Dict[str, float] = {
    "first_timer": 8.0,
    "day": 10.0,
    "night": 12.0,
    "multi_day": 14.0,
}

_TIER_MIN_WEEKS: Dict[str, int] = {
    "first_timer": 8,
    "day": 12,
    "night": 16,
    "multi_day": 20,
}

_TIER_MAX_WEEKS: Dict[str, int] = {
    "first_timer": 20,
    "day": 28,
    "night": 36,
    "multi_day": 40,
}

# Backyard volume arrives as many medium sessions rather than a few big ones,
# so the weekly frequency floor is higher than the distance alone implies.
_TIER_MIN_RUNS_PER_WEEK: Dict[str, int] = {
    "first_timer": 3,
    "day": 4,
    "night": 5,
    "multi_day": 5,
}

# Extra minutes a loop costs per 100 m of climb at easy running effort. Used
# only to answer "what flat fitness does this hilly loop demand?" — the clock
# does not care about the hill, so the runner has to.
_CLIMB_MINUTES_PER_100M = 0.8

# Nobody should be told their loop needs faster than this; below it the honest
# advice is to pick fewer loops, not to run harder.
_MIN_SANE_LOOP_PACE_MIN_KM = 3.5


def _classify_tier(target_loops: int) -> Tier:
    if target_loops >= _TIER_MULTI_DAY_MIN_LOOPS:
        return "multi_day"
    if target_loops >= _TIER_NIGHT_MIN_LOOPS:
        return "night"
    if target_loops >= _TIER_DAY_MIN_LOOPS:
        return "day"
    return "first_timer"


@dataclass(frozen=True)
class BackyardProfile:
    """Parameterized backyard goal threaded through plan generation."""

    target_loops: int
    loop_km: float
    loop_elevation_gain_m: float
    tier: Tier

    # --- What the runner is actually signing up for ------------------------

    @property
    def target_hours(self) -> int:
        """Hours on the clock at the goal. One loop is one hour, always."""
        return self.target_loops

    @property
    def total_distance_km(self) -> float:
        """Distance covered at the goal loop count — the real race distance."""
        return self.target_loops * self.loop_km

    @property
    def total_elevation_gain_m(self) -> float:
        return self.target_loops * self.loop_elevation_gain_m

    @property
    def m_per_km(self) -> float:
        if self.loop_km <= 0:
            return 0.0
        return self.loop_elevation_gain_m / self.loop_km

    # --- The rest budget, which is the whole sport -------------------------

    @property
    def turnaround_minutes(self) -> float:
        """Minutes off the feet per hour the goal needs."""
        return _TIER_TURNAROUND_MIN[self.tier]

    @property
    def loop_budget_minutes(self) -> float:
        """Minutes the loop itself may take if that turnaround is to survive."""
        return BACKYARD_CORRAL_MINUTES - self.turnaround_minutes

    @property
    def loop_pace_min_km(self) -> float:
        """Pace that spends exactly the loop budget — the pace to rehearse."""
        if self.loop_km <= 0:
            return 0.0
        return self.loop_budget_minutes / self.loop_km

    @property
    def loop_climb_cost_minutes(self) -> float:
        """Minutes the loop's climb takes out of the budget before you run."""
        return (self.loop_elevation_gain_m / 100.0) * _CLIMB_MINUTES_PER_100M

    @property
    def flat_equivalent_pace_min_km(self) -> float:
        """Flat pace the runner must own to hold the budget on *this* loop.

        A 120 m climb per lap does not buy extra minutes — it spends them. So
        a 50-minute budget on a hilly loop is a harder flat-ground ask than
        the raw loop pace suggests, and this is the number to train at.
        """
        if self.loop_km <= 0:
            return 0.0
        usable = self.loop_budget_minutes - self.loop_climb_cost_minutes
        return max(_MIN_SANE_LOOP_PACE_MIN_KM, usable / self.loop_km)

    # --- What the clock does to the runner ---------------------------------

    @property
    def runs_in_darkness(self) -> bool:
        """Whether the goal takes the runner past sunset (typical AM start)."""
        return self.target_loops >= _TIER_DAY_MIN_LOOPS

    @property
    def crosses_full_night(self) -> bool:
        """Whether the goal means running all the way through a night."""
        return self.target_loops >= _TIER_NIGHT_MIN_LOOPS

    @property
    def crosses_two_nights(self) -> bool:
        return self.target_loops >= _TIER_MULTI_DAY_MIN_LOOPS

    @property
    def category_key(self) -> str:
        """Compound key for coaching copy lookups, e.g. ``Backyard_night``."""
        return f"Backyard_{self.tier}"

    # --- Projection onto the existing trail engine -------------------------

    @property
    def equivalent_distance_km(self) -> float:
        """Race distance the plan engine should periodise against.

        The honest total (loops × loop length) is the right thing to *show* the
        runner, but it is the wrong thing to build a mileage progression from
        once it passes the trail engine's ceiling: nobody trains differently
        for 268 km than for 163 km, they just run out of weeks. Clamped so a
        48-loop goal produces a sane plan rather than an impossible one.
        """
        return min(TRAIL_DISTANCE_MAX_KM, self.total_distance_km)

    @property
    def equivalent_elevation_gain_m(self) -> float:
        """Climb over :attr:`equivalent_distance_km`, preserving the loop's m/km.

        Elevation *class* is what steers terrain-specific session selection,
        and class is a ratio — so the projection has to scale climb with the
        clamped distance rather than carry the raw race total across.
        """
        return min(TRAIL_ELEVATION_MAX_M, self.m_per_km * self.equivalent_distance_km)

    def as_trail_profile(self) -> TrailProfile:
        """The :class:`TrailProfile` the plan engine should run on."""
        return classify_trail(
            self.equivalent_distance_km, self.equivalent_elevation_gain_m
        )

    @property
    def elevation_class(self) -> str:
        return self.as_trail_profile().elevation_class


def classify_backyard(
    target_loops: int,
    loop_km: float = BACKYARD_LOOP_KM,
    loop_elevation_gain_m: float = 0.0,
) -> BackyardProfile:
    """Build a :class:`BackyardProfile` from raw inputs.

    Args:
        target_loops: Hourly loops the runner is training to complete.
            Expected in [``MIN_TARGET_LOOPS``, ``MAX_TARGET_LOOPS``].
        loop_km: Loop length in km. Defaults to the standard 6.706 km.
        loop_elevation_gain_m: Climb per loop in m (0 for a flat loop).
    """
    return BackyardProfile(
        target_loops=int(target_loops),
        loop_km=float(loop_km),
        loop_elevation_gain_m=float(loop_elevation_gain_m),
        tier=_classify_tier(int(target_loops)),
    )


# --- Tier-aware plan constraints --------------------------------------------
# Consumed by PlanRequest validators, mirroring the trail_* helpers.


def backyard_min_weeks(profile: BackyardProfile) -> int:
    return _TIER_MIN_WEEKS[profile.tier]


def backyard_max_weeks(profile: BackyardProfile) -> int:
    return _TIER_MAX_WEEKS[profile.tier]


def backyard_min_runs_per_week(profile: BackyardProfile) -> int:
    return _TIER_MIN_RUNS_PER_WEEK[profile.tier]


def backyard_min_weekly_km(profile: BackyardProfile) -> float:
    """Weekly base a runner needs before starting a plan for this goal.

    Scales with loops rather than with the projected distance, because the
    projection is clamped and the ask is not: going from 24 to 36 loops is a
    real step up in required base even though both project to 163 km. A hilly
    loop adds 15% — the eccentric cost of the descents compounds hour over
    hour in a way flat loops never do.
    """
    base = min(90.0, max(25.0, 2.2 * profile.target_loops + 8.0))
    if profile.elevation_class in ("hilly", "mountainous"):
        base *= 1.15
    return round(base, 1)


def backyard_max_weekly_km(profile: BackyardProfile) -> float:
    """Soft upper bound used to surface a 'high mileage' warning."""
    raw = 3.4 * profile.target_loops + 30.0
    return round(min(160.0, max(55.0, raw)), 1)


def backyard_summary(profile: BackyardProfile) -> Dict[str, object]:
    """Display-ready numbers for a backyard goal.

    One source of truth for every surface that shows the runner their own
    goal — the plan header, the weekly card, the shared view — so a pace
    string never disagrees with itself across two templates.
    """
    return {
        "target_loops": profile.target_loops,
        "target_hours": profile.target_hours,
        "tier": profile.tier,
        "loop_km": round(profile.loop_km, 3),
        "loop_elevation_gain_m": round(profile.loop_elevation_gain_m),
        "total_distance_km": round(profile.total_distance_km, 1),
        "loop_budget_min": round(profile.loop_budget_minutes),
        "turnaround_min": round(profile.turnaround_minutes),
        "loop_pace_str": format_pace(profile.loop_pace_min_km),
        "flat_equivalent_pace_str": format_pace(profile.flat_equivalent_pace_min_km),
        "crosses_full_night": profile.crosses_full_night,
    }
