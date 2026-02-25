"""Race-day protocol generator.

Produces a structured race-day guide covering:
- Week-before checklist
- Race-morning timeline
- Km-by-km pacing splits
- Nutrition & hydration timing
- Mental checkpoints
"""

import math
from typing import Any, Dict, List, Optional


# Distance display names
_DIST_NAMES = {
    5.0: "5K",
    10.0: "10K",
    21.1: "Half Marathon",
    30.0: "30K Trail",
    42.2: "Marathon",
}

# Pacing strategy text per distance
_PACING_STRATEGY = {
    5.0: (
        "Start 3–5 sec/km slower than goal pace for the first 1 km to avoid blowing up. "
        "Settle into goal pace by km 2. Give everything in the final km. "
        "A 5K is an aerobic sprint — controlled aggression from the gun."
    ),
    10.0: (
        "First 2 km: run goal pace minus 3–5 sec/km. "
        "Km 3–8: lock into goal pace and hold it. "
        "Final 2 km: dig in — if you have anything left, use it now. "
        "The 10K rewards patience in the first half."
    ),
    21.1: (
        "First 5 km: goal pace minus 5–8 sec/km — resist the crowd. "
        "Km 5–16: settle into goal pace, focus on smooth, relaxed running. "
        "Km 16–21: the real race begins — draw on your training and execute. "
        "Negative splits (faster second half) produce the best results."
    ),
    30.0: (
        "Trail racing requires effort-based pacing, not pace-based pacing. "
        "Climb hills with power hiking if needed — it's often faster than running uphill. "
        "Run descents confidently — this is where time is made on trails. "
        "Eat and drink earlier than you think you need to."
    ),
    42.2: (
        "First 10 km: goal pace minus 5–10 sec/km — the hardest discipline in marathon running. "
        "Km 10–30: goal pace. Focus on fueling, staying relaxed, keeping form. "
        "Km 30–40: this is where your training weeks show. Push through. "
        "Final 2.2 km: leave nothing behind."
    ),
}

# Nutrition timing per distance
_NUTRITION = {
    5.0: [
        {"icon": "🍌", "when": "2–3 hrs before", "what": "Light carb meal (toast, banana, oats)"},
        {"icon": "💧", "when": "30 min before", "what": "200–300 ml water"},
        {"icon": "🏃", "when": "During race", "what": "No fueling needed for most runners"},
        {"icon": "🍫", "when": "Immediately after", "what": "Simple carbs + protein within 30 min"},
    ],
    10.0: [
        {"icon": "🍌", "when": "2–3 hrs before", "what": "Light carb meal (toast, banana, oats)"},
        {"icon": "💧", "when": "30 min before", "what": "200–300 ml water"},
        {"icon": "💧", "when": "At 5 km", "what": "Water at aid station (hot day: take it)"},
        {"icon": "🍫", "when": "Within 30 min after", "what": "Protein + carbs for recovery"},
    ],
    21.1: [
        {"icon": "🍌", "when": "3 hrs before", "what": "Tested pre-race meal (oats, banana, white bread)"},
        {"icon": "☕", "when": "90 min before", "what": "Optional: coffee if you use it in training"},
        {"icon": "💧", "when": "Every 5 km", "what": "Water at every aid station"},
        {"icon": "🍬", "when": "At 10 km & 16 km", "what": "Gel or energy chews — use brands you've trained with"},
        {"icon": "🧂", "when": "If hot/humid", "what": "Electrolyte tablet at km 10"},
        {"icon": "🍫", "when": "Within 30 min after", "what": "Protein shake or chocolate milk + carbs"},
    ],
    30.0: [
        {"icon": "🍌", "when": "3 hrs before", "what": "Larger carb meal — you'll need the reserves"},
        {"icon": "🍬", "when": "Every 5–6 km", "what": "Gel or real food (dates, banana pieces) starting at km 8"},
        {"icon": "💧", "when": "Every 3–4 km", "what": "Water — more on climbs, trail runs sweat harder"},
        {"icon": "🧂", "when": "Every 10 km", "what": "Electrolytes — cramps on trails are race-ending"},
        {"icon": "🍫", "when": "Immediately after", "what": "Real food: protein + substantial carbs"},
    ],
    42.2: [
        {"icon": "🍌", "when": "3 hrs before", "what": "Tested breakfast: oatmeal + banana + white toast"},
        {"icon": "☕", "when": "2 hrs before", "what": "Coffee if trained with it; avoid if not"},
        {"icon": "🍬", "when": "Every 6–7 km from km 8", "what": "Gel every 6–7 km — do NOT skip early gels"},
        {"icon": "💧", "when": "Every aid station", "what": "Water: walk aid stations to drink efficiently"},
        {"icon": "🧂", "when": "At km 15 & 30", "what": "Electrolyte drink or tab — critical after km 25"},
        {"icon": "🍫", "when": "Within 30 min after", "what": "Recovery shake immediately; real meal within 2 hrs"},
    ],
}

# Mental checkpoints per distance
_MENTAL = {
    5.0: [
        {"distance": "1 km", "message": "Settle in. Ignore the adrenaline — run your pace."},
        {"distance": "2.5 km", "message": "Halfway. How do you feel? If easy, stay patient. If hard, focus on form."},
        {"distance": "4 km", "message": "One km left. This is what you trained for — find another gear."},
        {"distance": "Finish", "message": "Empty the tank. Sprint or try to sprint — leave nothing behind."},
    ],
    10.0: [
        {"distance": "2 km", "message": "Resist the urge to race others. Lock into your goal pace."},
        {"distance": "5 km", "message": "Halfway. Reassess: can you sustain this to the finish?"},
        {"distance": "8 km", "message": "The real race starts now. Every step matters."},
        {"distance": "9 km", "message": "One km. Trust your training and push."},
    ],
    21.1: [
        {"distance": "5 km", "message": "Feel easy? Good — that's the plan. Stay patient."},
        {"distance": "10 km", "message": "One quarter done. Find your rhythm and protect it."},
        {"distance": "16 km", "message": "The halfway point emotionally. This is where half marathons are won."},
        {"distance": "19 km", "message": "Two km left. Dig in — this discomfort is temporary."},
        {"distance": "Finish", "message": "You've earned this. Finish strong."},
    ],
    30.0: [
        {"distance": "5 km", "message": "First climb. Power hike if needed — no shame in that."},
        {"distance": "15 km", "message": "Halfway. How is fueling going? Eat something now if not recently."},
        {"distance": "22 km", "message": "The hardest part of any trail race. Run your own race, not someone else's."},
        {"distance": "27 km", "message": "3 km to go. The finish line is real — put your head down."},
    ],
    42.2: [
        {"distance": "10 km", "message": "One quarter done. Still feeling fresh? Good — stay conservative."},
        {"distance": "21 km", "message": "Halfway. If you feel great, stay controlled. The race starts at 30 km."},
        {"distance": "30 km", "message": "The wall zone. This is where your training runs matter most. Hold form."},
        {"distance": "35 km", "message": "7 km. Count them down. Everything hurts — keep moving."},
        {"distance": "40 km", "message": "2 km. You will finish. Make these last steps count."},
    ],
}

# Race morning timeline per distance
_MORNING_TIMES = {
    5.0: [
        ("2 hrs before", "Wake up and eat pre-race meal"),
        ("90 min before", "Arrive at venue, collect bib"),
        ("45 min before", "Light dynamic warm-up: leg swings, A-skips, strides"),
        ("15 min before", "Final bathroom stop, drop bag, move to start"),
        ("5 min before", "Easy jog 2–3 min, shake out the legs"),
    ],
    10.0: [
        ("2 hrs before", "Wake up and eat pre-race meal"),
        ("90 min before", "Arrive at venue, collect bib, walk the start area"),
        ("45 min before", "10 min easy jog + dynamic drills (high knees, butt kicks)"),
        ("20 min before", "4–6 × 20-sec strides at goal pace"),
        ("10 min before", "Final bathroom, move to corral"),
    ],
    21.1: [
        ("2.5 hrs before", "Eat pre-race meal (tested in training)"),
        ("2 hrs before", "Arrive at venue, bag drop, bib collection"),
        ("60 min before", "Easy 10-min jog to warm up the engine"),
        ("40 min before", "Dynamic drills: leg swings, hip circles, A-skips"),
        ("20 min before", "2–3 × 30-sec strides at goal pace"),
        ("10 min before", "Corral, final mindset check"),
    ],
    30.0: [
        ("3 hrs before", "Larger pre-race breakfast — you'll burn more than any other distance"),
        ("2 hrs before", "Arrive at venue, gear check (poles if used, hydration vest)"),
        ("60 min before", "Easy hike or jog to warm legs"),
        ("30 min before", "Confirm nutrition plan, take an early gel if long start queue"),
        ("10 min before", "Arrive at start, stay calm"),
    ],
    42.2: [
        ("3 hrs before", "Eat tested breakfast — this timing is non-negotiable"),
        ("2 hrs before", "Arrive at venue — marathons have complex logistics"),
        ("90 min before", "Bag drop, porta-loo queue (expect a wait)"),
        ("45 min before", "Easy 5-min jog only — conserve energy"),
        ("20 min before", "Into start corral — find your pace group"),
        ("5 min before", "Deep breaths. Trust your training."),
    ],
}

# Week-before checklist (universal + distance-specific)
_WEEK_BEFORE = [
    "Confirm race start time, location, and parking/transport",
    "Pick up race bib and packet if pre-collection is available",
    "Study the course map and identify key hills or turns",
    "Prepare and test your race-day outfit (including socks)",
    "Check the weather forecast and plan layers accordingly",
    "Charge GPS watch and earphones",
    "Prepare race nutrition: count gels, tabs, food",
    "Taper your training — trust the process, resist extra sessions",
    "Prioritise sleep: aim for 8+ hrs the night before the night before (Friday often matters more than Saturday)",
    "Avoid new foods, alcohol, and strenuous non-running activity",
]

_DISTANCE_EXTRAS = {
    30.0: [
        "Test run your hydration vest or belt on an easy run",
        "Sharpen or replace trail shoe spikes/lugs if worn",
        "Confirm drop bag rules and pack accordingly",
    ],
    42.2: [
        "Write your goal pace on your wrist or arm in permanent marker",
        "Plan where supporters will be — agree on specific km markers",
        "Prepare a 'Plan B' pace in case the first km feels harder than expected",
    ],
}


def _seconds_to_hhmmss(total_seconds: int) -> str:
    """Convert integer seconds to H:MM:SS or MM:SS string."""
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _generate_pacing_splits(
    target_distance: float,
    goal_pace_min_km: Optional[float],
) -> List[Dict[str, str]]:
    """Generate km-by-km (or key checkpoint) pacing splits."""
    if not goal_pace_min_km:
        return []

    splits = []

    # Determine split checkpoints based on distance
    if target_distance <= 5.0:
        checkpoints = [1, 2, 3, 4, 5]
    elif target_distance <= 10.0:
        checkpoints = [2, 5, 8, 10]
    elif target_distance <= 21.1:
        checkpoints = [5, 10, 15, 20, 21.1]
    elif target_distance <= 30.0:
        checkpoints = [5, 10, 15, 20, 25, 30]
    else:
        checkpoints = [5, 10, 15, 21.1, 25, 30, 35, 40, 42.2]

    cumulative_seconds = 0.0
    prev_km = 0.0

    for km in checkpoints:
        segment_km = km - prev_km
        segment_seconds = segment_km * goal_pace_min_km * 60
        cumulative_seconds += segment_seconds

        split_seconds = round(segment_seconds)
        cum_seconds = round(cumulative_seconds)

        is_finish = abs(km - target_distance) < 0.2
        is_halfway = abs(km - target_distance / 2) < 0.3

        splits.append({
            "distance": f"{km:.1f}" if km != int(km) else str(int(km)),
            "split_time": _seconds_to_hhmmss(split_seconds),
            "target_pace": f"{int(goal_pace_min_km)}:{round((goal_pace_min_km % 1) * 60):02d}/km",
            "cumulative": _seconds_to_hhmmss(cum_seconds),
            "highlight": is_finish or is_halfway,
        })

        prev_km = km

    return splits


def generate_race_protocol(
    target_distance: float,
    goal_pace_min_km: Optional[float],
) -> Dict[str, Any]:
    """Generate a complete race-day protocol.

    Args:
        target_distance: Race distance in km (5.0, 10.0, 21.1, 30.0, 42.2)
        goal_pace_min_km: Target pace in min/km (from VDOT or user input), optional

    Returns:
        Dict with all protocol sections for template rendering
    """
    # Normalise to a known distance key
    dist_key = min(_DIST_NAMES.keys(), key=lambda d: abs(d - target_distance))
    dist_name = _DIST_NAMES.get(dist_key, f"{target_distance}km")

    checklist = list(_WEEK_BEFORE)
    checklist.extend(_DISTANCE_EXTRAS.get(dist_key, []))

    # Predicted finish time
    predicted_finish = None
    if goal_pace_min_km:
        total_seconds = int(target_distance * goal_pace_min_km * 60)
        predicted_finish = _seconds_to_hhmmss(total_seconds)

    return {
        "distance_name": dist_name,
        "predicted_finish_time": predicted_finish,
        "week_before_checklist": checklist,
        "race_morning_timeline": [
            {"time": t, "activity": a}
            for t, a in _MORNING_TIMES.get(dist_key, _MORNING_TIMES[21.1])
        ],
        "pacing_strategy": _PACING_STRATEGY.get(dist_key, ""),
        "pacing_splits": _generate_pacing_splits(target_distance, goal_pace_min_km),
        "nutrition_timing": _NUTRITION.get(dist_key, _NUTRITION[21.1]),
        "mental_checkpoints": _MENTAL.get(dist_key, _MENTAL[21.1]),
    }
