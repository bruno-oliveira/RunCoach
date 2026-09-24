"""Step grouping and the display view built on it.

The watch export, the day card, the drill-down and the PDF all read the same
grouping, so these pin the shapes real builders emit.
"""

from app.core.training.workouts.workout_steps.presentation import session_view
from app.core.training.workouts.workout_steps.quality import (
    _build_interval_steps_high_base,
)
from app.core.training.workouts.workout_steps.structure import group_steps


def _step(kind, repeat=1, **kw):
    return {"kind": kind, "repeat": repeat, **kw}


def test_plain_steps_are_single_blocks():
    blocks = group_steps(
        [_step("warmup", distance_m=1000), _step("run", distance_m=5000)]
    )
    assert [b["repeat"] for b in blocks] == [1, 1]


def test_work_steps_sharing_a_count_alternate():
    over = _step("run", 6, duration_s=90, pace_zone="I")
    under = _step("run", 6, duration_s=150, pace_zone="T")
    (block,) = group_steps([over, under])
    assert block["repeat"] == 6
    assert block["steps"] == [over, under]
    assert not block["skip_last_recovery"]


def test_a_recovery_closes_the_unit():
    steps = [
        _step("run", 4, distance_m=400),
        _step("recovery", 4, distance_m=200),
        _step("run", 4, distance_m=200),
        _step("recovery", 4, distance_m=200),
    ]
    blocks = group_steps(steps)
    assert [len(b["steps"]) for b in blocks] == [2, 2]


def test_n_minus_one_recovery_sits_between_reps():
    steps = [_step("run", 5, distance_m=1000), _step("recovery", 4, duration_s=90)]
    (block,) = group_steps(steps)
    assert block["repeat"] == 5
    assert block["skip_last_recovery"]
    assert len(block["steps"]) == 2


def test_bare_strides_get_an_implied_jog_back():
    (block,) = group_steps([_step("strides", 6, distance_m=100)])
    assert block["steps"][-1]["implied"] is True
    assert block["skip_last_recovery"]


def test_pyramid_recovers_between_every_rung():
    steps = _build_interval_steps_high_base(1, None, 5, 5, 5)
    kinds = [s["kind"] for s in steps]
    assert kinds.count("recovery") == 4
    # No trailing recovery before the cool-down, and none without an amount.
    assert kinds[-2] == "run"
    assert all(s.get("distance_m") or s.get("duration_s") for s in steps)


def test_session_view_expands_profile_rep_by_rep():
    steps = [
        _step("warmup", distance_m=2000, pace_zone="E", pace_str="6:00/km"),
        _step(
            "run",
            5,
            distance_m=400,
            pace_zone="I",
            pace_str="4:00/km",
            label="5 × 400 m",
        ),
        _step("recovery", 4, duration_s=90, pace_zone="E", label="90 s jog"),
        _step("cooldown", distance_m=2000, pace_zone="E", pace_str="6:00/km"),
    ]
    view = session_view(steps)
    assert view is not None
    assert view["has_repeats"]
    # warm-up + 5 reps + 4 recoveries + cool-down
    assert len(view["profile"]) == 11
    assert abs(sum(seg["share"] for seg in view["profile"]) - 100) < 0.1
    rep = view["blocks"][1]["steps"][0]
    assert rep["amount"] == "400 m"
    assert rep["pace"] == "4:00 /km"
    assert rep["name"] == "Interval pace"  # "5 × 400 m" is only an amount
    # The zone-E recovery borrows the runner's easy pace, as the watch does.
    assert view["blocks"][1]["steps"][1]["pace"] == "6:00 /km"


def test_session_view_never_prints_a_default_pace_as_yours():
    view = session_view([_step("run", distance_m=5000, pace_zone="E")])
    assert view is not None
    assert view["blocks"][0]["steps"][0]["pace"] is None


def test_walks_and_hills_read_as_by_feel():
    view = session_view(
        [
            _step("run", 10, duration_s=30, pace_zone="R", effort="hard uphill"),
            _step("recovery", 10, duration_s=60, pace_zone="WALK", effort="walk"),
        ]
    )
    assert view is not None
    hill, walk = view["blocks"][0]["steps"]
    assert hill["by_feel"] and hill["pace"] is None
    assert walk["by_feel"] and walk["level"] == 1


def test_empty_steps_have_no_view():
    assert session_view([]) is None
    assert session_view(None) is None
