"""The block after the race: a short reverse taper back to steady running.

A training plan ends on race day, and for a long time so did RunCoach: the
runner got a "Plan complete" card and a blank calendar at exactly the moment
they are most likely to either stop running or jump straight back into hard
work on legs that are still repairing. Coaches fill that gap with a recovery
block — all easy running, volume brought back in steps, no quality until the
race has been absorbed — and this module prescribes one.

Two constraints shape it:

* **Length follows the race, not the plan.** It is the same one-easy-day-per-
  mile rule the "Recover first" line on a finished plan quotes
  (:func:`app.core.race.recovery.easy_days_after`), rounded up to whole weeks,
  plus one week to return to steady running: two weeks after a 5K, three after
  a half, five after a marathon — which is also the length of Pfitzinger's
  post-marathon schedule.
* **Volume is anchored on the runner's own peak.** The block steps back up to
  the same share of the peak week that line tells the runner to start their
  next plan from (``NEXT_BLOCK_FRACTION``), and never above it, so the two
  surfaces cannot give different advice.

Everything here is pure: the numbers in, a ``plan_data`` week list out, in the
same shape the generators produce so the plan page, the watch mirror and the
adaptation engine read it without special cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from app.core.race.recovery import NEXT_BLOCK_FRACTION, easy_days_after
from app.core.training.workouts.workout_steps.aerobic import (
    build_recovery_block_steps,
)

# The shortest run worth lacing up for. Below this the week loses a run rather
# than scheduling several jogs too short to be training — down to two runs,
# which may then be shorter: the volume is never inflated past the runner's
# own peak to make the runs "worth it".
_MIN_RUN_KM = 3.0

# Once it returns, the long run is this multiple of the week's easy runs: a
# clearly longer day, but no step-change while the legs are still rebuilding.
_LONG_RATIO = 1.4

# Weekday layouts (1 = first day of the block's week). The first week keeps the
# days straight after the race free; in later weeks the last run listed — the
# long one, once it returns — lands on day 6, matching the generators so the
# runner's rhythm carries over. Tuesday and Friday stay free (``FREE_WEEKDAYS``
# in tuning.py) wherever the week has room; six runs need one of them back and
# take Friday.
_FIRST_WEEK_DAYS: Dict[int, tuple[int, ...]] = {
    2: (3, 6),
    3: (3, 4, 6),
    4: (3, 4, 6, 7),
}
_WEEK_DAYS: Dict[int, tuple[int, ...]] = {
    2: (3, 6),
    3: (1, 3, 6),
    4: (1, 3, 4, 6),
    5: (1, 3, 4, 7, 6),
    6: (1, 3, 4, 5, 7, 6),
}


@dataclass(frozen=True)
class RecoveryPrescription:
    """How long the block is and how its volume returns, week by week."""

    # Share of the finished plan's peak week scheduled in each week.
    volume_fractions: tuple[float, ...]
    # First week (0-indexed) whose runs carry strides again.
    strides_from_week: int
    # First week (0-indexed) with a long run.
    long_run_from_week: int

    @property
    def weeks(self) -> int:
        return len(self.volume_fractions)


# Share of the peak scheduled in the week straight after the race. The longer
# the race, the deeper the first week: a 5K barely dents the legs, an ultra
# leaves them needing most of a week off.
_FIRST_WEEK_FRACTION = ((10.0, 0.55), (21.1, 0.45), (42.2, 0.35))
_ULTRA_FIRST_WEEK_FRACTION = 0.3


def recovery_prescription(race_km: float) -> RecoveryPrescription:
    """Prescribe the recovery block for a race of ``race_km``."""
    easy_weeks = -(-easy_days_after(race_km) // 7)  # ceil
    weeks = easy_weeks + 1
    start = next(
        (f for limit, f in _FIRST_WEEK_FRACTION if race_km <= limit),
        _ULTRA_FIRST_WEEK_FRACTION,
    )
    step = (NEXT_BLOCK_FRACTION - start) / (weeks - 1)
    fractions = tuple(round(start + step * i, 3) for i in range(weeks))
    return RecoveryPrescription(
        volume_fractions=fractions,
        # Strides are form work, not a hard session, so they may return in the
        # last easy-only week rather than waiting for the steady one.
        strides_from_week=max(1, easy_weeks - 1),
        long_run_from_week=1 if race_km <= 42.2 else 2,
    )


def peak_weekly_km(plan_data: Sequence[Dict[str, Any]]) -> float:
    """The biggest week the runner was scheduled, race weeks included."""
    return max(
        (float(week.get("total_km") or 0.0) for week in plan_data or []),
        default=0.0,
    )


def _split_week(
    volume_km: float, runs: int, with_long: bool
) -> tuple[List[float], Optional[int]]:
    """Share ``volume_km`` across ``runs`` runs, to 0.1 km, summing exactly.

    Returns the distances and the index of the long run (or ``None``).
    """
    if with_long and runs >= 3:
        easy_km = volume_km / (runs - 1 + _LONG_RATIO)
        distances = [easy_km] * (runs - 1) + [easy_km * _LONG_RATIO]
        long_index: Optional[int] = runs - 1
    else:
        distances = [volume_km / runs] * runs
        long_index = None
    rounded = [round(d, 1) for d in distances]
    # Put the rounding remainder on the last run so the week sums to its target.
    rounded[-1] = round(rounded[-1] + round(volume_km, 1) - round(sum(rounded), 1), 1)
    return rounded, long_index


def _runs_for(volume_km: float, wanted: int) -> int:
    return max(2, min(wanted, int(volume_km // _MIN_RUN_KM)))


def _week_copy(index: int, weeks: int, race_name: str) -> tuple[str, List[str]]:
    """Rationale and tips for week ``index`` of ``weeks``."""
    if index == 0:
        return (
            f"Your {race_name} is still in your legs even when they feel fine — "
            "the muscle damage takes days to clear. Every run this week is short "
            "and slower than feels necessary.",
            [
                "Skip a run rather than push through lingering soreness",
                "Sleep and protein do more for you this week than mileage",
                "No pace targets — if in doubt, slow down",
            ],
        )
    if index == weeks - 1:
        return (
            "Back to steady running: volume at about 70% of your peak "
            "and strides to reawaken leg speed. This is the base your next block "
            "starts from.",
            [
                "Strides are form work — quick and relaxed, never a sprint",
                "Pick your next goal this week so the momentum carries over",
            ],
        )
    return (
        "Rebuilding: easy aerobic running with the volume creeping back. Still no "
        "hard sessions — the fitness from your build is not going anywhere.",
        [
            "Keep every run conversational",
            "A niggle that lingers now is worth resting, not running through",
        ],
    )


def build_recovery_block(
    *,
    race_km: float,
    race_name: str,
    peak_km: float,
    runs_per_week: int,
    pace_zones: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Build the recovery block as ``plan_data`` weeks.

    Args:
        race_km: Distance of the race the finished plan built to.
        race_name: How to name that race in coaching copy ("marathon").
        peak_km: The finished plan's peak weekly volume.
        runs_per_week: How often the runner was running; the block never
            schedules more, and its first week one fewer.
        pace_zones: The runner's Daniels zones, for step paces. Optional — the
            block is all easy running and reads fine without targets.
    """
    if peak_km <= 0:
        return []
    prescription = recovery_prescription(race_km)
    wanted = max(2, min(runs_per_week or 3, max(_WEEK_DAYS)))

    weeks: List[Dict[str, Any]] = []
    for index, fraction in enumerate(prescription.volume_fractions):
        volume = round(peak_km * fraction, 1)
        first = index == 0
        runs = _runs_for(
            volume, min(wanted - 1, max(_FIRST_WEEK_DAYS)) if first else wanted
        )
        days = (_FIRST_WEEK_DAYS if first else _WEEK_DAYS)[runs]
        with_long = index >= prescription.long_run_from_week
        distances, long_index = _split_week(volume, runs, with_long)
        stride_runs = (
            0
            if index < prescription.strides_from_week
            else 2
            if index == prescription.weeks - 1
            else 1
        )
        rationale, tips = _week_copy(index, prescription.weeks, race_name)

        by_day: Dict[int, Dict[str, Any]] = {}
        easy_seen = 0
        for run_index, (day, km) in enumerate(zip(days, distances)):
            if run_index == long_index:
                by_day[day] = _long_day(day, km, pace_zones)
                continue
            easy_seen += 1
            # Strides go on the week's second and third easy runs: never the
            # first run back after a rest day.
            strides = 6 if 2 <= easy_seen <= 1 + stride_runs else 0
            by_day[day] = _easy_day(day, km, pace_zones, first, strides)

        daily = [by_day.get(day) or _rest_day(day, first) for day in range(1, 8)]
        for workout in daily:
            if workout["type"] != "rest":
                workout["coaching_rationale"] = rationale
        weeks.append(
            {
                "week": index + 1,
                "phase": "recovery",
                "is_recovery": True,
                "is_race_week": False,
                "total_km": round(sum(d["distance"] for d in daily), 1),
                "weekly_target_km": volume,
                "training_km": 0.0,
                "training_tips": tips,
                "daily_workouts": daily,
            }
        )
    return weeks


def _easy_day(
    day: int,
    km: float,
    pace_zones: Optional[Dict[str, Any]],
    very_easy: bool,
    strides: int,
) -> Dict[str, Any]:
    if very_easy:
        description = f"Recovery run, {km:g} km. Truly easy — walk breaks are fine."
    elif strides:
        description = f"Easy run, {km:g} km, finishing with {strides} × 100 m strides."
    else:
        description = f"Easy run, {km:g} km at conversational pace."
    return {
        "day": day,
        "type": "easy",
        "distance": km,
        "intensity": "low",
        "description": description,
        "slot_label": "Recovery" if very_easy else "Easy",
        "steps": build_recovery_block_steps(
            km, pace_zones, very_easy=very_easy, strides=strides
        ),
    }


def _long_day(
    day: int, km: float, pace_zones: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    return {
        "day": day,
        "type": "long",
        "distance": km,
        "intensity": "low",
        "description": f"Easy long run, {km:g} km. Time on feet, not pace.",
        "slot_label": "Long Run",
        "steps": build_recovery_block_steps(km, pace_zones),
    }


def _rest_day(day: int, first_week: bool) -> Dict[str, Any]:
    return {
        "day": day,
        "type": "rest",
        "distance": 0,
        "intensity": "rest",
        "description": (
            "Rest. A walk or easy spin if your legs want to move."
            if first_week
            else "Rest day — mobility or a walk if you like."
        ),
    }
