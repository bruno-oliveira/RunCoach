"""Training tip database and selection logic.

Provides weekly training tips based on training phase, week number,
and target race distance.
"""

from typing import List

TRAINING_TIP_DATABASE = {
    "foundation": [
        "Establish a consistent training schedule - same time daily builds habit",
        "Start with conservative mileage increases (10% rule maximum)",
        "Focus on building your aerobic base before adding intensity",
        "Create a dedicated training space at home for pre/post-run routines",
        "Set up your gear night before to eliminate morning barriers",
    ],
    "routine": [
        "Develop pre-run warm-up routine: 5min walk + dynamic stretches",
        "Establish post-run recovery routine: stretching + nutrition timing",
        "Create a sleep schedule targeting 7-9 hours consistently",
        "Build hydration habits throughout day, not just during runs",
        "Set weekly training goals that are process-oriented (consistency over speed)",
    ],
    "equipment": [
        "Get fitted for proper running shoes at specialty running store",
        "Test different socks to prevent blisters during longer runs",
        "Consider GPS watch for tracking pace and distance accurately",
        "Invest in quality running clothes that prevent chafing",
        "Create a fueling belt or system for long run nutrition",
    ],
    "form": [
        "Focus on quick cadence (180+ steps per minute) for efficiency",
        "Keep shoulders relaxed and arms swinging forward, not across body",
        "Maintain upright posture - imagine a string pulling you upward",
        "Land mid-foot rather than heel striking for better shock absorption",
        "Practice running form drills 2x per week: high knees, butt kicks, bounding",
    ],
    "consistency": [
        "Never miss two consecutive training days - consistency trumps perfection",
        "Have backup plans for bad weather: treadmill, indoor alternatives",
        "Track your training in a log or app to monitor progress and stay motivated",
        "Find a training partner or group for accountability on tough days",
        "Celebrate showing up even when motivation is low",
    ],
    "recovery": [
        "Take ice baths after particularly hard workouts to reduce inflammation",
        "Use foam rolling 3-4 times per week, focusing on legs and hips",
        "Schedule active recovery days: gentle walking, swimming, or cycling",
        "Prioritize sleep - it's when your muscles repair and strengthen",
        "Consider massage therapy or self-massage tools for deep tissue work",
    ],
    "endurance": [
        "Practice negative splitting runs: second half faster than first",
        "Include progression runs: start easy, finish at threshold pace",
        "Build mental toughness by pushing through discomfort in final miles",
        "Test different fueling strategies during runs over 90 minutes",
        "Practice running on tired legs with back-to-back training days",
    ],
    "mental": [
        "Develop race mantras for different parts of race",
        "Practice visualization techniques: see yourself succeeding",
        "Create contingency plans for bad race moments (cramps, bad weather)",
        "Break long runs into smaller, manageable segments mentally",
        "Practice positive self-talk during challenging training sessions",
    ],
    "nutrition": [
        "Time your pre-run meals: 2-3 hours before for larger meals",
        "Practice race day breakfast during training weeks",
        "Experiment with different types of fuel during long runs",
        "Focus on post-run nutrition within 30 minutes: 3:1 carb:protein ratio",
        "Stay hydrated throughout day, not just around training",
    ],
    "pace": [
        "Learn your different paces: easy, tempo, interval, race pace",
        "Practice perceived effort vs. actual pace to develop internal awareness",
        "Use breathing patterns to gauge intensity: conversational for easy",
        "Test race pace in shorter segments during long runs",
        "Practice pace judgment by running without looking at your watch",
    ],
    "strength": [
        "Include core work 3x per week: planks, side planks, dead bugs",
        "Add single-leg exercises: Bulgarian split squats, single-leg deadlifts",
        "Incorporate plyometric exercises: box jumps, bounding, jump squats",
        "Focus on hip strengthening: clamshells, side-lying leg raises",
        "Practice running-specific strength: hill repeats, stair climbing",
    ],
    "injury_prevention": [
        "Listen to your body - distinguish between discomfort and pain",
        "Address minor aches immediately before they become major issues",
        "Include mobility work: hip flexor stretches, ankle mobility",
        "Vary running surfaces to reduce repetitive stress on joints",
        "Schedule regular rest days to allow for tissue repair",
    ],
    "race_simulation": [
        "Practice race day outfit during long runs including shoes and socks",
        "Simulate race start times in your training (early morning practice)",
        "Test your complete fueling strategy during long training runs",
        "Practice running expected race terrain: hills, flats, trails",
        "Do a dress rehearsal run at race pace for shorter distances",
    ],
    "strategy": [
        "Develop pacing strategy: conservative start, strong middle, fast finish",
        "Plan your nutrition timing: when to take gels, water, electrolytes",
        "Create mental checkpoints for different race distances",
        "Have backup plans for weather conditions: heat, rain, wind",
        "Practice race day decision making in training scenarios",
    ],
    "gear": [
        "Test all race day gear in training multiple times",
        "Break in new shoes gradually - never wear new shoes on race day",
        "Practice with your fueling system: belt, handheld, bottles",
        "Test anti-chafe products: Body Glide, Vaseline, specialized balms",
        "Choose socks based on distance - thicker for longer races",
    ],
    "confidence": [
        "Review your training log to see how far you've come",
        "Practice finishing strong in training runs to build race confidence",
        "Remind yourself of tough workouts you've completed successfully",
        "Visualize crossing the finish line at your goal time",
        "Trust your training - you've put in the work",
    ],
    "taper_preparation": [
        "Start reducing mileage while maintaining some intensity",
        "Focus on quality over quantity in remaining workouts",
        "Use extra time for sleep, nutrition, and mental preparation",
        "Avoid trying new things during taper period",
        "Stay busy with light activities to distract from pre-race nerves",
    ],
    "mental_training": [
        "Practice race day meditation or breathing exercises",
        "Develop pre-race routine to calm nerves and focus mind",
        "Write down your race goals and review them daily",
        "Practice dealing with pre-race anxiety: visualization, positive talk",
        "Prepare mentally for different race scenarios and outcomes",
    ],
    "final_preparations": [
        "Lay out race day gear night before race",
        "Plan your race morning timeline: wake up, breakfast, travel",
        "Check weather forecast and prepare appropriate clothing",
        "Charge your GPS watch and any electronic devices",
        "Prepare post-race recovery items: change of clothes, food",
    ],
    "logistics": [
        "Map out your route to race start and timing",
        "Plan parking or transportation to race venue",
        "Know race course: hills, aid stations, finish line location",
        "Prepare race day nutrition and pack it night before",
        "Have backup plans for transportation and gear issues",
    ],
    "race_day": [
        "Arrive at race venue early to avoid stress and allow warm-up",
        "Stick to your pre-race nutrition routine exactly as practiced",
        "Trust your training and don't get caught up in pre-race excitement",
        "Execute your pacing plan regardless of what others are doing",
        "Enjoy experience and celebrate your accomplishment",
    ],
    "taper": [
        "Embrace reduced mileage - your body is getting stronger",
        "Fight the urge to add extra training during taper",
        "Use extra mental energy for visualization and race planning",
        "Focus on hydration and nutrition more than ever",
        "Get extra sleep - every hour counts during taper",
    ],
    "visualization": [
        "Visualize entire race from start to finish successfully",
        "Imagine yourself handling tough moments with strength",
        "Picture crossing the finish line with your goal time",
        "See yourself executing your race strategy perfectly",
        "Visualize feeling strong and confident throughout race",
    ],
    "recovery_focus": [
        "Prioritize sleep above all else during final week",
        "Focus on anti-inflammatory foods: berries, leafy greens, omega-3s",
        "Stay hydrated but don't overdo it",
        "Keep moving with light activity to prevent stiffness",
        "Prepare mentally for post-race recovery period",
    ],
    "sharpening": [
        "Include short, sharp workouts to maintain fitness without fatigue",
        "Practice race pace efforts to stay familiar with goal speed",
        "Keep some intensity but reduce overall volume significantly",
        "Focus on running form and efficiency in final workouts",
        "Stay loose and mobile with stretching and light drills",
    ],
    "final_workouts": [
        "Make your last quality workout count but don't overdo it",
        "Practice race pace one final time to build confidence",
        "Keep workouts short but purposeful in final days",
        "Focus on feeling good and strong rather than pushing limits",
        "End each workout feeling like you could do more",
    ],
    "race_ready": [
        "Trust your taper - you're more fit than you feel",
        "Resist urge to test your fitness one last time",
        "Focus on feeling fresh and energized rather than tired",
        "Believe in your training and all the work you've done",
        "You're ready - now it's time to execute",
    ],
    "peak_performance": [
        "Execute your race strategy without hesitation",
        "Stay present and focused on each mile of race",
        "Draw strength from your training when things get tough",
        "Push through discomfort knowing you've prepared for it",
        "Leave everything on course - no regrets",
    ],
    "race_execution": [
        "Start conservatively - it's better to finish strong",
        "Stick to your nutrition plan regardless of how you feel",
        "Focus on form when fatigue sets in during later miles",
        "Use your mental training techniques when facing challenges",
        "Break race into smaller segments mentally",
    ],
    "post_race": [
        "Celebrate your accomplishment regardless of outcome",
        "Focus on proper recovery: nutrition, hydration, rest",
        "Reflect on what went well and what you learned",
        "Plan your return to training with adequate recovery time",
        "Thank supporters, volunteers, and fellow racers",
    ],
    "advanced_strategy": [
        "Practice surging and changing pace during training runs",
        "Learn to run tangents efficiently on road courses",
        "Master downhill running technique to save energy",
        "Practice drafting and positioning in crowded races",
        "Develop race-specific pacing for different course profiles",
    ],
    "course_specific": [
        "Study race course elevation profile and plan accordingly",
        "Practice running on similar terrain if possible",
        "Identify key points on course for mental checkpoints",
        "Plan your effort based on course challenges and features",
        "Know where tough sections are and prepare mentally",
    ],
    "conditions": [
        "Practice running in expected weather conditions",
        "Adjust your race strategy for heat, humidity, or cold",
        "Have gear options ready for different weather scenarios",
        "Practice hydration and fueling for specific conditions",
        "Mentally prepare for less-than-ideal race weather",
    ],
    "marathon_focus": [
        "Practice marathon pace during long runs to build familiarity",
        "Test your complete fueling strategy multiple times",
        "Include very long runs (20+ miles) to build mental confidence",
        "Practice running on tired legs in final miles of long runs",
        "Master art of patience in early marathon miles",
    ],
    "fueling_master": [
        "Create detailed fueling timeline for race day",
        "Practice with exact race day fuels during training",
        "Know where aid stations are and plan your fueling around them",
        "Practice taking nutrition while running at race pace",
        "Have backup fuel options in case of stomach issues",
    ],
    "mental_toughness": [
        "Practice embracing discomfort during training runs",
        "Develop strategies for pushing through marathon wall",
        "Build confidence by completing challenging workouts",
        "Practice positive self-talk during difficult training sessions",
        "Prepare mentally for unique challenges of 26.2 miles",
    ],
}

# Week number -> tip category rotation
_WEEK_CATEGORIES = {
    1: ["foundation", "routine", "equipment"],
    2: ["form", "consistency", "recovery"],
    3: ["endurance", "mental", "nutrition"],
    4: ["pace", "strength", "injury_prevention"],
    5: ["race_simulation", "strategy", "gear"],
    6: ["confidence", "taper_preparation", "mental_training"],
    7: ["final_preparations", "logistics", "race_day"],
    8: ["taper", "visualization", "recovery_focus"],
    9: ["sharpening", "final_workouts", "race_ready"],
    10: ["peak_performance", "race_execution", "post_race"],
    11: ["advanced_strategy", "course_specific", "conditions"],
    12: ["marathon_focus", "fueling_master", "mental_toughness"],
}

_MOTIVATIONAL_TIPS = [
    "Week {week}: Every mile in training pays dividends on race day",
    "Week {week}: Trust the process - you're stronger than last week",
    "Week {week}: Consistency is the secret weapon of successful runners",
    "Week {week}: Embrace the challenge - that's where growth happens",
    "Week {week}: Your future race self is thanking you for this work",
    "Week {week}: One day at a time, one workout at a time",
    "Week {week}: The pain of training is temporary, the pride is forever",
    "Week {week}: You've already committed - now execute with confidence",
]

_DISTANCE_TIPS = {
    "trail": [
        "Practice power hiking steep sections - sometimes walking is faster",
        "Test your trail shoes on technical terrain before race day",
        "Practice running with trekking poles if allowed in your race",
        "Learn to read trail markings and navigate confidently",
        "Practice fueling with handheld bottles or hydration packs",
        "Include downhill running practice to build quad strength",
        "Test different sock combinations for wet trail conditions",
        "Practice running on varied surfaces: rocks, roots, mud, sand",
    ],
    "5k": [
        "Practice running at slightly faster than goal pace for short intervals",
        "Include strides (100m accelerations) after easy runs to improve leg turnover",
        "Focus on quick leg turnover and efficient running form",
        "Practice race starts with controlled acceleration",
        "Include some hill repeats to build power and speed",
        "Practice running the exact race distance at goal pace",
        "Focus on explosive power: box jumps, bounding exercises",
        "Practice mental preparation for short, intense effort",
    ],
    "10k": [
        "Practice fast finishes on easy runs (last 1-2km at goal pace)",
        "Include tempo runs at goal race pace (3-5km total)",
        "Practice race pace nutrition: gel or sports drink at 5-6km mark",
        "Test your ability to hold pace through middle miles of race",
        "Practice race simulation: 2-3km at goal pace with proper warmup/cool",
        "Include progression runs building to race pace in final kilometers",
        "Practice mental focus for maintaining pace through 8km mark",
        "Test different pre-race meal timing for 10K distance",
    ],
    "half": [
        "Practice fueling during long runs (every 45-60 minutes)",
        "Include race-pace efforts in long runs (final 3-5km at goal pace)",
        "Practice running on tired legs (back-to-back long runs on weekend)",
        "Test your half marathon nutrition strategy multiple times",
        "Practice maintaining form through 15-18km when fatigue sets in",
        "Include race simulation runs of 15-16km at goal pace",
        "Test different shoes and socks for 21.1km distance comfort",
        "Practice mental strategies for dealing with fatigue around 18km mark",
    ],
    "marathon": [
        "Practice comprehensive fueling strategy: gels, drinks, real food options",
        "Include very long runs (75-90% of race distance) with race simulation",
        "Practice running with race day gear and nutrition for 3+ hours",
        "Test mental strategies for dealing with fatigue around 30km mark",
        "Practice marathon pace during long runs to build muscle memory",
        "Test your complete race day nutrition plan multiple times",
        "Include back-to-back long runs to simulate marathon fatigue",
        "Practice running the wall - push through tough patches in training",
        "Test different pre-race carbo-loading strategies",
        "Practice mental preparation for 26.2 mile challenge",
    ],
}


def _get_distance_key(target_distance: float, trail_profile=None) -> str:
    """Map target distance (and optional trail context) to a distance tip key."""
    if trail_profile is not None or target_distance == 30:
        return "trail"
    if target_distance <= 5:
        return "5k"
    if target_distance <= 10:
        return "10k"
    if target_distance <= 21.1:
        return "half"
    return "marathon"


# Bracket-specific tips bolt onto the base "trail" pool — added when the
# user's plan crosses into ultra / long_ultra territory so the coaching
# vocabulary matches the race demands.
_TRAIL_BRACKET_TIPS = {
    "short": [
        "Trail isn't road — relax your form on technical sections, eyes 5–10 m ahead.",
        "Practise descents on tired legs; learn to let go a little on smooth downhills.",
    ],
    "standard": [
        "Power-hike the steepest 10% of your hills in training — it's a race tactic, not a weakness.",
        "Eat your first gel by minute 30, even if you don't feel hungry. Train the gut.",
        "Run at least one long run on the actual race terrain, or as close as you can find.",
    ],
    "ultra": [
        "Add a back-to-back long-run weekend during build (Sat long, Sun medium-long).",
        "Test every gel, chew, and aid-station food in training — not on race day.",
        "Practise eating real food on the move (potato, banana, rice ball) on long runs.",
        "Pack a drop-bag dry-run: spare socks, lube, jacket, headlamp batteries, real food.",
    ],
    "long_ultra": [
        "Do at least one night training run with the headlamp + backup torch you'll race with.",
        "Plan a sleep strategy: brief 10–20 min naps at major aid stations are normal.",
        "Brief your crew on warning signs (slurred speech, hypothermia, wobble) and the abort plan.",
        "Practise switching shoes / changing socks mid-run — the dry-shoe reset is a real morale boost.",
    ],
}

_TRAIL_FLAT_ACCESS_TIPS = {
    "short": [
        "Use bridge repeats, parking-garage ramps, or treadmill incline to simulate short climbs.",
        "Do 20-30 min brisk power-walk blocks each week to rehearse race-day hiking muscles.",
    ],
    "standard": [
        "On flat routes, run climbs by effort: 3-6 min hard surges with easy jog recoveries.",
        "Use soft surfaces (grass, gravel, dirt) for at least one run weekly to mimic trail load.",
        "If local terrain is flat, add incline treadmill or stairs for vertical-specific strength.",
    ],
    "ultra": [
        "Replace one weekly quality run with incline treadmill or stair climbing to build vertical capacity.",
        "Stack long-run fatigue with back-to-back days when you cannot access long climbs.",
        "Keep race fueling rehearsal strict: every 30 min, even on easier flat terrain.",
    ],
    "long_ultra": [
        "When terrain is flat, emphasize time-on-feet and climbing-specific strength over chasing pace.",
        "Add long incline-hike blocks (10-20 min) to mimic sustained mountain climbs.",
        "Rehearse gear and fueling under fatigue; flat routes still let you stress-test systems.",
    ],
}


def get_tips_for_week(
    week_number: int,
    target_distance: float,
    trail_profile=None,
    training_terrain: str | None = None,
) -> List[str]:
    """Generate diverse and week-specific training tips.

    Args:
        week_number: 1-indexed week number in the plan.
        target_distance: Race distance in km.
        trail_profile: Optional ``TrailProfile`` — bracket-aware tips
            (power hiking, fueling rehearsal, drop bags, night running)
            replace the generic distance tip when present.
        training_terrain: Optional terrain access string for where the runner
            trains (flat/rolling/hilly/mountainous). When ``flat``, trail tips
            switch to flat-access alternatives.
    """
    tips: List[str] = []

    # Get categories for current week (cycle through if longer than 12)
    current_week_categories = _WEEK_CATEGORIES.get(
        week_number,
        _WEEK_CATEGORIES[(week_number - 1) % 12 + 1],
    )

    # Select tips from current week categories
    for category in current_week_categories:
        category_tips = TRAINING_TIP_DATABASE[category]
        num_tips = 1 if len(current_week_categories) > 2 else 2
        start_index = (week_number - 1) % len(category_tips)
        for i in range(num_tips):
            tip_index = (start_index + i) % len(category_tips)
            tips.append(category_tips[tip_index])

    # Distance-specific or bracket-specific tip.
    if trail_profile is not None:
        if training_terrain == "flat":
            bracket_tips = _TRAIL_FLAT_ACCESS_TIPS.get(
                trail_profile.bracket,
                _DISTANCE_TIPS["trail"],
            )
        else:
            bracket_tips = _TRAIL_BRACKET_TIPS.get(
                trail_profile.bracket,
                _DISTANCE_TIPS["trail"],
            )
        tips.append(bracket_tips[(week_number - 1) % len(bracket_tips)])
    else:
        dist_key = _get_distance_key(target_distance)
        dist_tips = _DISTANCE_TIPS[dist_key]
        tips.append(dist_tips[(week_number - 1) % len(dist_tips)])

    # Add one rotating motivational tip
    motivational_index = (week_number - 1) % len(_MOTIVATIONAL_TIPS)
    tips.append(_MOTIVATIONAL_TIPS[motivational_index].format(week=week_number))

    return tips[:4]
