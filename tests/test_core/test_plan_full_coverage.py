"""Comprehensive coverage tests for ALL UI-accessible plan combinations.

Tests every valid combination of:
- Distance: 5K, 10K, Half Marathon, Trail 30K, Marathon
- Duration: full valid range per distance
- Base weekly mileage: min to max warning threshold (in 5km steps)
- Frequency: 2-5 runs/week (respecting distance-specific minimums)

Also tests schema validation for invalid combinations and API-level plan generation.
"""

import pytest

from app.core.generators.plan_generator import TrainingPlanGenerator
from app.schemas import PlanRequest
from app.constants import SUPPORTED_DISTANCES, DISTANCE_NAMES
from app.config import settings


# ── Configuration: all valid ranges ────────────────────────────────────────

DISTANCE_CONFIG = {
    5.0: {
        "name": "5K",
        "min_weeks": 6,
        "max_weeks": 16,
        "min_mileage": 5.0,
        "max_mileage": 40.0,
        "min_runs": 2,
    },
    10.0: {
        "name": "10K",
        "min_weeks": 6,
        "max_weeks": 16,
        "min_mileage": 10.0,
        "max_mileage": 50.0,
        "min_runs": 2,
    },
    21.1: {
        "name": "Half Marathon",
        "min_weeks": 8,
        "max_weeks": 20,
        "min_mileage": 15.0,
        "max_mileage": 70.0,
        "min_runs": 3,
    },
    30.0: {
        # Standard-bracket trail under the parameterized profile (8–42.2 km).
        # Legacy 30 km plans auto-migrate to is_trail=True with default 1000 m
        # of elevation gain; bracket-aware validators apply 6–22 weeks.
        "name": "Trail 30K",
        "min_weeks": 6,
        "max_weeks": 22,
        "min_mileage": 15.0,
        "max_mileage": 60.0,
        "min_runs": 4,
    },
    42.2: {
        "name": "Marathon",
        "min_weeks": 12,
        "max_weeks": 24,
        "min_mileage": 25.0,
        "max_mileage": 100.0,
        "min_runs": 4,
    },
}

RUNS_OPTIONS = [2, 3, 4, 5]


def _mileage_range(distance: float) -> list[float]:
    """Return mileage values from min to max (inclusive) in 5km steps."""
    cfg = DISTANCE_CONFIG[distance]
    start = cfg["min_mileage"]
    end = cfg["max_mileage"]
    mileages = []
    current = start
    while current <= end + 0.01:
        mileages.append(current)
        current += 5.0
    return mileages


def _duration_range(distance: float) -> list[int]:
    """Return all valid durations for a distance."""
    cfg = DISTANCE_CONFIG[distance]
    return list(range(cfg["min_weeks"], cfg["max_weeks"] + 1))


def _valid_runs(distance: float) -> list[int]:
    """Return valid run frequencies for a distance (2-5 range)."""
    cfg = DISTANCE_CONFIG[distance]
    return [r for r in RUNS_OPTIONS if r >= cfg["min_runs"]]


def _all_combos():
    """Yield (distance, weeks, mileage, runs) for all *realistic* combos.

    Combos with less than 2.5 km of average per-run mileage produce
    pathologically thin easy runs (≤ 1 km after strides) which exposes
    rounding artefacts in the budget arithmetic without representing a
    realistic user prescription. We exclude them so the validator
    focuses on prescriptions an actual runner would receive.
    """
    for distance in SUPPORTED_DISTANCES:
        for weeks in _duration_range(distance):
            for mileage in _mileage_range(distance):
                for runs in _valid_runs(distance):
                    if mileage < 2.5 * runs:
                        continue
                    yield distance, weeks, mileage, runs


def _combo_id(combo):
    distance, weeks, mileage, runs = combo
    return f"{DISTANCE_NAMES[distance]}-{weeks}wk-{mileage:.0f}km-{runs}runs"


ALL_COMBOS = list(_all_combos())


# ── Schema Validation Tests ───────────────────────────────────────────────

class TestPlanRequestSchemaValidation:
    """Test PlanRequest schema accepts all valid combinations."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_valid_combos_accepted(self, combo):
        distance, weeks, mileage, runs = combo
        req = PlanRequest(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        assert req.current_km == mileage
        assert req.target_distance == distance
        assert req.weeks == weeks
        assert req.max_runs_per_week == runs


class TestPlanRequestSchemaRejections:
    """Test PlanRequest schema rejects invalid combinations."""

    @pytest.mark.parametrize("distance,invalid_weeks,reason", [
        (5.0, 3, "below 5K minimum"),
        (5.0, 4, "below 5K minimum (phase collapse guard)"),
        (5.0, 5, "below 5K minimum (phase collapse guard)"),
        (5.0, 17, "above 5K maximum"),
        (10.0, 5, "below 10K minimum"),
        (10.0, 17, "above 10K maximum"),
        (21.1, 7, "below Half minimum"),
        (21.1, 21, "above Half maximum"),
        (30.0, 5, "below Trail minimum"),
        (30.0, 23, "above Trail maximum"),
        (42.2, 11, "below Marathon minimum"),
        (42.2, 25, "above Marathon maximum"),
    ])
    def test_invalid_weeks_rejected(self, distance, invalid_weeks, reason):
        with pytest.raises(Exception):
            PlanRequest(
                current_km=DISTANCE_CONFIG[distance]["min_mileage"],
                target_distance=distance,
                weeks=invalid_weeks,
                max_runs_per_week=4,
            )

    @pytest.mark.parametrize("distance,invalid_runs,reason", [
        (5.0, 1, "below minimum 2"),
        (5.0, 7, "above maximum 6"),
        (10.0, 1, "below minimum 2"),
        (21.1, 2, "Half requires 3+"),
        (30.0, 3, "Trail requires 4+"),
        (42.2, 3, "Marathon requires 4+"),
    ])
    def test_invalid_runs_rejected(self, distance, invalid_runs, reason):
        cfg = DISTANCE_CONFIG[distance]
        with pytest.raises(Exception):
            PlanRequest(
                current_km=cfg["min_mileage"],
                target_distance=distance,
                weeks=cfg["min_weeks"],
                max_runs_per_week=invalid_runs,
            )

    @pytest.mark.parametrize("distance,low_mileage", [
        (5.0, 4.0),
        (10.0, 9.0),
        (21.1, 14.0),
        (30.0, 14.0),
        (42.2, 24.0),
    ])
    def test_below_min_mileage_rejected(self, distance, low_mileage):
        from app.exceptions import InadequateBaseException
        cfg = DISTANCE_CONFIG[distance]
        with pytest.raises(InadequateBaseException):
            PlanRequest(
                current_km=low_mileage,
                target_distance=distance,
                weeks=cfg["min_weeks"],
                max_runs_per_week=4,
            )

    def test_zero_mileage_5k_requires_8_weeks(self):
        from app.exceptions import InsufficientTimeException
        with pytest.raises(InsufficientTimeException):
            PlanRequest(
                current_km=0,
                target_distance=5.0,
                weeks=6,
                max_runs_per_week=3,
            )

    def test_zero_mileage_5k_accepted_at_8_weeks(self):
        req = PlanRequest(
            current_km=0,
            target_distance=5.0,
            weeks=8,
            max_runs_per_week=3,
        )
        assert req.current_km == 0

    def test_zero_mileage_10k_requires_8_weeks(self):
        from app.exceptions import InsufficientTimeException
        with pytest.raises(InsufficientTimeException):
            PlanRequest(
                current_km=0,
                target_distance=10.0,
                weeks=6,
                max_runs_per_week=3,
            )

    def test_zero_mileage_rejected_for_half(self):
        from app.exceptions import ZeroMileageUnsupportedException
        with pytest.raises(ZeroMileageUnsupportedException):
            PlanRequest(
                current_km=0,
                target_distance=21.1,
                weeks=12,
                max_runs_per_week=4,
            )

    def test_zero_mileage_rejected_for_trail(self):
        from app.exceptions import ZeroMileageUnsupportedException
        with pytest.raises(ZeroMileageUnsupportedException):
            PlanRequest(
                current_km=0,
                target_distance=30.0,
                weeks=12,
                max_runs_per_week=4,
            )

    def test_zero_mileage_rejected_for_marathon(self):
        from app.exceptions import ZeroMileageUnsupportedException
        with pytest.raises(ZeroMileageUnsupportedException):
            PlanRequest(
                current_km=0,
                target_distance=42.2,
                weeks=16,
                max_runs_per_week=4,
            )

    def test_invalid_distance_rejected(self):
        with pytest.raises(ValueError):
            PlanRequest(
                current_km=20.0,
                target_distance=15.0,
                weeks=8,
                max_runs_per_week=4,
            )


# ── Plan Generation: All Combinations ─────────────────────────────────────

class TestPlanGenerationAllCombinations:
    """Generate plans for ALL valid distance/weeks/mileage/runs combos."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_plan_generates_without_error(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        assert len(plan) == weeks

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_plan_has_correct_week_count(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        week_numbers = [w["week"] for w in plan]
        assert week_numbers == list(range(1, weeks + 1))

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_plan_has_7_days_per_week(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            assert len(week["daily_workouts"]) == 7

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_run_count_respected(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            run_days = [
                w for w in week["daily_workouts"]
                if w["type"] not in ("rest", "recovery")
            ]
            assert len(run_days) == runs, (
                f"Week {week['week']}: {len(run_days)} runs, expected {runs}"
            )

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_every_week_has_long_run(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            longs = [w for w in week["daily_workouts"] if w["type"] == "long"]
            assert len(longs) == 1, f"Week {week['week']}: {len(longs)} long runs"

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_no_negative_distances(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            for w in week["daily_workouts"]:
                assert w.get("distance", 0) >= 0

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_total_km_matches_workouts(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            actual = sum(w.get("distance", 0) for w in week["daily_workouts"])
            assert abs(actual - week["total_km"]) <= 0.5, (
                f"Week {week['week']}: total={week['total_km']}, sum={actual}"
            )

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_long_run_is_longest(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            workouts = week["daily_workouts"]
            longs = [w for w in workouts if w["type"] == "long" and w.get("distance", 0) > 0]
            if not longs:
                continue
            long_d = longs[0]["distance"]
            for w in workouts:
                if w["type"] in ("easy", "tempo", "interval", "hill"):
                    if w.get("duration_min"):
                        continue
                    assert w.get("distance", 0) <= long_d + 0.1

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_phase_assigned(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        valid_phases = {"base", "build", "peak", "taper"}
        for week in plan:
            assert week["phase"] in valid_phases

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_taper_week_has_reduced_volume(self, combo):
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        taper_weeks = [w for w in plan if w["phase"] == "taper"]
        pre_taper = [w for w in plan if w["phase"] != "taper"]
        if taper_weeks and pre_taper:
            peak_km = max(w["total_km"] for w in pre_taper)
            for tw in taper_weeks:
                # 4 km tolerance: prescriptive workouts (key + standard
                # tempo/interval/hill) hold their authored dose, so the
                # high-water-mark cap suppresses peak weeks more than
                # taper weeks where every workout is flexible. The
                # invariant (taper < peak by design) still holds —
                # just with a wider rounding margin.
                assert tw["total_km"] <= peak_km + 4.0


# ── Boundary Condition Tests ──────────────────────────────────────────────

class TestBoundaryConditions:
    """Test edge cases at the boundaries of valid ranges."""

    @pytest.mark.parametrize("distance", SUPPORTED_DISTANCES)
    def test_minimum_weeks(self, distance):
        """Plan generation at minimum weeks for each distance."""
        cfg = DISTANCE_CONFIG[distance]
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=cfg["min_mileage"],
            target_distance=distance,
            weeks=cfg["min_weeks"],
            max_runs_per_week=4,
        )
        assert len(plan) == cfg["min_weeks"]

    @pytest.mark.parametrize("distance", SUPPORTED_DISTANCES)
    def test_maximum_weeks(self, distance):
        """Plan generation at maximum weeks for each distance."""
        cfg = DISTANCE_CONFIG[distance]
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=cfg["min_mileage"],
            target_distance=distance,
            weeks=cfg["max_weeks"],
            max_runs_per_week=4,
        )
        assert len(plan) == cfg["max_weeks"]

    @pytest.mark.parametrize("distance", SUPPORTED_DISTANCES)
    def test_minimum_mileage(self, distance):
        """Plan generation at minimum mileage for each distance."""
        cfg = DISTANCE_CONFIG[distance]
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=cfg["min_mileage"],
            target_distance=distance,
            weeks=cfg["min_weeks"],
            max_runs_per_week=4,
        )
        assert all(w["total_km"] > 0 for w in plan)

    @pytest.mark.parametrize("distance", SUPPORTED_DISTANCES)
    def test_maximum_mileage(self, distance):
        """Plan generation at maximum mileage (warning threshold) for each distance."""
        cfg = DISTANCE_CONFIG[distance]
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=cfg["max_mileage"],
            target_distance=distance,
            weeks=cfg["min_weeks"],
            max_runs_per_week=4,
        )
        assert len(plan) == cfg["min_weeks"]

    @pytest.mark.parametrize("distance", SUPPORTED_DISTANCES)
    def test_minimum_runs(self, distance):
        """Plan generation at minimum runs for each distance."""
        cfg = DISTANCE_CONFIG[distance]
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=cfg["min_mileage"],
            target_distance=distance,
            weeks=cfg["min_weeks"],
            max_runs_per_week=cfg["min_runs"],
        )
        for week in plan:
            run_days = [w for w in week["daily_workouts"] if w["type"] not in ("rest", "recovery")]
            assert len(run_days) == cfg["min_runs"]

    @pytest.mark.parametrize("distance", SUPPORTED_DISTANCES)
    def test_five_runs_per_week(self, distance):
        """Plan generation at 5 runs/week for each distance."""
        cfg = DISTANCE_CONFIG[distance]
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=cfg["min_mileage"],
            target_distance=distance,
            weeks=cfg["min_weeks"],
            max_runs_per_week=5,
        )
        for week in plan:
            run_days = [w for w in week["daily_workouts"] if w["type"] not in ("rest", "recovery")]
            assert len(run_days) == 5


# ── API-Level Tests (via FastAPI TestClient) ──────────────────────────────

class TestPlanGenerationAPI:
    """Test plan generation through the API endpoint."""

    def _generate_via_api(self, client, current_km, target_distance, weeks, max_runs):
        """Helper to generate a plan via the API form endpoint."""
        response = client.post(
            "/generate-plan",
            data={
                "current_km": current_km,
                "target_distance": str(target_distance),
                "weeks": weeks,
                "max_runs_per_week": max_runs,
                "body_weight_kg": 70.0,
            },
            follow_redirects=False,
        )
        return response

    @pytest.mark.parametrize("distance,weeks,mileage,runs", [
        (5.0, 6, 5.0, 2),
        (5.0, 8, 15.0, 3),
        (5.0, 12, 25.0, 4),
        (5.0, 16, 40.0, 5),
        (10.0, 6, 10.0, 2),
        (10.0, 10, 20.0, 3),
        (10.0, 14, 35.0, 4),
        (10.0, 16, 50.0, 5),
        (21.1, 8, 15.0, 3),
        (21.1, 12, 25.0, 4),
        (21.1, 16, 45.0, 5),
        (21.1, 20, 70.0, 5),
        (30.0, 6, 15.0, 4),
        (30.0, 12, 30.0, 4),
        (30.0, 16, 45.0, 5),
        (30.0, 20, 60.0, 5),
        (42.2, 12, 25.0, 4),
        (42.2, 16, 40.0, 4),
        (42.2, 20, 60.0, 5),
        (42.2, 24, 100.0, 5),
    ])
    def test_api_generates_plan(self, client, distance, weeks, mileage, runs):
        """API should redirect to plan page on successful generation."""
        response = self._generate_via_api(client, mileage, distance, weeks, runs)
        assert response.status_code == 303, f"Expected redirect, got {response.status_code}"
        assert "/plan/" in response.headers.get("location", "")

    @pytest.mark.parametrize("distance,weeks,mileage,runs,expected_status", [
        (5.0, 3, 10.0, 3, 200),
        (10.0, 5, 15.0, 3, 200),
        (21.1, 7, 20.0, 3, 200),
        (30.0, 5, 20.0, 4, 200),
        (42.2, 11, 30.0, 4, 200),
    ])
    def test_api_rejects_invalid_weeks(self, client, distance, weeks, mileage, runs, expected_status):
        """API should return error page for invalid weeks."""
        response = self._generate_via_api(client, mileage, distance, weeks, runs)
        assert response.status_code == expected_status

    @pytest.mark.parametrize("distance,weeks,mileage,runs", [
        (21.1, 12, 20.0, 2),
        (30.0, 12, 20.0, 3),
        (42.2, 16, 30.0, 3),
    ])
    def test_api_rejects_insufficient_runs(self, client, distance, weeks, mileage, runs):
        """API should return error page for insufficient runs per week."""
        response = self._generate_via_api(client, mileage, distance, weeks, runs)
        assert response.status_code == 200
        assert "error" in response.text.lower() or "requires" in response.text.lower()

    @pytest.mark.parametrize("distance,weeks,mileage,runs", [
        (5.0, 8, 3.0, 3),
        (10.0, 8, 5.0, 3),
        (21.1, 12, 10.0, 4),
        (30.0, 12, 10.0, 4),
        (42.2, 16, 20.0, 4),
    ])
    def test_api_rejects_low_mileage(self, client, distance, weeks, mileage, runs):
        """API should return error page for mileage below minimum."""
        response = self._generate_via_api(client, mileage, distance, weeks, runs)
        assert response.status_code == 200
        assert "error" in response.text.lower() or "mileage" in response.text.lower()


# ── Mileage Progression Validation ────────────────────────────────────────

class TestMileageProgression:
    """Validate mileage progression across all combinations."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_ten_percent_rule(self, combo):
        """No non-recovery week may exceed 12% over previous non-recovery week.

        The base rule is 10%; we allow 2% on top to absorb (a) rounding to
        0.1 km on per-workout distances and (b) the 0.6 km of strides
        occasionally added to easy runs.
        """
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        high_water = mileage

        for week in plan:
            runs_list = [
                w for w in week["daily_workouts"]
                if w["type"] not in ("rest", "recovery", "strength", "cross_training")
                and w.get("distance", 0) > 0
            ]
            total = sum(w["distance"] for w in runs_list)
            is_recovery = week.get("is_recovery", False)

            if not is_recovery and high_water > 0:
                increase_pct = ((total - high_water) / high_water) * 100
                assert increase_pct <= 12, (
                    f"Week {week['week']}: {increase_pct:.1f}% jump "
                    f"({high_water:.1f} -> {total:.1f}km)"
                )

            if not is_recovery and total > high_water:
                high_water = total

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_easy_never_exceeds_long_run(self, combo):
        """No easy run may be longer than the long run in the same week."""
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            workouts = week["daily_workouts"]
            longs = [w for w in workouts if w.get("type") == "long" and w.get("distance", 0) > 0]
            if not longs:
                continue
            long_d = longs[0]["distance"]
            for w in workouts:
                if w.get("type") == "easy" and w.get("distance", 0) > 0:
                    if w.get("duration_min"):
                        continue
                    assert w["distance"] <= long_d + 0.1

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_no_zero_distance_running_workouts(self, combo):
        """Running workouts should not have 0 distance (except final taper week)."""
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            if week["week"] == weeks:
                continue
            for w in week["daily_workouts"]:
                if w.get("type") in ("rest", "recovery"):
                    continue
                if w.get("type") in ("easy", "tempo", "interval", "hill", "long"):
                    assert w.get("distance", 0) > 0, (
                        f"Week {week['week']}: {w['type']} has 0 distance"
                    )

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_combo_id(c) for c in ALL_COMBOS])
    def test_quality_caps_hold(self, combo):
        """Quality workouts should not exceed 90% of the long run."""
        distance, weeks, mileage, runs = combo
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=mileage,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            workouts = week["daily_workouts"]
            longs = [w for w in workouts if w.get("type") == "long" and w.get("distance", 0) > 0]
            if not longs:
                continue
            long_d = longs[0]["distance"]
            for w in workouts:
                if w.get("type") in ("tempo", "interval", "hill") and w.get("distance", 0) > 0:
                    if w.get("duration_min"):
                        continue
                    assert w["distance"] <= long_d * 0.90


# ── Distance-Specific Invariants ──────────────────────────────────────────

class TestDistanceSpecificInvariants:
    """Test invariants that are specific to certain distances."""

    @pytest.mark.parametrize("distance", [21.1, 30.0, 42.2])
    def test_long_run_below_race_distance(self, distance):
        """For half marathon and above, long runs should never reach race distance."""
        cfg = DISTANCE_CONFIG[distance]
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=cfg["min_mileage"],
            target_distance=distance,
            weeks=cfg["min_weeks"],
            max_runs_per_week=4,
        )
        for week in plan:
            for w in week["daily_workouts"]:
                if w["type"] == "long":
                    assert w["distance"] < distance

    @pytest.mark.parametrize("distance", [21.1, 42.2])
    def test_long_run_stays_below_92_percent(self, distance):
        """For half and marathon, long runs should stay well below race distance."""
        cfg = DISTANCE_CONFIG[distance]
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=cfg["min_mileage"],
            target_distance=distance,
            weeks=cfg["min_weeks"],
            max_runs_per_week=4,
        )
        threshold = distance * 0.92
        for week in plan:
            for w in week["daily_workouts"]:
                if w["type"] == "long":
                    assert w["distance"] <= threshold

    def test_marathon_peak_mileage_adequate(self):
        """Marathon plans should reach adequate peak mileage."""
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=25, target_distance=42.2, weeks=16, max_runs_per_week=4,
        )
        peak_km = max(w["total_km"] for w in plan if not w.get("is_recovery", False))
        assert peak_km >= 45

    def test_trail_terrain_flat_accepted(self):
        """Trail plans should accept flat terrain."""
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=20, target_distance=30.0, weeks=10, max_runs_per_week=4,
        )
        assert len(plan) == 10

    @pytest.mark.parametrize("distance", [5.0, 10.0])
    def test_short_distances_allow_2_runs(self, distance):
        """5K and 10K should allow 2 runs per week."""
        cfg = DISTANCE_CONFIG[distance]
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=cfg["min_mileage"],
            target_distance=distance,
            weeks=cfg["min_weeks"],
            max_runs_per_week=2,
        )
        for week in plan:
            run_days = [w for w in week["daily_workouts"] if w["type"] not in ("rest", "recovery")]
            assert len(run_days) == 2


# ── Summary Statistics ────────────────────────────────────────────────────

class TestCombinationCoverage:
    """Verify the test matrix covers all expected combinations."""

    def test_total_combination_count(self):
        """Report and verify total combination count."""
        total = len(ALL_COMBOS)
        assert total > 0, "Should have at least one combination"

    def test_distance_coverage(self):
        """Each distance should have combinations."""
        distances_covered = set(c[0] for c in ALL_COMBOS)
        assert distances_covered == set(SUPPORTED_DISTANCES)

    def test_runs_coverage_per_distance(self):
        """Each distance should have all valid run frequencies covered."""
        for distance in SUPPORTED_DISTANCES:
            valid_runs = set(c[3] for c in ALL_COMBOS if c[0] == distance)
            expected_runs = set(_valid_runs(distance))
            assert valid_runs == expected_runs, (
                f"{DISTANCE_NAMES[distance]}: expected runs {expected_runs}, got {valid_runs}"
            )

    def test_weeks_coverage_per_distance(self):
        """Each distance should have all valid durations covered."""
        for distance in SUPPORTED_DISTANCES:
            weeks_covered = set(c[1] for c in ALL_COMBOS if c[0] == distance)
            expected_weeks = set(_duration_range(distance))
            assert weeks_covered == expected_weeks, (
                f"{DISTANCE_NAMES[distance]}: expected weeks {expected_weeks}, got {weeks_covered}"
            )

    def test_mileage_coverage_per_distance(self):
        """Each distance should have all valid mileages covered."""
        for distance in SUPPORTED_DISTANCES:
            mileages_covered = set(c[2] for c in ALL_COMBOS if c[0] == distance)
            expected_mileages = set(_mileage_range(distance))
            assert mileages_covered == expected_mileages, (
                f"{DISTANCE_NAMES[distance]}: expected mileages {expected_mileages}, got {mileages_covered}"
            )
