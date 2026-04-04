"""Coaching notes generator — explains *why* each workout was assigned.

Generates 2-3 sentence rationales that explain the physiological benefit,
the training-phase context, and a brief execution tip.
"""

from typing import Dict, Optional


# Coaching rationale templates keyed by (workout_type, phase)
# Each value is a string; {distance_name} and {phase} are interpolated if present.
_NOTES: Dict[str, str] = {
    # ── Easy runs ─────────────────────────────────────────────────────────
    "easy_base": (
        "Building your aerobic engine. This easy run strengthens your heart, "
        "increases capillary density, and teaches your body to burn fat efficiently "
        "— all without adding meaningful stress. "
        "Keep the pace genuinely conversational: if you can't speak in full sentences, slow down."
    ),
    "easy_build": (
        "Staying aerobically active between quality sessions. "
        "Easy runs in the Build phase help you recover from harder workouts while "
        "maintaining your weekly mileage and reinforcing good running economy. "
        "Resist the temptation to push — saving energy here pays off on your quality days."
    ),
    "easy_peak": (
        "Active recovery at peak training load. "
        "With your hardest weeks behind you, these easy runs keep your legs moving "
        "without adding fatigue. "
        "Focus on relaxed form and controlled breathing — your speed comes from rest, not extra effort here."
    ),
    "easy_taper": (
        "Maintaining feel for the road while letting your body supercompensate. "
        "Research shows that even a 50% volume reduction preserves fitness for 2-3 weeks. "
        "Run easy, stay fresh, trust your training."
    ),

    # ── Tempo runs ────────────────────────────────────────────────────────
    "tempo_base": (
        "Light introduction to sustained effort. "
        "Even in the Base phase, brief tempo work teaches your body where the lactate threshold is. "
        "Focus on comfortably hard — challenging but controlled, never a sprint."
    ),
    "tempo_build": (
        "Raising your lactate threshold — the single biggest predictor of race performance. "
        "Running at tempo pace trains your body to clear lactate faster, "
        "so you can sustain a harder effort on race day. "
        "Classic rule: you should be able to speak 3–4 words at a time, not hold a conversation."
    ),
    "tempo_peak": (
        "Race-sharpening threshold work at peak fitness. "
        "Your aerobic base is fully built; these sessions are converting fitness into race-day speed. "
        "Aim for a pace that feels controlled-hard — if it feels easy, you're too slow; if you're gasping, back off."
    ),
    "tempo_taper": (
        "A brief sharpener to keep your legs snappy before race day. "
        "Short tempo efforts maintain neuromuscular activation without building fatigue. "
        "Keep the volume low but the effort genuine — one or two quality minutes is enough."
    ),

    # ── Intervals ─────────────────────────────────────────────────────────
    "interval_base": (
        "Short strides to reinforce running form and leg turnover. "
        "Even in base building, brief accelerations teach your body efficient mechanics "
        "without imposing hard physiological stress. "
        "Focus on quick, light feet rather than maximal effort."
    ),
    "interval_build": (
        "VO₂max development — improving your ceiling for oxygen use. "
        "These high-intensity intervals push your cardiovascular system to near its maximum, "
        "triggering the most powerful aerobic adaptations. "
        "Full recovery between reps is essential: you're training quality, not accumulating fatigue."
    ),
    "interval_peak": (
        "Final VO₂max stimulus at peak fitness. "
        "Your aerobic ceiling is at its highest; these sessions sharpen your ability to "
        "maintain race pace when it gets hard in the final kilometres. "
        "Execute with purpose — controlled aggression, not desperation."
    ),
    "interval_taper": (
        "Short, sharp strides to keep your neuromuscular system primed. "
        "A few fast reps remind your legs of race pace without creating meaningful fatigue. "
        "Short, controlled, and confident."
    ),

    # ── Long runs ─────────────────────────────────────────────────────────
    "long_base": (
        "The cornerstone of endurance training. "
        "Long runs develop mitochondrial density, fat oxidation, and mental toughness — "
        "adaptations that nothing else can replicate. "
        "Run it slow enough that you could run for another hour after you finish. If you can't, you're going too fast."
    ),
    "long_build": (
        "Progressive endurance: your long run is growing to match your race demands. "
        "Today's session is training your body's fuel system and your mind's ability to push through discomfort. "
        "Practise your race-day nutrition and hydration strategy during this run."
    ),
    "long_peak": (
        "Your longest training run — the confidence-builder. "
        "Completing today's distance at a controlled effort is the clearest evidence "
        "that you're ready for race day. "
        "Treat the final 20% of the run as race practice: focus on form when fatigue arrives."
    ),
    "long_taper": (
        "A reduced long run to maintain endurance without digging into your reserves. "
        "Your fitness is locked in — this run reinforces it without creating new fatigue. "
        "Think of it as a dress rehearsal: similar route, similar fueling, easy effort."
    ),

    # ── Hill workouts ─────────────────────────────────────────────────────
    "hill_base": (
        "Hill strides to build leg strength and power economically. "
        "Running uphill forces a stronger push-off, activating glutes and calves in ways "
        "that flat running doesn't. "
        "Focus on driving your arms and lifting your knees — the effort is natural on the incline."
    ),
    "hill_build": (
        "Hill repeats: the safest form of speed work. "
        "Incline running delivers interval-like cardiovascular stimulus at a lower injury risk "
        "because ground impact forces are reduced. "
        "Attack each hill with short, quick strides; jog or walk back down for full recovery."
    ),
    "hill_peak": (
        "Race-specific strength and power at peak fitness. "
        "For trail runners especially, hill strength late in training translates directly to "
        "race performance on climbs. "
        "Run uphill aggressively but efficiently — lean into the grade, short steps, high cadence."
    ),
    "hill_taper": (
        "A brief hill session to maintain leg power going into race week. "
        "A few quality repeats keep your fast-twitch fibres awake without accumulating fatigue. "
        "Short, punchy, and relaxed."
    ),

    # ── Rest days ─────────────────────────────────────────────────────────
    "rest_base": (
        "Adaptation happens during rest, not during the run. "
        "Your muscles repair micro-tears, your glycogen stores refill, and your cardiovascular "
        "system rebuilds stronger than before. "
        "Treat rest days as seriously as training days — they're part of the programme."
    ),
    "rest_build": (
        "Strategic recovery between hard sessions. "
        "Skipping rest days doesn't make you fitter faster — it extends fatigue and increases "
        "injury risk. "
        "Light mobility work, adequate sleep, and good nutrition today will amplify tomorrow's training."
    ),
    "rest_peak": (
        "Essential recovery at your highest training load. "
        "Your body is absorbing the most demanding weeks of the programme. "
        "Protect this day: prioritise sleep, nutrition, and stress management."
    ),
    "rest_taper": (
        "Rest is now your most important training tool. "
        "Glycogen stores are topping up, minor niggles are fading, and your central nervous "
        "system is recharging for race day. "
        "Stay off your feet, stay hydrated, and trust the process."
    ),

    # ── Recovery (active recovery day — swim/walk) ─────────────────────
    "recovery_base": (
        "Active recovery with zero impact on your joints. "
        "Swimming or easy walking promotes blood flow and speeds muscle repair "
        "without adding running stress to the week. "
        "This is not a lost training day — it's a deliberate recovery tool."
    ),
    "recovery_build": (
        "Low-impact movement to flush out training fatigue. "
        "A swim or easy walk keeps your cardiovascular system ticking over while giving "
        "your legs a complete break from pounding. "
        "Keep the effort light — this is recovery, not fitness work."
    ),
    "recovery_peak": (
        "Complete break from running stress at peak load. "
        "Your legs need this impact-free day more than ever right now. "
        "Even 20 minutes of easy swimming will accelerate recovery for tomorrow's session."
    ),
    "recovery_taper": (
        "Gentle movement to stay loose without accumulating fatigue. "
        "An easy swim or short walk is ideal in taper week: "
        "it keeps you active, reduces pre-race anxiety, and doesn't cost you anything physiologically."
    ),
}

# Fallback notes for any missing combination
_FALLBACK: Dict[str, str] = {
    "easy": "Easy aerobic run. Keep the effort genuinely conversational to build your aerobic base without accumulating fatigue.",
    "tempo": "Threshold work. Run at comfortably hard effort — sustainable but challenging — to raise your lactate threshold.",
    "interval": "High-intensity intervals to develop VO₂max. Full recovery between reps is as important as the reps themselves.",
    "long": "Long endurance run. The most important session of the week for building race-specific endurance.",
    "hill": "Hill repeats to build strength and power. Focus on form and full recovery between efforts.",
    "rest": "Rest day. Adaptation happens during recovery — protect this day.",
    "recovery": "Active recovery. Low-impact movement to promote blood flow and speed muscle repair.",
    "strength": "Strength training to support your running. Focus on quality movement over heavy loads.",
}


def generate_coaching_note(
    workout_type: str,
    phase: str,
    week_number: int,
    target_distance: float,
    is_recovery_week: bool = False,
) -> Optional[str]:
    """Generate a coaching rationale for a given workout.

    Args:
        workout_type: 'easy', 'tempo', 'interval', 'long', 'hill', 'rest', 'recovery'
        phase: 'base', 'build', 'peak', 'taper'
        week_number: 1-based week number within the plan
        target_distance: Target race distance in km
        is_recovery_week: Whether this is a planned recovery/down week

    Returns:
        2-3 sentence coaching note, or None for unknown types
    """
    key = f"{workout_type}_{phase}"
    note = _NOTES.get(key)

    if not note:
        note = _FALLBACK.get(workout_type)

    if not note:
        return None

    # Append recovery-week context where relevant
    if is_recovery_week and workout_type in ("easy", "long", "tempo"):
        note += (
            " Note: this is a planned recovery week — "
            "distances are intentionally reduced to let your body absorb recent training."
        )

    return note
