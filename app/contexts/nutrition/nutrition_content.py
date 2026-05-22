"""Static nutrition content: tips and hydration guidelines."""

from typing import Any, Dict, List


def generate_general_nutrition_tips(
    weekly_km: float, target_distance: float
) -> List[str]:
    """Generate general nutrition tips for the training plan."""
    tips = [
        "Focus on whole foods and minimize processed items",
        "Time your meals to optimize training performance and recovery",
        "Stay hydrated throughout the day, not just during runs",
        "Include a variety of colorful vegetables for micronutrients",
    ]

    if weekly_km >= 50:
        tips.extend(
            [
                "Increase carbohydrate intake to fuel high mileage",
                "Pay attention to electrolyte balance, especially sodium",
                "Consider timing protein intake around key workouts",
            ]
        )
    elif weekly_km >= 30:
        tips.extend(
            [
                "Balance macronutrients based on training intensity",
                "Focus on recovery nutrition after hard sessions",
            ]
        )
    else:
        tips.extend(
            [
                "Build a solid nutritional foundation with quality foods",
                "Practice fueling strategies during longer runs",
            ]
        )

    if target_distance >= 42.2:
        tips.extend(
            [
                "Practice race day nutrition during long training runs",
                "Focus on iron-rich foods to support endurance training",
                "Test different fueling options to find what works for you",
            ]
        )
    elif target_distance >= 30:
        tips.extend(
            [
                "Practice nutrition on technical terrain and elevation changes",
                "Focus on portable, lightweight fueling options",
                "Include electrolyte-rich foods for trail conditions",
            ]
        )
    elif target_distance >= 21.1:
        tips.extend(
            [
                "Pay attention to pre-run fueling for quality sessions",
                "Include post-workout protein to support muscle repair",
            ]
        )

    return tips[:6]


def generate_hydration_guide(
    weekly_km: float, target_distance: float
) -> Dict[str, Any]:
    """Generate hydration guidelines."""
    base_daily = 2000
    training_addition = min(1500, weekly_km * 15)

    race_day_target = "300-500ml per hour"
    long_run_target = "200-400ml per hour"

    if target_distance >= 42.2:
        race_day_target = "500-750ml per hour, with electrolytes"
        long_run_target = "400-600ml per hour"
    elif target_distance >= 30:
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
            "Recovery starts with proper rehydration",
        ],
    }
