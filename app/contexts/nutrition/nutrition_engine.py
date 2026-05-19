from typing import List, Dict, Any, Optional
import random
from functools import lru_cache

from app.contexts.nutrition.meal_selector import MealSelector
from app.contexts.nutrition.nutrition_content import (
    generate_general_nutrition_tips,
    generate_hydration_guide,
)


# --- Nutrition formula constants ----------------------------------------------
# Resting-metabolism baseline: approx 22 kcal per kg of body weight for a
# lightly-active adult runner. Derived from Harris-Benedict simplified for the
# endurance-athlete population (source: ACSM Nutrition for Athletic Performance).
BASE_CALORIES_PER_KG = 22

# Training-load multiplier: every 50 km/week adds 30% on top of base calories.
# A 0-km runner eats base; a 50-km runner eats 1.3x base; 100-km eats 1.6x.
# Calibrated against the ~60 kcal/km burn rate for average pace running.
TRAINING_KM_REFERENCE = 50
TRAINING_FACTOR_PER_REFERENCE = 0.3

# Distance-specific boost on top of the training factor — longer races
# require higher glycogen turnover and post-session recovery fuel.
DISTANCE_BOOST_MARATHON = 0.10  # 42.2 km
DISTANCE_BOOST_ULTRA_TRAIL = 0.10  # 30 km (trail)
DISTANCE_BOOST_HALF = 0.05  # 21.1 km

# Daily protein: 1.8 g/kg is the upper end of the ACSM endurance recommendation
# (1.2-2.0 g/kg) — runners on a training block sit near the top.
PROTEIN_G_PER_KG = 1.8

# Daily fiber: USDA recommended minimum for adults.
DAILY_FIBER_G = 35


# Trail / ultra: continuous boost in distance + elevation, capped at 30%.
# Calibrated so 30 km / 1000 m sits near the legacy stepped value (~0.10),
# while 100 km / 5000 m unlocks ~+25% uplift the stepped formula couldn't
# express and 163 km / 6000 m saturates at the 30% ceiling.
_TRAIL_BOOST_FLOOR = 0.05
_TRAIL_BOOST_CEILING = 0.30
_TRAIL_DISTANCE_DIVISOR = 800.0
_TRAIL_ELEVATION_DIVISOR = 100000.0


def _trail_distance_boost(distance_km: float, elevation_gain_m: float) -> float:
    raw = (
        _TRAIL_BOOST_FLOOR
        + distance_km / _TRAIL_DISTANCE_DIVISOR
        + max(0.0, elevation_gain_m) / _TRAIL_ELEVATION_DIVISOR
    )
    return max(_TRAIL_BOOST_FLOOR, min(_TRAIL_BOOST_CEILING, raw))


def build_in_race_fueling_table(
    distance_km: float, elevation_gain_m: float
) -> Dict[str, Any]:
    """Build an in-race fueling table for trail/ultra plans.

    Carbs/h drops as predicted duration grows (longer races shift to mixed
    real food) and electrolyte cadence tightens. Surfaced in plan view +
    PDF for any trail plan.
    """
    # Crude time estimate without VDOT context: 6 min/km flat baseline plus
    # ~30 sec/km penalty for every 100 m/km of elevation. Used only to
    # bucket the carbs-per-hour band; the per-runner goal time, when known,
    # comes through ``predicted_seconds`` upstream (race protocol generator).
    pace_min_km = 6.0 + 0.5 * (elevation_gain_m / max(distance_km, 1.0)) / 10.0
    estimated_hours = (distance_km * pace_min_km) / 60.0

    if estimated_hours < 2:
        carb_band = "60–90 g/h"
        food_note = "Gels and chews — no real food needed at this duration."
    elif estimated_hours < 6:
        carb_band = "60–80 g/h"
        food_note = "Mostly gels and chews; introduce dates / banana from hour 3."
    else:
        carb_band = "50–70 g/h"
        food_note = (
            "Mixed real food at aid stations — boiled potato, rice balls, broth, "
            "salted nut butter wraps. Sweetness fatigue is real over 6+ hours."
        )

    if distance_km >= 50.0:
        electrolyte_note = "1 capsule every 60–90 min, denser if hot or sweaty."
    else:
        electrolyte_note = "1 capsule every ~10 km."

    return {
        "estimated_duration_hours": round(estimated_hours, 1),
        "carbs_per_hour": carb_band,
        "fluid_per_hour_ml": "500–800 ml/h (more in heat)",
        "electrolytes": electrolyte_note,
        "real_food_strategy": food_note,
        "rehearsal_advice": (
            "Practise this exact fueling pattern on your longest training runs. "
            "Race day is not the place to introduce a new gel brand or food."
        ),
    }


@lru_cache(maxsize=256)
def _calculate_nutrition_needs_cached(
    weekly_km: float,
    target_distance: float,
    body_weight: float,
    is_trail: bool = False,
    target_elevation_gain_m: float = 0.0,
) -> tuple:
    """Pure function for calculating nutrition needs (cached).

    Formula: ``base_kcal = body_weight * BASE_CALORIES_PER_KG``
             ``factor = 1 + (weekly_km / 50) * 0.3 + distance_boost``
             ``daily_kcal = base_kcal * factor``

    For trail/ultra plans (``is_trail=True``) the distance boost is a
    continuous function of distance + elevation, which lets a 100-mile race
    receive a meaningful caloric uplift the road stepped formula can't
    express. Road behaviour is unchanged.
    """
    if body_weight <= 0:
        raise ValueError("body_weight must be positive")

    base_calories = body_weight * BASE_CALORIES_PER_KG
    training_factor = 1.0 + (weekly_km / TRAINING_KM_REFERENCE) * TRAINING_FACTOR_PER_REFERENCE

    if is_trail:
        training_factor += _trail_distance_boost(target_distance, target_elevation_gain_m)
    elif target_distance >= 42.2:
        training_factor += DISTANCE_BOOST_MARATHON
    elif target_distance >= 30:
        training_factor += DISTANCE_BOOST_ULTRA_TRAIL
    elif target_distance >= 21.1:
        training_factor += DISTANCE_BOOST_HALF

    daily_calories = base_calories * training_factor
    daily_protein = body_weight * PROTEIN_G_PER_KG
    daily_fiber = DAILY_FIBER_G

    return (round(daily_calories, 0), round(daily_protein, 0), daily_fiber)


class NutritionEngine:
    """Smart nutrition engine for runners focused on protein and fiber"""

    def __init__(self, random_seed: int = None):
        self._rng = random.Random(random_seed)
        self._meal_selector = MealSelector(self._rng)

    def calculate_nutrition_needs(
        self,
        weekly_km: float,
        target_distance: float,
        body_weight: float = 70,
        is_trail: bool = False,
        target_elevation_gain_m: float = 0.0,
    ) -> Dict[str, float]:
        """
        Calculate daily nutrition needs based on training load

        Args:
            weekly_km: Current weekly mileage
            target_distance: Target race distance in km (30.0 = Trail Running)
            body_weight: Athlete's weight in kg (default 70kg)
            is_trail: True for parameterized trail/ultra plans — switches to
                the continuous distance + elevation boost formula.
            target_elevation_gain_m: Total race elevation gain in m (only
                used when ``is_trail`` is True).

        Returns:
            Dictionary with daily nutrition targets
        """
        calories, protein, fiber = _calculate_nutrition_needs_cached(
            weekly_km, target_distance, body_weight,
            is_trail=is_trail,
            target_elevation_gain_m=target_elevation_gain_m,
        )

        return {
            "calories": calories,
            "protein": protein,
            "fiber": fiber,
            "fat": round(calories * 0.25 / 9, 0),
            "carbs": max(0, round((calories - (protein * 4) - (round(calories * 0.25 / 9, 0) * 9)) / 4, 0))
        }

    def generate_weekly_meal_plan(
        self,
        weekly_km: float,
        target_distance: float,
        body_weight: float = 70,
        is_trail: bool = False,
        target_elevation_gain_m: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Generate a meal blueprint with variety options

        Args:
            weekly_km: Current weekly mileage
            target_distance: Target race distance in km (30.0 = Trail Running)
            body_weight: Athlete's weight in kg
            is_trail: Forwarded to nutrition-needs calculator for trail uplift.
            target_elevation_gain_m: Total race elevation gain in m.

        Returns:
            Dictionary with meal blueprint and nutrition targets
        """
        nutrition_needs = self.calculate_nutrition_needs(
            weekly_km, target_distance, body_weight,
            is_trail=is_trail,
            target_elevation_gain_m=target_elevation_gain_m,
        )

        meal_blueprint = {
            "nutrition_targets": nutrition_needs,
            "meal_options": {},
            "general_tips": generate_general_nutrition_tips(weekly_km, target_distance),
            "hydration_guide": generate_hydration_guide(weekly_km, target_distance),
        }
        if is_trail:
            meal_blueprint["in_race_fueling"] = build_in_race_fueling_table(
                target_distance, target_elevation_gain_m,
            )

        meal_types = ["breakfast", "lunch", "dinner", "snack", "post_workout"]

        for meal_type in meal_types:
            if meal_type == "post_workout" and weekly_km < 20:
                continue

            meal_options = []
            used_meals = set()

            for i in range(4):
                selected_meal = self._meal_selector.select_varied_meal(
                    meal_type, nutrition_needs, used_meals,
                )
                if selected_meal and selected_meal["name"] not in used_meals:
                    meal_options.append(selected_meal)
                    used_meals.add(selected_meal["name"])

                if len(meal_options) >= 3:
                    break

            meal_blueprint["meal_options"][meal_type] = meal_options

        return meal_blueprint

    def generate_phased_nutrition_plan(
        self,
        plan_data: List[Dict],
        weekly_km: float,
        target_distance: float,
        body_weight_kg: float = 70.0,
        is_trail: bool = False,
        target_elevation_gain_m: float = 0.0,
    ) -> Dict[str, Any]:
        """Generate phase-specific nutrition targets for a training plan.

        Nutrition targets shift between Base, Build, Peak, and Taper phases to
        match the evolving training load.

        Args:
            plan_data:      Generated weekly plan (list of week dicts with 'phase' key)
            weekly_km:      Starting weekly mileage
            target_distance: Target race distance in km
            body_weight_kg: Athlete body weight in kg

        Returns:
            Dict mapping phase names to nutrition targets and advice
        """
        phase_weeks: Dict[str, List[int]] = {"base": [], "build": [], "peak": [], "taper": []}
        for week in plan_data:
            phase = week.get("phase", "base")
            if phase in phase_weeks:
                phase_weeks[phase].append(week["week"])
            else:
                phase_weeks["base"].append(week["week"])

        peak_km = max((w.get("total_km", weekly_km) for w in plan_data), default=weekly_km)

        phase_configs = {
            "base": {
                "km": weekly_km,
                "carb_multiplier": 1.0,
                "cal_multiplier": 1.0,
                "advice": (
                    "Your base phase focuses on building your aerobic engine. "
                    "Prioritise whole grains, lean proteins, and plenty of vegetables. "
                    "Carb intake is moderate — you're building a foundation, not fuelling a race."
                ),
            },
            "build": {
                "km": (weekly_km + peak_km) / 2,
                "carb_multiplier": 1.08,
                "cal_multiplier": 1.05,
                "advice": (
                    "Build phase brings quality sessions — your carb needs increase to fuel "
                    "tempo runs and intervals. Add an extra serving of complex carbs on hard "
                    "training days (pasta, rice, sweet potato). Protein stays high for muscle repair."
                ),
            },
            "peak": {
                "km": peak_km,
                "carb_multiplier": 1.12,
                "cal_multiplier": 1.08,
                "advice": (
                    "Peak training demands maximum fuelling. Carbs are your primary performance lever "
                    "right now. Practise your race-day nutrition strategy during long runs. "
                    "Iron, vitamin D, and omega-3s are especially important at high training loads."
                ),
            },
            "taper": {
                "km": weekly_km * 0.6,
                "carb_multiplier": 1.05,   # slightly elevated to top up glycogen
                "cal_multiplier": 0.92,    # overall calories fall with reduced volume
                "advice": (
                    "Taper phase: volume drops but don't cut carbs. Your muscles are topping up "
                    "glycogen stores for race day. In the final 2–3 days before the race, shift to "
                    "~70% carbs. Keep protein steady and stay well hydrated."
                ),
            },
        }

        result: Dict[str, Any] = {}
        for phase_name, config in phase_configs.items():
            weeks_in_phase = phase_weeks.get(phase_name, [])
            if not weeks_in_phase:
                continue

            base_needs = self.calculate_nutrition_needs(
                config["km"], target_distance, body_weight_kg,
                is_trail=is_trail,
                target_elevation_gain_m=target_elevation_gain_m,
            )

            calories = round(base_needs["calories"] * config["cal_multiplier"])
            protein = round(base_needs["protein"])   # protein unchanged between phases
            carbs = round(base_needs["carbs"] * config["carb_multiplier"])
            fat = round(calories * 0.25 / 9)

            result[phase_name] = {
                "weeks": weeks_in_phase,
                "daily_calories": calories,
                "protein_g": protein,
                "carbs_g": carbs,
                "fats_g": fat,
                "advice": config["advice"],
            }

        return result
