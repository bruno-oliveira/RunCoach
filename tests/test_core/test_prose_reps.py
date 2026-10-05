"""A card's prose must cite the reps its steps deliver.

The prose is rendered from the card's distance and the steps are then trimmed
by ceilings the distance knows nothing about, so the two used to part ways:
"2 x 1.6km" above a single 1.6 km rep. These pin the steps as the authority at
every point they become final — the overlay, and the page render.
"""

import copy

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_data_enricher import _repair_key_workout_steps
from app.core.training.workouts.key_workout_data import WORKOUTS
from app.core.training.workouts.key_workout_library.builders import (
    build_key_workout_steps,
)
from app.core.training.workouts.key_workout_library.rewrites import (
    _rewrite_key_workout_description,
)
from app.core.training.workouts.workout_steps import (
    prose_contradicts_steps,
    recount_reps,
    sync_prose_to_steps,
)


def _step(kind: str, repeat: int = 1, **amount) -> dict:
    return {"kind": kind, "repeat": repeat, **amount}


def _session(*work: dict) -> list[dict]:
    return [
        _step("warmup", distance_m=1000),
        *work,
        _step("cooldown", distance_m=1000),
    ]


class TestRecountReps:
    def test_a_dropped_rep_is_dropped_from_the_sentence(self):
        steps = _session(
            _step("run", distance_m=1600), _step("recovery", distance_m=350)
        )
        assert (
            recount_reps("Run 2 x 1.6km at 5K goal pace.", steps)
            == "Run 1 x 1.6km at 5K goal pace."
        )

    def test_each_set_of_a_two_part_session_keeps_its_own_count(self):
        steps = _session(
            _step("run", distance_m=800),
            _step("recovery", distance_m=200),
            _step("run", repeat=2, distance_m=400),
            _step("recovery", repeat=2, distance_m=200),
        )
        text = "2 x 800m with 200 m jog, then 3 x 400m slightly quicker"
        assert recount_reps(text, steps) == (
            "1 x 800m with 200 m jog, then 2 x 400m slightly quicker"
        )

    def test_a_recovery_of_the_same_length_is_never_mistaken_for_the_set(self):
        steps = _session(
            _step("run", repeat=3, distance_m=200),
            _step("recovery", repeat=2, distance_m=200),
        )
        assert recount_reps("4 x 200m fast", steps) == "3 x 200m fast"

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("6 × 3 min hard", "4 × 3 min hard"),
            ("6 x 180s hard", "4 x 180s hard"),
            ("6 × 180-second efforts", "4 × 180-second efforts"),
        ],
    )
    def test_timed_reps_are_recounted_in_any_spelling(self, text, expected):
        steps = _session(_step("run", repeat=4, duration_s=180))
        assert recount_reps(text, steps) == expected

    def test_reps_written_out_one_by_one_are_counted_together(self):
        steps = _session(
            _step("run", distance_m=1600),
            _step("recovery", distance_m=400),
            _step("run", distance_m=1600),
        )
        assert recount_reps("2 x 1.6km cutting down", steps) == (
            "2 x 1.6km cutting down"
        )

    def test_a_citation_with_no_such_set_is_left_as_written(self):
        steps = _session(_step("run", repeat=2, distance_m=1100))
        assert recount_reps("2 x 1.6km", steps) == "2 x 1.6km"

    def test_an_authored_range_holding_the_delivered_reps_is_kept(self):
        steps = _session(_step("run", repeat=8, duration_s=60))
        text = "Run 8-10 x 60 seconds hard uphill"
        assert recount_reps(text, steps) == text

    def test_an_authored_range_the_trim_fell_out_of_becomes_the_count(self):
        steps = _session(_step("run", repeat=5, duration_s=60))
        assert recount_reps("Run 8-10 x 60 seconds hard uphill", steps) == (
            "Run 5 x 60 seconds hard uphill"
        )

    def test_a_distance_named_twice_reads_the_same_set(self):
        steps = _session(_step("run", repeat=3, distance_m=400))
        text = "5 x 400m. Keep all 5 x 400m even."
        assert recount_reps(text, steps) == "3 x 400m. Keep all 3 x 400m even."


class TestProseContradictsSteps:
    def test_a_miscount_is_a_contradiction(self):
        card = {
            "description": "Warm up 1.0km easy. Run 2 x 1.6km.",
            "steps": _session(_step("run", distance_m=1600)),
        }
        assert prose_contradicts_steps(card)
        sync_prose_to_steps(card)
        assert not prose_contradicts_steps(card)

    def test_a_warmup_the_steps_do_not_run_is_a_contradiction(self):
        card = {
            "description": "Warm up 2.0km easy. Run 3km continuous.",
            "steps": _session(_step("run", distance_m=3000)),
        }
        assert prose_contradicts_steps(card)

    def test_prose_citing_nothing_checkable_contradicts_nothing(self):
        card = {
            "description": "Run by feel, finishing strong.",
            "steps": _session(_step("run", distance_m=3000)),
        }
        assert not prose_contradicts_steps(card)

    def test_a_card_with_no_steps_has_nothing_to_contradict(self):
        assert not prose_contradicts_steps({"description": "Run 2 x 1.6km."})


@pytest.mark.parametrize("workout", WORKOUTS, ids=lambda w: w["id"])
@pytest.mark.parametrize("distance", [6.0, 8.0, 12.0])
def test_prose_that_already_agrees_with_its_steps_is_never_reworded(workout, distance):
    card = {
        "description": _rewrite_key_workout_description(
            workout["description"], workout["id"], distance
        ),
        "steps": build_key_workout_steps(
            workout, workout["structure"], distance, workout["type"], None
        ),
    }
    if prose_contradicts_steps(card):
        pytest.skip("authored count differs from the builder's — recounting applies")
    authored = card["description"]
    sync_prose_to_steps(card)
    assert card["description"] == authored


@pytest.fixture(scope="module")
def low_mileage_cards() -> list[dict]:
    """Key sessions of a 15 km/week 5K block — every one meets a ceiling."""
    plan = TrainingPlanGenerator().generate_plan(15, 5.0, 8, 5)
    return [
        w
        for week in plan
        for w in week["daily_workouts"]
        if w.get("key_workout_id") and w.get("steps")
    ]


def _work_reps(card: dict) -> list[tuple[int, int]]:
    return [(s["repeat"], s["distance_m"]) for s in card["steps"] if s["kind"] == "run"]


class TestTrimmedCards:
    def test_the_goal_pace_session_cites_the_single_rep_it_was_trimmed_to(
        self, low_mileage_cards
    ):
        single_rep = [
            card
            for card in low_mileage_cards
            if card["key_workout_id"] == "5k_race_pace_3km"
            and _work_reps(card) == [(1, 1600)]
        ]
        assert single_rep, "expected the ceiling to leave one 1.6 km rep"
        for card in single_rep:
            assert "1 x 1.6km" in card["description"]
            assert card["structure"].startswith("1 x 1.6km")

    def test_no_generated_card_contradicts_its_steps(self, low_mileage_cards):
        assert [c["key_workout_id"] for c in low_mileage_cards]
        assert not [
            (c["key_workout_id"], c["description"])
            for c in low_mileage_cards
            if prose_contradicts_steps(c)
        ]

    def test_the_page_render_keeps_the_prose_on_the_steps(self, low_mileage_cards):
        """The render used to re-derive the text from the trimmed distance."""
        for card in low_mileage_cards:
            rendered = copy.deepcopy(card)
            _repair_key_workout_steps(rendered)
            assert rendered["description"] == card["description"]
            assert rendered["steps"] == card["steps"]


class TestPlansStoredBeforeTheFix:
    def _stored_card(self) -> dict:
        return {
            "type": "tempo",
            "key_workout_id": "5k_race_pace_3km",
            "distance": 4.0,
            "description": (
                "Warm up 1.0km easy. Run 2 x 1.6km at 5K goal pace with an "
                "easy jog recovery between reps. Cool down 1.0km easy."
            ),
            "structure": "2 x 1.6km at 5K goal pace.",
            "steps": _session(
                _step("run", distance_m=1600), _step("recovery", distance_m=350)
            ),
        }

    def test_a_stale_count_is_corrected_without_resizing_the_session(self):
        card = self._stored_card()
        _repair_key_workout_steps(card)
        assert card["description"].startswith("Warm up 1.0km easy. Run 1 x 1.6km")
        assert card["structure"] == "1 x 1.6km at 5K goal pace."

    def test_text_that_still_contradicts_the_steps_is_re_rendered(self):
        card = self._stored_card()
        card["description"] = "Warm up 3.0km easy. Run 2 x 1.6km. Cool down 3.0km."
        _repair_key_workout_steps(card)
        assert not card["description"].startswith("Warm up 3.0km")
