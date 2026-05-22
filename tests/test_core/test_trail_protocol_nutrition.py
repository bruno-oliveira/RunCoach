"""Phase 5: race protocol + nutrition for parameterized trail/ultra plans."""

import pytest

from app.contexts.nutrition.nutrition_engine import (
    NutritionEngine,
    _trail_distance_boost,
    build_in_race_fueling_table,
)
from app.core.race.race_protocol_generator import generate_race_protocol
from app.core.training.trail_profile import classify_trail

# --- Race protocol -----------------------------------------------------------


class TestTrailRaceProtocol:
    """Race protocol scales with bracket / elevation when trail_profile is set."""

    def test_legacy_road_path_unchanged(self):
        """No trail_profile + road distance → original tabular protocol."""
        protocol = generate_race_protocol(42.2, goal_pace_min_km=5.0)
        assert protocol["distance_name"] == "Marathon"
        assert protocol.get("is_trail") is False
        # Legacy road protocol uses fixed mental checkpoints.
        assert any("10 km" in cp["distance"] for cp in protocol["mental_checkpoints"])

    def test_trail_distance_name_uses_bracket_label(self):
        # Standard 30km
        std = generate_race_protocol(
            30.0, 5.5, trail_profile=classify_trail(30.0, 1000.0)
        )
        assert "Trail" in std["distance_name"]
        # Ultra 50km
        ultra = generate_race_protocol(
            50.0, 6.0, trail_profile=classify_trail(50.0, 1500.0)
        )
        assert "Ultra Trail" in ultra["distance_name"]
        # Long ultra 100mi
        lu = generate_race_protocol(
            163.0, 7.0, trail_profile=classify_trail(163.0, 6000.0)
        )
        assert "Ultra Trail" in lu["distance_name"]
        assert "163" in lu["distance_name"]

    def test_mental_checkpoints_scale_with_distance(self):
        protocol = generate_race_protocol(
            50.0, 6.0, trail_profile=classify_trail(50.0, 1500.0)
        )
        # Anchors are at 10/33/50/75/90% of 50km → 5, 16.5, 25, 37.5, 45 km.
        distances = [cp["distance"] for cp in protocol["mental_checkpoints"]]
        assert "5.0 km" in distances
        assert "25.0 km" in distances
        assert "45.0 km" in distances

    def test_long_ultra_morning_starts_4_hrs_before(self):
        protocol = generate_race_protocol(
            163.0, 7.0, trail_profile=classify_trail(163.0, 6000.0)
        )
        first_step = protocol["race_morning_timeline"][0]
        assert "4 hrs before" in first_step["time"]
        # And mentions kit-check / mandatory gear
        text = " ".join(s["activity"] for s in protocol["race_morning_timeline"])
        assert "kit" in text.lower() or "mandatory" in text.lower()

    def test_ultra_extras_include_drop_bag_and_pacer(self):
        protocol = generate_race_protocol(
            80.0, 6.5, trail_profile=classify_trail(80.0, 3000.0)
        )
        text = " ".join(protocol["week_before_checklist"]).lower()
        assert "drop bag" in text or "drop bags" in text
        assert "pacer" in text or "crew" in text

    def test_long_ultra_extras_include_sleep_strategy(self):
        protocol = generate_race_protocol(
            163.0, 7.0, trail_profile=classify_trail(163.0, 6000.0)
        )
        text = " ".join(protocol["week_before_checklist"]).lower()
        assert "sleep" in text
        assert "headlamp" in text

    def test_ultra_extras_NOT_in_short_trail_protocol(self):
        # Base trail extras (any bracket) include a one-line drop-bag reminder.
        # The ultra-only items we want absent: detailed drop-bag packing,
        # crew/pacer hand-offs, sleep strategy.
        protocol = generate_race_protocol(
            15.0, 5.5, trail_profile=classify_trail(15.0, 500.0)
        )
        text = " ".join(protocol["week_before_checklist"]).lower()
        assert "pacer" not in text
        assert "crew" not in text
        assert "sleep strategy" not in text
        assert "spare socks" not in text  # belongs to ultra drop-bag packing list

    def test_mountainous_extras_mention_descent_grip(self):
        protocol = generate_race_protocol(
            50.0, 6.5, trail_profile=classify_trail(50.0, 2700.0)
        )
        text = " ".join(protocol["week_before_checklist"]).lower()
        assert "descent" in text or "deep-lug" in text

    def test_nutrition_dense_for_ultra(self):
        protocol = generate_race_protocol(
            80.0, 6.5, trail_profile=classify_trail(80.0, 3000.0)
        )
        text = " ".join(item["what"] for item in protocol["nutrition_timing"]).lower()
        # Real food guidance only fires for distance >= 50 km.
        assert "real food" in text
        # Long-duration: electrolytes get tighter cadence.
        assert any("60–90 min" in item["when"] for item in protocol["nutrition_timing"])

    def test_short_trail_keeps_simpler_nutrition(self):
        protocol = generate_race_protocol(
            15.0, 5.5, trail_profile=classify_trail(15.0, 500.0)
        )
        text = " ".join(item["what"] for item in protocol["nutrition_timing"]).lower()
        # No real-food strategy for short trail.
        assert "real food at aid stations" not in text


# --- Nutrition engine --------------------------------------------------------


class TestTrailNutritionFormula:
    """Continuous distance + elevation boost for trail nutrition needs."""

    def test_formula_floor_for_short_low_elevation(self):
        # 8 km / 0 m → boost should equal floor (0.05)
        assert _trail_distance_boost(8.0, 0.0) == pytest.approx(
            0.05 + 8 / 800, abs=0.001
        )

    def test_formula_clamps_at_ceiling(self):
        # Massive vert + max distance → clamp at 0.30
        assert _trail_distance_boost(163.0, 10000.0) == 0.30

    def test_30km_1000m_close_to_legacy_value(self):
        # 30 km / 1000 m: 0.05 + 30/800 + 1000/100000 = 0.0875 + 0.01 = 0.0975
        # Roughly matches the legacy stepped 0.10 boost — back-compat OK.
        boost = _trail_distance_boost(30.0, 1000.0)
        assert 0.09 < boost < 0.11

    def test_100mi_5000m_unlocks_meaningful_uplift(self):
        # 163 km / 5000 m: 0.05 + 163/800 + 5000/100000 = 0.05 + 0.204 + 0.05 = 0.304 → 0.30
        boost = _trail_distance_boost(163.0, 5000.0)
        assert boost >= 0.25, "100mi/5000m should unlock ≥25% caloric uplift"

    def test_100mi_high_elevation_caloric_uplift_vs_road_marathon(self):
        engine = NutritionEngine()
        # Road marathon: stepped boost = 0.10
        marathon_needs = engine.calculate_nutrition_needs(
            weekly_km=60.0,
            target_distance=42.2,
            body_weight=70,
        )
        # 100mi mountain: continuous boost ~0.30
        ultra_needs = engine.calculate_nutrition_needs(
            weekly_km=60.0,
            target_distance=163.0,
            body_weight=70,
            is_trail=True,
            target_elevation_gain_m=5000.0,
        )
        # Ultra calories must be ≥ marathon calories (same training volume).
        assert ultra_needs["calories"] > marathon_needs["calories"]

    def test_road_path_unchanged_when_is_trail_false(self):
        engine = NutritionEngine()
        # Road call (no is_trail): legacy stepped formula.
        legacy_30k = engine.calculate_nutrition_needs(
            weekly_km=40.0,
            target_distance=30.0,
            body_weight=70,
        )
        # Road 42.2: legacy +0.10 boost.
        marathon = engine.calculate_nutrition_needs(
            weekly_km=40.0,
            target_distance=42.2,
            body_weight=70,
        )
        # 30 and 42.2 both get +0.10 → identical calories.
        assert legacy_30k["calories"] == marathon["calories"]


class TestInRaceFuelingTable:
    """Trail meal plan exposes a per-runner fueling table."""

    def test_table_present_for_trail_meal_plan(self):
        engine = NutritionEngine()
        plan = engine.generate_weekly_meal_plan(
            weekly_km=40.0,
            target_distance=50.0,
            body_weight=70,
            is_trail=True,
            target_elevation_gain_m=1500.0,
        )
        assert "in_race_fueling" in plan
        table = plan["in_race_fueling"]
        assert "carbs_per_hour" in table
        assert "electrolytes" in table
        assert "real_food_strategy" in table

    def test_table_absent_for_road_plan(self):
        engine = NutritionEngine()
        plan = engine.generate_weekly_meal_plan(
            weekly_km=40.0,
            target_distance=42.2,
            body_weight=70,
        )
        assert "in_race_fueling" not in plan

    def test_table_carb_band_drops_for_long_duration(self):
        # Short-duration: 15 km / 500 m → estimated < 2 h → high carb band.
        short = build_in_race_fueling_table(15.0, 500.0)
        assert "60–90" in short["carbs_per_hour"]
        # Mid-duration: 30 km / 600 m → estimated 3–6 h → mid band.
        mid = build_in_race_fueling_table(30.0, 600.0)
        assert "60–80" in mid["carbs_per_hour"]
        # Ultra-duration: 163 km / 6000 m → estimated > 6 h → real-food band.
        ultra = build_in_race_fueling_table(163.0, 6000.0)
        assert "50–70" in ultra["carbs_per_hour"]
        assert (
            "potato" in ultra["real_food_strategy"].lower()
            or "broth" in ultra["real_food_strategy"].lower()
        )

    def test_table_electrolyte_cadence_tightens_for_50km_plus(self):
        short = build_in_race_fueling_table(15.0, 500.0)
        long = build_in_race_fueling_table(80.0, 3000.0)
        assert "10 km" in short["electrolytes"]
        assert "60–90 min" in long["electrolytes"]
