"""Custom plans: the runner's choices fill the week, the engine still sizes it.

Pins the contract in ``app.core.training.custom_plan`` and the generator path
that honours it: every build/peak quality day and shaped long run is the
runner's choice, the weekly volume is the engine's (within a few km of the
automatic plan for the same inputs), and the plan passes the same structural
checks as any generated plan.
"""

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.generators.plan_structure_guard import check_plan_structure
from app.core.training.custom_plan import (
    CustomPlanSpec,
    CustomRotation,
    SlotKind,
    StrengthChoice,
    default_spec,
    eligible_options,
    rewrite_distribution,
    slot_grid,
    validate_spec,
)
from app.core.training.profiles.trail_profile import classify_trail
from app.core.training.workouts.key_workout_library import KeyWorkoutLibrary
from app.core.training.workouts.key_workout_library.selection import _CUSTOM_ONLY_IDS
from app.exceptions import InvalidCustomPlanException

# (label, current km, distance, weeks, trail (distance, gain) or None)
MATRIX = [
    ("5K", 25, 5.0, 10, None),
    ("10K", 30, 10.0, 12, None),
    ("Half", 35, 21.1, 14, None),
    ("Marathon", 45, 42.2, 18, None),
    ("Trail30", 35, 30.0, 14, (30.0, 1000.0)),
]


def _spec(runs, dist, trail_profile, template="climb_descent"):
    base = default_spec(runs, target_distance=dist, trail_profile=trail_profile)
    return CustomPlanSpec(menus=base.menus, strength=StrengthChoice(2, template))


def _plans(runs, km, dist, weeks, trail):
    tp = classify_trail(*trail) if trail else None
    spec = _spec(runs, dist, tp)
    auto = TrainingPlanGenerator().generate_plan(
        km, dist, weeks, runs, vdot=45, trail_profile=tp
    )
    custom = TrainingPlanGenerator().generate_plan(
        km, dist, weeks, runs, vdot=45, trail_profile=tp, custom_spec=spec
    )
    return spec, auto, custom


# --- the grid and the spec ---------------------------------------------------


def test_grid_follows_what_the_composers_schedule():
    # Base weeks carry no quality day at any frequency; 3-4 runs have one
    # quality day in build/peak, 5-6 have a speed day and a threshold day.
    for runs in (3, 4):
        grid = slot_grid(runs)
        assert grid["base"] == (SlotKind.LONG,)
        assert grid["build"] == (SlotKind.LONG, SlotKind.QUALITY)
    for runs in (5, 6):
        assert slot_grid(runs)["peak"] == (
            SlotKind.LONG,
            SlotKind.SPEED,
            SlotKind.THRESHOLD,
        )


def test_spec_round_trips_through_json():
    spec = _spec(5, 21.1, None)
    assert CustomPlanSpec.from_json(spec.to_json()) == spec


def test_default_spec_is_valid_for_every_goal_and_frequency():
    for _label, _km, dist, _weeks, trail in MATRIX:
        tp = classify_trail(*trail) if trail else None
        for runs in (3, 4, 5, 6):
            spec = default_spec(runs, target_distance=dist, trail_profile=tp)
            assert not validate_spec(
                spec, runs_per_week=runs, target_distance=dist, trail_profile=tp
            )


def _problem_keys(spec, runs=5, dist=21.1):
    return {
        p.key for p in validate_spec(spec, runs_per_week=runs, target_distance=dist)
    }


def test_validation_names_each_problem():
    good = _spec(5, 21.1, None)
    menus = {phase: dict(cells) for phase, cells in good.menus.items()}

    assert "too_few_runs" in _problem_keys(good, runs=2)

    empty = dict(menus, build={**menus["build"], SlotKind.SPEED: ()})
    assert "empty_cell" in _problem_keys(CustomPlanSpec(menus=empty))

    crowded = dict(
        menus, build={**menus["build"], SlotKind.SPEED: ("a", "b", "c", "d")}
    )
    assert "too_many_sessions" in _problem_keys(CustomPlanSpec(menus=crowded))

    unknown = dict(menus, build={**menus["build"], SlotKind.SPEED: ("no_such_id",)})
    assert "ineligible_session" in _problem_keys(CustomPlanSpec(menus=unknown))

    wrong_slot = dict(menus, base={**menus["base"], SlotKind.SPEED: ("ftm_800s",)})
    assert "unknown_slot" in _problem_keys(CustomPlanSpec(menus=wrong_slot))

    strength = CustomPlanSpec(menus=menus, strength=StrengthChoice(3, "auto"))
    assert "strength_sessions" in _problem_keys(strength)


def test_threshold_cell_never_offers_a_second_vo2_session():
    for phase in ("build", "peak"):
        for option in eligible_options(phase, SlotKind.THRESHOLD, target_distance=10.0):
            entry = KeyWorkoutLibrary.get_by_id(option.id)
            assert entry["pace_zone"] not in ("I", "R"), option.id


def test_race_pace_sessions_are_offered_only_for_their_own_race():
    marathon_ids = {
        o.id for o in eligible_options("build", SlotKind.QUALITY, target_distance=42.2)
    }
    five_k_ids = {
        o.id for o in eligible_options("build", SlotKind.QUALITY, target_distance=5.0)
    }
    assert "marathon_mp_blocks" in marathon_ids
    assert "marathon_mp_blocks" not in five_k_ids
    # ...while a universal session crosses distances.
    assert "10k_vo2max_1000s" in five_k_ids


def test_trail_sessions_are_offered_only_for_trail_goals():
    road = {
        o.id for o in eligible_options("build", SlotKind.QUALITY, target_distance=10.0)
    }
    assert not any(i.startswith("trail_") for i in road)
    trail = {
        o.id
        for o in eligible_options(
            "build",
            SlotKind.QUALITY,
            target_distance=30.0,
            trail_profile=classify_trail(30.0, 1000.0),
        )
    }
    assert any(i.startswith("trail_") for i in trail)


def test_flat_to_mountain_sessions_stay_out_of_the_automatic_rotation():
    assert _CUSTOM_ONLY_IDS
    for label, km, dist, weeks, trail in MATRIX:
        tp = classify_trail(*trail) if trail else None
        plan = TrainingPlanGenerator().generate_plan(
            km, dist, weeks, 5, vdot=45, trail_profile=tp
        )
        used = {d.get("key_workout_id") for w in plan for d in w["daily_workouts"]}
        assert not used & _CUSTOM_ONLY_IDS, label


def test_rotation_walks_each_menu_in_order():
    menus = {"build": {SlotKind.QUALITY: ("a", "b", "c")}}
    rotation = CustomRotation(CustomPlanSpec(menus=menus), runs_per_week=4)
    seen = []
    for _ in range(4):
        seen.append(rotation.ordered("build", SlotKind.QUALITY)[0])
        rotation.advance("build", SlotKind.QUALITY)
    assert seen == ["a", "b", "c", "a"]


def test_distribution_is_typed_by_the_picks_and_keeps_every_key():
    distribution = {"easy": 2, "long": 1, "interval": 0, "tempo": 1, "hill": 0}
    out = rewrite_distribution(distribution, [(SlotKind.QUALITY, ["ftm_800s"])])
    assert out["interval"] == 1 and out["tempo"] == 0 and out["hill"] == 0
    assert out["easy"] == 2 and out["long"] == 1


# --- the generated plan ------------------------------------------------------


@pytest.mark.parametrize("runs", [3, 4, 5, 6])
@pytest.mark.parametrize("case", MATRIX, ids=[c[0] for c in MATRIX])
def test_every_choice_is_honoured_and_the_volume_is_the_engines(case, runs):
    _label, km, dist, weeks, trail = case
    spec, auto, custom = _plans(runs, km, dist, weeks, trail)

    for week in custom:
        phase = week["phase"]
        chosen = {i for ids in spec.menus.get(phase, {}).values() for i in ids}
        for day in week["daily_workouts"]:
            if phase in ("build", "peak") and day["type"] in (
                "interval",
                "tempo",
                "hill",
            ):
                assert (
                    day.get("key_workout_id") in chosen
                    or day.get("custom_deferral_code") == "quality_budget"
                ), (week["week"], day)
            if (
                phase in ("base", "build", "peak")
                and day["type"] == "long"
                and not week["is_recovery"]
            ):
                assert day.get("long_shape_id") in chosen, (week["week"], day)
                assert not day.get("key_workout_id")

    for a, c in zip(auto, custom):
        # The budget is the engine's; only the per-type quality sizing moves.
        assert abs(a["total_km"] - c["total_km"]) <= max(6.0, 0.15 * a["total_km"])


@pytest.mark.parametrize("case", MATRIX, ids=[c[0] for c in MATRIX])
def test_custom_plans_pass_the_structure_guard(case):
    _label, km, dist, weeks, trail = case
    _spec_, auto, custom = _plans(4, km, dist, weeks, trail)
    auto_report = check_plan_structure(auto)
    custom_report = check_plan_structure(custom)
    assert custom_report["fatal"] == []
    # Shaped long runs and chosen sessions keep their steps in step with their
    # distance: no more step-distance warnings than the automatic plan has.
    assert len(custom_report["warnings"]) <= len(auto_report["warnings"])


def test_strength_follows_the_book_rules():
    _spec_, _auto, custom = _plans(5, 35, 21.1, 14, None)
    for week in custom:
        sessions = [d for d in week["daily_workouts"] if d.get("strength_session")]
        if week["phase"] == "taper":
            assert len(sessions) <= 1
            continue
        if len(sessions) == 2:
            assert sessions[0]["strength_session"]["focus"] == "climb"
            assert sessions[1]["strength_session"]["focus"] == "descent"
            assert sessions[1]["day"] - sessions[0]["day"] > 1
        if week["phase"] == "peak":
            long_days = {
                d["day"] for d in week["daily_workouts"] if d["type"] == "long"
            }
            for d in sessions:
                assert d["day"] + 1 not in long_days


def test_generator_refuses_what_a_custom_plan_cannot_be():
    spec = _spec(3, 5.0, None)
    with pytest.raises(InvalidCustomPlanException):
        TrainingPlanGenerator().generate_plan(0, 5.0, 8, 3, custom_spec=spec)


def test_a_stand_in_choice_does_not_stand_in_twice():
    # 1 km repeats need a 5.5 km day; early build days are smaller, so the
    # next choice stands in — and the rotation must then move past it.
    menus = {
        phase: {
            SlotKind.LONG: ("steady_long",),
            **(
                {
                    SlotKind.QUALITY: (
                        "5k_vo2max_400s",
                        "10k_vo2max_1000s",
                        "ftm_kenyan_fartlek",
                    )
                }
                if phase != "base"
                else {}
            ),
        }
        for phase in ("base", "build", "peak")
    }
    plan = TrainingPlanGenerator().generate_plan(
        30, 21.1, 14, 4, vdot=45, custom_spec=CustomPlanSpec(menus=menus)
    )
    build = [
        d["key_workout_id"]
        for w in plan
        if w["phase"] == "build" and not w["is_recovery"]
        for d in w["daily_workouts"]
        if d["type"] in ("interval", "tempo", "hill")
    ]
    assert all(a != b for a, b in zip(build, build[1:])), build
