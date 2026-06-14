"""Tests for quality-run internal consistency.

Verifies that every key workout that can appear in an interval/tempo/hill
slot generates steps whose effort and pace zone are consistent with the
declared workout type, and that the standalone validator correctly flags
mismatches.
"""

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.generators.plan_validator import validate_quality_run_steps
from app.core.training.key_workout_library.builders import build_key_workout_steps
from app.core.training.key_workout_library.selection import KeyWorkoutLibrary

# ---------------------------------------------------------------------------
# Constants shared by several tests
# ---------------------------------------------------------------------------

# Key workouts that previously fell through to the easy-run defensive default,
# producing steps with effort="conversational" / pace_zone="E" even though the
# workout type is "interval", "tempo", or "hill".  Every entry here must now
# produce at least one non-easy work step.
PREVIOUSLY_BROKEN_IDS = [
    "10k_rolling_500s",
    "10k_broken_miles",
    "10k_200m_repeats",
    "10k_pyramid_intervals",
    "10k_mile_up_overs",
    "trail_technical_terrain",
    "trail_flat_base_strides",
    "trail_flat_base_fartlek",
    "trail_flat_proprioception",
    "trail_flat_rolling_500s",
    "trail_flat_broken_miles",
    "trail_flat_pyramid",
    "trail_flat_vo2max_intervals",
    "trail_flat_threshold_blocks",
    "trail_flat_progressive_tempo",
    "trail_flat_over_unders",
    "trail_flat_steady_state",
    "trail_broken_climbs",
    "trail_rolling_500s",
    "trail_stacked_efforts",
    "trail_climb_surge_fartlek",
    "trail_downhill_broken_miles",
    "trail_hill_pyramid",
    "trail_base_hike_run",
    "trail_base_surges",
]

_EASY_EFFORTS = frozenset({"easy", "conversational", ""})
_QUALITY_ZONES = frozenset({"T", "I", "M", "R", "10K", "5K"})


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _has_quality_work(steps: list, wtype: str) -> bool:
    """Return True when *steps* contain at least one genuinely hard run step."""
    work_steps = [s for s in steps if s.get("kind") == "run"]
    if not work_steps:
        # Walk-kind hill or hike-run sessions pass: no 'run' steps expected.
        return True
    efforts = [s.get("effort", "") or "" for s in work_steps]
    zones = [s.get("pace_zone", "") or "" for s in work_steps]
    if wtype in ("interval", "hill"):
        return any(e not in _EASY_EFFORTS for e in efforts) or any(
            z in _QUALITY_ZONES for z in zones
        )
    # tempo
    return any(z in _QUALITY_ZONES for z in zones)


# ---------------------------------------------------------------------------
# Unit tests: step builders produce consistent steps
# ---------------------------------------------------------------------------


class TestPreviouslyBrokenKeyWorkoutsHaveConsistentSteps:
    """Each formerly-broken key workout must now generate steps that match its
    declared type (interval steps for interval workouts, etc.)."""

    @pytest.mark.parametrize("kid", PREVIOUSLY_BROKEN_IDS)
    def test_steps_match_workout_type(self, kid: str) -> None:
        wk = KeyWorkoutLibrary.get_by_id(kid)
        assert wk is not None, f"Key workout '{kid}' not found in library"

        wtype = wk["type"]
        steps = build_key_workout_steps(wk, wk.get("structure", ""), 7.0, wtype, None)

        assert steps, f"{kid}: build produced no steps"
        assert _has_quality_work(steps, wtype), (
            f"{kid} (type={wtype}): all run steps have easy effort/zone — "
            f"steps are not internally consistent with the declared type.\n"
            f"Efforts: {[s.get('effort') for s in steps if s.get('kind') == 'run']}\n"
            f"Zones:   {[s.get('pace_zone') for s in steps if s.get('kind') == 'run']}"
        )

    @pytest.mark.parametrize("kid", PREVIOUSLY_BROKEN_IDS)
    def test_steps_produce_nonzero_distance(self, kid: str) -> None:
        """Every fixed-structure key workout must produce a non-zero step distance."""
        from app.core.training.workout_steps import compute_distance_from_steps_checked

        wk = KeyWorkoutLibrary.get_by_id(kid)
        wtype = wk["type"]
        steps = build_key_workout_steps(wk, wk.get("structure", ""), 7.0, wtype, None)
        step_km, _ = compute_distance_from_steps_checked(steps)
        assert step_km > 0, (
            f"{kid}: step total distance is 0 — builder returned empty or "
            "all-duration steps with no resolvable pace"
        )


# ---------------------------------------------------------------------------
# Unit tests: validate_quality_run_steps
# ---------------------------------------------------------------------------


class TestValidateQualityRunSteps:
    """Standalone validator catches mismatches and passes correct workouts."""

    def _make_workout(self, wtype, steps, distance=5.0, kid=None):
        w = {"type": wtype, "steps": steps, "distance": distance}
        if kid:
            w["key_workout_id"] = kid
        return w

    def test_valid_interval_with_hard_steps_passes(self):
        steps = [
            {"kind": "warmup", "effort": "easy", "pace_zone": "E", "distance_m": 1000},
            {"kind": "run", "effort": "hard", "pace_zone": "I", "distance_m": 400, "repeat": 6},
            {"kind": "recovery", "effort": "jog", "pace_zone": "E", "duration_s": 90, "repeat": 5},
            {"kind": "cooldown", "effort": "easy", "pace_zone": "E", "distance_m": 1000},
        ]
        ok, msg = validate_quality_run_steps(self._make_workout("interval", steps, 5.0))
        assert ok, msg

    def test_interval_with_only_easy_steps_fails(self):
        steps = [
            {"kind": "run", "effort": "conversational", "pace_zone": "E", "distance_m": 5000},
        ]
        ok, msg = validate_quality_run_steps(self._make_workout("interval", steps, 5.0))
        assert not ok
        assert "easy effort/zone" in msg

    def test_valid_tempo_with_T_zone_passes(self):
        steps = [
            {"kind": "warmup", "effort": "easy", "pace_zone": "E", "distance_m": 1000},
            {"kind": "run", "effort": "comfortably hard", "pace_zone": "T", "distance_m": 3000},
            {"kind": "cooldown", "effort": "easy", "pace_zone": "E", "distance_m": 1000},
        ]
        ok, msg = validate_quality_run_steps(self._make_workout("tempo", steps, 5.0))
        assert ok, msg

    def test_tempo_with_only_E_zone_fails(self):
        steps = [
            {"kind": "run", "effort": "easy", "pace_zone": "E", "distance_m": 5000},
        ]
        ok, msg = validate_quality_run_steps(self._make_workout("tempo", steps, 5.0))
        assert not ok
        assert "easy-zone" in msg

    def test_hill_with_hard_uphill_effort_passes(self):
        steps = [
            {"kind": "warmup", "effort": "easy", "pace_zone": "E", "distance_m": 1000, "repeat": 1},
            {"kind": "run", "effort": "hard uphill", "pace_zone": "R", "duration_s": 30, "repeat": 10},
            {"kind": "recovery", "effort": "walk", "pace_zone": "WALK", "duration_s": 60, "repeat": 10},
            {"kind": "cooldown", "effort": "easy", "pace_zone": "E", "distance_m": 1000, "repeat": 1},
        ]
        # No key_workout_id → distance check applies.
        # Duration-based reps are priced at default pace: 10 × 30s at R-pace (5 min/km)
        # = 1.0 km work; 10 × 60s walk at WALK (12 min/km) = 0.83 km; 2 km wu+cd → ~3.83 km.
        # Report 4.0 km so the gap (0.17 km) sits inside the 0.3 + 40%×4.0 = 1.9 km tolerance.
        ok, msg = validate_quality_run_steps(self._make_workout("hill", steps, 4.0))
        assert ok, msg

    def test_easy_workout_is_skipped(self):
        """validate_quality_run_steps should not flag non-quality workout types."""
        steps = [{"kind": "run", "effort": "easy", "pace_zone": "E", "distance_m": 5000}]
        ok, msg = validate_quality_run_steps({"type": "easy", "steps": steps, "distance": 5.0})
        assert ok, msg

    def test_distance_mismatch_fails(self):
        """A large discrepancy between steps total and reported distance should fail."""
        steps = [
            {"kind": "warmup", "effort": "easy", "pace_zone": "E", "distance_m": 500},
            {"kind": "run", "effort": "hard", "pace_zone": "I", "distance_m": 400, "repeat": 4},
            {"kind": "cooldown", "effort": "easy", "pace_zone": "E", "distance_m": 500},
        ]
        # Reported 10 km but steps only total ~2.6 km
        ok, msg = validate_quality_run_steps(self._make_workout("interval", steps, 10.0))
        assert not ok
        assert "km" in msg


# ---------------------------------------------------------------------------
# Integration tests: full plan generation produces no consistency violations
# ---------------------------------------------------------------------------


class TestPlanGenerationQualityRunConsistency:
    """Generate plans across a matrix of configs and assert every quality run
    in the resulting plan passes the consistency validator."""

    @pytest.mark.parametrize(
        "mileage,race_km,weeks,runs",
        [
            (20, 10.0, 10, 4),
            (40, 10.0, 10, 4),
            (30, 21.1, 12, 4),
            (50, 21.1, 12, 4),
            (50, 42.2, 16, 4),
            (20, 5.0, 8, 3),
        ],
    )
    def test_all_quality_runs_consistent(self, mileage, race_km, weeks, runs):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(float(mileage), race_km, weeks, runs)

        violations = []
        for week in plan:
            for w in week.get("daily_workouts", []):
                if w.get("type") not in ("interval", "tempo", "hill"):
                    continue
                ok, reason = validate_quality_run_steps(w)
                if not ok:
                    violations.append(
                        f"Week {week['week']} Day {w.get('day')} "
                        f"kid={w.get('key_workout_id','—')}: {reason}"
                    )

        assert not violations, (
            f"{len(violations)} quality-run consistency violation(s) in "
            f"plan({mileage}km/{race_km}km/{weeks}w/{runs}runs):\n"
            + "\n".join(violations)
        )
