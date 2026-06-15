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


# Race-phase metadata for grouping trail fuel in the UI. Order matters —
# the template renders phases in this sequence (the natural race timeline).
TRAIL_FUEL_PHASES: List[Dict[str, str]] = [
    {
        "key": "before",
        "label": "Before",
        "blurb": "Carb-loading the night before and topping up race morning.",
    },
    {
        "key": "during",
        "label": "During",
        "blurb": "Portable fuel that travels in a vest and stays easy to stomach.",
    },
    {
        "key": "after",
        "label": "After",
        "blurb": "Recovery fuel to refill glycogen and repair within the hour.",
    },
]


def generate_trail_fuel_ideas() -> List[Dict[str, Any]]:
    """Portable, trail-ready fuel ideas across the race timeline.

    Curated real-food options spanning the night before, the race itself and
    recovery. Each entry carries a ``phase`` (before / during / after) so the
    UI can group ideas by *when* you eat them, an approximate carb count, and
    a ``category`` (sweet / savoury / drink) used as a badge. Carb figures are
    per-serving estimates for a typical home recipe — a starting point, not
    gospel.
    """
    return [
        # --- Before: carb-load + race morning -------------------------------
        {
            "name": "Tomato rice, carb-load edition",
            "phase": "before",
            "category": "savoury",
            "carbs": "~70 g per bowl",
            "note": (
                "A slightly soupy tomato rice the night before. Easy to digest "
                "and tops up glycogen without sitting heavy."
            ),
        },
        {
            "name": "Beetroot & feta pre-race rice",
            "phase": "before",
            "category": "savoury",
            "carbs": "~65 g per bowl",
            "note": (
                "Nitrate-rich beetroot stirred through rice the night before — "
                "carbs plus a small endurance edge from the beets."
            ),
        },
        {
            "name": "Race-morning overnight oats",
            "phase": "before",
            "category": "sweet",
            "carbs": "~60 g per bowl",
            "note": (
                "Mixed the night before so there's nothing to cook at 4 a.m. "
                "Eat 2.5–3 hours before the start to settle the gut."
            ),
        },
        {
            "name": "Honey & salt toast",
            "phase": "before",
            "category": "sweet",
            "carbs": "~40 g per serving",
            "note": (
                "Quick race-morning carbs with a little salt; add banana "
                "slices if you can stomach more. Simple and reliable."
            ),
        },
        # --- During: on the move --------------------------------------------
        {
            "name": "Date & cocoa trail balls",
            "phase": "during",
            "category": "sweet",
            "carbs": "~25 g each",
            "note": (
                "Blended dates, oats and cocoa rolled into bite-size balls. "
                "Soft, easy to chew on the move, and a clean source of carbs."
            ),
        },
        {
            "name": "Salted maple rice cakes",
            "phase": "during",
            "category": "sweet",
            "carbs": "~30 g each",
            "note": (
                "Sticky rice pressed with maple syrup and a pinch of salt. "
                "Gentle on the gut and a welcome change from gels."
            ),
        },
        {
            "name": "Peanut butter & honey pinwheels",
            "phase": "during",
            "category": "sweet",
            "carbs": "~20 g each",
            "note": (
                "A thin tortilla spread with PB and honey, rolled and sliced. "
                "Adds a little fat and protein for slower-burning energy."
            ),
        },
        {
            "name": "Salted banana bread bites",
            "phase": "during",
            "category": "sweet",
            "carbs": "~22 g each",
            "note": (
                "Dense banana bread cut into cubes with extra salt baked in. "
                "Real food that still feels like a treat deep into a long run."
            ),
        },
        {
            "name": "Apricot & almond energy bars",
            "phase": "during",
            "category": "sweet",
            "carbs": "~28 g each",
            "note": (
                "No-bake bars of dried apricot, almonds and oats. Hold their "
                "shape in a hot vest pocket and pack a lot of carbs per gram."
            ),
        },
        {
            "name": "Salty boiled potato bites",
            "phase": "during",
            "category": "savoury",
            "carbs": "~15 g each",
            "note": (
                "Small boiled potatoes rolled in salt. The classic ultra "
                "savoury swap once sweetness fatigue sets in around hour four."
            ),
        },
        {
            "name": "Savoury mini wraps",
            "phase": "during",
            "category": "savoury",
            "carbs": "~25 g each",
            "note": (
                "Small wraps with salted nut butter or a little cheese. Save "
                "these for the back half when you can't face another gel."
            ),
        },
        {
            "name": "Homemade sports drink",
            "phase": "during",
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
            "phase": "during",
            "category": "drink",
            "carbs": "~25 g each",
            "note": (
                "Maple syrup with a shot of espresso and a pinch of salt. A "
                "homemade caffeinated option — save it for the race's second "
                "half and rehearse the dose in training first."
            ),
        },
        # --- After: recovery ------------------------------------------------
        {
            "name": "Recovery smoothie",
            "phase": "after",
            "category": "drink",
            "carbs": "~50 g per glass",
            "note": (
                "Roughly a 3:1 carbs-to-protein blend within ~45 minutes of "
                "finishing — milk or yoghurt, banana, oats and berries."
            ),
        },
        {
            "name": "Protein rice pudding",
            "phase": "after",
            "category": "sweet",
            "carbs": "~55 g per bowl",
            "note": (
                "A warm recovery dessert that pairs comforting carbs with "
                "protein when a cold smoothie doesn't appeal post-race."
            ),
        },
        {
            "name": "Cottage cheese & berry bowl",
            "phase": "after",
            "category": "sweet",
            "carbs": "~25 g per bowl",
            "note": (
                "Slow-digesting casein with berries before bed — supports "
                "overnight repair after a long day on the trails."
            ),
        },
    ]


def generate_trail_nutrition_tips() -> List[Dict[str, str]]:
    """Trail- and ultra-specific fuelling golden rules, tagged by topic.

    Higher-level strategy that complements the daily macros and the in-race
    fuelling table: gut training, sodium, caffeine timing and the hard-won
    race-day rules that keep runners moving when sweet fuel stops working.
    Each tip carries a ``topic`` so the UI can offer filter chips.
    """
    return [
        {
            "topic": "Fueling",
            "text": (
                "Train your gut like a muscle — practise 60–90 g of carbs per "
                "hour on your long runs for weeks before race day, not once."
            ),
        },
        {
            "topic": "Strategy",
            "text": (
                "Nothing new on race day: every gel, bar and home recipe should "
                "be tested on training runs first."
            ),
        },
        {
            "topic": "Sodium",
            "text": (
                "In the heat or on efforts over four hours, aim for roughly "
                "300–600 mg of sodium per hour to stay ahead of cramps."
            ),
        },
        {
            "topic": "Caffeine",
            "text": (
                "Save caffeine for the second half — about 2–3 mg per kg of "
                "body weight, and rehearse the dose in training."
            ),
        },
        {
            "topic": "Mind",
            "text": (
                "Eat before you decide: most dark patches after two hours are a "
                "calorie deficit talking, not your legs giving up."
            ),
        },
        {
            "topic": "Fueling",
            "text": (
                "Switch to savoury food when sweet fuel turns your stomach — "
                "usually somewhere around hour four."
            ),
        },
        {
            "topic": "Strategy",
            "text": (
                "Walk the aid stations with purpose rather than stopping dead; "
                "it keeps the legs moving and the gut settled."
            ),
        },
        {
            "topic": "Gear",
            "text": (
                "Soft flasks beat a bladder for trail — you can see what's left "
                "and refill them fast at aid stations."
            ),
        },
        {
            "topic": "Heat",
            "text": (
                "Use ice like fuel on hot days: stash it at aid stations to "
                "cool your core and reset before the next climb."
            ),
        },
        {
            "topic": "Fueling",
            "text": (
                "Start eating before the big climbs, while your stomach is calm "
                "— it's harder to take food in once the effort spikes."
            ),
        },
        {
            "topic": "Recovery",
            "text": (
                "Get a 3:1 carb-to-protein hit in within ~45 minutes of "
                "finishing to kick-start glycogen and muscle repair."
            ),
        },
        {
            "topic": "Recovery",
            "text": (
                "Move, don't stretch, after a race — easy walking beats static "
                "stretching for quads battered by long descents."
            ),
        },
        {
            "topic": "Gear",
            "text": (
                "Anti-chafe balm is mandatory kit: apply before long runs, not "
                "after the hotspots have already started."
            ),
        },
    ]
