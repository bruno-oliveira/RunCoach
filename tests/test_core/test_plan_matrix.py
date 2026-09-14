"""The plan matrix: every goal the app accepts, generated and audited.

The whole plan-generation surface in one file: **5K to a 163 km ultra, 2 to 6
runs a week**, across the three families the app serves — road presets,
parameterized trail/ultra, and backyard (stated in hourly loops).

It supersedes the earlier ``test_plan_full_coverage`` grid, which had begun to
describe a product the app does not ship: it carried its own copy of the
constraint table (already drifted), discarded every combo under 2.5 km/run —
exactly where the rejection boundaries and the degenerate plans live — and
stopped short of anything past the marathon. Two things only that grid could
see are kept in layer 5: the form endpoint itself, and the legacy 30 km
sentinel that a stored row still arrives on.

Four things this file does that a shape check cannot:

* an **acceptance spec**: the boundary one notch below every published floor
  must be *rejected*, with the exact exception the layer raises. The app is
  supposed to refuse a 50 km ultra trained at 3 runs a week; nothing pinned
  that before.
* an **imbalance census**: every generated plan is measured against
  ``physiological_envelope`` and the result pinned per goal. A plan that starts
  exceeding its band — over-prescribing volume, or leaning on one session for
  most of the week — fails here even when its shape is legal.
* an **adaptation check**: the invariants are re-asserted on a plan *after* the
  adaptive engine re-paces it, against a runner who over-reaches, under-performs
  or skips.
* a **pinned ledger** of the defects found (below), so they cannot get quietly
  worse.

The matrix is derived from the app's own registries (``DISTANCE_CONSTRAINTS``,
the trail bracket tables, the backyard tier tables) rather than a hand-copied
table, so a constraint change moves both the app and this spec together.

This grid found four defects, and all four are now **fixed** in the app rather
than pinned:

* a trail ``short`` plan could be accepted at 5 weeks and then refused by the
  generator (``_BRACKET_MIN_WEEKS`` said 5, ``MIN_WEEKS_FOR_PHASES`` requires 6);
* the trail long-run curve reached 48 km for 100-mile prep against the 38 km
  ``_TRAIL_HARD_CEILINGS`` bound it was supposed to sit under;
* marginal backyard weeks composed into a 0.0 km "easy" card and a jump past
  the app's own weekly ramp cap;
* ``PEAK_WEEK_KM`` / ``PEAK_LONG_RUN_KM`` stopped at the marathon, so every ultra
  and every backyard goal was judged against a marathon's bands.

The first three are now hard assertions here — the grid says so directly, so a
regression fails on the combination that caused it. ``_ENVELOPE_CENSUS`` remains
a *pinned* ledger because the envelope's long-run band is a published reference
while ``training_constants`` is the binding contract; it is a drift detector, and
the docstring on it says which columns are expected to be non-zero and why.
"""

from __future__ import annotations

import copy
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.constants import DISTANCE_CONSTRAINTS
from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.generators.plan_generator import (
    TrainingPlanGenerator,
    _viable_run_frequency,
)
from app.contexts.plan.generators.plan_structure_guard import (
    MIN_VIABLE_NON_RECOVERY_KM,
    check_plan_structure,
)
from app.contexts.plan.plan_creation_helpers import (
    persist_plan_core,
    persist_weekly_workouts,
)
from app.core.training import physiological_envelope as env
from app.core.training.backyard_profile import (
    _TIER_MAX_WEEKS,
    _TIER_MIN_RUNS_PER_WEEK,
    _TIER_MIN_WEEKS,
    BackyardProfile,
    backyard_min_weekly_km,
    classify_backyard,
)
from app.core.training.trail_profile import (
    _BRACKET_MAX_WEEKS,
    _BRACKET_MIN_RUNS,
    _BRACKET_MIN_WEEKS,
    TrailProfile,
    classify_trail,
)
from app.core.training.training_constants import get_hard_ceiling, training_km
from app.exceptions import (
    InadequateBaseException,
    InsufficientTimeException,
    ZeroMileageUnsupportedException,
)
from app.infrastructure.integrations.post_sync_service import auto_map_and_adjust
from app.models import RunLog, TrainingPlan, User
from app.schemas.plan_request import PlanRequest

# Types that occupy a day but are not a training run.
NON_RUNNING = ("rest", "recovery")
# Volume that is a hard prescription rather than a budget the scaler may move.
QUALITY_TYPES = ("tempo", "interval", "hill")

GEN = TrainingPlanGenerator()


# ── The goal space ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Goal:
    """One trainable goal, with the floors the app publishes for it."""

    id: str
    kind: str  # "road" | "trail" | "backyard"
    distance_km: float  # what the engine periodises against
    min_weeks: int
    max_weeks: int
    min_runs: int
    bases: Tuple[float, ...]
    trail: Optional[TrailProfile] = None
    backyard: Optional[BackyardProfile] = None

    def request_kwargs(self) -> Dict[str, Any]:
        """The ``PlanRequest`` fields that describe this goal."""
        if self.backyard is not None:
            return {
                "is_backyard": True,
                "backyard_target_loops": self.backyard.target_loops,
                "backyard_loop_km": self.backyard.loop_km,
                "backyard_loop_elevation_gain_m": self.backyard.loop_elevation_gain_m,
            }
        if self.trail is not None:
            return {
                "is_trail": True,
                "target_distance": self.trail.distance_km,
                "target_elevation_gain_m": self.trail.elevation_gain_m,
            }
        return {"target_distance": self.distance_km}

    def generator_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if self.trail is not None:
            kwargs["trail_profile"] = self.trail
        if self.backyard is not None:
            kwargs["backyard_profile"] = self.backyard
        return kwargs


def _base_candidates(lo: float, hi: float) -> Tuple[float, ...]:
    """Four reference bases: the floor, 2× the floor, the midpoint, the ceiling."""
    return (lo, lo * 2, (lo + hi) / 2, hi)


def _road_goals() -> List[Goal]:
    goals = []
    for dist, c in DISTANCE_CONSTRAINTS.items():
        if dist == 30.0:
            # The legacy trail sentinel: a road request at 30.0 is auto-promoted
            # to a trail plan, so it is not a road goal (covered as trail below).
            continue
        floor = 2 if dist <= 10.0 else (3 if dist < 42.2 else 4)
        goals.append(
            Goal(
                id=f"road-{dist:g}km",
                kind="road",
                distance_km=dist,
                min_weeks=c.min_weeks,
                max_weeks=c.max_weeks,
                min_runs=floor,
                bases=tuple(sorted(_base_candidates(c.min_mileage, c.max_mileage))),
            )
        )
    return goals


# One representative race per bracket, plus the 100 km ultra the product has to
# get right. Elevation is chosen so each profile lands in a distinct elevation
# class (flat → mountainous), because elevation drives the plan's shape.
_TRAIL_RACES = (
    (12.0, 400.0),
    (30.0, 1000.0),
    (50.0, 2000.0),
    (60.0, 2400.0),
    (80.0, 3000.0),
    (100.0, 4000.0),
    (163.0, 6000.0),
)


def _trail_goals() -> List[Goal]:
    goals = []
    for dist, elev in _TRAIL_RACES:
        profile = classify_trail(dist, elev)
        bracket = profile.bracket
        lo = max(15.0, 0.35 * dist)
        if profile.elevation_class == "mountainous":
            lo *= 1.2
        goals.append(
            Goal(
                id=f"trail-{dist:g}km/{bracket}",
                kind="trail",
                distance_km=dist,
                min_weeks=_BRACKET_MIN_WEEKS[bracket],
                max_weeks=_BRACKET_MAX_WEEKS[bracket],
                min_runs=_BRACKET_MIN_RUNS[bracket],
                bases=tuple(round(lo * m, 1) for m in (1, 2, 3)),
                trail=profile,
            )
        )
    return goals


# Every tier boundary, since the boundary is where the floors change.
_BACKYARD_LOOPS = (6, 11, 12, 17, 18, 29, 30, 48)


def _backyard_goals() -> List[Goal]:
    goals = []
    for loops in _BACKYARD_LOOPS:
        profile = classify_backyard(loops, loop_elevation_gain_m=0.0)
        tier = profile.tier
        lo = backyard_min_weekly_km(profile)
        goals.append(
            Goal(
                id=f"backyard-{loops}loops/{tier}",
                kind="backyard",
                distance_km=profile.equivalent_distance_km,
                min_weeks=_TIER_MIN_WEEKS[tier],
                max_weeks=_TIER_MAX_WEEKS[tier],
                min_runs=_TIER_MIN_RUNS_PER_WEEK[tier],
                bases=tuple(round(lo * m, 1) for m in (1, 1.5, 2)),
                backyard=profile,
            )
        )
    return goals


GOALS: List[Goal] = _road_goals() + _trail_goals() + _backyard_goals()


def _weeks_for(goal: Goal) -> List[int]:
    """Reference durations: the floor, the floor + 1, the midpoint, the ceiling."""
    floor = goal.min_weeks
    mid = (goal.min_weeks + goal.max_weeks) // 2
    if goal.kind == "backyard":
        return sorted({floor, mid, goal.max_weeks})
    return sorted({floor, floor + 1, mid, goal.max_weeks})


@dataclass(frozen=True)
class Combo:
    goal: Goal
    weeks: int
    base: float
    runs: int  # as requested; may be reduced to `viable_runs` by the generator

    @property
    def viable_runs(self) -> int:
        """The frequency the generator will actually schedule."""
        return _viable_run_frequency(self.base, self.runs)

    @property
    def id(self) -> str:
        return f"{self.goal.id}|{self.weeks}wk|{self.base:g}base|{self.runs}r"


def _combos() -> List[Combo]:
    out = []
    for goal in GOALS:
        for weeks in _weeks_for(goal):
            for base in goal.bases:
                for runs in range(goal.min_runs, 7):
                    out.append(Combo(goal, weeks, base, runs))
    return out


COMBOS: List[Combo] = _combos()

# Generating the same combo once per assertion would multiply the matrix by the
# number of invariants. Every test reads from this cache instead.
_PLAN_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def generate(combo: Combo) -> List[Dict[str, Any]]:
    plan = _PLAN_CACHE.get(combo.id)
    if plan is None:
        kwargs = dict(
            current_km=combo.base,
            target_distance=combo.goal.distance_km,
            weeks=combo.weeks,
            max_runs_per_week=combo.viable_runs,
        )
        kwargs.update(combo.goal.generator_kwargs())
        plan = GEN.generate_plan(**kwargs)
        _PLAN_CACHE[combo.id] = plan
    return plan


# ── Layer 1: structural invariants ────────────────────────────────────────

# Rounding + the 0.6 km of strides occasionally added to an easy run.
_RATIO_SLACK_KM = 0.1
# The base rule is 10 %/week; 2 % absorbs per-workout rounding.
_WEEKLY_RAMP_CEILING = 12.0


def _running(week: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        w
        for w in week.get("daily_workouts", [])
        if w.get("type") not in NON_RUNNING and (w.get("distance") or 0) > 0
    ]


def _invariant_failures(combo: Combo, plan: List[Dict[str, Any]]) -> List[str]:
    """Every way a generated plan can be unsound, as human-readable strings."""
    bad: List[str] = []
    weeks = combo.weeks

    def note(msg: str) -> None:
        bad.append(msg)

    if len(plan) != weeks:
        note(f"expected {weeks} weeks, got {len(plan)}")

    if [w.get("week") for w in plan] != list(range(1, weeks + 1)):
        note("week numbers are not 1..N")

    expected_runs = combo.viable_runs
    high_water = combo.base
    peak_training = 0.0

    for week in plan:
        num = week.get("week")
        days = week.get("daily_workouts", [])
        is_recovery = week.get("is_recovery", False)
        is_final = num == weeks

        if len(days) != 7:
            note(f"week {num}: {len(days)} days, expected 7")

        if week.get("phase") not in ("base", "build", "peak", "taper"):
            note(f"week {num}: unexpected phase {week.get('phase')!r}")

        # A long run, or the race standing in for it. One per week — with a
        # single sanctioned exception: a backyard weekend rehearses
        # *back-to-back* long days, so its peak weekends carry two, and they
        # must be on consecutive days. Two non-adjacent long runs would be a
        # split long run, which is a different and unsound thing.
        anchors = [w for w in days if w.get("type") in ("long", "race")]
        max_anchors = 2 if combo.goal.kind == "backyard" else 1
        if not 1 <= len(anchors) <= max_anchors:
            note(
                f"week {num}: {len(anchors)} long/race sessions, "
                f"expected 1..{max_anchors}"
            )
        if len(anchors) == 2:
            anchor_days = sorted(w.get("day") for w in anchors)
            if anchor_days[1] - anchor_days[0] != 1:
                note(f"week {num}: two long days on {anchor_days}, not back-to-back")

        # The requested frequency, as the generator was asked. It may have been
        # reduced from the request (never below the request's own floor). A
        # backyard week flexes by one either way: its peak weekends add a
        # session for the second long day, and a peak week at 6 runs may drop
        # one rather than stretch the remaining runs past their per-run cap.
        run_days = [w for w in days if w.get("type") not in NON_RUNNING]
        allowed_runs = {expected_runs}
        if combo.goal.kind == "backyard":
            allowed_runs.update({expected_runs - 1, expected_runs + 1})
        # Race week deliberately reduces frequency for a sharper taper —
        # the race plus at most 2 pre-race runs.
        if is_final:
            allowed_runs.update(range(2, expected_runs + 1))
        if len(run_days) not in allowed_runs:
            note(
                f"week {num}: {len(run_days)} running days, expected "
                f"{sorted(allowed_runs)} (requested {combo.runs})"
            )
        # However much it flexes, a week may never fall below the frequency the
        # goal's own bracket publishes as its floor.  Race week is exempt: it
        # runs as few as 2 (shakeout + race) by design.
        if not is_final and len(run_days) < combo.goal.min_runs:
            note(
                f"week {num}: {len(run_days)} running days is below the "
                f"{combo.goal.id} floor of {combo.goal.min_runs}"
            )

        # The headline number must equal the sessions it claims to summarise.
        total = week.get("total_km") or 0
        summed = round(sum(w.get("distance", 0) or 0 for w in days), 1)
        if abs(total - summed) > 0.5:
            note(f"week {num}: total_km {total} != summed {summed}")

        for w in days:
            if (w.get("distance") or 0) < 0:
                note(f"week {num} day {w.get('day')}: negative distance")

        # A running day that prescribes nothing is a hole in the week. Race week
        # is exempt: the shakeout and the race are sized by other rules.
        if not is_final:
            for w in days:
                if w.get("type") in ("easy", "long", "tempo", "interval", "hill"):
                    if (w.get("distance") or 0) <= 0:
                        note(
                            f"week {num} day {w.get('day')}: {w['type']} with no distance"
                        )

        # Measured against the *longest* of the week's long days: on a backyard
        # back-to-back weekend the second one is the bigger, and it is the
        # session everything else must stay under.
        long_km = max((w.get("distance") or 0) for w in anchors) if anchors else 0.0
        if long_km > 0:
            # No easy run may rival the long run.
            for w in days:
                if w.get("type") == "easy" and not w.get("duration_min"):
                    if (w.get("distance") or 0) > long_km * 1.25 + _RATIO_SLACK_KM:
                        note(
                            f"week {num}: easy {(w.get('distance'))} km exceeds "
                            f"1.25x long run {long_km} km"
                        )
            # A quality day may approach the long run but never reach it.
            for w in days:
                if w.get("type") in QUALITY_TYPES and not w.get("duration_min"):
                    if (w.get("distance") or 0) > long_km * 0.95 + _RATIO_SLACK_KM:
                        note(
                            f"week {num}: {w['type']} {(w.get('distance'))} km "
                            f"rivals the long run {long_km} km"
                        )

        # Volume may only grow ~10 % a week, measured against the high-water mark.
        if not is_recovery and high_water > 0:
            training = sum(
                w.get("distance", 0) or 0
                for w in days
                if w.get("type")
                not in ("rest", "recovery", "strength", "cross_training", "race")
            )
            ramp = ((training - high_water) / high_water) * 100
            if ramp > _WEEKLY_RAMP_CEILING:
                note(
                    f"week {num}: {ramp:.1f}% jump "
                    f"({high_water:.1f} -> {training:.1f} km)"
                )
            if training > high_water:
                high_water = training

        if not is_recovery:
            peak_training = max(peak_training, training_km(week))

    # The taper descends, and never exceeds the peak it is drawing down from.
    taper = [training_km(w) for w in plan if w.get("phase") == "taper"]
    for earlier, later in zip(taper, taper[1:]):
        if later > earlier + 0.05:
            note(f"taper climbs toward race day: {taper}")
    if taper and peak_training:
        # 4 km of slack: prescriptive sessions hold their authored dose, so the
        # high-water cap suppresses peak weeks more than taper weeks.
        if taper[0] > peak_training + 4.0:
            note(f"taper {taper[0]} km exceeds peak {peak_training:.1f} km")

    # The long run must respect the app's own hard ceiling for the distance —
    # the binding contract (``LONG_RUN_HARD_CEILINGS``), not the envelope's
    # tighter reference band.
    #
    # This replaced a "stays below 92 % of the race" check. That rule only held
    # because the old grid sampled each distance's *minimum* base: a
    # well-adapted half-marathon runner is prescribed a 24 km long run against a
    # 21.1 km race, which the hard ceiling explicitly sanctions. The rule encoded
    # an assumption the app does not make. Trail brackets breach the ceiling in a
    # handful of cases; those are pinned separately by
    # ``test_long_runs_respect_the_app_hard_ceiling`` rather than smuggled in
    # here.
    if combo.goal.kind == "road":
        ceiling = get_hard_ceiling(combo.goal.distance_km, None)
        for week in plan:
            for w in week.get("daily_workouts", []):
                if w.get("type") == "long" and (w.get("distance") or 0) > ceiling + 0.5:
                    note(
                        f"week {week.get('week')}: long run {w.get('distance')} km "
                        f"past the {ceiling:g} km ceiling"
                    )

    # The plan-level guard is part of the invariant, not a separate concern.
    fatal = check_plan_structure(plan)["fatal"]
    if fatal:
        note("structure guard: " + "; ".join(fatal))

    return bad


# ── Layer 2: the envelope census ──────────────────────────────────────────

# Tolerance for the peak-week band, and for the envelope's long-run reference.
_ENVELOPE_SLACK_KM = 0.6

# goal id -> (combos, peak_over, long_over, share_over).
#
# `peak_over` is the one that would matter for safety: a plan prescribing more
# weekly volume than the envelope's ceiling for that goal and frequency. It is
# **zero for every road and trail goal and must stay zero** — asserted directly
# by ``test_no_race_plan_over_prescribes_weekly_volume``, so the census cannot
# drift on that column.
#
# The backyard rows are *indicative only*. A backyard plan is keyed here on its
# projected distance, and that projection is clamped (29, 30 and 48 loops all
# project to 163 km) while the loop count is what actually drives the training.
# ``backyard-17loops`` shows a non-zero peak_over for exactly that reason: its
# runners start from a base already above the band's ceiling, so the plan is
# *reducing* their week, not over-prescribing.
#
# `long_over` is near-universal and is *expected*: the envelope's long-run band
# is a published reference, while the app's own contract lives in
# ``training_constants`` and ``tuning`` (a 42.2 km plan may reach a 36 km long
# run against the envelope's 32 km; a backyard's long day is a loop simulation
# sized by the format). The envelope's docstring calls the tier table
# authoritative, so this column is a drift detector, not a defect.
#
# `share_over` is the frequency-aware 0.55 ceiling from
# ``long_run_share_ceiling`` — deliberately not the published 25-35 % band, which
# a 2-3 run week cannot honour. Non-zero on the lowest-frequency weeks, where
# there is nowhere else for the volume to live.
_ENVELOPE_CENSUS: Dict[str, Tuple[int, int, int, int]] = {
    # goal: (combos, peak_over, long_over, share_over)
    "backyard-11loops/first_timer": (36, 0, 13, 4),
    "backyard-12loops/day": (27, 0, 18, 1),
    "backyard-17loops/day": (27, 6, 25, 3),
    "backyard-18loops/night": (18, 0, 18, 0),
    "backyard-29loops/night": (18, 0, 18, 12),
    "backyard-30loops/multi_day": (18, 0, 18, 0),
    "backyard-48loops/multi_day": (18, 0, 18, 12),
    "backyard-6loops/first_timer": (36, 0, 10, 9),
    "road-10km": (80, 0, 9, 0),
    "road-21.1km": (64, 0, 16, 0),
    "road-42.2km": (48, 0, 39, 0),
    "road-5km": (80, 0, 12, 0),
    "trail-100km/long_ultra": (12, 0, 0, 0),
    "trail-12km/short": (48, 0, 0, 0),
    "trail-163km/long_ultra": (12, 0, 0, 0),
    "trail-30km/standard": (36, 0, 7, 0),
    "trail-50km/ultra": (24, 0, 0, 4),
    "trail-60km/ultra": (24, 0, 0, 3),
    "trail-80km/long_ultra": (12, 0, 0, 0),
}


def _peak_week(plan: List[Dict[str, Any]]) -> float:
    loading = [
        w for w in plan if not w.get("is_recovery") and not w.get("is_race_week")
    ]
    if not loading:
        return 0.0
    return max((w.get("total_km") or 0) for w in loading)


def _longest_long_run(plan: List[Dict[str, Any]]) -> float:
    return max(
        (
            (w.get("distance") or 0)
            for week in plan
            for w in week.get("daily_workouts", [])
            if w.get("type") == "long"
        ),
        default=0.0,
    )


def _worst_long_run_share(plan: List[Dict[str, Any]]) -> float:
    worst = 0.0
    for week in plan:
        if week.get("is_recovery"):
            continue
        total = week.get("total_km") or 0
        if total <= 0:
            continue
        long_km = max(
            (
                (w.get("distance") or 0)
                for w in week.get("daily_workouts", [])
                if w.get("type") == "long"
            ),
            default=0.0,
        )
        if long_km > 0:
            worst = max(worst, long_km / total)
    return worst


def _classify(combo: Combo, plan: List[Dict[str, Any]]) -> Dict[str, bool]:
    dist = combo.goal.distance_km
    runs = combo.viable_runs
    _, peak_hi = env.peak_week_band(dist, runs)
    _, long_hi = env.peak_long_run_band(dist)
    ceiling = env.long_run_share_ceiling(runs)
    return {
        "peak_over": _peak_week(plan) > peak_hi + _ENVELOPE_SLACK_KM,
        "long_over": _longest_long_run(plan) > long_hi + _ENVELOPE_SLACK_KM,
        "share_over": _worst_long_run_share(plan) > ceiling + 0.005,
    }


def _census() -> Tuple[Dict[str, Tuple[int, int, int, int]], Dict[str, str]]:
    """Per-goal deviation census, plus any combo the generator cannot build.

    Skips a combo the generator rejects: ``_KNOWN_UNPRODUCIBLE`` already pins
    those, and counting them here would double-report the same defect.
    """
    buckets: Dict[str, List[int]] = defaultdict(lambda: [0, 0, 0, 0])
    unbuildable: Dict[str, str] = {}
    for combo in COMBOS:
        try:
            plan = generate(combo)
        except Exception as exc:  # noqa: BLE001 - recorded, asserted separately
            _PLAN_CACHE.pop(combo.id, None)
            unbuildable[combo.id] = type(exc).__name__
            continue
        row = buckets[combo.goal.id]
        row[0] += 1
        verdict = _classify(combo, plan)
        for index, key in enumerate(("peak_over", "long_over", "share_over"), start=1):
            if verdict[key]:
                row[index] += 1
    return {k: tuple(v) for k, v in buckets.items()}, unbuildable


# ── Layer 3: the acceptance spec ──────────────────────────────────────────

# (label, PlanRequest kwargs, the exact exception the app must raise).
#
# One notch outside a published floor, per goal family and per axis. Until this
# existed, "the app refuses a 50 km ultra trained 3× a week" was an assumption
# nobody had written down.
#
# ``Exception`` is the placeholder for "the pydantic schema layer raised this".
# The schema wraps every validator ``ValueError`` in a ``ValidationError``, and a
# domain exception raised *inside* a validator propagates as itself (hence the
# named types). ``_expected_error`` resolves the placeholder, so an assertion
# here still pins the real type rather than passing on any failure whatsoever.
_SCHEMA_LAYER = ValidationError


def _expected_error(expected: type) -> type:
    """Resolve the table's ``Exception`` placeholder to the concrete type."""
    return _SCHEMA_LAYER if expected is Exception else expected


_REJECTIONS: Tuple[Tuple[str, Dict[str, Any], type], ...] = (
    # -- weeks: below the floor, and above the ceiling ----------------------
    (
        "5K below min weeks",
        {"target_distance": 5.0, "current_km": 20, "weeks": 5},
        InsufficientTimeException,
    ),
    (
        "5K above max weeks",
        {"target_distance": 5.0, "current_km": 20, "weeks": 17},
        Exception,
    ),
    (
        "Half below min weeks",
        {"target_distance": 21.1, "current_km": 30, "weeks": 7},
        InsufficientTimeException,
    ),
    (
        "Half above max weeks",
        {"target_distance": 21.1, "current_km": 30, "weeks": 21},
        Exception,
    ),
    (
        "Marathon below min weeks",
        {"target_distance": 42.2, "current_km": 40, "weeks": 11},
        InsufficientTimeException,
    ),
    (
        "Marathon above max weeks",
        {"target_distance": 42.2, "current_km": 40, "weeks": 25},
        Exception,
    ),
    ("weeks below the schema floor", {"weeks": 3}, Exception),
    ("weeks above the schema ceiling", {"weeks": 41}, Exception),
    # -- runs per week: the constraint the product is named for -------------
    (
        "Marathon at 3 runs",
        {
            "target_distance": 42.2,
            "current_km": 40,
            "weeks": 16,
            "max_runs_per_week": 3,
        },
        Exception,
    ),
    (
        "Half at 2 runs",
        {
            "target_distance": 21.1,
            "current_km": 30,
            "weeks": 12,
            "max_runs_per_week": 2,
        },
        Exception,
    ),
    (
        "any goal at 1 run",
        {"target_distance": 5.0, "current_km": 20, "weeks": 10, "max_runs_per_week": 1},
        Exception,
    ),
    (
        "any goal at 7 runs",
        {"target_distance": 5.0, "current_km": 20, "weeks": 10, "max_runs_per_week": 7},
        Exception,
    ),
    # -- base mileage ------------------------------------------------------
    (
        "5K from a 4 km base",
        {"target_distance": 5.0, "current_km": 4, "weeks": 10},
        InadequateBaseException,
    ),
    (
        "10K from a 9 km base",
        {"target_distance": 10.0, "current_km": 9, "weeks": 10},
        InadequateBaseException,
    ),
    (
        "Half from a 14 km base",
        {"target_distance": 21.1, "current_km": 14, "weeks": 12},
        InadequateBaseException,
    ),
    (
        "Marathon from a 24 km base",
        {"target_distance": 42.2, "current_km": 24, "weeks": 16},
        InadequateBaseException,
    ),
    ("base above the schema ceiling", {"current_km": 201}, Exception),
    ("base below zero", {"current_km": -1}, Exception),
    # -- zero mileage ------------------------------------------------------
    (
        "zero base for a Half",
        {"target_distance": 21.1, "current_km": 0, "weeks": 12},
        ZeroMileageUnsupportedException,
    ),
    (
        "zero base for a Marathon",
        {"target_distance": 42.2, "current_km": 0, "weeks": 16},
        ZeroMileageUnsupportedException,
    ),
    (
        "zero base for a 5K in under 8 weeks",
        {"target_distance": 5.0, "current_km": 0, "weeks": 6, "max_runs_per_week": 3},
        InsufficientTimeException,
    ),
    # -- trail / ultra: the combinations this module exists to pin ----------
    (
        "50 km ultra at 2 runs",
        {
            "target_distance": 50.0,
            "current_km": 60,
            "weeks": 20,
            "max_runs_per_week": 2,
            "is_trail": True,
            "target_elevation_gain_m": 2000.0,
        },
        Exception,
    ),
    (
        "50 km ultra at 3 runs",
        {
            "target_distance": 50.0,
            "current_km": 60,
            "weeks": 20,
            "max_runs_per_week": 3,
            "is_trail": True,
            "target_elevation_gain_m": 2000.0,
        },
        Exception,
    ),
    (
        "50 km ultra at 4 runs",
        {
            "target_distance": 50.0,
            "current_km": 60,
            "weeks": 20,
            "max_runs_per_week": 4,
            "is_trail": True,
            "target_elevation_gain_m": 2000.0,
        },
        Exception,
    ),
    (
        "50 km ultra in 10 weeks",
        {
            "target_distance": 50.0,
            "current_km": 60,
            "weeks": 10,
            "max_runs_per_week": 5,
            "is_trail": True,
            "target_elevation_gain_m": 2000.0,
        },
        InsufficientTimeException,
    ),
    (
        "50 km ultra on a 17 km base",
        {
            "target_distance": 50.0,
            "current_km": 17.0,
            "weeks": 20,
            "max_runs_per_week": 5,
            "is_trail": True,
            "target_elevation_gain_m": 2000.0,
        },
        InadequateBaseException,
    ),
    (
        "100 km ultra at 5 runs",
        {
            "target_distance": 100.0,
            "current_km": 60,
            "weeks": 24,
            "max_runs_per_week": 5,
            "is_trail": True,
            "target_elevation_gain_m": 4000.0,
        },
        Exception,
    ),
    (
        "100 km ultra on a 34 km base",
        {
            "target_distance": 100.0,
            "current_km": 34.0,
            "weeks": 24,
            "max_runs_per_week": 6,
            "is_trail": True,
            "target_elevation_gain_m": 4000.0,
        },
        InadequateBaseException,
    ),
    (
        "trail shorter than the trail floor",
        {
            "target_distance": 7.0,
            "current_km": 30,
            "weeks": 10,
            "is_trail": True,
            "target_elevation_gain_m": 300.0,
        },
        Exception,
    ),
    (
        "trail longer than the trail ceiling",
        {
            "target_distance": 164.0,
            "current_km": 60,
            "weeks": 20,
            "is_trail": True,
            "target_elevation_gain_m": 4000.0,
        },
        Exception,
    ),
    (
        "trail with no elevation given",
        {"target_distance": 50.0, "current_km": 60, "weeks": 20, "is_trail": True},
        Exception,
    ),
    # -- road distance membership -----------------------------------------
    (
        "a 15 km road race",
        {"target_distance": 15.0, "current_km": 30, "weeks": 10},
        Exception,
    ),
    (
        "a 100 km road race (needs trail mode)",
        {"target_distance": 100.0, "current_km": 60, "weeks": 20},
        Exception,
    ),
    # -- backyard ----------------------------------------------------------
    (
        "backyard under the loop floor",
        {
            "current_km": 60,
            "weeks": 20,
            "max_runs_per_week": 5,
            "is_backyard": True,
            "backyard_target_loops": 5,
        },
        Exception,
    ),
    (
        "backyard over the loop ceiling",
        {
            "current_km": 60,
            "weeks": 20,
            "max_runs_per_week": 5,
            "is_backyard": True,
            "backyard_target_loops": 49,
        },
        Exception,
    ),
    (
        "24-loop backyard at 3 runs",
        {
            "current_km": 70,
            "weeks": 20,
            "max_runs_per_week": 3,
            "is_backyard": True,
            "backyard_target_loops": 24,
        },
        Exception,
    ),
    (
        "24-loop backyard on a 10 km base",
        {
            "current_km": 10,
            "weeks": 20,
            "max_runs_per_week": 5,
            "is_backyard": True,
            "backyard_target_loops": 24,
        },
        InadequateBaseException,
    ),
    (
        "24-loop backyard in a week-less block",
        {
            "current_km": 70,
            "weeks": 3,
            "max_runs_per_week": 5,
            "is_backyard": True,
            "backyard_target_loops": 24,
        },
        Exception,
    ),
)


# ── Layer 4: adaptation scenarios ─────────────────────────────────────────


@dataclass(frozen=True)
class Scenario:
    """A goal plus how much of the plan the runner has already executed."""

    goal: Goal
    weeks: int
    base: float
    runs: int
    completion: float
    distance_factor: float
    pace_min_km: float
    label: str


def _goal(goal_id: str) -> Goal:
    """Look a goal up by id, so a scenario says which goal it means."""
    for goal in GOALS:
        if goal.id == goal_id:
            return goal
    raise KeyError(f"no such goal: {goal_id}")


SCENARIOS: Tuple[Scenario, ...] = (
    Scenario(_goal("road-21.1km"), 16, 40.0, 4, 1.0, 1.0, 5.5, "on-plan half runner"),
    Scenario(
        _goal("road-42.2km"), 16, 50.0, 5, 0.75, 1.25, 4.6, "over-reaching marathoner"
    ),
    Scenario(
        _goal("road-21.1km"),
        14,
        35.0,
        4,
        0.6,
        0.7,
        6.4,
        "under-performing half runner",
    ),
    Scenario(
        _goal("trail-50km/ultra"), 20, 60.0, 5, 1.0, 1.0, 6.0, "on-plan 50 km ultra"
    ),
    Scenario(
        _goal("trail-100km/long_ultra"),
        24,
        90.0,
        6,
        0.8,
        1.1,
        6.2,
        "100 km ultra, over plan",
    ),
    Scenario(
        _goal("backyard-18loops/night"), 20, 70.0, 5, 1.0, 1.0, 5.8, "on-plan backyard"
    ),
)


def _request_for(scenario: Scenario, runs: int) -> PlanRequest:
    kwargs: Dict[str, Any] = {
        "current_km": scenario.base,
        "weeks": scenario.weeks,
        "max_runs_per_week": runs,
    }
    kwargs.update(scenario.goal.request_kwargs())
    return PlanRequest(**kwargs)


def _persist(db: Session, scenario: Scenario) -> Tuple[User, TrainingPlan]:
    """Generate and store a plan exactly the way the app does."""
    user = User(
        id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.com", name="Matrix Runner"
    )
    db.add(user)
    db.flush()

    request = _request_for(scenario, scenario.runs)
    plan_data = GEN.generate_plan(
        current_km=scenario.base,
        target_distance=scenario.goal.distance_km,
        weeks=scenario.weeks,
        max_runs_per_week=scenario.runs,
        **scenario.goal.generator_kwargs(),
    )
    plan = persist_plan_core(request, user, plan_data, db)
    plan.start_date = date.today() - timedelta(days=7 * 6)
    persist_weekly_workouts(plan, plan_data, db)
    db.commit()
    return user, plan


def _reload(db: Session, plan: TrainingPlan) -> List[Dict[str, Any]]:
    """A deep copy of the stored snapshot.

    Deep matters: a shallow copy shares the nested workout dicts with the live
    object, so a "before" snapshot silently mutates along with "after" and the
    comparison becomes vacuously true.
    """
    db.expire_all()
    fresh = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
    return copy.deepcopy(list(fresh.plan_data or []))


def _log_sessions(
    db: Session, user: User, plan: TrainingPlan, scenario: Scenario
) -> int:
    """Log the planned sessions up to today, as the runner would have run them."""
    today = date.today()
    # ``start_date`` comes back off the row as a datetime; compare on the date.
    start = (
        plan.start_date.date() if hasattr(plan.start_date, "date") else plan.start_date
    )
    # Collect the sessions that are already in the past, then log a share of
    # them. ``completion`` is the archetype's adherence; taking a chronological
    # prefix keeps the miss pattern deterministic (a tail of missed sessions
    # rather than a random scatter).
    past: List[Tuple[date, float]] = []
    for week in _reload(db, plan):
        week_start = start + timedelta(weeks=week["week"] - 1)
        for workout in week.get("daily_workouts", []):
            if (workout.get("distance") or 0) <= 0:
                continue
            if workout.get("type") in NON_RUNNING:
                continue
            day = week_start + timedelta(days=(workout.get("day") or 1) - 1)
            if day <= today:
                past.append((day, float(workout["distance"])))

    logged = 0
    for day, prescribed in past[: int(len(past) * scenario.completion)]:
        km = round(prescribed * scenario.distance_factor, 2)
        if km <= 0:
            continue
        db.add(
            RunLog(
                id=str(uuid.uuid4()),
                user_id=user.id,
                training_plan_id=plan.id,
                date=day,
                distance_km=km,
                duration_minutes=round(km * scenario.pace_min_km, 1),
                avg_pace_min_km=scenario.pace_min_km,
                workout_type="easy",
                source="intervals",
            )
        )
        logged += 1
    db.commit()
    return logged


# ── Layer 1 tests ─────────────────────────────────────────────────────────


# Defects this grid used to carry are FIXED, and the ledger is deliberately
# empty rather than deleted: it is a regression net. Two kinds of breakage live
# here — a flexible session squeezed to a 0.0 km card, and a week jumping past
# the app's own weekly ramp cap. Both came from marginal backyard weeks, where
# a format-sized prescriptive weekend was funded out of the budget the midweek
# sessions had already spent (there is no simulation-week sizing that takes the
# week's other sessions into account, so the easy runs absorbed the shortfall).
#
# Recorded as *kinds* rather than raw strings, so retuning a distance does not
# churn the ledger — but any combo that starts failing again shows up here, and
# `test_week_defect_ledger_is_complete` names it.
ZERO_DISTANCE_RUN = "zero-distance run"
WEEKLY_RAMP_BREACH = "10% ramp breach"

_KNOWN_WEEK_DEFECTS: Dict[str, Tuple[str, ...]] = {}


def _failure_kind(message: str) -> str:
    """Collapse a failure message to its kind, so the ledger survives retuning."""
    if "easy with no distance" in message:
        return ZERO_DISTANCE_RUN
    if "% jump (" in message:
        return WEEKLY_RAMP_BREACH
    return message


def _week_defects() -> Dict[str, Tuple[str, ...]]:
    """Every combo with at least one invariant failure, as kinds of failure."""
    out: Dict[str, Tuple[str, ...]] = {}
    for combo in COMBOS:
        if _is_unproducible(combo):
            continue
        failures = _invariant_failures(combo, generate(combo))
        if failures:
            out[combo.id] = tuple(sorted({_failure_kind(f) for f in failures}))
    return out


@pytest.mark.parametrize("combo", COMBOS, ids=[c.id for c in COMBOS])
def test_generated_plan_satisfies_every_invariant(combo: Combo):
    """No accepted combination may produce an unsound plan.

    One generation per combo, every invariant checked in one body. The old grid
    regenerated the same plan once per assertion, which is what kept it from
    ever being widened to ultras.
    """
    if _is_unproducible(combo):  # pragma: no cover - asserted empty below
        pytest.skip("unproducible — see test_every_accepted_combo_is_generatable")

    failures = _invariant_failures(combo, generate(combo))
    pinned = _KNOWN_WEEK_DEFECTS.get(combo.id)
    if pinned is not None:
        assert failures, (
            f"{combo.id}: the pinned defect is gone — remove it from "
            "_KNOWN_WEEK_DEFECTS"
        )
        kinds = sorted({_failure_kind(f) for f in failures})
        assert kinds == sorted(pinned), (
            f"{combo.id}: pinned defects changed shape.\n"
            f"  pinned: {sorted(pinned)}\n  actual: {kinds}\n  raw: {failures}"
        )
        return

    assert failures == [], f"{combo.id}: " + "; ".join(failures)


def test_week_defect_ledger_is_complete():
    """No combo on the grid may compose into a broken week.

    The ledger above is empty, so this asserts the grid is clean — and reports
    each offender by name (and kind) rather than by a count, so a regression
    lands on the responsible combination.
    """
    actual = _week_defects()
    new_defects = sorted(set(actual) - set(_KNOWN_WEEK_DEFECTS))
    fixed = sorted(set(_KNOWN_WEEK_DEFECTS) - set(actual))
    changed = {
        cid: {
            "pinned": sorted(_KNOWN_WEEK_DEFECTS[cid]),
            "actual": sorted(actual[cid]),
        }
        for cid in sorted(set(actual) & set(_KNOWN_WEEK_DEFECTS))
        if actual[cid] != tuple(sorted(_KNOWN_WEEK_DEFECTS[cid]))
    }
    assert not (new_defects or fixed or changed), (
        f"week defect ledger drifted.\n  new defects: {new_defects}\n"
        f"  pinned but now clean: {fixed}\n  changed shape: {changed}"
    )


def test_matrix_covers_the_advertised_range():
    """The matrix must actually span 5K→163 km, 2→6 runs, all three families."""
    kinds = {c.goal.kind for c in COMBOS}
    assert kinds == {"road", "trail", "backyard"}

    assert min(c.goal.distance_km for c in COMBOS) <= 5.0
    assert max(c.goal.distance_km for c in COMBOS) >= 100.0

    assert min(c.runs for c in COMBOS) == 2
    assert max(c.runs for c in COMBOS) == 6

    # One representative per trail bracket, and the 100 km ultra specifically.
    brackets = {c.goal.trail.bracket for c in COMBOS if c.goal.trail is not None}
    assert brackets == {"short", "standard", "ultra", "long_ultra"}
    assert any(c.goal.trail is not None and c.goal.distance_km == 100.0 for c in COMBOS)


def test_matrix_is_derived_from_the_app_registries():
    """Every goal's floors must equal the app's published floors.

    This is the check the old grid could not pass — it carried its own copy of
    the constraint table, so a registry change moved the app and left the spec
    behind.
    """
    for goal in GOALS:
        if goal.kind == "road":
            c = DISTANCE_CONSTRAINTS[goal.distance_km]
            assert (goal.min_weeks, goal.max_weeks) == (c.min_weeks, c.max_weeks)
            assert goal.bases[0] == c.min_mileage
        elif goal.kind == "trail":
            bracket = goal.trail.bracket
            assert goal.min_weeks == _BRACKET_MIN_WEEKS[bracket]
            assert goal.max_weeks == _BRACKET_MAX_WEEKS[bracket]
            assert goal.min_runs == _BRACKET_MIN_RUNS[bracket]
        else:
            tier = goal.backyard.tier
            assert goal.min_weeks == _TIER_MIN_WEEKS[tier]
            assert goal.max_weeks == _TIER_MAX_WEEKS[tier]
            assert goal.min_runs == _TIER_MIN_RUNS_PER_WEEK[tier]


# ── Layer 2 tests ─────────────────────────────────────────────────────────


# The trail ``short`` bracket used to advertise ``min_weeks = 5`` while
# ``phase_calculator.MIN_WEEKS_FOR_PHASES`` refused anything under 6, so every
# 5-week short-bracket request passed ``PlanRequest`` and then threw from the
# generator: the validator's floor and the engine's floor disagreed. The bracket
# floor is 6 now and the grid derives its week axis from it, so the invariant is
# simply that nothing the schema accepts is unbuildable.
def test_every_accepted_combo_is_generatable():
    """An accepted request must produce a plan — no accepted-but-unbuildable combo.

    Fails on any disagreement between a validator floor and the engine's own.
    That is exactly how the trail ``short`` 5-week hole survived: the schema
    said yes and the generator said no, and nothing compared the two.
    """
    unbuildable = sorted(c.id for c in COMBOS if _is_unproducible(c))
    assert unbuildable == [], (
        "the app accepts these but cannot generate them: " + ", ".join(unbuildable)
    )


_UNPRODUCIBLE_CACHE: Dict[str, bool] = {}


@pytest.mark.parametrize("combo", COMBOS, ids=[c.id for c in COMBOS])
def test_plan_request_accepts_every_matrix_combo(combo: Combo):
    """Every combo in the grid must be one the schema layer actually accepts.

    Generating straight from the engine would let a combo into the matrix that
    ``PlanRequest`` refuses — the grid would then be describing a product that
    does not exist. The rejection table covers the other direction.
    """
    request = PlanRequest(
        current_km=combo.base,
        weeks=combo.weeks,
        max_runs_per_week=combo.runs,
        **combo.goal.request_kwargs(),
    )
    assert request.weeks == combo.weeks


def _is_unproducible(combo: Combo) -> bool:
    if combo.id in _UNPRODUCIBLE_CACHE:
        return _UNPRODUCIBLE_CACHE[combo.id]
    try:
        generate(combo)
        ok = False
    except Exception:  # noqa: BLE001 - any failure counts
        _PLAN_CACHE.pop(combo.id, None)
        ok = True
    _UNPRODUCIBLE_CACHE[combo.id] = ok
    return ok


def test_envelope_census_matches_the_pinned_ledger():
    """The imbalance census must match the pinned per-goal counts.

    A change in any column is a deliberate decision, not a side effect: it means
    some goal started leaning harder on its long run, or over-prescribing.
    """
    actual, _ = _census()
    assert actual == _ENVELOPE_CENSUS, (
        "envelope census drifted.\n"
        f"  newly deviating goals: {sorted(set(actual) - set(_ENVELOPE_CENSUS))}\n"
        f"  goals that disappeared: {sorted(set(_ENVELOPE_CENSUS) - set(actual))}\n"
        + "\n".join(
            f"  {g}: pinned {_ENVELOPE_CENSUS[g]} -> actual {actual[g]}"
            for g in sorted(set(actual) & set(_ENVELOPE_CENSUS))
            if actual[g] != _ENVELOPE_CENSUS[g]
        )
    )


def test_no_race_plan_over_prescribes_weekly_volume():
    """A race-based plan must never exceed the envelope's peak-week ceiling.

    Split out of the census on purpose. The census pins *counts*, which is a
    drift detector; this is the safety property underneath it. Over-prescribing
    a recreational runner's peak week is the one deviation the envelope exists
    to prevent, and it must fail on its own rather than as an arithmetic
    difference.

    Covers road **and** trail. It used to be road-only because the envelope's
    band stopped at the marathon, so every ultra was judged against a marathon's
    ceiling; ``PEAK_WEEK_KM`` now runs to 163 km and the trail column passes.
    Backyard is excluded and cannot be checked this way: its band is keyed on a
    clamped projection, so a high-base backyard runner sits above a band derived
    from a race distance they are not training for.
    """
    offenders = []
    for combo in COMBOS:
        if combo.goal.kind == "backyard":
            continue  # keyed on a clamped projection, not a race distance
        plan = generate(combo)
        _, hi = env.peak_week_band(combo.goal.distance_km, combo.viable_runs)
        peak = _peak_week(plan)
        if peak > hi + _ENVELOPE_SLACK_KM:
            offenders.append(f"{combo.id}: peak {peak:.1f} > ceiling {hi:.1f}")
    assert offenders == [], "over-prescribed peak weeks: " + "; ".join(offenders)


def test_long_runs_respect_the_app_hard_ceiling():
    """No long run may exceed the app's own tiered ceiling.

    ``physiological_envelope`` is a published reference band;
    ``training_constants`` holds the contract the app enforces, and the
    envelope's own docstring says the tier table wins where the two disagree —
    so this is the binding check.

    It used to fail: the trail curve reached 48 km for 100-mile prep against a
    38 km ceiling, so the generator prescribed straight past its own safety net
    (the "looser absolute" bound was in fact tighter than the cap it bounded).
    The curve is now clamped to the bracket value, which is what makes this an
    assertion rather than a ledger.
    """
    offenders = []
    for combo in COMBOS:
        if _is_unproducible(combo):  # pragma: no cover - asserted empty above
            continue
        ceiling = get_hard_ceiling(combo.goal.distance_km, combo.goal.trail)
        longest = _longest_long_run(generate(combo))
        if longest > ceiling + _ENVELOPE_SLACK_KM:
            offenders.append(
                f"{combo.id}: long run {longest:.1f} > ceiling {ceiling:.1f}"
            )
    assert offenders == [], "long runs past the hard ceiling: " + "; ".join(offenders)


# ── Layer 3 tests ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "label,kwargs,expected",
    _REJECTIONS,
    ids=[r[0].replace(" ", "-") for r in _REJECTIONS],
)
def test_invalid_combination_is_rejected(label: str, kwargs, expected):
    """The app must refuse the invalid combination, with the right exception type.

    ``expected`` is the public type the caller is meant to catch, so a
    regression that downgrades a domain error to a bare ``ValueError`` — or
    drops the check entirely — fails here.
    """
    payload = {
        "current_km": 30.0,
        "target_distance": 10.0,
        "weeks": 10,
        "max_runs_per_week": 4,
    }
    payload.update(kwargs)
    with pytest.raises(_expected_error(expected)):
        PlanRequest(**payload)


@pytest.mark.parametrize(
    "label,kwargs,expected",
    _REJECTIONS,
    ids=[r[0].replace(" ", "-") for r in _REJECTIONS],
)
def test_rejection_is_not_a_bare_crash(label: str, kwargs, expected):
    """A rejected request must carry a user-facing message, not just blow up.

    ``RunCoachException`` carries ``user_message``/``suggestion`` and is mapped
    to an HTTP response by the global handler; a rejection a user cannot read is
    a rejection the UI renders as a 500.
    """
    payload = {
        "current_km": 30.0,
        "target_distance": 10.0,
        "weeks": 10,
        "max_runs_per_week": 4,
    }
    payload.update(kwargs)
    with pytest.raises(_expected_error(expected)) as caught:
        PlanRequest(**payload)
    exc = caught.value
    message = getattr(exc, "user_message", None) or str(exc)
    assert message and message.strip(), f"{label}: rejection has no message"


# ── Layer 4 tests ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scenario", SCENARIOS, ids=[s.label.replace(" ", "-") for s in SCENARIOS]
)
def test_adaptation_keeps_the_plan_sound(test_db: Session, scenario: Scenario):
    """Re-pacing an executed block must not break the plan's balance.

    This is the half that static generation cannot answer: the runner logs what
    they actually ran, the adaptive engine re-paces the future, and the *result*
    must still hold the invariants. A distance or frequency that generates
    cleanly but adapts into a collapsed week is caught here and nowhere else.
    """
    user, plan = _persist(test_db, scenario)
    before = _reload(test_db, plan)
    logged = _log_sessions(test_db, user, plan, scenario)
    assert logged > 0, f"{scenario.label}: fixture logged no runs"

    results = auto_map_and_adjust(user, test_db, AdaptationService())
    assert results, f"{scenario.label}: engine returned no result"

    after = _reload(test_db, plan)
    assert len(after) == len(before), "adaptation changed the number of weeks"

    issues = check_plan_structure(after)
    assert issues["fatal"] == [], (
        f"adaptation made the plan unrunnable: {issues['fatal']}"
    )

    # Race day is set by the event; no adaptation may move it.
    assert _race_distance(after) == _race_distance(before), "adaptation moved race day"

    for week in after:
        assert _running(week), f"week {week.get('week')} lost its runnable session"
        if not week.get("is_recovery"):
            total = week.get("total_km") or 0
            assert total >= MIN_VIABLE_NON_RECOVERY_KM, (
                f"week {week.get('week')} collapsed to {total} km"
            )

    # A taper may be drawn down, never inflated, and must still descend.
    for original, adapted in zip(before, after):
        if original.get("phase") != "taper":
            continue
        assert training_km(adapted) <= training_km(original) + 0.05, (
            f"taper week {adapted.get('week')} grew from "
            f"{training_km(original):.1f} to {training_km(adapted):.1f} km"
        )
    taper = [training_km(w) for w in after if w.get("phase") == "taper"]
    for earlier, later in zip(taper, taper[1:]):
        assert later <= earlier + 0.05, f"taper climbs after adaptation: {taper}"


@pytest.mark.parametrize(
    "scenario", SCENARIOS, ids=[s.label.replace(" ", "-") for s in SCENARIOS]
)
def test_adaptation_does_not_over_prescribe(test_db: Session, scenario: Scenario):
    """Adapting must not push a road plan past its envelope ceiling either.

    Generation is checked separately; this is the same ceiling applied to what
    the runner ends up holding after the engine has re-paced them.
    """
    user, plan = _persist(test_db, scenario)
    _log_sessions(test_db, user, plan, scenario)
    auto_map_and_adjust(user, test_db, AdaptationService())
    after = _reload(test_db, plan)

    if scenario.goal.kind != "road":
        pytest.skip("envelope band is interpolated for trail/ultra")  # pragma: no cover

    _, hi = env.peak_week_band(scenario.goal.distance_km, scenario.runs)
    peak = _peak_week(after)
    assert peak <= hi + _ENVELOPE_SLACK_KM, (
        f"{scenario.label}: adapted peak {peak:.1f} > ceiling {hi:.1f}"
    )


def _race_distance(plan_data: List[Dict[str, Any]]) -> float:
    for week in plan_data:
        for workout in week.get("daily_workouts", []):
            if workout.get("type") == "race":
                return float(workout.get("distance") or 0)
    return 0.0


# ── Layer 5: the form endpoint and the legacy call paths ──────────────────
#
# Everything above drives the schema or the engine directly. These drive the
# thing the runner actually touches, plus the back-compat paths that only the
# HTTP layer or an already-stored row can reach.


def _post_plan(client, **fields):
    """Submit the plan form the way the browser does."""
    payload = {
        "current_km": 20.0,
        "target_distance": "10.0",
        "weeks": 10,
        "max_runs_per_week": 4,
        "body_weight_kg": 70.0,
    }
    payload.update(fields)
    return client.post("/generate-plan", data=payload, follow_redirects=False)


# One per goal family, at both ends of each axis.
_ACCEPTED_VIA_HTTP = (
    (5.0, "5.0", 6, 2),
    (40.0, "5.0", 16, 5),
    (10.0, "10.0", 6, 2),
    (50.0, "10.0", 16, 5),
    (15.0, "21.1", 8, 3),
    (70.0, "21.1", 20, 5),
    (25.0, "42.2", 12, 4),
    (100.0, "42.2", 24, 5),
    (15.0, "30.0", 6, 4),
    (60.0, "30.0", 20, 5),
)


@pytest.mark.parametrize(
    "current_km,distance,weeks,runs",
    _ACCEPTED_VIA_HTTP,
    ids=[f"{d}km-{w}wk-{k:g}base-{r}r" for k, d, w, r in _ACCEPTED_VIA_HTTP],
)
def test_http_accepts_a_valid_plan(client, current_km, distance, weeks, runs):
    """A valid submission redirects to the plan page.

    The schema and the engine are each checked on their own above; neither can
    see whether the form wires them together and answers with a redirect rather
    than an error.
    """
    response = _post_plan(
        client,
        current_km=current_km,
        target_distance=distance,
        weeks=weeks,
        max_runs_per_week=runs,
    )
    assert response.status_code == 303, response.text[:400]
    assert "/plan/" in response.headers.get("location", "")


# (current_km, distance, weeks, runs) one notch outside a floor, plus the phrase
# the rendered page must carry. Each is the *user-facing* end of a rejection
# asserted at the schema layer above — this is where the ``user_message``
# contract is cashed in.
_REJECTED_VIA_HTTP = (
    (20.0, "5.0", 5, 2, "requires at least"),
    (20.0, "10.0", 5, 3, "requires at least"),
    (30.0, "21.1", 7, 3, "requires at least"),
    (30.0, "42.2", 11, 4, "requires at least"),
    (20.0, "21.1", 12, 2, "requires at least"),
    (30.0, "42.2", 16, 3, "requires at least"),
    (3.0, "5.0", 8, 3, "below recommended minimum"),
    (5.0, "10.0", 8, 3, "below recommended minimum"),
    (10.0, "21.1", 12, 4, "below recommended minimum"),
    (20.0, "42.2", 16, 4, "below recommended minimum"),
    (0.0, "42.2", 16, 4, "not recommended"),
)


@pytest.mark.parametrize(
    "current_km,distance,weeks,runs,phrase",
    _REJECTED_VIA_HTTP,
    ids=[f"{d}km-{w}wk-{k:g}base-{r}r" for k, d, w, r, _ in _REJECTED_VIA_HTTP],
)
def test_http_renders_a_readable_rejection(
    client, current_km, distance, weeks, runs, phrase
):
    """An invalid submission must reach the runner as a page, not a 500.

    ``RunCoachException`` carries ``user_message``/``suggestion`` for exactly
    this moment. A rejection the template cannot render is a stack trace in
    front of the user, so the page is asserted on, not just the status code.
    """
    response = _post_plan(
        client,
        current_km=current_km,
        target_distance=distance,
        weeks=weeks,
        max_runs_per_week=runs,
    )
    assert response.status_code == 200, response.status_code
    body = response.text.lower()
    assert 'class="alert alert-' in body, "rejection rendered without an alert"
    assert phrase in body, f"{phrase!r} missing from the error page"


@pytest.mark.parametrize("distance", [5.0, 10.0])
def test_two_run_weeks_do_not_collapse_mid_plan(distance):
    """A 2-run build/peak week must not crater far below the plan's peak.

    Regression: both weekly slots used to take a prescriptive key workout, so
    the flexible volume had nowhere to live and the shortfall was silently
    dropped — a 30 km/week runner could fall to ~12 km mid-plan. With no easy
    run to carry the volume the long run has to stay flexible.
    """
    plan = TrainingPlanGenerator().generate_plan(30, distance, 12, 2)
    peak = max(w["total_km"] for w in plan if not w.get("is_recovery"))

    for week in plan:
        if week.get("is_recovery") or week["phase"] == "taper":
            continue
        running = [
            w
            for w in week["daily_workouts"]
            if w.get("type") not in NON_RUNNING and (w.get("distance") or 0) > 0
        ]
        longs = [w for w in running if w["type"] == "long"]
        if not any(w["type"] == "easy" for w in running) and longs:
            assert not longs[0].get("key_workout_id"), (
                f"week {week['week']}: long run pinned with no easy run to "
                "carry the volume"
            )
        assert week["total_km"] >= 0.6 * peak, (
            f"week {week['week']} ({week['phase']}) collapsed to "
            f"{week['total_km']} km against a {peak} km peak"
        )


def test_marathon_peak_is_adequate():
    """A 16-week marathon block must actually periodise into marathon volume.

    Distinct from the envelope census, which compares *bands*: this pins that a
    25 km/week runner is taken somewhere real rather than held near their
    starting volume.
    """
    plan = TrainingPlanGenerator().generate_plan(25, 42.2, 16, 4)
    peak = max(w["total_km"] for w in plan if not w.get("is_recovery"))
    assert peak >= 45


def test_legacy_road_30km_promotes_to_trail():
    """A bare ``target_distance=30.0`` still becomes a trail plan.

    Pre-existing form posts and stored rows used 30.0 plus a ``terrain`` toggle;
    the schema migrates them at the edge. Nothing else pins that path, and
    dropping it would break every 30 km plan already in the database.
    """
    migrated = PlanRequest(
        current_km=20.0, target_distance=30.0, weeks=10, max_runs_per_week=4
    )
    assert migrated.is_trail is True
    assert migrated.target_elevation_gain_m == 1000.0

    flat = PlanRequest(
        current_km=20.0,
        target_distance=30.0,
        weeks=10,
        max_runs_per_week=4,
        terrain="flat",
    )
    assert flat.target_elevation_gain_m == 200.0

    # The engine accepts the legacy signature too, with no profile passed.
    plan = TrainingPlanGenerator().generate_plan(20.0, 30.0, 10, 4)
    assert len(plan) == 10
    assert check_plan_structure(plan)["fatal"] == []
