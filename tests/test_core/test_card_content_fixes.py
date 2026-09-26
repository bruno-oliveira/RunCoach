"""Two card-content bugs seen on real plans.

- Older generators stamped a "short strides" rationale on every base-phase
  interval slot, so a Relaxed Fartlek or a 3 x 800 m explained itself as
  strides. Stored plans are healed at view time; new plans no longer write it.
- Rest and 0 km recovery days offered "Open full session", leading to a day
  page with nothing to run.
"""

import pytest

from app.core.coaching.coaching_notes_generator import (
    generate_coaching_note,
    heal_legacy_rationale,
)
from app.template_helpers import create_templates

LEGACY = (
    "Short strides to reinforce running form and leg turnover. Even in base "
    "building, brief accelerations teach your body efficient mechanics."
)


class TestLegacyStridesRationale:
    @pytest.mark.parametrize(
        "session",
        [
            "Relaxed Fartlek Within an easy run, play with 6 x (1 min / 2 min)",
            " 6km VO2max: 2km warmup, 3x800m at 5:13/km",
        ],
    )
    def test_non_strides_session_is_healed(self, session):
        healed = heal_legacy_rationale(LEGACY, session)
        assert healed != LEGACY
        assert "stride" not in healed.lower()

    def test_a_real_strides_session_keeps_its_note(self):
        session = "Easy Run + Strides Run easy, then 6 x 100 m strides"
        assert heal_legacy_rationale(LEGACY, session) == LEGACY

    @pytest.mark.parametrize("rationale", [None, "", "Build your aerobic base."])
    def test_other_rationales_are_untouched(self, rationale):
        assert heal_legacy_rationale(rationale, "Relaxed Fartlek") == rationale

    def test_new_base_interval_note_does_not_promise_strides(self):
        note = generate_coaching_note("interval", "base", 3, 10.0)
        assert note and "stride" not in note.lower()


def _render_card(workout):
    template = create_templates().env.get_template("components/workout_item.html")
    return template.render(
        workout=workout,
        week={"week": 2},
        logged_run=None,
        is_past=False,
        day_names=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        workout_date_labels=None,
        current_week_number=None,
        current_day_of_week=None,
        plan_id="plan-1",
        user=None,
        feedback_map={},
    )


class TestOpenFullSessionLink:
    @pytest.mark.parametrize(
        "workout",
        [
            {"id": "w1", "day": 5, "type": "rest", "distance": 0},
            {"id": "w2", "day": 2, "type": "recovery", "distance": 0},
        ],
    )
    def test_rest_and_recovery_days_have_no_day_link(self, workout):
        workout["description"] = "Rest and recover."
        assert "workout-open-day" not in _render_card(workout)

    def test_a_run_links_to_its_day_page(self):
        workout = {"id": "w3", "day": 1, "type": "easy", "distance": 6.0}
        workout["description"] = "Easy run."
        assert 'href="/plan/plan-1/day/w3"' in _render_card(workout)
