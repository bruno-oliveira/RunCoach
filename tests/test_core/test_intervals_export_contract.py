"""The outbound export contract, checked against plans the engine really builds.

``test_intervals_export`` pins the syntax with hand-written step dicts. That
proves the renderer works on the shapes someone thought to write down; it cannot
prove the engine only ever *emits* those shapes. A new step kind, a new zone or a
new key-workout that nobody mirrored into a fixture would sail straight through.

This file closes the loop the other way round: generate real plans across the
profiles the app serves, then assert every exported line satisfies the grammar
``build_intervals_workout`` documents. It sweeps the *effective* steps — the
day's own ``steps`` when it has them, ``_fallback_steps`` otherwise — so a day
that reaches the watch only through the fallback is measured too. That is how
the couch-to-5K defect at the bottom of this file was found.

It is the outbound half of "does what we send actually parse?". The inbound half
— whether the completed activity comes back with structured laps — needs a live
device and cannot be tested here.

The rules asserted, all from the module docstring:

* a step line is ``- <cue> <amount> [<pace> Pace]``;
* ``<amount>`` is ``km``/``mi`` for distance or ``s``/``m``/``m<s>`` for time —
  never bare metres, because ``m`` means MINUTES to Intervals;
* ``<pace>`` is an absolute ``m:ss/km`` (optionally a fast-slow range);
* a cue carries no digits, so Intervals can never read part of it as a duration;
* walks, rests and hill reps carry no pace target — they are run by feel, and a
  pace alarm on them only ever beeps.
"""

import re

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.profiles.backyard_profile import BackyardProfile
from app.core.training.profiles.trail_profile import TrailProfile
from app.core.training.workouts.workout_steps.intervals_export import (
    _fallback_steps,
    _step_line,
    build_intervals_workout,
    is_hill,
    is_walk,
    step_cue,
    zone_paces_of,
)

_AMOUNT = r"(?:\d+(?:\.\d+)?km|\d+(?:\.\d+)?mi|\d+m(?:\d+s)?|\d+s)"
_PACE = r"\d+:\d{2}/km(?:-\d+:\d{2}/km)?"
_REP_HEADER = re.compile(r"^Rep \d+x$")
# ``[^\d]+`` for the cue is the "no digits in a cue" rule, enforced structurally.
_STEP_LINE = re.compile(rf"^- [^\d]+ {_AMOUNT}(?: {_PACE} Pace)?$")

_NO_PACE_KINDS = ("walk", "rest")
_TRAIL_50 = TrailProfile(
    distance_km=50.0,
    elevation_gain_m=2500.0,
    bracket="ultra",
    elevation_class="hilly",
)
_TRAIL_100 = TrailProfile(
    distance_km=100.0,
    elevation_gain_m=4500.0,
    bracket="long_ultra",
    elevation_class="mountainous",
)
_BACKYARD = BackyardProfile(
    target_loops=12,
    loop_km=6.706,
    loop_elevation_gain_m=50.0,
    tier="day",
)


def _cases():
    """(label, kwargs) for every profile the generator serves."""
    return [
        ("road-5k-4run", dict(current_km=20, target_distance=5.0, weeks=10)),
        (
            "road-5k-3run",
            dict(current_km=15, target_distance=5.0, weeks=10, max_runs_per_week=3),
        ),
        ("road-10k", dict(current_km=25, target_distance=10.0, weeks=12)),
        ("road-half", dict(current_km=35, target_distance=21.1, weeks=14)),
        ("road-marathon", dict(current_km=45, target_distance=42.2, weeks=16)),
        (
            "road-marathon-6run",
            dict(current_km=60, target_distance=42.2, weeks=18, max_runs_per_week=6),
        ),
        ("road-from-zero", dict(current_km=0, target_distance=5.0, weeks=10)),
        ("road-vdot", dict(current_km=25, target_distance=10.0, weeks=12, vdot=52.0)),
        (
            "trail-50k",
            dict(
                current_km=45, target_distance=50.0, weeks=16, trail_profile=_TRAIL_50
            ),
        ),
        (
            "trail-100k-itw",
            dict(
                current_km=60,
                target_distance=100.0,
                weeks=20,
                trail_profile=_TRAIL_100,
                intensive_weekend_enabled=True,
            ),
        ),
        (
            "backyard-12loops",
            dict(
                current_km=50,
                target_distance=60.0,
                weeks=16,
                backyard_profile=_BACKYARD,
            ),
        ),
    ]


def _sessions():
    """``(label, day, effective_steps)`` for every day that reaches the watch."""
    generator = TrainingPlanGenerator()
    out = []
    for label, kwargs in _cases():
        plan = generator.generate_plan(**kwargs)
        for week in plan:
            for day in week["daily_workouts"]:
                try:
                    build_intervals_workout(day)
                except ValueError:
                    continue  # a rest day is legitimately not sendable
                steps = day.get("steps") or _fallback_steps(day)
                out.append((f"{label} wk{week['week']} d{day['day']}", day, steps))
    return out


@pytest.fixture(scope="module")
def sessions():
    return _sessions()


def test_the_sweep_actually_exercises_every_shape(sessions):
    """Guard against this file silently becoming vacuous.

    If a refactor stops emitting steps, or the case list stops covering the
    profiles, the grammar checks below would pass trivially.
    """
    kinds = {step.get("kind") for _, _, steps in sessions for step in steps}
    zones = {
        step.get("pace_zone")
        for _, _, steps in sessions
        for step in steps
        if step.get("pace_zone")
    }
    types = {day.get("type") for _, day, _ in sessions}

    assert len(sessions) > 200, f"only {len(sessions)} sessions swept"
    assert {"warmup", "cooldown", "run", "recovery"} <= kinds, kinds
    assert {"E", "I", "T"} <= zones, zones
    # The couch-to-5K path is only reachable through the fallback, so it
    # silently vanished from this sweep once already.
    assert "run_walk" in types, types


def test_every_exported_line_matches_the_documented_grammar(sessions):
    for label, day, _ in sessions:
        description = build_intervals_workout(day)["description"]
        assert description.strip(), f"{label}: empty description"

        for block in description.split("\n\n"):
            lines = block.split("\n")
            if _REP_HEADER.match(lines[0]):
                assert len(lines) > 1, f"{label}: rep header with no steps"
                lines = lines[1:]
            for line in lines:
                assert _STEP_LINE.match(line), f"{label}: {line!r}"


def test_distance_is_never_sent_as_bare_metres(sessions):
    """``m`` means minutes to Intervals, so a metres value would become a
    multi-hour step on the watch."""
    for label, _, steps in sessions:
        for step in steps:
            line = _step_line(step, zone_paces_of(steps))
            if line is None:
                continue
            amount = line.rsplit(" ", 1)[-1]
            if amount.endswith("m") and not amount.endswith("km"):
                # A minutes amount: something a human could actually run.
                assert float(amount[:-1]) <= 180, f"{label}: {line!r}"


def test_walks_rests_and_hills_carry_no_pace_alarm(sessions):
    """A pace target on a by-feel step is a target the watch only ever beeps at."""
    by_feel = 0
    walked = 0
    for label, _, steps in sessions:
        zone_paces = zone_paces_of(steps)
        for step in steps:
            if is_walk(step):
                walked += 1
            if not (
                is_hill(step) or is_walk(step) or step.get("kind") in _NO_PACE_KINDS
            ):
                continue
            line = _step_line(step, zone_paces)
            if line is None:
                continue
            by_feel += 1
            assert " Pace" not in line, f"{label}: {line!r}"

    assert by_feel > 0, "no by-feel steps in the sweep — check is vacuous"
    assert walked > 0, "no walk steps in the sweep — check is vacuous"


def test_cues_stay_digit_free(sessions):
    for label, _, steps in sessions:
        for step in steps:
            cue = step_cue(step)
            assert not any(ch.isdigit() for ch in cue), f"{label}: {cue!r}"


def test_rep_headers_are_the_only_special_lines(sessions):
    """Every line is either a ``Rep Nx`` counter or a step; nothing else leaks."""
    for label, day, _ in sessions:
        description = build_intervals_workout(day)["description"]
        for block in description.split("\n\n"):
            for line in block.split("\n"):
                assert line.startswith("- ") or _REP_HEADER.match(line), (
                    f"{label}: {line!r}"
                )


def test_moving_time_is_positive_for_every_session(sessions):
    for label, day, _ in sessions:
        assert build_intervals_workout(day)["moving_time"] > 0, label


def test_exported_names_are_bounded_and_non_empty(sessions):
    for label, day, _ in sessions:
        name = build_intervals_workout(day)["name"]
        assert name and len(name) <= 60, f"{label}: {name!r}"


# ---------------------------------------------------------------------------
# Couch-to-5K: the shape that only ever reached the watch through the fallback
# ---------------------------------------------------------------------------


def _run_walk_day(**overrides):
    day = {
        "day": 1,
        "type": "run_walk",
        "distance": 1.0,
        "intensity": "low",
        "duration_min": 20,
        "run_min": 1,
        "walk_min": 1.5,
        "repeats": 8,
    }
    day.update(overrides)
    return day


def test_run_walk_day_exports_the_intervals_not_a_single_easy_run():
    """Was ``- Easy 1km 8:00/km Pace``: a 1 km, 8-minute easy run standing in for
    a 20-minute run/walk session, with the walks missing entirely."""
    workout = build_intervals_workout(_run_walk_day())

    assert workout["description"] == "Rep 8x\n- Run 1m\n- Walk 1m30s"


def test_run_walk_moving_time_matches_the_day_itself():
    """The exported duration must agree with the session the plan describes, not
    with the placeholder ``distance`` it used to be priced from."""
    day = _run_walk_day()

    assert build_intervals_workout(day)["moving_time"] == day["duration_min"] * 60


def test_run_walk_carries_no_pace_alarm():
    """A one-minute beginner jog is run by feel; a pace target on it would only
    ever beep at the runner it is meant to encourage."""
    assert "Pace" not in build_intervals_workout(_run_walk_day())["description"]


def test_run_walk_day_with_no_walk_portion_has_no_walk_step():
    """A late-plan day that is pure running must not invent a walk."""
    day = _run_walk_day(run_min=20, walk_min=0, repeats=1, duration_min=20)

    assert build_intervals_workout(day)["description"] == "- Run 20m"


def test_non_run_walk_days_still_use_the_distance_fallback():
    """The legacy road path must be untouched by the new branch."""
    day = {"type": "easy", "distance": 8.0, "steps": None}

    assert build_intervals_workout(day)["description"] == "- Easy 8km 8:00/km Pace"
