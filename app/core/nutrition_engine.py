from typing import List, Dict, Any, Optional
import random
import json
from functools import lru_cache
from app.meal_database import get_meal_database


@lru_cache(maxsize=256)
def _calculate_nutrition_needs_cached(
    weekly_km: float,
    target_distance: float,
    body_weight: float
) -> tuple:
    """Pure function for calculating nutrition needs (cached)."""
    base_calories = body_weight * 22

    training_factor = 1.0 + (weekly_km / 50) * 0.3

    if target_distance >= 42.2:
        training_factor += 0.1
    elif target_distance >= 30:
        training_factor += 0.1
    elif target_distance >= 21.1:
        training_factor += 0.05

    daily_calories = base_calories * training_factor
    daily_protein = body_weight * 1.8
    daily_fiber = 35

    return (round(daily_calories, 0), round(daily_protein, 0), daily_fiber)


class NutritionEngine:
    """Smart nutrition engine for runners focused on protein and fiber"""

    def __init__(self, random_seed: int = None):
        self.meal_db = get_meal_database()
        if random_seed is not None:
            random.seed(random_seed)

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
            "carbs": round((calories - (protein * 4) - (fiber * 2)) / 4, 0),
            "fat": round(calories * 0.25 / 9, 0)
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
    
    def _generate_daily_meal_plan(self, day: int, nutrition_needs: Dict[str, float], weekly_km: float, target_distance: float) -> Dict[str, Any]:
        """Generate meal plan for a specific day"""
        
        # Adjust nutrition based on training day
        day_adjustments = self._get_training_day_adjustments(day, weekly_km, target_distance)
        adjusted_needs = nutrition_needs.copy()
        
        for key, adjustment in day_adjustments.items():
            adjusted_needs[key] = round(adjusted_needs[key] * adjustment, 0)
        
        # Generate meal plan
        daily_plan = {
            "day": day,
            "nutrition_targets": adjusted_needs,
            "meals": {},
            "daily_totals": {"calories": 0, "protein": 0, "fiber": 0, "carbs": 0, "fat": 0},
            "nutrition_tips": self._generate_daily_nutrition_tips(day, weekly_km, target_distance)
        }
        
        # Select meals for each meal type
        meal_types = ["breakfast", "lunch", "dinner", "snack", "post_workout"]
        
        for meal_type in meal_types:
            # Skip post_workout on rest days
            if meal_type == "post_workout" and self._is_rest_day(day, weekly_km):
                continue
                
            selected_meal = self._select_optimal_meal(meal_type, adjusted_needs, daily_plan["daily_totals"])
            if selected_meal:
                daily_plan["meals"][meal_type] = selected_meal
                # Update daily totals
                for nutrient in ["calories", "protein", "fiber", "carbs", "fat"]:
                    daily_plan["daily_totals"][nutrient] += selected_meal[nutrient]
        
        return daily_plan
    
    def _get_training_day_adjustments(self, day: int, weekly_km: float, target_distance: float) -> Dict[str, float]:
        """Get nutrition adjustments based on training day type"""
        
        # Determine day type based on weekly structure
        if day in [1, 3, 5]:  # Moderate training days
            return {"calories": 1.0, "protein": 1.0, "fiber": 1.0}
        elif day in [2, 4]:  # Hard training days (intervals, tempo)
            return {"calories": 1.15, "protein": 1.1, "fiber": 1.0}
        elif day == 6:  # Long run day
            return {"calories": 1.2, "protein": 1.15, "fiber": 1.1}
        else:  # Rest day (day 7)
            return {"calories": 0.9, "protein": 0.95, "fiber": 1.0}
    
    def _is_rest_day(self, day: int, weekly_km: float) -> bool:
        """Determine if this is a rest day"""
        return day == 7  # Sunday as rest day
    
    def _select_optimal_meal(self, meal_type: str, nutrition_needs: Dict[str, float], current_totals: Dict[str, float], force_random: bool = False) -> Optional[Dict[str, Any]]:
        """Select the optimal meal based on nutritional needs and current totals"""
        
        available_meals = self.meal_db.get_meals_by_type(meal_type)
        if not available_meals:
            return None
        
        # Score meals based on how well they fit remaining nutritional needs
        scored_meals = []
        remaining_needs = {
            "calories": nutrition_needs["calories"] - current_totals["calories"],
            "protein": nutrition_needs["protein"] - current_totals["protein"],
            "fiber": nutrition_needs["fiber"] - current_totals["fiber"]
        }
        
        for meal in available_meals:
            score = 0
            
            # Protein scoring (most important)
            if remaining_needs["protein"] > 0:
                protein_ratio = min(meal["protein"] / remaining_needs["protein"], 1.0)
                score += protein_ratio * 3
            
            # Fiber scoring
            if remaining_needs["fiber"] > 0:
                fiber_ratio = min(meal["fiber"] / remaining_needs["fiber"], 1.0)
                score += fiber_ratio * 2
            
            # Calorie scoring
            if remaining_needs["calories"] > 0:
                calorie_ratio = min(meal["calories"] / remaining_needs["calories"], 1.0)
                score += calorie_ratio * 1
            
            # Bonus for high protein meals
            if meal["protein"] >= 25:
                score += 1
            
            # Bonus for high fiber meals
            if meal["fiber"] >= 10:
                score += 1
            
            # Add randomness factor for variety
            if force_random:
                score += random.uniform(-2, 2)  # Add random variation
            
            scored_meals.append((score, meal))
        
        # Select meal with more randomness when forced
        if scored_meals:
            scored_meals.sort(key=lambda x: x[0], reverse=True)
            
            if force_random:
                # Select from top 5 meals with more randomness
                top_meals = scored_meals[:min(5, len(scored_meals))]
                # Weight towards top but allow lower-ranked meals
                weights = [3, 2.5, 2, 1.5, 1][:len(top_meals)]
                selected = random.choices(top_meals, weights=weights)[0][1]
            else:
                # Select from top 3 meals for normal variety
                top_meals = scored_meals[:min(3, len(scored_meals))]
                selected = random.choice(top_meals)[1]
            
            return selected
        
        return None
    
    def generate_randomized_daily_plan(self, day: int, nutrition_needs: Dict[str, float], weekly_km: float, target_distance: float) -> Dict[str, Any]:
        """Generate a daily meal plan with forced randomization"""
        
        daily_plan = {
            "day": day,
            "nutrition_targets": nutrition_needs,
            "meals": {},
            "daily_totals": {"calories": 0, "protein": 0, "fiber": 0, "carbs": 0, "fat": 0},
            "nutrition_tips": self._generate_daily_nutrition_tips(day, weekly_km, target_distance)
        }
        
        # Select meals for each meal type with forced randomization
        meal_types = ["breakfast", "lunch", "dinner", "snack", "post_workout"]
        
        for meal_type in meal_types:
            # Skip post_workout on rest days
            if meal_type == "post_workout" and self._is_rest_day(day, weekly_km):
                continue
                
            selected_meal = self._select_optimal_meal(meal_type, nutrition_needs, daily_plan["daily_totals"], force_random=True)
            if selected_meal:
                daily_plan["meals"][meal_type] = selected_meal
                # Update daily totals
                for nutrient in ["calories", "protein", "fiber", "carbs", "fat"]:
                    daily_plan["daily_totals"][nutrient] += selected_meal[nutrient]
        
        return daily_plan
    
    def _generate_daily_nutrition_tips(self, day: int, weekly_km: float, target_distance: float) -> List[str]:
        """Generate nutrition tips for the day"""
        
        tips = []
        
        # Day-specific tips
        if day == 6:  # Long run day
            tips.extend([
                "Carb-load the night before with whole grains and sweet potatoes",
                "Pre-run breakfast: Focus on easily digestible carbs",
                "During long run: Take in 30-60g carbs per hour after 60 minutes",
                "Post-run recovery: Protein and carbs within 30 minutes"
            ])
        elif day == 7:  # Rest day
            tips.extend([
                "Focus on protein for muscle repair and recovery",
                "Include antioxidant-rich foods to reduce inflammation",
                "Stay well-hydrated throughout the day",
                "Light, nutrient-dense meals to support recovery"
            ])
        elif day in [2, 4]:  # Hard workout days
            tips.extend([
                "Pre-workout fuel: Complex carbs 2-3 hours before training",
                "Hydration is key for intense sessions",
                "Post-workout: Include 20-30g protein for muscle repair",
                "Consider beet juice or nitrate-rich foods for performance"
            ])
        else:  # Moderate training days
            tips.extend([
                "Balanced meals with protein, complex carbs, and vegetables",
                "Focus on whole foods and consistent meal timing",
                "Include healthy fats for hormone production",
                "Fiber-rich foods for sustained energy release"
            ])
        
        # Distance-specific tips
        if target_distance >= 42.2:  # Marathon
            tips.extend([
                "Practice race day nutrition during long runs",
                "Include iron-rich foods to prevent deficiency",
                "Consider electrolyte balance, especially sodium"
            ])
        elif target_distance >= 30:  # 30K / Trail running
            tips.extend([
                "Practice nutrition on varied terrain and longer durations",
                "Focus on electrolyte balance for trail conditions",
                "Include portable, lightweight nutrition options"
            ])
        elif target_distance >= 21.1:  # Half marathon
            tips.extend([
                "Test different fueling strategies during long runs",
                "Focus on glycogen replenishment after hard workouts"
            ])
        
        # General tips
        general_tips = [
            "Aim for a rainbow of vegetables for micronutrients",
            "Include probiotic foods for gut health",
            "Time your meals to optimize training performance",
            "Listen to your body's hunger and fullness cues"
        ]
        
        # Add 1-2 general tips
        tips.extend(random.sample(general_tips, min(2, len(general_tips))))
        
        return tips[:4]  # Return max 4 tips
    
    def get_meal_suggestions(self, meal_type: str, dietary_preferences: List[str] = None) -> List[Dict[str, Any]]:
        """Get meal suggestions based on type and preferences"""
        
        available_meals = self.meal_db.get_meals_by_type(meal_type)
        
        if dietary_preferences:
            # Filter by dietary preferences
            filtered_meals = []
            for meal in available_meals:
                meal_tags = json.loads(meal["dietary_tags"])
                if any(pref in meal_tags for pref in dietary_preferences):
                    filtered_meals.append(meal)
            available_meals = filtered_meals
        
        # Sort by protein and fiber content
        available_meals.sort(key=lambda x: (x["protein"] + x["fiber"]), reverse=True)
        
        return available_meals[:5]  # Return top 5 suggestions
    
    def calculate_daily_nutrition_summary(self, daily_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate nutrition summary for a daily plan"""
        
        totals = {"calories": 0, "protein": 0, "fiber": 0, "carbs": 0, "fat": 0}
        meal_count = 0
        
        for meal in daily_plan["meals"].values():
            for nutrient in totals:
                totals[nutrient] += meal[nutrient]
            meal_count += 1
        
        # Calculate percentages of targets
        targets = daily_plan["nutrition_targets"]
        percentages = {}
        for nutrient in totals:
            if targets[nutrient] > 0:
                percentages[nutrient] = round((totals[nutrient] / targets[nutrient]) * 100, 0)
            else:
                percentages[nutrient] = 0
        
        return {
            "totals": totals,
            "percentages": percentages,
            "meal_count": meal_count,
            "targets_met": all(80 <= pct <= 120 for pct in percentages.values())
        }
    
    def _select_varied_meal(self, meal_type: str, nutrition_needs: Dict[str, float], used_meals: set) -> Optional[Dict[str, Any]]:
        """Select a meal with emphasis on variety from already used meals"""

        available_meals = self.meal_db.get_meals_by_type(meal_type)

        # Filter out already used meals
        remaining_meals = [meal for meal in available_meals if meal["name"] not in used_meals]

        # If we've used most meals, allow some repeats but with lower priority
        if len(remaining_meals) < 2:
            remaining_meals = available_meals

        # Shuffle the available meals first to add randomness
        random.shuffle(remaining_meals)

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

            # MUCH more randomness to ensure different meals each time
            # Random bonus now dominates the selection (0-50 range)
            score += random.uniform(0, 50)

            scored_meals.append((score, meal))

        if scored_meals:
            scored_meals.sort(key=lambda x: x[0], reverse=True)
            # Select randomly from top options with weighted probability
            top_meals = scored_meals[:min(8, len(scored_meals))]
            # Use weighted random to favor top scores but allow variety
            weights = [8, 7, 6, 5, 4, 3, 2, 1][:len(top_meals)]
            selected = random.choices(top_meals, weights=weights)[0][1]
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