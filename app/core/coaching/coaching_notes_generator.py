"""Coaching notes generator — explains *why* each workout was assigned.

Generates a one-line rationale tying each session to the runner's race
distance and current training phase.  When a key workout overlay supplies
its own rationale (from the catalog), that takes priority — callers merge
the two fields into ``coaching_rationale``.
"""

from typing import Any, Dict, Optional

_DISTANCE_NAMES: Dict[float, str] = {
    5.0: "5K",
    10.0: "10K",
    21.1: "half marathon",
    42.2: "marathon",
}


def _distance_name(target_distance: float) -> str:
    for km, label in _DISTANCE_NAMES.items():
        if abs(target_distance - km) < 0.5:
            return label
    return f"{target_distance:g} km"


# Coaching rationale templates keyed by ``{type}_{phase}``.
# ``{race}`` is interpolated with the race-distance label at render time.
_NOTES: Dict[str, str] = {
    # ── Easy runs ─────────────────────────────────────────────────────────
    "easy_base": (
        "Building the aerobic base that everything in your {race} build sits on — "
        "keep the pace genuinely conversational."
    ),
    "easy_build": (
        "Aerobic maintenance between quality sessions — saving energy here "
        "pays off on your hard days."
    ),
    "easy_peak": (
        "Active recovery at peak load — your {race} speed comes from rest, "
        "not extra effort here."
    ),
    "easy_taper": (
        "Staying loose while your body supercompensates for {race} day — "
        "run easy, stay fresh, trust your training."
    ),
    # ── Tempo runs ────────────────────────────────────────────────────────
    "tempo_base": (
        "Light introduction to sustained effort — teaching your body where "
        "the lactate threshold is before the {race} build begins."
    ),
    "tempo_build": (
        "Raising your lactate threshold so you can hold a harder effort "
        "across the full {race} distance."
    ),
    "tempo_peak": (
        "Race-sharpening threshold work — converting your fitness into "
        "{race} race-day speed."
    ),
    "tempo_taper": (
        "A brief sharpener to keep your legs snappy before your {race} — "
        "low volume, genuine effort."
    ),
    # ── Intervals ─────────────────────────────────────────────────────────
    "interval_base": (
        "Short strides to reinforce running form and leg turnover — "
        "efficient mechanics now pay off across your {race} build."
    ),
    "interval_build": (
        "VO₂max development — raising the aerobic ceiling you'll draw on "
        "in the late kilometres of your {race}."
    ),
    "interval_peak": (
        "Final VO₂max stimulus — sharpening your ability to hold {race} "
        "pace when it gets hard in the closing stretch."
    ),
    "interval_taper": (
        "Short, sharp strides to keep your neuromuscular system primed "
        "for {race} day."
    ),
    # ── Long runs ─────────────────────────────────────────────────────────
    "long_base": (
        "The cornerstone of {race} training — building mitochondrial density "
        "and fat oxidation that nothing else replicates."
    ),
    "long_build": (
        "Progressive endurance toward {race} distance — practise your "
        "race-day fuelling and hydration here."
    ),
    "long_peak": (
        "Your longest training run — completing this at controlled effort "
        "is the clearest evidence you're ready for {race} day."
    ),
    "long_taper": (
        "A reduced long run to maintain endurance without digging into your "
        "{race} reserves — dress rehearsal effort."
    ),
    # ── Hill workouts ─────────────────────────────────────────────────────
    "hill_base": (
        "Hill strides to build leg strength and power economically — "
        "a stronger push-off now pays dividends across your {race} build."
    ),
    "hill_build": (
        "Hill repeats: interval-like cardiovascular stimulus at lower injury "
        "risk — building the strength your {race} demands."
    ),
    "hill_peak": (
        "Race-specific hill strength at peak fitness — translates directly "
        "to {race} performance on climbs and surges."
    ),
    "hill_taper": (
        "A few quality hill reps to keep fast-twitch fibres awake going "
        "into your {race}."
    ),
    # ── Rest days ─────────────────────────────────────────────────────────
    "rest_base": (
        "Adaptation happens during rest, not during the run — treat this "
        "day as seriously as any training day."
    ),
    "rest_build": (
        "Strategic recovery between hard sessions — good sleep and "
        "nutrition today amplify tomorrow's {race} training."
    ),
    "rest_peak": (
        "Essential recovery at your highest training load — protect this "
        "day to absorb the work."
    ),
    "rest_taper": (
        "Rest is your most important tool now — glycogen stores are topping "
        "up and your body is recharging for {race} day."
    ),
    # ── Recovery (active recovery day — swim/walk) ─────────────────────
    "recovery_base": (
        "Zero-impact active recovery — swimming or walking promotes blood "
        "flow without adding running stress."
    ),
    "recovery_build": (
        "Low-impact movement to flush training fatigue — keep the effort "
        "light, this is recovery, not fitness work."
    ),
    "recovery_peak": (
        "Complete break from running stress at peak load — even 20 minutes "
        "of easy swimming accelerates recovery."
    ),
    "recovery_taper": (
        "Gentle movement to stay loose without accumulating fatigue — "
        "ideal for the days before your {race}."
    ),
}

_FALLBACK: Dict[str, str] = {
    "easy": "Easy aerobic run — keep the effort conversational to build your base without fatigue.",
    "tempo": "Threshold work — comfortably hard effort to raise your lactate threshold for {race} day.",
    "interval": "High-intensity intervals to develop your VO₂max ceiling for {race} performance.",
    "long": "Long endurance run — the most important session for building {race}-specific endurance.",
    "hill": "Hill repeats to build strength and power for your {race} — form and full recovery between efforts.",
    "rest": "Rest day — adaptation happens during recovery, not during the run.",
    "recovery": "Active recovery — low-impact movement to promote blood flow and speed repair.",
    "strength": "Strength training to support your {race} running — quality movement over heavy loads.",
}


def _band_pace_str(pace_zones: Dict[str, Any], key: str) -> Optional[str]:
    """Formatted pace for a top-level VDOT band (E/M/T/I/R), if present."""
    zone = pace_zones.get(key)
    if isinstance(zone, dict):
        return zone.get("pace_str")
    return None


def _sub_pace_str(pace_zones: Dict[str, Any], sub: str) -> Optional[str]:
    """Formatted pace for an E sub-zone (easy / recovery / long_run)."""
    e = pace_zones.get("E")
    if isinstance(e, dict):
        sub_zone = e.get("sub_zones", {}).get(sub)
        if isinstance(sub_zone, dict):
            return sub_zone.get("pace_str")
        return e.get("pace_str")
    return None


def build_pace_cue(
    workout_type: str,
    phase: str,
    pace_zones: Optional[Dict[str, Any]],
) -> Optional[str]:
    """One concrete pace/rep cue grounded in the runner's VDOT zones (audit E2).

    Turns the static rationale into something actionable ("Run the reps at
    3:54/km (I-pace)") and tightens toward race effort in peak. Returns None
    when paces are unavailable so callers fall back to prose only.
    """
    if not pace_zones:
        return None

    if workout_type == "easy":
        easy = _sub_pace_str(pace_zones, "easy")
        return f"Today's target: around {easy} (E-pace)." if easy else None

    if workout_type == "long":
        long_pace = _sub_pace_str(pace_zones, "long_run")
        if not long_pace:
            return None
        cue = f"Settle in around {long_pace} (long-run pace)."
        m_pace = _band_pace_str(pace_zones, "M")
        if phase == "peak" and m_pace:
            cue += (
                f" Lift the final stretch to {m_pace} (M-pace) to rehearse race effort."
            )
        return cue

    if workout_type == "tempo":
        t_pace = _band_pace_str(pace_zones, "T")
        if not t_pace:
            return None
        if phase == "peak":
            return f"Lock into {t_pace} (T-pace) — controlled-hard, race-sharpening."
        return f"Hold {t_pace} (T-pace) through the threshold portion."

    if workout_type == "interval":
        i_pace = _band_pace_str(pace_zones, "I")
        return (
            f"Run the reps at {i_pace} (I-pace) with full recovery between."
            if i_pace
            else None
        )

    if workout_type == "hill":
        r_pace = _band_pace_str(pace_zones, "R")
        return (
            f"Drive each rep at ~{r_pace} (R-pace) effort; jog down to recover."
            if r_pace
            else None
        )

    return None


def generate_coaching_note(
    workout_type: str,
    phase: str,
    week_number: int,
    target_distance: float,
    is_recovery_week: bool = False,
    pace_zones: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """One-line coaching rationale tied to race distance and phase.

    The "after yesterday's…" render-time prefix is applied by the single live
    implementation in ``plan_template_context._coaching_prefix``; persisted
    rationales stay stable here (audit B12).
    """
    key = f"{workout_type}_{phase}"
    note = _NOTES.get(key)

    if not note:
        note = _FALLBACK.get(workout_type)

    if not note:
        return None

    race = _distance_name(target_distance)
    note = note.replace("{race}", race)

    if is_recovery_week and workout_type in ("easy", "long", "tempo"):
        note += " (recovery week — distances intentionally reduced)"

    cue = build_pace_cue(workout_type, phase, pace_zones)
    if cue:
        note += " " + cue

    return note
