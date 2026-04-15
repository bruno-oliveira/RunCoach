from typing import List, Dict, Any, Optional
import random
from functools import lru_cache
from app.core.nutrition.meal_database import get_meal_database


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


@lru_cache(maxsize=256)
def _calculate_nutrition_needs_cached(
    weekly_km: float,
    target_distance: float,
    body_weight: float
) -> tuple:
    """Pure function for calculating nutrition needs (cached).

    Formula: ``base_kcal = body_weight * BASE_CALORIES_PER_KG``
             ``factor = 1 + (weekly_km / 50) * 0.3 + distance_boost``
             ``daily_kcal = base_kcal * factor``
    See module constants for the rationale behind each coefficient.
    """
    if body_weight <= 0:
        raise ValueError("body_weight must be positive")

    base_calories = body_weight * BASE_CALORIES_PER_KG
    training_factor = 1.0 + (weekly_km / TRAINING_KM_REFERENCE) * TRAINING_FACTOR_PER_REFERENCE

    if target_distance >= 42.2:
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
        self.meal_db = get_meal_database()
        self._rng = random.Random(random_seed)

    def calculate_nutrition_needs(self, weekly_km: float, target_distance: float, body_weight: float = 70) -> Dict[str, float]:
        """
        Calculate daily nutrition needs based on training load

        Args:
            weekly_km: Current weekly mileage
            target_distance: Target race distance in km (30.0 = Trail Running)
            body_weight: Athlete's weight in kg (default 70kg)

        Returns:
            Dictionary with daily nutrition targets
        """
        calories, protein, fiber = _calculate_nutrition_needs_cached(
            weekly_km, target_distance, body_weight
        )

        return {
            "calories": calories,
            "protein": protein,
            "fiber": fiber,
            "fat": round(calories * 0.25 / 9, 0),
            "carbs": max(0, round((calories - (protein * 4) - (round(calories * 0.25 / 9, 0) * 9)) / 4, 0))
        }
    
    def generate_weekly_meal_plan(self, weekly_km: float, target_distance: float, body_weight: float = 70) -> Dict[str, Any]:
        """
        Generate a meal blueprint with variety options

        Args:
            weekly_km: Current weekly mileage
            target_distance: Target race distance in km (30.0 = Trail Running)
            body_weight: Athlete's weight in kg

        Returns:
            Dictionary with meal blueprint and nutrition targets
        """
        nutrition_needs = self.calculate_nutrition_needs(weekly_km, target_distance, body_weight)
        
        # Generate meal blueprint with multiple options per meal type
        meal_blueprint = {
            "nutrition_targets": nutrition_needs,
            "meal_options": {},
            "general_tips": self._generate_general_nutrition_tips(weekly_km, target_distance),
            "hydration_guide": self._generate_hydration_guide(weekly_km, target_distance)
        }
        
        # Generate 3-4 different options for each meal type
        meal_types = ["breakfast", "lunch", "dinner", "snack", "post_workout"]
        
        for meal_type in meal_types:
            # Skip post_workout for low intensity plans
            if meal_type == "post_workout" and weekly_km < 20:
                continue
                
            meal_options = []
            used_meals = set()
            
            # Generate 3-4 different options with variety
            for i in range(4):
                selected_meal = self._select_varied_meal(meal_type, nutrition_needs, used_meals)
                if selected_meal and selected_meal["name"] not in used_meals:
                    meal_options.append(selected_meal)
                    used_meals.add(selected_meal["name"])
                    
                # Stop if we have 3 good options
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
        # Determine which weeks belong to each phase
        phase_weeks: Dict[str, List[int]] = {"base": [], "build": [], "peak": [], "taper": []}
        for week in plan_data:
            phase = week.get("phase", "base")
            if phase in phase_weeks:
                phase_weeks[phase].append(week["week"])
            else:
                # Unrecognized phase (e.g. "beginner") — treat as base
                phase_weeks["base"].append(week["week"])

        # Calculate peak mileage from plan data for build/peak phases
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
                config["km"], target_distance, body_weight_kg
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

    def _select_varied_meal(self, meal_type: str, nutrition_needs: Dict[str, float], used_meals: set) -> Optional[Dict[str, Any]]:
        """Select a meal with emphasis on variety from already used meals"""

        available_meals = self.meal_db.get_meals_by_type(meal_type)

        # Filter out already used meals
        remaining_meals = [meal for meal in available_meals if meal["name"] not in used_meals]

        # If we've used most meals, allow some repeats but with lower priority
        if len(remaining_meals) < 2:
            remaining_meals = available_meals

        # Shuffle the available meals first to add randomness
        self._rng.shuffle(remaining_meals)

        # Score meals with MUCH stronger randomness to ensure variety
        scored_meals = []
        for meal in remaining_meals:
            score = 0

            # Reduced nutritional scoring weight to allow more variety
            for nutrient in ["protein", "fiber"]:
                if meal[nutrient] > 0:
                    # Scale down nutritional scores significantly
                    score += meal[nutrient] * (0.3 if nutrient == "protein" else 0.2)

            # Stronger variety bonus for meals not used before
            if meal["name"] not in used_meals:
                score += 10
            else:
                score -= 20  # Stronger penalty for already used meals

            # Add randomness for variety without dominating nutritional scores
            score += self._rng.uniform(0, 15)

            scored_meals.append((score, meal))

        if scored_meals:
            scored_meals.sort(key=lambda x: x[0], reverse=True)
            # Select randomly from top options with weighted probability
            top_meals = scored_meals[:min(8, len(scored_meals))]
            # Use weighted random to favor top scores but allow variety
            weights = [8, 7, 6, 5, 4, 3, 2, 1][:len(top_meals)]
            selected = self._rng.choices(top_meals, weights=weights)[0][1]
            return selected

        return None
    
    def _generate_general_nutrition_tips(self, weekly_km: float, target_distance: float) -> List[str]:
        """Generate general nutrition tips for the training plan"""
        
        tips = []
        
        # Base tips for all runners
        tips.extend([
            "Focus on whole foods and minimize processed items",
            "Time your meals to optimize training performance and recovery",
            "Stay hydrated throughout the day, not just during runs",
            "Include a variety of colorful vegetables for micronutrients"
        ])
        
        # Training volume tips
        if weekly_km >= 50:
            tips.extend([
                "Increase carbohydrate intake to fuel high mileage",
                "Pay attention to electrolyte balance, especially sodium",
                "Consider timing protein intake around key workouts"
            ])
        elif weekly_km >= 30:
            tips.extend([
                "Balance macronutrients based on training intensity",
                "Focus on recovery nutrition after hard sessions"
            ])
        else:
            tips.extend([
                "Build a solid nutritional foundation with quality foods",
                "Practice fueling strategies during longer runs"
            ])
        
        # Distance-specific tips
        if target_distance >= 42.2:
            tips.extend([
                "Practice race day nutrition during long training runs",
                "Focus on iron-rich foods to support endurance training",
                "Test different fueling options to find what works for you"
            ])
        elif target_distance >= 30:  # 30K / Trail running
            tips.extend([
                "Practice nutrition on technical terrain and elevation changes",
                "Focus on portable, lightweight fueling options",
                "Include electrolyte-rich foods for trail conditions"
            ])
        elif target_distance >= 21.1:
            tips.extend([
                "Pay attention to pre-run fueling for quality sessions",
                "Include post-workout protein to support muscle repair"
            ])
        
        return tips[:6]  # Return max 6 tips
    
    def _generate_hydration_guide(self, weekly_km: float, target_distance: float) -> Dict[str, Any]:
        """Generate hydration guidelines"""

        base_daily = 2000  # ml base daily hydration

        # Adjust for training volume
        training_addition = min(1500, weekly_km * 15)  # Add 15ml per km run

        # Race-specific adjustments
        race_day_target = "300-500ml per hour"  # Default
        long_run_target = "200-400ml per hour"   # Default

        if target_distance >= 42.2:
            race_day_target = "500-750ml per hour, with electrolytes"
            long_run_target = "400-600ml per hour"
        elif target_distance >= 30:  # 30K / Trail running
            race_day_target = "600-800ml per hour, with electrolytes"
            long_run_target = "500-700ml per hour"
        elif target_distance >= 21.1:
            race_day_target = "400-600ml per hour"
        
        return {
            "daily_target": f"{base_daily + training_addition}ml",
            "pre_run": "300-500ml, 2 hours before",
            "during_run": long_run_target,
            "post_run": "150% of fluid lost during exercise",
            "race_day": race_day_target,
            "electrolytes": weekly_km >= 30,
            "tips": [
                "Monitor urine color as a hydration indicator",
                "Include sodium in fluids for runs over 60 minutes",
                "Recovery starts with proper rehydration"
            ]
        }