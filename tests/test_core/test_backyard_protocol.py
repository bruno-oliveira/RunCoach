"""The two things that actually decide a backyard: the corral and the food.

A backyard protocol has no splits to hit and no finish line to pace toward,
so these tests are about the parts that replace them — a turnaround routine
that fits inside the runner's own rest budget, and a fuelling plan that steps
down as the gut does rather than assuming hour twenty feels like hour one.
"""

import pytest

from app.core.race.backyard_protocol import (
    build_backyard_protocol,
    corral_routine,
    hourly_fuelling_schedule,
)
from app.core.race.race_protocol_generator import generate_race_protocol
from app.core.training.backyard_profile import classify_backyard
from app.core.training.trail_profile import classify_trail


def _protocol(loops=24):
    return generate_race_protocol(
        160.9, None, backyard_profile=classify_backyard(loops)
    )


class TestCorralRoutine:
    def test_the_routine_fits_inside_the_runner_s_rest_budget(self):
        """A routine that overruns the hour is a routine that ends the race."""
        for loops in (8, 14, 24, 36):
            profile = classify_backyard(loops)
            timed = [
                s["when"] for s in corral_routine(profile) if s["when"].startswith("+")
            ]
            last = timed[-1].lstrip("+")
            minutes, seconds = (int(x) for x in last.split(":"))
            assert minutes + seconds / 60 < profile.turnaround_minutes

    def test_a_longer_budget_gives_a_more_spread_out_routine(self):
        def last_offset(loops):
            steps = corral_routine(classify_backyard(loops))
            m, s = (int(x) for x in steps[4]["when"].lstrip("+").split(":"))
            return m + s / 60

        assert last_offset(8) < last_offset(24) < last_offset(36)

    def test_drinking_comes_before_eating_and_both_before_kit(self):
        steps = [s["action"].lower() for s in corral_routine(classify_backyard(24))]
        drink = next(i for i, a in enumerate(steps) if "drink" in a)
        eat = next(i for i, a in enumerate(steps) if "eat" in a)
        restock = next(i for i, a in enumerate(steps) if "restock" in a)
        assert drink < eat < restock

    def test_the_routine_ends_on_the_whistles_not_on_a_stopwatch(self):
        """By three minutes to go the clock the runner obeys is the race's."""
        steps = corral_routine(classify_backyard(24))
        assert [s["when"] for s in steps[-3:]] == [
            "3 min whistle",
            "2 min whistle",
            "1 min whistle",
        ]
        assert "corral" in steps[-2]["action"].lower()

    def test_every_step_explains_itself(self):
        for step in corral_routine(classify_backyard(24)):
            assert step["why"].strip()
            assert step["action"].strip()


class TestHourlyFuelling:
    def test_intake_steps_down_as_the_race_goes_on(self):
        """Gut capacity falls; a flat plan is a plan that stops being eaten."""

        def first_number(text):
            return int("".join(c for c in text.split("–")[0] if c.isdigit()) or 0)

        rows = hourly_fuelling_schedule(classify_backyard(36))
        carbs = [
            first_number(r["carbs"])
            for r in rows
            if any(c.isdigit() for c in r["carbs"])
        ]
        assert carbs == sorted(carbs, reverse=True)

    def test_the_schedule_covers_every_loop_with_no_gaps(self):
        rows = hourly_fuelling_schedule(classify_backyard(24))
        assert rows[0]["loops"].startswith("Loops 1")
        # Bands are contiguous: each starts where the previous one ended.
        bounds = []
        for row in rows:
            digits = [
                int(x)
                for x in row["loops"].replace("–", " ").replace("+", " ").split()
                if x.isdigit()
            ]
            bounds.append(digits)
        for prev, nxt in zip(bounds, bounds[1:]):
            assert nxt[0] == prev[-1] + 1

    def test_the_final_band_is_open_ended(self):
        """A backyard has no scheduled last hour."""
        rows = hourly_fuelling_schedule(classify_backyard(24))
        assert rows[-1]["loops"].endswith("+")

    def test_a_short_goal_is_not_told_about_hour_thirty(self):
        rows = hourly_fuelling_schedule(classify_backyard(8))
        assert len(rows) <= 2
        assert "night" not in " ".join(r["focus"] for r in rows).lower()

    def test_a_multi_day_goal_gets_the_second_day_band(self):
        rows = hourly_fuelling_schedule(classify_backyard(36))
        assert "second day" in rows[-1]["focus"].lower()

    def test_every_band_prescribes_carbs_fluid_and_sodium(self):
        for row in hourly_fuelling_schedule(classify_backyard(36)):
            assert row["carbs"] and row["fluid"] and row["sodium"]
            assert row["fuel"].strip()


class TestProtocolAssembly:
    def test_a_backyard_protocol_is_flagged_and_named_in_loops(self):
        p = _protocol()
        assert p["is_backyard"] is True
        assert p["is_trail"] is False
        assert p["distance_name"] == "24-Loop Backyard Ultra"
        assert p["predicted_finish_time"] == "24 h"

    def test_it_carries_no_split_table(self):
        """Every loop is the same distance at the same pace."""
        assert _protocol()["pacing_splits"] == []

    def test_the_pacing_strategy_is_the_rest_budget(self):
        strategy = _protocol()["pacing_strategy"]
        assert "48 min" in strategy
        assert "12 min" in strategy

    def test_mental_checkpoints_count_loops_not_kilometres(self):
        for cp in _protocol()["mental_checkpoints"]:
            assert cp["distance"].startswith("Loop ")
            assert "km" not in cp["distance"]

    def test_checkpoints_never_run_past_the_goal(self):
        for loops in (6, 12, 24, 48):
            p = _protocol(loops)
            numbers = [int(cp["distance"].split()[1]) for cp in p["mental_checkpoints"]]
            assert max(numbers) == loops
            assert numbers == sorted(numbers)

    def test_darkness_only_earns_night_content_when_it_applies(self):
        day = _protocol(8)
        night = _protocol(24)
        assert not any("caffeine" in i["what"].lower() for i in day["nutrition_timing"])
        assert any("caffeine" in i["what"].lower() for i in night["nutrition_timing"])
        assert any("headlamp" in c.lower() for c in night["week_before_checklist"])
        assert not any("headlamp" in c.lower() for c in day["week_before_checklist"])

    def test_a_multi_day_goal_plans_for_sleep(self):
        p = _protocol(36)
        text = " ".join(p["week_before_checklist"]) + p["pacing_strategy"]
        assert "sleep" in text.lower()

    def test_the_universal_checklist_survives(self):
        assert any(
            "bib" in item.lower() for item in _protocol()["week_before_checklist"]
        )

    def test_the_morning_timeline_builds_the_camp_before_the_gun(self):
        activities = " ".join(
            i["activity"] for i in _protocol()["race_morning_timeline"]
        )
        assert "camp" in activities.lower()
        assert "corral" in activities.lower()


class TestOtherPlanKindsUnaffected:
    def test_a_trail_protocol_is_not_a_backyard(self):
        p = generate_race_protocol(
            50.0, 6.0, trail_profile=classify_trail(50.0, 2000.0)
        )
        assert p["is_backyard"] is False
        assert p["is_trail"] is True
        assert "corral_routine" not in p
        assert p["pacing_splits"]

    def test_a_road_protocol_is_not_a_backyard(self):
        p = generate_race_protocol(42.2, 5.0)
        assert p["is_backyard"] is False
        assert "hourly_fuelling" not in p

    @pytest.mark.parametrize("loops", [6, 12, 24, 36, 48])
    def test_every_goal_size_builds_a_complete_protocol(self, loops):
        p = build_backyard_protocol(classify_backyard(loops), ["base item"])
        for key in (
            "corral_routine",
            "hourly_fuelling",
            "pacing_strategy",
            "nutrition_timing",
            "mental_checkpoints",
            "race_morning_timeline",
            "week_before_checklist",
        ):
            assert p[key], f"{key} empty for {loops} loops"
