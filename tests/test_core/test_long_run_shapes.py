"""Long-run shapes stay flexible: any distance, steps that total it, mostly easy."""

import pytest

from app.contexts.plan.generators.workout_scaler import is_prescriptive, set_distance
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.workouts.long_run_shapes import (
    MAX_SHAPE_QUALITY_SHARE,
    MAX_SHAPE_THRESHOLD_SHARE,
    SHAPES,
    build_shaped_long_run,
    reshape_long_card,
    shape_zone_shares,
)
from app.core.training.workouts.workout_steps import compute_distance_from_steps_checked
from app.core.training.workouts.workout_steps.structure import group_steps

PACE_ZONES = VDOTCalculator().get_pace_zones(45)


@pytest.mark.parametrize("shape_id", sorted(SHAPES))
@pytest.mark.parametrize("distance", [8.0, 12.4, 18.0, 26.0, 32.0])
def test_a_shape_fits_any_distance_and_stays_an_aerobic_day(shape_id, distance):
    card = build_shaped_long_run(shape_id, 6, distance, PACE_ZONES)
    assert card is not None
    km, priced = compute_distance_from_steps_checked(card["steps"])
    assert priced
    assert km == pytest.approx(distance, abs=0.15)
    threshold, quality = shape_zone_shares(card["steps"])
    assert threshold <= MAX_SHAPE_THRESHOLD_SHARE + 1e-9
    assert quality <= MAX_SHAPE_QUALITY_SHARE + 1e-9
    assert card["long_shape_id"] == shape_id
    assert card["key_workout_name"] == SHAPES[shape_id].name


def test_a_shaped_long_run_is_not_a_prescription():
    card = build_shaped_long_run("negative_split_long", 6, 18.0, PACE_ZONES)
    assert card is not None
    assert not is_prescriptive(card)


def test_a_resize_relays_the_same_shape():
    card = build_shaped_long_run("fast_finish_long", 6, 16.0, PACE_ZONES)
    assert card is not None
    set_distance(card, 20.0, PACE_ZONES)
    assert card["long_shape_id"] == "fast_finish_long"
    assert card["distance"] == 20.0
    km, _ = compute_distance_from_steps_checked(card["steps"])
    assert km == pytest.approx(20.0, abs=0.15)
    assert card["description"].startswith("Fast-finish long run: 16.0 km easy")


def test_reshape_leaves_a_plain_card_alone():
    card = {"type": "long", "distance": 14.0, "steps": [], "description": "x"}
    assert reshape_long_card(card, 16.0, PACE_ZONES) is False
    assert card["distance"] == 14.0


def test_surges_run_as_one_repeated_block():
    card = build_shaped_long_run("surge_long", 6, 18.0, PACE_ZONES)
    assert card is not None
    blocks = group_steps(card["steps"])
    repeated = [b for b in blocks if b["repeat"] > 1]
    assert len(repeated) == 1
    assert [s["label"] for s in repeated[0]["steps"]] == [
        "Surge",
        "Easy between surges",
    ]
