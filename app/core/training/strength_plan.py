"""Phase-periodized, experience-adapted strength training for running plans.

Pure data module — no DB, no I/O. All exercise templates are hardcoded
so that TrainingPlanGenerator stays dependency-free and fully testable.
"""

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Experience level derivation
# ---------------------------------------------------------------------------


def derive_experience_level(current_km: float) -> str:
    """Derive runner experience level from current weekly mileage."""
    if current_km < 20:
        return "beginner"
    if current_km < 40:
        return "intermediate"
    return "advanced"


# ---------------------------------------------------------------------------
# Phase focus rotations
# ---------------------------------------------------------------------------
# Each phase prescribes an ordered list of focus areas. The plan generator
# picks focuses in order as it encounters easy-run slots in the week.

PHASE_FOCUS_ROTATIONS: Dict[str, List[str]] = {
    "base": ["lower_body", "core"],
    "build": ["lower_body", "core", "plyometric"],
    "peak": ["lower_body", "plyometric", "core"],
    "taper": ["core"],
}

# Trail runners get stability work replacing generic full_body. Kept as the
# default rolling/hilly rotation; flat and mountainous use the elevation-class
# table below.
TRAIL_FOCUS_ROTATIONS: Dict[str, List[str]] = {
    "base": ["lower_body", "trail_stability", "core"],
    "build": ["lower_body", "trail_stability", "plyometric"],
    "peak": ["lower_body", "plyometric", "trail_stability"],
    "taper": ["core"],
}

# Per-elevation-class trail rotations.
#
# * Flat trail (no hill access) — addresses the user's flaw #2 directly:
#   replaces the missing hill-driven power stimulus with plyometric work
#   (depth jumps, broad jumps, single-leg hops — all bodyweight, no gym).
# * Rolling / hilly — current trail rotation (terrain itself drives stability
#   adaptation; gym work supplements with eccentric strength).
# * Mountainous — emphasises stability + plyometric for descents and steep
#   climbs; the lower_body rotation prepares quads for the eccentric load.
TRAIL_ROTATIONS_BY_ELEVATION: Dict[str, Dict[str, List[str]]] = {
    "flat": {
        "base": ["flat_trail_strength", "core", "plyometric"],
        "build": ["flat_trail_strength", "plyometric", "flat_trail_strength"],
        "peak": ["flat_trail_strength", "plyometric", "core"],
        "taper": ["core"],
    },
    "rolling": TRAIL_FOCUS_ROTATIONS,
    "hilly": TRAIL_FOCUS_ROTATIONS,
    "mountainous": {
        "base": ["lower_body", "trail_stability", "plyometric"],
        "build": ["lower_body", "trail_stability", "plyometric"],
        "peak": ["lower_body", "trail_stability", "plyometric"],
        "taper": ["trail_stability"],
    },
}


# ---------------------------------------------------------------------------
# Phase modifiers for sets / reps / duration
# ---------------------------------------------------------------------------

_PHASE_MODIFIERS: Dict[str, Dict[str, Any]] = {
    "base": {"sets_delta": 0, "duration_delta": 0, "note": None},
    "build": {"sets_delta": 0, "duration_delta": 5, "note": None},
    "peak": {
        "sets_delta": 0,
        "duration_delta": 0,
        "note": "Explosive tempo — controlled power",
    },
    "taper": {
        "sets_delta": -1,
        "duration_delta": -10,
        "note": "Maintenance only — preserve strength, minimise fatigue",
    },
}


# ---------------------------------------------------------------------------
# Exercise database: focus × level
# ---------------------------------------------------------------------------
# Each entry: warm_up (list[str]), exercises (list[dict]), cool_down (list[str]),
# base_duration (str like "25-35 min")

_EXERCISES: Dict[str, Dict[str, Dict[str, Any]]] = {
    # ── Lower body ────────────────────────────────────────────────────────
    # Simple, proven bodyweight exercises that complement running.
    "lower_body": {
        "beginner": {
            "base_duration": "20-30 min",
            "warm_up": [
                "5 min easy walk",
                "Bodyweight squats — 10 reps",
                "Ankle circles — 10 each side",
            ],
            "exercises": [
                {"name": "Bodyweight Squat", "sets": 3, "reps": "12-15"},
                {"name": "Glute Bridge", "sets": 3, "reps": "15"},
                {"name": "Calf Raises", "sets": 3, "reps": "15"},
                {"name": "Reverse Lunge", "sets": 2, "reps": "10 each side"},
                {"name": "Wall Sit", "sets": 2, "reps": "30 sec hold"},
            ],
            "cool_down": [
                "Standing quad stretch — 30 sec each",
                "Pigeon pose — 45 sec each side",
                "Calf stretch — 30 sec each",
            ],
        },
        "intermediate": {
            "base_duration": "25-35 min",
            "warm_up": [
                "5 min easy walk or light jog",
                "Leg swings — 10 each side",
                "Hip circles — 10 each direction",
            ],
            "exercises": [
                {"name": "Split Squat", "sets": 3, "reps": "10 each side"},
                {"name": "Single-leg Glute Bridge", "sets": 3, "reps": "12 each side"},
                {"name": "Single-leg Calf Raise", "sets": 3, "reps": "12 each side"},
                {"name": "Step-ups", "sets": 3, "reps": "10 each side"},
                {"name": "Side-lying Leg Raise", "sets": 3, "reps": "15 each side"},
            ],
            "cool_down": [
                "Pigeon pose — 45 sec each side",
                "Standing hamstring stretch — 30 sec each",
                "Calf stretch — 30 sec each",
            ],
        },
        "advanced": {
            "base_duration": "30-40 min",
            "warm_up": [
                "5 min easy jog",
                "Walking lunges — 10 each side",
                "Leg swings — 10 each direction",
            ],
            "exercises": [
                {"name": "Bulgarian Split Squat", "sets": 3, "reps": "10 each side"},
                {
                    "name": "Single-leg Deadlift (bodyweight)",
                    "sets": 3,
                    "reps": "10 each side",
                },
                {"name": "Jump Squat", "sets": 3, "reps": "10"},
                {"name": "Walking Lunge", "sets": 3, "reps": "12 each side"},
                {"name": "Single-leg Calf Raise", "sets": 3, "reps": "15 each side"},
            ],
            "cool_down": [
                "Pigeon pose — 60 sec each side",
                "Standing quad stretch — 30 sec each",
                "Downward dog — 45 sec",
            ],
        },
    },
    # ── Core ──────────────────────────────────────────────────────────────
    "core": {
        "beginner": {
            "base_duration": "20-25 min",
            "warm_up": [
                "5 min easy walk",
                "Cat-cow stretch — 10 reps",
                "Hip circles — 10 each direction",
            ],
            "exercises": [
                {"name": "Plank", "sets": 3, "reps": "30-45 sec hold"},
                {"name": "Dead Bug", "sets": 3, "reps": "8 each side"},
                {"name": "Bird Dog", "sets": 3, "reps": "10 each side"},
                {"name": "Side Plank", "sets": 2, "reps": "20-30 sec each side"},
                {"name": "Glute Bridge", "sets": 2, "reps": "15"},
            ],
            "cool_down": [
                "Child's pose — 30 sec",
                "Cat-cow — 10 slow reps",
                "Hip flexor stretch — 30 sec each side",
            ],
        },
        "intermediate": {
            "base_duration": "25-30 min",
            "warm_up": [
                "5 min easy walk",
                "Cat-cow — 10 reps",
                "Leg swings — 10 each side",
            ],
            "exercises": [
                {"name": "Plank", "sets": 3, "reps": "45-60 sec hold"},
                {"name": "Side Plank", "sets": 3, "reps": "30 sec each side"},
                {"name": "Dead Bug", "sets": 3, "reps": "12 each side"},
                {"name": "Bicycle Crunch", "sets": 3, "reps": "15 each side"},
                {"name": "Superman Hold", "sets": 3, "reps": "30 sec"},
            ],
            "cool_down": [
                "Child's pose — 30 sec",
                "Supine twist — 30 sec each side",
                "Hip flexor stretch — 30 sec each side",
            ],
        },
        "advanced": {
            "base_duration": "25-35 min",
            "warm_up": [
                "5 min light jog",
                "Cat-cow — 10 reps",
                "Hip circles — 10 each direction",
            ],
            "exercises": [
                {"name": "Plank", "sets": 3, "reps": "60 sec hold"},
                {
                    "name": "Side Plank with Leg Lift",
                    "sets": 3,
                    "reps": "30 sec each side",
                },
                {"name": "Mountain Climber", "sets": 3, "reps": "20 each side"},
                {"name": "Hollow Body Hold", "sets": 3, "reps": "30-45 sec"},
                {"name": "Bird Dog", "sets": 3, "reps": "12 each side"},
            ],
            "cool_down": [
                "Child's pose — 45 sec",
                "Supine twist — 30 sec each side",
                "Downward dog — 30 sec",
            ],
        },
    },
    # ── Plyometrics (progressive by level) ──────────────────────────────
    "plyometric": {
        "beginner": {
            "base_duration": "15-20 min",
            "warm_up": [
                "5 min easy walk",
                "Bodyweight squats — 10 reps",
                "Ankle circles — 10 each side",
            ],
            "exercises": [
                {
                    "name": "Box Step-Down (slow eccentric)",
                    "sets": 3,
                    "reps": "8 each side",
                },
                {
                    "name": "Bilateral Landing Drill (jump & stick)",
                    "sets": 3,
                    "reps": "6",
                },
                {"name": "Calf Bounce (low amplitude)", "sets": 3, "reps": "15"},
                {"name": "Squat Jump (quarter depth)", "sets": 2, "reps": "6"},
            ],
            "cool_down": [
                "Standing quad stretch — 30 sec each",
                "Calf stretch — 30 sec each",
                "Ankle circles — 10 each side",
            ],
        },
        "intermediate": {
            "base_duration": "20-25 min",
            "warm_up": [
                "5 min easy jog",
                "Leg swings — 10 each side",
                "A-skips — 2 x 20m",
            ],
            "exercises": [
                {"name": "Single-Leg Hop (forward)", "sets": 3, "reps": "8 each side"},
                {"name": "Lateral Bound", "sets": 3, "reps": "8 each side"},
                {"name": "Low Box Jump", "sets": 3, "reps": "8"},
                {
                    "name": "Split Squat Jump (alternating)",
                    "sets": 3,
                    "reps": "6 each side",
                },
            ],
            "cool_down": [
                "Pigeon pose — 45 sec each side",
                "Calf stretch — 30 sec each",
                "Standing quad stretch — 30 sec each",
            ],
        },
        "advanced": {
            "base_duration": "20-30 min",
            "warm_up": [
                "5 min easy jog",
                "A-skips — 2 x 20m",
                "B-skips — 2 x 20m",
            ],
            "exercises": [
                {"name": "Depth Drop (from step)", "sets": 3, "reps": "6"},
                {"name": "Single-Leg Bounding", "sets": 3, "reps": "10"},
                {"name": "Jump Squat (full depth)", "sets": 3, "reps": "10"},
                {"name": "Lateral Bound to Stick", "sets": 3, "reps": "8 each side"},
                {"name": "Box Jump (high)", "sets": 3, "reps": "6"},
            ],
            "cool_down": [
                "Pigeon pose — 60 sec each side",
                "Downward dog — 45 sec",
                "Calf stretch — 30 sec each",
            ],
        },
    },
    # ── Trail proprioception & lateral stability ─────────────────────────
    "trail_stability": {
        "beginner": {
            "base_duration": "15-20 min",
            "warm_up": [
                "5 min easy walk on uneven surface",
                "Ankle circles — 10 each side",
                "Single-leg stand — 15 sec each",
            ],
            "exercises": [
                {
                    "name": "Single-Leg Balance (eyes open)",
                    "sets": 3,
                    "reps": "30 sec each side",
                },
                {
                    "name": "Lateral Step-Down (from step)",
                    "sets": 3,
                    "reps": "10 each side",
                },
                {"name": "Slow Eccentric Step-Down", "sets": 3, "reps": "8 each side"},
                {"name": "Calf Raise (single-leg)", "sets": 3, "reps": "12 each side"},
            ],
            "cool_down": [
                "Ankle circles — 10 each side",
                "Calf stretch — 30 sec each",
                "Standing quad stretch — 30 sec each",
            ],
        },
        "intermediate": {
            "base_duration": "20-25 min",
            "warm_up": [
                "5 min easy jog on grass/trail",
                "Ankle circles — 10 each side",
                "Single-leg stand — 20 sec each (eyes closed)",
            ],
            "exercises": [
                {
                    "name": "Single-Leg Balance (eyes closed)",
                    "sets": 3,
                    "reps": "30 sec each side",
                },
                {"name": "Lateral Step-Down (slow)", "sets": 3, "reps": "10 each side"},
                {"name": "Nordic Curl Negative", "sets": 3, "reps": "5"},
                {
                    "name": "Lateral Bounds (stick landing)",
                    "sets": 3,
                    "reps": "8 each side",
                },
                {"name": "Single-Leg Deadlift", "sets": 3, "reps": "10 each side"},
            ],
            "cool_down": [
                "Pigeon pose — 45 sec each side",
                "Calf stretch — 30 sec each",
                "Ankle circles — 10 each side",
            ],
        },
        "advanced": {
            "base_duration": "20-30 min",
            "warm_up": [
                "5 min easy jog on grass/trail",
                "A-skips — 2 x 20m on grass",
                "Single-leg stand — 30 sec each (eyes closed, on pillow)",
            ],
            "exercises": [
                {
                    "name": "Single-Leg Balance on Unstable Surface",
                    "sets": 3,
                    "reps": "30 sec each side",
                },
                {"name": "Nordic Curl", "sets": 3, "reps": "8"},
                {
                    "name": "Pistol Squat (assisted or full)",
                    "sets": 3,
                    "reps": "6 each side",
                },
                {
                    "name": "Lateral Bound to Single-Leg Stick",
                    "sets": 3,
                    "reps": "8 each side",
                },
                {
                    "name": "Depth Drop to Single-Leg Land",
                    "sets": 3,
                    "reps": "6 each side",
                },
            ],
            "cool_down": [
                "Pigeon pose — 60 sec each side",
                "Downward dog — 45 sec",
                "Ankle circles — 10 each side",
            ],
        },
    },
    # ── Flat-trail specific strength (Amsterdam-style prep) ───────────────
    # Builds climb-equivalent durability without hill access: calf/soleus,
    # unilateral leg strength, eccentric quad tolerance, and anti-rotation core.
    "flat_trail_strength": {
        "beginner": {
            "base_duration": "20-30 min",
            "warm_up": [
                "5 min brisk walk",
                "Ankle circles — 10 each side",
                "Bodyweight split squat — 8 each side",
            ],
            "exercises": [
                {"name": "Split Squat", "sets": 3, "reps": "10 each side"},
                {
                    "name": "Step-up (controlled eccentric)",
                    "sets": 3,
                    "reps": "8 each side",
                },
                {"name": "Calf Raise", "sets": 3, "reps": "15"},
                {"name": "Tibialis Raise", "sets": 3, "reps": "12"},
                {"name": "Side Plank", "sets": 2, "reps": "25-30 sec each side"},
            ],
            "cool_down": [
                "Calf stretch — 30 sec each",
                "Standing quad stretch — 30 sec each",
                "Hip flexor stretch — 30 sec each",
            ],
        },
        "intermediate": {
            "base_duration": "25-35 min",
            "warm_up": [
                "5 min easy jog",
                "Leg swings — 10 each side",
                "A-skips — 2 x 20m",
            ],
            "exercises": [
                {"name": "Bulgarian Split Squat", "sets": 3, "reps": "8 each side"},
                {
                    "name": "Single-leg RDL (bodyweight)",
                    "sets": 3,
                    "reps": "10 each side",
                },
                {
                    "name": "Step-down (3 sec lowering)",
                    "sets": 3,
                    "reps": "8 each side",
                },
                {"name": "Single-leg Calf Raise", "sets": 3, "reps": "12 each side"},
                {"name": "Pallof Press (band)", "sets": 3, "reps": "10 each side"},
            ],
            "cool_down": [
                "Pigeon pose — 45 sec each side",
                "Calf stretch — 30 sec each",
                "Ankle mobility rocks — 10 each side",
            ],
        },
        "advanced": {
            "base_duration": "30-40 min",
            "warm_up": [
                "5 min easy jog",
                "A-skips — 2 x 20m",
                "Walking lunge with rotation — 8 each side",
            ],
            "exercises": [
                {
                    "name": "Rear-foot Elevated Split Squat",
                    "sets": 3,
                    "reps": "8 each side",
                },
                {"name": "Single-leg RDL", "sets": 3, "reps": "8 each side"},
                {
                    "name": "Eccentric Step-down (4 sec)",
                    "sets": 3,
                    "reps": "8 each side",
                },
                {"name": "Seated Soleus Raise", "sets": 3, "reps": "15"},
                {"name": "Pallof Press + Hold", "sets": 3, "reps": "8 each side"},
            ],
            "cool_down": [
                "Pigeon pose — 60 sec each side",
                "Calf stretch — 45 sec each",
                "Thoracic rotation stretch — 30 sec each side",
            ],
        },
    },
    # ── Full body ─────────────────────────────────────────────────────────
    "full_body": {
        "beginner": {
            "base_duration": "25-35 min",
            "warm_up": [
                "5 min easy walk",
                "Arm circles — 10 each direction",
                "Leg swings — 10 each side",
            ],
            "exercises": [
                {"name": "Push-ups (or knee push-ups)", "sets": 3, "reps": "8-12"},
                {"name": "Bodyweight Squat", "sets": 3, "reps": "12-15"},
                {"name": "Plank Shoulder Taps", "sets": 3, "reps": "10 each side"},
                {"name": "Glute Bridge", "sets": 3, "reps": "15"},
                {"name": "Reverse Lunge", "sets": 2, "reps": "10 each side"},
            ],
            "cool_down": [
                "Chest stretch — 30 sec",
                "Hamstring stretch — 30 sec each side",
                "Downward dog — 30 sec",
            ],
        },
        "intermediate": {
            "base_duration": "30-40 min",
            "warm_up": [
                "5 min easy jog",
                "Arm circles — 10 each direction",
                "Leg swings — 10 each side",
            ],
            "exercises": [
                {"name": "Push-ups", "sets": 3, "reps": "12-15"},
                {"name": "Split Squat", "sets": 3, "reps": "10 each side"},
                {"name": "Plank", "sets": 3, "reps": "45-60 sec hold"},
                {"name": "Lateral Lunge", "sets": 3, "reps": "10 each side"},
                {"name": "Superman", "sets": 3, "reps": "12"},
            ],
            "cool_down": [
                "Chest stretch — 30 sec",
                "Pigeon pose — 45 sec each side",
                "Downward dog — 30 sec",
            ],
        },
        "advanced": {
            "base_duration": "30-40 min",
            "warm_up": [
                "5 min easy jog",
                "Walking lunges — 10 each side",
                "Arm circles — 10 each direction",
            ],
            "exercises": [
                {"name": "Push-ups", "sets": 3, "reps": "15-20"},
                {"name": "Bulgarian Split Squat", "sets": 3, "reps": "10 each side"},
                {"name": "Plank with Leg Lift", "sets": 3, "reps": "10 each side"},
                {"name": "Jump Squat", "sets": 3, "reps": "12"},
                {"name": "Single-leg Glute Bridge", "sets": 3, "reps": "12 each side"},
            ],
            "cool_down": [
                "Chest stretch — 30 sec",
                "Pigeon pose — 60 sec each side",
                "Downward dog — 45 sec",
            ],
        },
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_phase_focus_rotation(
    phase: str,
    target_distance: float = 0.0,
    trail_profile=None,
) -> List[str]:
    """Return the ordered focus list for a training phase.

    Trail / ultra plans dispatch to a per-elevation-class rotation: flat
    trails get extra plyometric work to replace the missing hill stimulus;
    mountainous routes get stability + plyometric every phase. Falls back
    to the "build" rotation for unknown phases.
    """
    if trail_profile is not None:
        rotations = TRAIL_ROTATIONS_BY_ELEVATION[trail_profile.elevation_class]
        return rotations.get(phase, rotations["build"])
    if target_distance == 30.0:
        return TRAIL_FOCUS_ROTATIONS.get(phase, TRAIL_FOCUS_ROTATIONS["build"])
    return PHASE_FOCUS_ROTATIONS.get(phase, PHASE_FOCUS_ROTATIONS["build"])


def generate_strength_session(
    focus: str,
    phase: str,
    level: str,
    week_number: int,
) -> Dict[str, Any]:
    """Build a strength session dict for embedding into a weekly plan.

    Args:
        focus: "lower_body", "core", or "full_body"
        phase: Training phase — "base", "build", "peak", "taper"
        level: "beginner", "intermediate", or "advanced"
        week_number: 1-indexed week number (unused today but available for
                     future per-week exercise rotation)

    Returns:
        Session dict with keys: type, focus, phase, level, duration,
        warm_up, exercises, cool_down.
    """
    template = _EXERCISES.get(focus, _EXERCISES["full_body"]).get(
        level, _EXERCISES["full_body"]["beginner"]
    )
    modifier = _PHASE_MODIFIERS.get(phase, _PHASE_MODIFIERS["build"])

    # Deep-copy exercises so callers can't mutate the template
    exercises = []
    for ex in template["exercises"]:
        adjusted_sets = max(2, ex["sets"] + modifier["sets_delta"])
        entry: Dict[str, Any] = {
            "name": ex["name"],
            "sets": adjusted_sets,
            "reps": ex["reps"],
        }
        exercises.append(entry)

    # Build duration string with modifier
    duration = template["base_duration"]
    if modifier["duration_delta"]:
        # Parse "25-35 min" → adjust both bounds
        parts = duration.replace(" min", "").split("-")
        if len(parts) == 2:
            lo = max(10, int(parts[0]) + modifier["duration_delta"])
            hi = max(lo + 5, int(parts[1]) + modifier["duration_delta"])
            duration = f"{lo}-{hi} min"

    session: Dict[str, Any] = {
        "type": focus,
        "focus": focus,
        "phase": phase,
        "level": level,
        "duration": duration,
        "warm_up": list(template["warm_up"]),
        "exercises": exercises,
        "cool_down": list(template["cool_down"]),
    }

    if modifier["note"]:
        session["note"] = modifier["note"]

    return session
