"""Tests for app.core.race.race_profiles registry and extensibility.

Two goals:
1. Regression — assert the generator wired to the new registry still emits
   the exact distance_name, pacing strategy first sentence, nutrition
   length, mental checkpoint count, and morning timeline length for each
   of the existing road distances.
2. Extensibility smoke test — show that adding a new RaceProfile (50K
   ultra) becomes a single-file change and the generator picks it up via
   snap-to-nearest.
"""

from app.core.race.race_profiles import (
    RACE_PROFILES,
    RaceProfile,
    lookup_profile,
)
from app.core.race.race_protocol_generator import generate_race_protocol


class TestRegistryRegression:
    def test_5k_protocol_shape(self):
        protocol = generate_race_protocol(5.0, goal_pace_min_km=4.5)
        assert protocol["distance_name"] == "5K"
        assert "aerobic sprint" in protocol["pacing_strategy"]
        assert len(protocol["nutrition_timing"]) == 4
        assert len(protocol["mental_checkpoints"]) == 4
        assert len(protocol["race_morning_timeline"]) == 5
        assert protocol["is_trail"] is False

    def test_10k_protocol_shape(self):
        protocol = generate_race_protocol(10.0, goal_pace_min_km=5.0)
        assert protocol["distance_name"] == "10K"
        assert "rewards patience" in protocol["pacing_strategy"]
        assert len(protocol["nutrition_timing"]) == 4
        assert len(protocol["mental_checkpoints"]) == 4

    def test_half_marathon_protocol_shape(self):
        protocol = generate_race_protocol(21.1, goal_pace_min_km=5.5)
        assert protocol["distance_name"] == "Half Marathon"
        assert "Negative splits" in protocol["pacing_strategy"]
        assert len(protocol["nutrition_timing"]) == 6
        assert len(protocol["mental_checkpoints"]) == 5

    def test_marathon_protocol_shape(self):
        protocol = generate_race_protocol(42.2, goal_pace_min_km=5.5)
        assert protocol["distance_name"] == "Marathon"
        assert (
            "the wall zone".lower() in protocol["pacing_strategy"].lower()
            or "the hardest discipline" in protocol["pacing_strategy"]
        )
        assert len(protocol["nutrition_timing"]) == 6
        # Marathon adds 3 week-before extras.
        assert any(
            "permanent marker" in line for line in protocol["week_before_checklist"]
        )

    def test_30k_trail_road_path_shape(self):
        # When called without a trail_profile, 30k goes through the road
        # path and returns the 30K Trail entry.
        protocol = generate_race_protocol(30.0, goal_pace_min_km=5.5)
        assert protocol["distance_name"] == "30K Trail"
        # Has trail-specific week_before_extras merged in.
        assert any(
            "hydration vest" in line for line in protocol["week_before_checklist"]
        )

    def test_snap_to_nearest_for_unknown_distance(self):
        # 8 km snaps to 10K profile.
        protocol = generate_race_protocol(8.0, goal_pace_min_km=5.0)
        assert protocol["distance_name"] == "10K"


class TestRegistryExtensibility:
    def test_adding_a_50k_ultra_profile_is_one_call(self):
        """Demo: adding a new road race distance is now a single registry
        insert. After this insert, `lookup_profile` picks it up
        automatically — no changes to race_protocol_generator needed."""
        ultra_50k = RaceProfile(
            distance_km=50.0,
            display_name="50K Ultra",
            pacing_strategy="Walk every steep climb. Eat to a clock, not to thirst.",
            nutrition_timing=[
                {"icon": "🍌", "when": "3 hrs before", "what": "Big carb breakfast"},
            ],
            mental_checkpoints=[
                {"distance": "10 km", "message": "Conservative — you have hours left."},
            ],
            morning_timeline=[
                ("3 hrs before", "Wake; tested breakfast"),
            ],
            week_before_extras=["Drop bags packed and labelled"],
        )
        # Register the new profile.
        RACE_PROFILES[50.0] = ultra_50k
        try:
            assert lookup_profile(50.0).display_name == "50K Ultra"
            # Snap-to-nearest still works.
            assert lookup_profile(48.0).display_name == "50K Ultra"
            # And the generator picks it up without code changes.
            protocol = generate_race_protocol(50.0, goal_pace_min_km=6.5)
            assert protocol["distance_name"] == "50K Ultra"
            assert "Walk every steep climb" in protocol["pacing_strategy"]
        finally:
            # Clean up so the registry isn't polluted for other tests.
            RACE_PROFILES.pop(50.0, None)
