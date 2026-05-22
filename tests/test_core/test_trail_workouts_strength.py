"""Phase 4: per-elevation-class strength rotations + bracket-aware
selection of trail key workouts."""

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.key_workout_library import KeyWorkoutLibrary
from app.core.training.strength_plan import (
    PHASE_FOCUS_ROTATIONS,
    TRAIL_FOCUS_ROTATIONS,
    get_phase_focus_rotation,
)
from app.core.training.trail_profile import classify_trail


def _build_plan(distance, elevation, weeks, runs, current_km, terrain=None):
    profile = classify_trail(distance, elevation)
    return TrainingPlanGenerator().generate_plan(
        current_km=current_km,
        target_distance=distance,
        weeks=weeks,
        max_runs_per_week=runs,
        terrain=terrain,
        trail_profile=profile,
    )


class TestStrengthRotationsByElevationClass:
    """Each elevation class picks its own strength focus rotation."""

    def test_flat_trail_build_uses_double_plyometric(self):
        profile = classify_trail(50.0, 100.0)  # flat 50k
        rotation = get_phase_focus_rotation("build", trail_profile=profile)
        # Flat trail now uses dedicated flat-trail strength as the primary
        # climb-equivalent strength stimulus and keeps one plyometric slot.
        assert "flat_trail_strength" in rotation
        assert rotation.count("plyometric") >= 1
        assert "trail_stability" not in rotation

    def test_flat_trail_base_includes_plyometric(self):
        profile = classify_trail(50.0, 100.0)
        rotation = get_phase_focus_rotation("base", trail_profile=profile)
        assert "flat_trail_strength" in rotation
        assert "plyometric" in rotation

    def test_rolling_uses_legacy_trail_rotation(self):
        profile = classify_trail(30.0, 600.0)  # rolling 30km (~20 m/km)
        for phase in ("base", "build", "peak", "taper"):
            assert (
                get_phase_focus_rotation(phase, trail_profile=profile)
                == TRAIL_FOCUS_ROTATIONS[phase]
            )

    def test_hilly_uses_legacy_trail_rotation(self):
        profile = classify_trail(30.0, 1000.0)  # 33 m/km → hilly
        for phase in ("base", "build", "peak", "taper"):
            assert (
                get_phase_focus_rotation(phase, trail_profile=profile)
                == TRAIL_FOCUS_ROTATIONS[phase]
            )

    def test_mountainous_includes_stability_and_plyometric_every_phase(self):
        profile = classify_trail(80.0, 4500.0)  # 56 m/km → mountainous
        for phase in ("base", "build", "peak"):
            rotation = get_phase_focus_rotation(phase, trail_profile=profile)
            assert "trail_stability" in rotation
            assert "plyometric" in rotation

    def test_road_unaffected(self):
        # No trail_profile → fall through to road rotation.
        for phase in ("base", "build", "peak", "taper"):
            assert get_phase_focus_rotation(phase) == PHASE_FOCUS_ROTATIONS[phase]

    def test_legacy_30km_target_still_picks_trail_rotation(self):
        # Back-compat: callers passing target_distance=30.0 without a
        # trail_profile still get the trail rotation.
        rotation = get_phase_focus_rotation("build", target_distance=30.0)
        assert rotation == TRAIL_FOCUS_ROTATIONS["build"]

    def test_full_plan_flat_trail_assigns_plyometric_strength(self):
        plan = _build_plan(50.0, 200.0, 16, 5, current_km=35.0)
        focuses_in_build = [
            s.get("focus")
            for week in plan
            if week["phase"] == "build"
            for s in week.get("strength_training", [])
        ]
        assert any(f == "plyometric" for f in focuses_in_build), (
            "Flat 50k build phase should prescribe plyometric strength sessions"
        )
        assert any(f == "flat_trail_strength" for f in focuses_in_build), (
            "Flat 50k build phase should prescribe flat-trail strength sessions"
        )

    def test_full_plan_rolling_30km_does_not_use_plyometric_in_base(self):
        # Rolling 30km uses legacy TRAIL_FOCUS_ROTATIONS — base = lower/stability/core
        plan = _build_plan(30.0, 600.0, 12, 4, current_km=22.0)
        focuses_in_base = [
            s.get("focus")
            for week in plan
            if week["phase"] == "base"
            for s in week.get("strength_training", [])
        ]
        # Plyometric is reserved for build/peak in rolling/hilly.
        assert "plyometric" not in focuses_in_base


class TestKeyWorkoutBracketGating:
    """Ultra-only workouts shouldn't fire for short trail plans."""

    def test_back_to_back_locked_to_ultra_brackets(self):
        short = classify_trail(15.0, 500.0)
        ultra = classify_trail(50.0, 1500.0)
        # short bracket: back_to_back excluded
        all_short = KeyWorkoutLibrary.get_all_for_distance(15.0, trail_profile=short)
        assert not any(w["id"] == "trail_back_to_back" for w in all_short)
        # ultra bracket: back_to_back available
        all_ultra = KeyWorkoutLibrary.get_all_for_distance(50.0, trail_profile=ultra)
        assert any(w["id"] == "trail_back_to_back" for w in all_ultra)

    def test_race_simulation_locked_to_ultra_brackets(self):
        short = classify_trail(15.0, 500.0)
        long_ultra = classify_trail(100.0, 3000.0)
        all_short = KeyWorkoutLibrary.get_all_for_distance(15.0, trail_profile=short)
        assert not any(w["id"] == "trail_long_race_simulation" for w in all_short)
        all_long_ultra = KeyWorkoutLibrary.get_all_for_distance(
            100.0, trail_profile=long_ultra
        )
        assert any(w["id"] == "trail_long_race_simulation" for w in all_long_ultra)

    def test_trail_workouts_unlock_for_50km(self):
        # Pre-Phase-4: trail workouts were locked to 30.0; this test guards
        # against regressing that lock.
        ultra = classify_trail(50.0, 1500.0)
        catalog = KeyWorkoutLibrary.get_all_for_distance(50.0, trail_profile=ultra)
        ids = {w["id"] for w in catalog}
        assert "trail_elevation_repeats" in ids
        assert "trail_time_on_feet" in ids
        assert "trail_power_hike" in ids

    def test_flat_trail_excludes_hilly_workouts(self):
        flat = classify_trail(50.0, 200.0)
        catalog = KeyWorkoutLibrary.get_all_for_distance(50.0, trail_profile=flat)
        # Hilly-tagged workouts should not appear when terrain is flat.
        for w in catalog:
            assert "flat" in w.get("terrain", ["any"]) or "any" in w.get(
                "terrain", ["any"]
            )
        # And the hilly elevation_repeats workout should be filtered out.
        ids = {w["id"] for w in catalog}
        assert "trail_elevation_repeats" not in ids

    def test_training_terrain_overrides_race_terrain_for_workout_filtering(self):
        hilly_race = classify_trail(50.0, 2500.0)
        catalog = KeyWorkoutLibrary.get_all_for_distance(
            50.0,
            terrain="flat",
            trail_profile=hilly_race,
        )
        ids = {w["id"] for w in catalog}
        assert "trail_elevation_repeats" not in ids
        assert "trail_flat_surge_fartlek" in ids
        assert "trail_flat_over_under_intervals" in ids


class TestNightRunForLongUltra:
    """The new headlamp night-run template only fires for long_ultra peak weeks."""

    def test_night_run_available_for_long_ultra(self):
        long_ultra = classify_trail(163.0, 6000.0)
        peak_options = [
            KeyWorkoutLibrary.get_for_phase(
                163.0,
                "peak",
                wk,
                "tempo",
                trail_profile=long_ultra,
            )
            for wk in range(8)
        ]
        ids = {w["id"] for w in peak_options if w}
        assert "trail_night_run" in ids

    def test_night_run_excluded_for_ultra_50km(self):
        ultra = classify_trail(50.0, 1500.0)
        all_workouts = KeyWorkoutLibrary.get_all_for_distance(50.0, trail_profile=ultra)
        assert not any(w["id"] == "trail_night_run" for w in all_workouts)

    def test_night_run_excluded_for_short(self):
        short = classify_trail(15.0, 500.0)
        all_workouts = KeyWorkoutLibrary.get_all_for_distance(15.0, trail_profile=short)
        assert not any(w["id"] == "trail_night_run" for w in all_workouts)

    def test_night_run_excluded_for_road(self):
        # No trail_profile → night_run not eligible.
        all_workouts = KeyWorkoutLibrary.get_all_for_distance(42.2)
        assert not any(w["id"] == "trail_night_run" for w in all_workouts)


class TestTrailWorkoutsAppearInGeneratedPlans:
    """End-to-end: the new selector actually surfaces trail workouts in
    generated plans for non-30km distances."""

    def test_50km_ultra_plan_includes_trail_workout_overlay(self):
        plan = _build_plan(50.0, 1500.0, 16, 5, current_km=35.0)
        keyed = [
            w
            for week in plan
            for w in week["daily_workouts"]
            if w.get("key_workout_id", "").startswith("trail_")
        ]
        assert keyed, (
            "50km ultra plan must overlay at least one trail-specific key workout"
        )

    def test_legacy_30km_plan_still_overlays_trail_workouts(self):
        # Back-compat smoke: passing target=30 with no trail_profile still works.
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=25.0,
            target_distance=30.0,
            weeks=12,
            max_runs_per_week=4,
        )
        keyed = [
            w
            for week in plan
            for w in week["daily_workouts"]
            if w.get("key_workout_id", "").startswith("trail_")
        ]
        assert keyed, "Legacy 30km path must still overlay trail key workouts"

    def test_hilly_race_with_flat_training_uses_flat_key_workouts(self):
        plan = _build_plan(50.0, 2500.0, 16, 5, current_km=35.0, terrain="flat")
        keyed_ids = {
            w.get("key_workout_id")
            for week in plan
            for w in week["daily_workouts"]
            if w.get("key_workout_id", "").startswith("trail_")
        }
        assert "trail_flat_surge_fartlek" in keyed_ids
        assert "trail_elevation_repeats" not in keyed_ids
