"""Race week: close the plan on the event itself.

A plan built backwards from a race used to stop one session short of it: the
last week ended on a taper long run and the runner was left to infer where the
race went. These passes install the race on its day and size what precedes it.

The race is never rescaled afterwards — its distance is set by the event (or,
for a backyard, by the runner's goal), not by a weekly budget — so both passes
run after every smoothing pass.
"""

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.plan_passes.cards import (
    MIN_VIABLE_QUALITY_KM,
    QUALITY_CARD_TYPES,
    RUNNING_CARD_TYPES,
    is_running_session,
    refresh_duration_hints,
    week_total_km,
)
from app.contexts.plan.generators.workout_scaler import scale_down, set_distance
from app.core.training.profiles.backyard_profile import BackyardProfile
from app.core.training.profiles.trail_profile import TrailProfile
from app.core.training.tuning import (
    RACE_WEEK_MIN_PRERACE_KM,
    RACE_WEEK_PRERACE_SHARE,
)
from app.core.training.workouts import workout_builders, workout_steps

# Race day sits on the last day of the final week. The week runs Mon..Sun
# (day 1..7), and the scheduler anchors the long run on day 6 — so the race
# lands on the Sunday that every plan was implicitly counting down to.
RACE_DAY_NUMBER = 7

# A backyard starts on a Saturday morning and runs into Sunday and beyond, so
# the event sits on day 6 rather than day 7 — the plan's last day belongs to
# the race, not to the day after it.
BACKYARD_RACE_DAY_NUMBER = 6

# Bounds on the day-before-race shakeout. Its job is to keep the legs open,
# not to add fitness — nothing gained the day before a race survives to the
# start line, and anything longer costs freshness. The floor keeps it a real
# run rather than a token one on low-volume plans.
RACE_WEEK_SHAKEOUT_MAX_KM = 4.0
RACE_WEEK_SHAKEOUT_MIN_KM = 2.0

# Race week keeps a shakeout plus at most one other session.  Selection now
# happens before sizing, so this freshness rule no longer causes the later
# trivial-session sweep to discard most of the pre-race budget by accident.
RACE_WEEK_MAX_PRERACE_RUNS = 2


def build_shakeout(
    day: int, distance_km: float, pace_zones: Optional[Dict]
) -> Dict[str, Any]:
    """The day-before-race shakeout: a few easy km with strides."""
    workout = workout_builders.generate_easy_run(
        day, distance_km, distance_km, pace_zones
    )
    workout["is_shakeout"] = True
    workout["description"] = (
        f"Shakeout — {distance_km:g} km very easy, finishing with 4 × 100 m "
        "strides. Just enough to keep the legs open and burn off nerves. "
        "Everything you feel today is taper legs, not lost fitness."
    )
    workout["steps"] = workout_steps.build_shakeout_steps(distance_km, pace_zones)
    workout["coaching_rationale"] = (
        "The day before is about staying loose, not proving anything. Strides "
        "remind your legs what fast feels like without costing you a thing."
    )
    return workout


def _prerace_budget(training_plan: List[Dict[str, Any]]) -> tuple[float, float]:
    """``(pre-race km, shakeout km)`` for the final week.

    Sized against the realized peak across every loading week — the same
    anchor the taper smoothing uses — so race week is measured against volume
    the runner actually ran.
    """
    final_week = training_plan[-1]
    realized_peak = max(
        (
            w.get("total_km", 0) or 0
            for w in training_plan[:-1]
            if not w.get("is_recovery")
        ),
        default=final_week.get("total_km", 0) or 0,
    )
    pre_race_target = max(
        RACE_WEEK_MIN_PRERACE_KM, round(realized_peak * RACE_WEEK_PRERACE_SHARE, 1)
    )
    shakeout_km = max(
        RACE_WEEK_SHAKEOUT_MIN_KM,
        min(RACE_WEEK_SHAKEOUT_MAX_KM, round(pre_race_target * 0.25, 1)),
    )
    return pre_race_target, shakeout_km


def _close_race_week(
    final_week: Dict[str, Any],
    workouts: List[Dict[str, Any]],
    pace_zones: Optional[Dict],
) -> None:
    """Write the finished race week back onto the plan."""
    refresh_duration_hints(workouts, pace_zones)
    final_week["daily_workouts"] = workouts
    final_week["total_km"] = week_total_km(workouts)
    final_week["is_race_week"] = True


def install_race_day(
    training_plan: List[Dict[str, Any]],
    target_distance: float,
    pace_zones: Optional[Dict],
    trail_profile: Optional[TrailProfile] = None,
    max_runs: int = RACE_WEEK_MAX_PRERACE_RUNS + 1,
) -> None:
    """Replace the final week's long run with the goal race (in place).

    Three things happen, in order:

    1. The final week's long run becomes a short shakeout. A near-race-distance
       long run one or two days before the race is not a taper, it is a second
       race — but going fully sedentary is not the answer either, so the day
       keeps a few easy kilometres with strides to hold the legs open. This
       also keeps race week at the runner's requested number of running days.
    2. Everything still standing before race day is scaled to
       ``RACE_WEEK_PRERACE_SHARE`` of the realized peak. The taper curve sized
       race week as though its long run were still the anchor; with the race
       installed the rest of the week is shakeout, and holding it at the taper
       total would send the runner to the start line with a normal training
       week in their legs.
    3. The race is installed on :data:`RACE_DAY_NUMBER`, displacing whatever
       easy run the scheduler had put there.
    """
    if not training_plan or target_distance <= 0:
        return
    final_week = training_plan[-1]
    workouts = final_week.get("daily_workouts") or []
    pre_race_target, shakeout_km = _prerace_budget(training_plan)

    # The race consumes one of the week's running slots rather than adding an
    # extra one, so race week keeps the runner's requested training frequency.
    # When the scheduler had already put a run on race day the race simply
    # takes it, and the freed long-run day becomes the day-before shakeout.
    # When race day was rest, the race is the extra run and the long-run day
    # rests instead — a marathon plan's race week reading easy / easy / tempo /
    # race, with the Saturday off.
    #
    # Displaced days are rewritten in place rather than dropped: every week in
    # a generated plan carries seven day entries, and removing one left race
    # week with a hole where Saturday should be.
    kept: List[Dict[str, Any]] = []
    for w in workouts:
        if w.get("type") == "long":
            kept.append(build_shakeout(w["day"], shakeout_km, pace_zones))
        elif w.get("day") == RACE_DAY_NUMBER:
            kept.append(workout_builders.generate_rest_day(w["day"]))
        elif w.get("type") in RUNNING_CARD_TYPES and (w.get("distance") or 0) <= 0:
            # A drained running card is rest, not a session. The
            # sub-threshold conversion below only sees positive distances,
            # so without this branch a 0.0 km "easy" card survives onto the
            # race-week calendar. (``duration_min`` here is a display hint
            # attached to *short* cards — a 0.0 km card gets a 1-minute one —
            # so it marks the junk, it cannot protect it.)
            kept.append(workout_builders.generate_rest_day(w["day"]))
        else:
            kept.append(w)

    # Choose the sessions that survive before sizing them.  The previous order
    # scaled every card and then discarded the thin results, silently throwing
    # away most of the pre-race budget.
    prerace_cap = max(
        1,
        min(
            RACE_WEEK_MAX_PRERACE_RUNS,
            max_runs - 1,
            max(1, int(pre_race_target // RACE_WEEK_SHAKEOUT_MIN_KM)),
        ),
    )
    running = [w for w in kept if is_running_session(w)]

    def _keep_priority(w: Dict[str, Any]) -> tuple[int, float]:
        if w.get("is_shakeout"):
            return (0, 0.0)
        if w.get("type") in QUALITY_CARD_TYPES:
            return (1, -(w.get("distance") or 0))
        return (2, -(w.get("distance") or 0))

    running.sort(key=_keep_priority)
    for w in running[prerace_cap:]:
        idx = kept.index(w)
        kept[idx] = workout_builders.generate_rest_day(w["day"])

    # Scale only the days *other than* the shakeout onto the remaining budget —
    # the shakeout is a fixed, deliberately tiny dose and must not absorb the
    # week's drawdown.
    others = [w for w in kept if not w.get("is_shakeout")]
    scale_down(
        others,
        max(0.0, pre_race_target - shakeout_km),
        pace_zones=pace_zones,
        protect_long=False,
    )

    # A selected taper sharpener must remain an executable quality session.
    # Earlier long-run-relative clamping can leave it at 1-2 km; race week has
    # a six-kilometre pre-race floor, so a 2.5 km sharpener plus the shakeout
    # fits without violating the taper budget.
    for w in kept:
        if (
            w.get("type") in QUALITY_CARD_TYPES
            and 0 < (w.get("distance") or 0) < MIN_VIABLE_QUALITY_KM
        ):
            set_distance(w, MIN_VIABLE_QUALITY_KM, pace_zones)

    # Convert sub-threshold easy runs to rest — scaling can crush them to a
    # fraction of a kilometre, which isn't worth lacing up for — and drained
    # (0.0 km) cards to rest unconditionally: a card with no distance is not
    # a session, and it was never counted as prerace running. But never
    # eliminate ALL pre-race running: low-volume short-distance plans may
    # have only one tiny run before the race, and rest-only → race is worse
    # than a short shakeout jog.
    prerace_running = sum(1 for w in kept if is_running_session(w))
    for i, w in enumerate(kept):
        dist = w.get("distance") or 0
        if w.get("type") != "easy" or w.get("is_shakeout"):
            continue
        drained = dist <= 0
        thin = 0 < dist < RACE_WEEK_SHAKEOUT_MIN_KM
        if thin and prerace_cap >= 2:
            # Selection already guaranteed room for this second session. Keep
            # it at the same coherent floor as the shakeout instead of deleting
            # it after sizing and collapsing a nominal 25%-of-peak race week to
            # one token jog.
            set_distance(w, RACE_WEEK_SHAKEOUT_MIN_KM, pace_zones)
            continue
        if drained or (thin and prerace_running > 1):
            kept[i] = workout_builders.generate_rest_day(w["day"])
            if thin:
                prerace_running -= 1

    # Guarantee the minimum contract after every conversion.  If the second
    # retained stimulus is deliberately short, grow the shakeout (still capped
    # at four kilometres) so race week contains at least a shakeout plus one
    # minimum coherent session's worth of running.
    desired_floor = min(
        pre_race_target,
        RACE_WEEK_SHAKEOUT_MIN_KM * (2 if prerace_cap >= 2 else 1),
    )
    current_prerace = sum(
        w.get("distance", 0) or 0
        for w in kept
        if w.get("type") not in ("rest", "recovery")
    )
    if current_prerace < desired_floor - 0.05:
        shakeout_index = next(
            (i for i, w in enumerate(kept) if w.get("is_shakeout")), None
        )
        if shakeout_index is not None:
            shakeout = kept[shakeout_index]
            grown = min(
                RACE_WEEK_SHAKEOUT_MAX_KM,
                (shakeout.get("distance") or 0) + desired_floor - current_prerace,
            )
            kept[shakeout_index] = build_shakeout(
                shakeout["day"], round(grown, 1), pace_zones
            )

    race = workout_builders.generate_race_day(
        RACE_DAY_NUMBER,
        target_distance,
        pace_zones,
        is_trail=trail_profile is not None,
    )
    race["coaching_rationale"] = (
        "Everything in this plan was built for today. Trust the taper — "
        "fresh legs always feel a little restless on the start line."
    )

    workouts = sorted(
        [w for w in kept if w.get("day") != RACE_DAY_NUMBER] + [race],
        key=lambda w: w.get("day", 0),
    )
    _close_race_week(final_week, workouts, pace_zones)


def install_backyard_race_day(
    training_plan: List[Dict[str, Any]],
    profile: BackyardProfile,
    pace_zones: Optional[Dict],
    max_runs: int = RACE_WEEK_MAX_PRERACE_RUNS + 1,
) -> None:
    """Close a backyard plan on the event itself (in place).

    Same intent as :func:`install_race_day` — a plan built backwards from a
    race should end on it — with the calendar shifted a day: the race takes
    Saturday, Sunday is left as rest because for most goals the runner
    is still out on the course, and the shakeout moves to Friday.
    """
    if not training_plan:
        return
    final_week = training_plan[-1]
    workouts = final_week.get("daily_workouts") or []
    pre_race_target, shakeout_km = _prerace_budget(training_plan)
    shakeout_day = BACKYARD_RACE_DAY_NUMBER - 1

    kept: List[Dict[str, Any]] = []
    for w in workouts:
        day = w.get("day")
        if day == BACKYARD_RACE_DAY_NUMBER:
            continue  # the race takes this day
        if day == shakeout_day:
            kept.append(build_shakeout(shakeout_day, shakeout_km, pace_zones))
        elif w.get("type") in RUNNING_CARD_TYPES and (w.get("distance") or 0) <= 0:
            # Same rule as the road race week: a drained card is rest.
            kept.append(workout_builders.generate_rest_day(day))
        elif day is not None and day > BACKYARD_RACE_DAY_NUMBER:
            # Still on the course, or sleeping it off. Either way, not training.
            kept.append(workout_builders.generate_rest_day(day))
        else:
            kept.append(w)

    others = [w for w in kept if not w.get("is_shakeout")]
    scale_down(
        others,
        max(0.0, pre_race_target - shakeout_km),
        pace_zones=pace_zones,
        protect_long=False,
    )

    # Scaling can crush a pre-race session to 0.0 km; render the drained card
    # as the rest day it effectively is (same rule as the road race week).
    def _drained_to_rest(card: dict[str, Any]) -> dict[str, Any]:
        # A drained card needs a concrete day to become a rest day; without
        # one, leave the card as-is rather than inventing a day.
        day = card.get("day")
        if (
            isinstance(day, int)
            and card.get("type") in RUNNING_CARD_TYPES
            and (card.get("distance") or 0) <= 0
        ):
            return workout_builders.generate_rest_day(day)
        return card

    kept = [_drained_to_rest(w) for w in kept]

    # Frequency budget: the race consumes one of the week's running slots, so
    # at most max_runs - 1 sessions may precede it — shakeout first, then the
    # hardest of what is left. Without this, a low-frequency backyard runner
    # got a race week with more running days than they asked for all block.
    prerace_cap = max(0, min(RACE_WEEK_MAX_PRERACE_RUNS, max_runs - 1))
    running = [w for w in kept if is_running_session(w)]
    if len(running) > prerace_cap:

        def _keep_priority(w: Dict[str, Any]) -> int:
            if w.get("is_shakeout"):
                return 0
            if w.get("type") in QUALITY_CARD_TYPES:
                return 1
            return 2

        running.sort(key=_keep_priority)
        for w in running[prerace_cap:]:
            idx = kept.index(w)
            kept[idx] = workout_builders.generate_rest_day(w["day"])

    race = workout_builders.generate_backyard_race_day(
        BACKYARD_RACE_DAY_NUMBER, profile, pace_zones
    )
    race["coaching_rationale"] = (
        "Every simulation in this plan was a rehearsal for the next few hours "
        "— and then for all the hours after those. Start slow enough that the "
        "first loop feels like a mistake."
    )

    workouts = sorted(kept + [race], key=lambda w: w.get("day", 0))
    _close_race_week(final_week, workouts, pace_zones)
