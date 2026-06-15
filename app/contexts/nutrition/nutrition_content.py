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


def generate_trail_fuel_ideas() -> List[Dict[str, Any]]:
    """Portable, trail-ready fuel ideas for long runs and race day.

    Curated real-food options that travel well in a vest and stay palatable
    over many hours, when sweet gels start to turn the stomach. Each entry
    carries an approximate carb count and a category so the UI can group
    sweet, savoury and drink options. Carb figures are per-piece estimates
    for a typical home recipe — treat them as a starting point, not gospel.
    """
    return [
        {
            "name": "Date & cocoa trail balls",
            "category": "sweet",
            "carbs": "~25 g each",
            "note": (
                "Blended dates, oats and cocoa rolled into bite-size balls. "
                "Soft, easy to chew on the move, and a clean source of carbs."
            ),
        },
        {
            "name": "Salted maple rice cakes",
            "category": "sweet",
            "carbs": "~30 g each",
            "note": (
                "Sticky rice pressed with maple syrup and a pinch of salt. "
                "Gentle on the gut and a welcome change from gels."
            ),
        },
        {
            "name": "Peanut butter & honey pinwheels",
            "category": "sweet",
            "carbs": "~20 g each",
            "note": (
                "A thin tortilla spread with PB and honey, rolled and sliced. "
                "Adds a little fat and protein for slower-burning energy."
            ),
        },
        {
            "name": "Salted banana bread bites",
            "category": "sweet",
            "carbs": "~22 g each",
            "note": (
                "Dense banana bread cut into cubes with extra salt baked in. "
                "Real food that still feels like a treat deep into a long run."
            ),
        },
        {
            "name": "Apricot & almond energy bars",
            "category": "sweet",
            "carbs": "~28 g each",
            "note": (
                "No-bake bars of dried apricot, almonds and oats. Hold their "
                "shape in a hot vest pocket and pack a lot of carbs per gram."
            ),
        },
        {
            "name": "Salty boiled potato bites",
            "category": "savoury",
            "carbs": "~15 g each",
            "note": (
                "Small boiled potatoes rolled in salt. The classic ultra "
                "savoury swap once sweetness fatigue sets in around hour four."
            ),
        },
        {
            "name": "Savoury mini wraps",
            "category": "savoury",
            "carbs": "~25 g each",
            "note": (
                "Small wraps with salted nut butter or a little cheese. Save "
                "these for the back half when you can't face another gel."
            ),
        },
        {
            "name": "Homemade sports drink",
            "category": "drink",
            "carbs": "~60 g per bottle",
            "note": (
                "Water, ~60 g sugar, a pinch of salt and a squeeze of lemon. "
                "One bottle per hour alongside solid food covers fluid, carbs "
                "and some sodium in a single flask."
            ),
        },
        {
            "name": "Maple espresso gel",
            "category": "drink",
            "carbs": "~25 g each",
            "note": (
                "Maple syrup with a shot of espresso and a pinch of salt. A "
                "homemade caffeinated option — save it for the race's second "
                "half and rehearse the dose in training first."
            ),
        },
    ]


def generate_trail_nutrition_tips() -> List[str]:
    """Trail- and ultra-specific fuelling golden rules.

    Higher-level strategy that complements the daily macros and the in-race
    fuelling table: gut training, sodium, caffeine timing and the hard-won
    race-day rules that keep runners moving when sweet fuel stops working.
    """
    return [
        "Train your gut like a muscle — practise 60–90 g of carbs per hour on "
        "your long runs for weeks before race day, not just once.",
        "Nothing new on race day: every gel, bar and home recipe should be "
        "tested on training runs first.",
        "In the heat or on efforts over four hours, aim for roughly "
        "300–600 mg of sodium per hour to stay ahead of cramps.",
        "Save caffeine for the second half — about 2–3 mg per kg of body "
        "weight, and rehearse the dose in training.",
        "Eat before you decide: most dark patches after two hours are a "
        "calorie deficit talking, not your legs giving up.",
        "Switch to savoury food when sweet fuel turns your stomach — usually "
        "somewhere around hour four.",
        "Walk the aid stations with purpose rather than stopping dead; it "
        "keeps the legs moving and the gut settled.",
        "Soft flasks beat a bladder for trail — you can see what's left and "
        "refill them fast at aid stations.",
    ]
