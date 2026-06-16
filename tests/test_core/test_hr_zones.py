"""Tests for heart rate zone calculator."""

from types import SimpleNamespace

from app.contexts.runner.fitness.hr_zone_service import (
    detect_resting_hr_from_runs,
    detect_threshold_hr_from_runs,
    gather_pace_hr_samples,
    get_user_max_hr,
    get_user_resting_hr,
    get_user_threshold_hr,
)
from app.core.training.hr_zone_calculator import HRZoneCalculator


class _FakeDB:
    """Minimal query-chain stub returning a fixed ``all()`` payload."""

    def __init__(self, rows):
        self._rows = rows

    def query(self, *a):
        return self

    def filter(self, *a):
        return self

    def order_by(self, *a):
        return self

    def limit(self, *a):
        return self

    def all(self):
        return self._rows


class TestCalculateZones:
    def test_returns_five_zones(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert len(zones) == 5

    def test_zone_bpm_ranges_are_ascending(self):
        zones = HRZoneCalculator.calculate_zones(190)
        for i in range(len(zones) - 1):
            assert zones[i]["max_bpm"] <= zones[i + 1]["min_bpm"]

    def test_zone_1_starts_at_60_pct(self):
        # Running-specific banding: Z1 starts at 60% of max (Daniels' floor
        # for easy running), not the generic 50% all-sports band.
        zones = HRZoneCalculator.calculate_zones(200)
        assert zones[0]["min_bpm"] == 120  # 60% of 200

    def test_zone_5_max_is_max_hr(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert zones[4]["max_bpm"] == 200

    def test_typical_runner_zones(self):
        """A runner with max HR ~190 should get *runnable* easy zones.

        Daniels places E pace at 65-79% of max; Zone 2 must sit inside the
        range an adult can actually run at, not the 114-133 walking band the
        old 60-70% model prescribed.
        """
        zones = HRZoneCalculator.calculate_zones(190)
        z2 = next(z for z in zones if z["zone"] == 2)
        assert z2["min_bpm"] == 133  # 70% of 190
        assert z2["max_bpm"] == 152  # 80% of 190


class TestClassifyHR:
    def test_low_hr_returns_zone_1(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert HRZoneCalculator.classify_hr(80, zones) == 1

    def test_very_high_hr_returns_zone_5(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert HRZoneCalculator.classify_hr(195, zones) == 5

    def test_exact_boundary(self):
        zones = HRZoneCalculator.calculate_zones(200)
        z3_min = zones[2]["min_bpm"]  # Zone 3 min
        assert HRZoneCalculator.classify_hr(z3_min, zones) == 3

    def test_mid_zone_2(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert HRZoneCalculator.classify_hr(150, zones) == 2  # 75% of 200


class TestWorkoutZone:
    def test_easy_maps_to_zone_2(self):
        assert HRZoneCalculator.get_workout_zone("easy") == 2

    def test_recovery_maps_to_zone_1(self):
        assert HRZoneCalculator.get_workout_zone("recovery") == 1

    def test_interval_and_hill_map_to_zone_4(self):
        # Session targets are judged on *average* run HR: a correctly run
        # VO2max session averages ~88-93% of max once recoveries are
        # included. Zone 5 (95-100%) is a classification band no whole run
        # can average, so it is never a session target.
        assert HRZoneCalculator.get_workout_zone("interval") == 4
        assert HRZoneCalculator.get_workout_zone("hill") == 4

    def test_tempo_quality_maps_to_zone_3(self):
        # Threshold-flavoured sessions live in the 80-88% tempo band, the
        # same band the plan's pace-zone table labels "Tempo".
        assert HRZoneCalculator.get_workout_zone("tempo") == 3
        assert HRZoneCalculator.get_workout_zone("cruise_interval") == 3
        assert HRZoneCalculator.get_workout_zone("race_pace") == 3

    def test_no_session_targets_zone_5(self):
        from app.core.training.hr_zone_calculator import WORKOUT_ZONE_MAP

        assert all(z <= 4 for z in WORKOUT_ZONE_MAP.values())

    def test_workout_targets_match_pace_table_bands(self):
        # The personal HR zones and the pace-zone table must be the same
        # banding so "Zone 3" means one thing everywhere on the plan page.
        from app.core.training.hr_zone_calculator import (
            TRAINING_ZONE_HR_PERCENTAGES,
            ZONE_DEFINITIONS,
        )

        for defn, (slug, pcts) in zip(
            ZONE_DEFINITIONS, TRAINING_ZONE_HR_PERCENTAGES.items()
        ):
            assert (defn["pct_min"], defn["pct_max"]) == pcts

    def test_unknown_defaults_to_zone_2(self):
        assert HRZoneCalculator.get_workout_zone("unknown") == 2


class TestZoneLabel:
    def test_format(self):
        zones = HRZoneCalculator.calculate_zones(200)
        label = HRZoneCalculator.zone_label(2, zones)
        assert "Zone 2" in label
        assert "Aerobic" in label
        assert "bpm" in label


class TestMaxHREstimation:
    def test_age_based_formula(self):
        # Tanaka formula: 208 - 0.7 * age
        assert HRZoneCalculator.estimate_max_hr_age_based(30) == 187
        assert HRZoneCalculator.estimate_max_hr_age_based(50) == 173

    def test_get_user_max_hr_no_data(self):
        """When no data available, returns default."""

        class FakeDB:
            def query(self, *a):
                return self

            def filter(self, *a):
                return self

            def order_by(self, *a):
                return self

            def limit(self, *a):
                return self

            def all(self):
                return []

        hr, source = get_user_max_hr("user1", FakeDB())
        assert source == "default"
        assert hr == 190

    def test_get_user_max_hr_with_age(self):
        class FakeDB:
            def query(self, *a):
                return self

            def filter(self, *a):
                return self

            def order_by(self, *a):
                return self

            def limit(self, *a):
                return self

            def all(self):
                return []

        hr, source = get_user_max_hr("user1", FakeDB(), user_age=35)
        assert source == "estimated"
        assert hr == round(208 - 0.7 * 35)

    def test_spike_rejected_without_corroboration(self):
        """A lone 212 reading among 186s is a sensor glitch, not a max."""

        class FakeDB:
            def query(self, *a):
                return self

            def filter(self, *a):
                return self

            def order_by(self, *a):
                return self

            def limit(self, *a):
                return self

            def all(self):
                return [(212,), (186,), (184,), (181,)]

        hr, source = get_user_max_hr("user1", FakeDB())
        assert source == "detected"
        assert hr == 186

    def test_corroborated_max_accepted(self):
        class FakeDB:
            def query(self, *a):
                return self

            def filter(self, *a):
                return self

            def order_by(self, *a):
                return self

            def limit(self, *a):
                return self

            def all(self):
                return [(193,), (191,), (188,)]

        hr, source = get_user_max_hr("user1", FakeDB())
        assert hr == 193

    def test_single_reading_still_accepted(self):
        class FakeDB:
            def query(self, *a):
                return self

            def filter(self, *a):
                return self

            def order_by(self, *a):
                return self

            def limit(self, *a):
                return self

            def all(self):
                return [(188,)]

        hr, source = get_user_max_hr("user1", FakeDB())
        assert hr == 188


class TestHeartRateReserve:
    def test_none_resting_matches_pct_max(self):
        assert HRZoneCalculator.calculate_zones(
            190
        ) == HRZoneCalculator.calculate_zones(190, resting_hr=None)

    def test_hrr_math(self):
        # max 190, resting 50 -> reserve 140. Aerobic band 70-80% HRR:
        #   50 + 0.70*140 = 148 ; 50 + 0.80*140 = 162
        zones = HRZoneCalculator.calculate_zones(190, resting_hr=50)
        z2 = zones[1]
        assert z2["min_bpm"] == 148
        assert z2["max_bpm"] == 162

    def test_hrr_sits_above_pct_max_for_low_resting(self):
        pct_max = HRZoneCalculator.calculate_zones(190)
        hrr = HRZoneCalculator.calculate_zones(190, resting_hr=50)
        # Karvonen lifts the easy band above the naive %max band.
        assert hrr[1]["min_bpm"] > pct_max[1]["min_bpm"]

    def test_top_of_zone_5_is_max_hr(self):
        zones = HRZoneCalculator.calculate_zones(190, resting_hr=50)
        assert zones[4]["max_bpm"] == 190

    def test_zones_ascending_under_hrr(self):
        zones = HRZoneCalculator.calculate_zones(195, resting_hr=45)
        for i in range(len(zones) - 1):
            assert zones[i]["max_bpm"] <= zones[i + 1]["min_bpm"]

    def test_implausible_resting_falls_back_to_pct_max(self):
        # Resting >= max, or out of the reliable band, is ignored.
        assert HRZoneCalculator.calculate_zones(
            190, resting_hr=200
        ) == HRZoneCalculator.calculate_zones(190)
        assert HRZoneCalculator.calculate_zones(
            190, resting_hr=10
        ) == HRZoneCalculator.calculate_zones(190)


class TestRestingHRDetection:
    def test_none_without_enough_easy_runs(self):
        db = _FakeDB([(130,), (128,)])  # fewer than the required minimum
        assert detect_resting_hr_from_runs("u1", db) is None

    def test_estimate_from_easy_floor_minus_offset(self):
        # Lowest easy-run avg 120 -> 120 - 25 offset = 95 -> clamped to 95.
        db = _FakeDB([(120,), (125,), (130,), (132,), (135,)])
        assert detect_resting_hr_from_runs("u1", db) == 95

    def test_estimate_clamped_to_floor(self):
        db = _FakeDB([(50,), (52,), (55,), (58,), (60,)])
        # 50 - 25 = 25 -> clamped up to the 30 BPM reliability floor.
        assert detect_resting_hr_from_runs("u1", db) == 30

    def test_user_value_preferred_over_estimate(self):
        user = SimpleNamespace(id="u1", resting_hr=48)
        resting, source = get_user_resting_hr(user, _FakeDB([]))
        assert resting == 48
        assert source == "user"

    def test_falls_back_to_estimate(self):
        user = SimpleNamespace(id="u1", resting_hr=None)
        db = _FakeDB([(120,), (125,), (130,), (132,), (135,)])
        resting, source = get_user_resting_hr(user, db)
        assert source == "estimated"
        assert resting == 95

    def test_none_when_no_data(self):
        user = SimpleNamespace(id="u1", resting_hr=None)
        resting, source = get_user_resting_hr(user, _FakeDB([]))
        assert resting is None
        assert source == "none"


class TestLTHRAnchoring:
    def test_none_lthr_matches_no_lthr(self):
        assert HRZoneCalculator.calculate_zones(
            190
        ) == HRZoneCalculator.calculate_zones(190, lthr=None)

    def test_threshold_boundary_equals_measured_lthr(self):
        # The Z3/Z4 boundary should land exactly on the measured LTHR rather
        # than the formula's 88% of max (= 167 for max 190).
        zones = HRZoneCalculator.calculate_zones(190, lthr=172)
        assert zones[2]["max_bpm"] == 172  # top of Zone 3 (Tempo)
        assert zones[3]["min_bpm"] == 172  # bottom of Zone 4 (VO2max)

    def test_floor_and_ceiling_are_pinned(self):
        baseline = HRZoneCalculator.calculate_zones(190)
        anchored = HRZoneCalculator.calculate_zones(190, lthr=172)
        assert anchored[0]["min_bpm"] == baseline[0]["min_bpm"]  # Z1 floor
        assert anchored[4]["max_bpm"] == 190  # ceiling = max HR

    def test_anchored_zones_remain_ascending(self):
        zones = HRZoneCalculator.calculate_zones(195, resting_hr=50, lthr=170)
        for i in range(len(zones) - 1):
            assert zones[i]["max_bpm"] <= zones[i + 1]["min_bpm"]

    def test_lower_lthr_pulls_subthreshold_bands_down(self):
        baseline = HRZoneCalculator.calculate_zones(190)
        # 88% of 190 = 167; a measured LTHR of 160 is lower, so the aerobic
        # band top should drop relative to the formula model.
        anchored = HRZoneCalculator.calculate_zones(190, lthr=160)
        assert anchored[1]["max_bpm"] < baseline[1]["max_bpm"]

    def test_implausible_lthr_ignored(self):
        # Below 70% (= 133) or above 95% (= 180) of max is not a threshold.
        assert HRZoneCalculator.calculate_zones(
            190, lthr=120
        ) == HRZoneCalculator.calculate_zones(190)
        assert HRZoneCalculator.calculate_zones(
            190, lthr=188
        ) == HRZoneCalculator.calculate_zones(190)

    def test_anchoring_composes_with_karvonen(self):
        zones = HRZoneCalculator.calculate_zones(190, resting_hr=50, lthr=168)
        assert zones[2]["max_bpm"] == 168
        assert zones[4]["max_bpm"] == 190


class TestThresholdHRDetection:
    def _run(self, wtype, hr):
        return SimpleNamespace(effective_workout_type=wtype, avg_heart_rate=hr)

    def test_none_below_minimum_runs(self):
        db = _FakeDB([self._run("tempo", 165), self._run("tempo", 167)])
        assert detect_threshold_hr_from_runs("u1", db) is None

    def test_median_of_threshold_runs(self):
        db = _FakeDB(
            [
                self._run("tempo", 165),
                self._run("cruise_interval", 170),
                self._run("race_pace", 168),
            ]
        )
        assert detect_threshold_hr_from_runs("u1", db) == 168

    def test_ignores_non_threshold_efforts(self):
        db = _FakeDB(
            [
                self._run("easy", 130),
                self._run("long", 135),
                self._run("interval", 185),
                self._run("tempo", 166),  # only one threshold run -> below min
            ]
        )
        assert detect_threshold_hr_from_runs("u1", db) is None

    def test_user_override_preferred(self):
        user = SimpleNamespace(id="u1", threshold_hr=171)
        lthr, source = get_user_threshold_hr(user, _FakeDB([]))
        assert lthr == 171
        assert source == "user"

    def test_falls_back_to_estimate(self):
        user = SimpleNamespace(id="u1", threshold_hr=None)
        db = _FakeDB(
            [
                self._run("tempo", 165),
                self._run("tempo", 170),
                self._run("tempo", 168),
            ]
        )
        lthr, source = get_user_threshold_hr(user, db)
        assert source == "estimated"
        assert lthr == 168

    def test_none_when_no_data(self):
        user = SimpleNamespace(id="u1", threshold_hr=None)
        lthr, source = get_user_threshold_hr(user, _FakeDB([]))
        assert lthr is None
        assert source == "none"


class TestGatherPaceHRSamples:
    """Rows are (avg_pace_min_km, avg_heart_rate, splits)."""

    def test_prefers_splits_when_present(self):
        splits = [
            {"km": 1, "pace_min_km": 5.5, "avg_hr": 140},
            {"km": 2, "pace_min_km": 5.0, "avg_hr": 150},
            {"km": 3, "pace_min_km": 4.5, "avg_hr": 162},
        ]
        db = _FakeDB([(5.0, 150, splits)])
        samples = gather_pace_hr_samples("u1", db)
        # All three splits used; the run average is NOT added on top.
        assert len(samples) == 3
        assert {round(s.pace_min_km, 1) for s in samples} == {5.5, 5.0, 4.5}

    def test_falls_back_to_run_average_without_splits(self):
        db = _FakeDB([(5.2, 148, None)])
        samples = gather_pace_hr_samples("u1", db)
        assert len(samples) == 1
        assert samples[0].pace_min_km == 5.2
        assert samples[0].hr == 148

    def test_skips_runs_missing_pace_or_hr(self):
        db = _FakeDB([(None, 150, None), (5.0, None, None), (5.0, 150, None)])
        samples = gather_pace_hr_samples("u1", db)
        assert len(samples) == 1

    def test_ignores_incomplete_splits(self):
        splits = [
            {"km": 1, "pace_min_km": 5.0},  # no hr
            {"km": 2, "avg_hr": 150},  # no pace
            {"km": 3, "pace_min_km": 4.8, "avg_hr": 155},  # usable
        ]
        db = _FakeDB([(5.0, 150, splits)])
        samples = gather_pace_hr_samples("u1", db)
        assert len(samples) == 1
        assert samples[0].pace_min_km == 4.8
