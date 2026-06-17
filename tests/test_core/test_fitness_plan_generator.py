"""Tests for FitnessPlanGenerator."""

import pytest

from app.contexts.plan.generators.fitness_plan_generator import FitnessPlanGenerator


class TestFitnessPlanGenerator:
    """Tests for FitnessPlanGenerator class."""

    @pytest.fixture
    def generator(self):
        return FitnessPlanGenerator()

    def test_generate_vo2max_plan(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
        )

        assert len(plan["weekly_plans"]) == 8
        assert plan["focus_area"] == "vo2max"
        assert "training_zones" in plan
        assert "phases" in plan
        assert "summary" in plan

    def test_generate_threshold_plan(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=30.0,
            weeks=10,
            runs_per_week=5,
            focus_area="threshold",
        )

        assert len(plan["weekly_plans"]) == 10
        assert plan["focus_area"] == "threshold"

    def test_generate_balanced_plan(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=20.0,
            weeks=6,
            runs_per_week=3,
            focus_area="balanced",
        )

        assert len(plan["weekly_plans"]) == 6
        assert plan["focus_area"] == "balanced"

    def test_time_trials_every_3_weeks(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=9,
            runs_per_week=4,
            focus_area="vo2max",
        )

        tt_weeks = [
            w["week"] for w in plan["weekly_plans"] if w.get("is_time_trial_week")
        ]
        assert 3 in tt_weeks
        assert 6 in tt_weeks
        assert 9 in tt_weeks

    def test_time_trial_week_has_time_trial_workout(
        self, generator: FitnessPlanGenerator
    ):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=6,
            runs_per_week=4,
            focus_area="vo2max",
        )

        for week in plan["weekly_plans"]:
            if week.get("is_time_trial_week"):
                tt_workouts = [
                    dw for dw in week["daily_workouts"] if dw["type"] == "time_trial"
                ]
                assert len(tt_workouts) >= 1
                assert tt_workouts[0].get("is_benchmark") is True

    def test_vo2max_focus_has_vo2max_workouts(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
        )

        vo2max_count = 0
        for week in plan["weekly_plans"]:
            for dw in week["daily_workouts"]:
                if dw["type"] in ("vo2max", "vo2max_ladder"):
                    vo2max_count += 1

        assert vo2max_count > 0

    def test_threshold_focus_has_threshold_workouts(
        self, generator: FitnessPlanGenerator
    ):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="threshold",
        )

        threshold_count = 0
        for week in plan["weekly_plans"]:
            for dw in week["daily_workouts"]:
                if dw["type"] in ("tempo", "cruise_interval"):
                    threshold_count += 1

        assert threshold_count > 0

    def test_mileage_progression(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=20.0,
            weeks=8,
            runs_per_week=4,
            focus_area="balanced",
        )

        weekly_km = [w["total_km"] for w in plan["weekly_plans"]]
        first_week = weekly_km[0]
        peak_week = max(weekly_km[:-2])

        assert peak_week > first_week
        assert peak_week <= 60.0

    def test_long_run_max_25_percent(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=30.0,
            weeks=6,
            runs_per_week=4,
            focus_area="vo2max",
        )

        for week in plan["weekly_plans"]:
            # Deload weeks intentionally cut midweek volume while keeping the
            # long run (standard down-week structure), so the long run is a
            # larger share of the reduced week. The 30% structural cap applies
            # to normal loading weeks.
            if week.get("is_recovery"):
                continue
            long_runs = [dw for dw in week["daily_workouts"] if dw["type"] == "long"]
            if long_runs:
                long_km = long_runs[0]["distance"]
                total_km = week["total_km"]
                assert long_km <= total_km * 0.30

    def test_recovery_weeks_exist(self, generator: FitnessPlanGenerator):
        # vo2max focus with 12 weeks → taper=1, peak=4 which triggers the
        # peak-phase recovery rule (3rd week of a 4+ week peak is recovery)
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=12,
            runs_per_week=4,
            focus_area="vo2max",
        )

        recovery_weeks = [w for w in plan["weekly_plans"] if w["is_recovery"]]
        assert len(recovery_weeks) > 0

        for rw in recovery_weeks:
            recovery_km = rw["total_km"]
            prev_weeks = [
                w
                for w in plan["weekly_plans"]
                if w["week"] < rw["week"] and not w["is_recovery"]
            ]
            if prev_weeks:
                prev_km = prev_weeks[-1]["total_km"]
                assert recovery_km < prev_km

    def test_zones_calculated_with_vdot(self, generator: FitnessPlanGenerator):
        zones = generator.calculate_training_zones(vdot=50.0)

        assert "zone_1_recovery" in zones
        assert "zone_4_vo2max" in zones
        assert "zone_5_race" in zones
        assert zones["zone_4_vo2max"]["pace"] < zones["zone_3_tempo"]["pace"]

    def test_zones_calculated_with_hr(self, generator: FitnessPlanGenerator):
        zones = generator.calculate_training_zones(vdot=50.0, max_hr=185)

        for zone_data in zones.values():
            assert "hr_bpm_range" in zone_data

    def test_summary_contains_time_trial_weeks(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=9,
            runs_per_week=4,
            focus_area="vo2max",
        )

        assert "time_trial_weeks" in plan["summary"]
        assert 3 in plan["summary"]["time_trial_weeks"]
        assert 6 in plan["summary"]["time_trial_weeks"]
        assert 9 in plan["summary"]["time_trial_weeks"]

    def test_week_has_seven_days(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=6,
            runs_per_week=4,
            focus_area="balanced",
        )

        for week in plan["weekly_plans"]:
            assert len(week["daily_workouts"]) == 7

    def test_rest_days_have_zero_distance(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=6,
            runs_per_week=4,
            focus_area="balanced",
        )

        for week in plan["weekly_plans"]:
            for dw in week["daily_workouts"]:
                if dw["type"] == "rest":
                    assert dw["distance"] == 0

    def test_vo2max_focus_reduces_taper(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
        )

        phases = plan["phases"]
        assert phases["taper"]["weeks"] <= 1

    def test_balanced_focus_keeps_taper(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="balanced",
        )

        phases = plan["phases"]
        assert phases["taper"]["weeks"] >= 1

    def test_focus_distance_stored(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
            focus_distance=10.0,
        )

        assert plan["focus_distance"] == 10.0

    def test_frequency_drives_peak_volume(self, generator: FitnessPlanGenerator):
        """Higher training frequency must target more weekly volume.

        Regression: the fitness peak ignored ``runs_per_week`` entirely, so a
        3x and a 6x plan landed on identical weekly km — the frequency knob
        only re-sliced a fixed volume into more (smaller) runs. Below the
        FITNESS_PEAK_CAP_KM ceiling, peak volume should rise with frequency.
        """
        peaks = {
            freq: generator.generate_plan(
                current_weekly_km=30.0,
                weeks=12,
                runs_per_week=freq,
                focus_area="balanced",
            )["summary"]["peak_weekly_km"]
            for freq in (3, 4, 5, 6)
        }

        assert peaks[3] < peaks[4] < peaks[5] < peaks[6], peaks
        # The reference frequency (4) keeps the original 1.3x target.
        assert peaks[4] == pytest.approx(30.0 * 1.3, abs=0.5)

    def test_frequency_never_detrains_below_base(self, generator: FitnessPlanGenerator):
        """Even the lowest frequency holds at least the runner's current base."""
        plan = generator.generate_plan(
            current_weekly_km=30.0,
            weeks=12,
            runs_per_week=3,
            focus_area="balanced",
        )
        assert plan["summary"]["peak_weekly_km"] >= 30.0

    @pytest.mark.parametrize("focus", ["vo2max", "threshold", "balanced"])
    @pytest.mark.parametrize("base", [20.0, 35.0, 50.0])
    def test_taper_descends_below_peak(self, generator, focus, base):
        """Regression: the MIN_NON_RECOVERY_BUMP floor was applied to taper weeks,
        lifting the final week back above the peak (the taper was inverted — the
        last week was the plan's biggest). The taper must descend."""
        plan = generator.generate_plan(
            current_weekly_km=base,
            weeks=10,
            runs_per_week=4,
            vdot=45,
            focus_area=focus,
            focus_distance=10.0,
        )
        totals = [w["total_km"] for w in plan["weekly_plans"]]
        peak = max(totals)
        # Final (taper) week must be a genuine drawdown, not >= peak.
        assert totals[-1] < peak * 0.85, (
            f"{focus} base{base}: taper week {totals[-1]} not below peak {peak}"
        )

    @pytest.mark.parametrize("base", [35.0, 50.0])
    def test_long_run_tracks_volume_not_token(self, generator, base):
        """Regression: the long-run ceiling was focus*0.7 (≈8 km for a 10 km
        focus), collapsing the long run to ~13% of the week at higher volume.
        It should now scale to a real endurance share."""
        plan = generator.generate_plan(
            current_weekly_km=base,
            weeks=10,
            runs_per_week=4,
            vdot=45,
            focus_area="balanced",
            focus_distance=10.0,
        )
        peak_long = 0.0
        peak_week_total = 0.0
        for w in plan["weekly_plans"]:
            if w.get("is_recovery"):
                continue
            longs = [d["distance"] for d in w["daily_workouts"] if d["type"] == "long"]
            if longs and w["total_km"] > peak_week_total:
                peak_week_total = w["total_km"]
            peak_long = max(peak_long, max(longs, default=0.0))
        assert peak_long >= 10.0, f"long run {peak_long} too short for base {base}"

    def test_run_count_honoured_on_time_trial_weeks(self, generator):
        """Regression: easy runs only used days [1,3,5,7], so a day-3 time trial
        starved a 6-run week of a slot. With enough volume the frequency holds."""
        plan = generator.generate_plan(
            current_weekly_km=45.0,
            weeks=10,
            runs_per_week=6,
            vdot=45,
            focus_area="vo2max",
            focus_distance=10.0,
        )
        for w in plan["weekly_plans"]:
            if w.get("is_recovery"):
                continue
            run_count = sum(
                1
                for d in w["daily_workouts"]
                if d.get("type") not in ("rest", "recovery")
                and d.get("distance", 0) > 0
            )
            assert run_count == 6, f"week {w['week']} has {run_count} runs, expected 6"
