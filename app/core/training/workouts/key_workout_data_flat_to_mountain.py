"""Quality sessions from the Flat to Mountain library, for custom plans.

These are the book's sessions the catalog did not already hold. Every one is
``custom_only``: a runner building their own plan may choose it, but the
automatic rotation never installs it (``_CUSTOM_ONLY_IDS`` in
``key_workout_library.selection``), so adding them changed no existing plan.

They are written on the catalog's rep families (``_CANONICAL_SPECS``, the
fartlek builder) so the prose, the structure line and the watch steps are all
derived from the same distance, like every other key workout. Field
documentation: ``key_workout_data``.
"""

from typing import Dict, List

# Every road distance plus the trail sentinel: these sessions are paced off the
# runner's own VDOT zones, so they suit any goal.
_ANY_GOAL = [5.0, 10.0, 21.1, 42.2, 30.0]

FLAT_TO_MOUNTAIN: List[Dict] = [
    {
        "id": "ftm_800s",
        "custom_only": True,
        "distances": _ANY_GOAL,
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "800s (the Classic)",
        "structure": "800m repeats at 5K effort, equal-time jog",
        "description": (
            "Warm up easy. Run 800m repeats at 5K effort with an equal-time easy "
            "jog between reps. Cool down easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "The sweet spot between quality and volume: each rep is a three-to-"
            "four-minute climb in disguise. If 1 km reps keep fading in the last "
            "200m, run these for a few weeks and go back."
        ),
    },
    {
        "id": "ftm_km_cutdowns",
        "custom_only": True,
        "distances": _ANY_GOAL,
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Cut-Downs",
        "structure": "1km repeats from threshold, each a little faster",
        "description": (
            "Warm up easy. Run 1km repeats starting at threshold effort and "
            "running each one a little faster, with an easy jog between reps. "
            "Cool down easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Finishing faster than you start is the signature of a well-raced "
            "course. Practise accelerating on tired legs and it will be there "
            "in the final kilometres."
        ),
    },
    {
        "id": "ftm_three_minute_repeats",
        "custom_only": True,
        "distances": _ANY_GOAL,
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "3-Minute Repeats",
        "structure": "3 min hard / 2 min easy jog, by feel",
        "description": (
            "Warm up easy. Run 3 min hard at 5K effort / 2 min easy jog, by feel. "
            "Cool down easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "The purest effort-based VO2max session: no track, no GPS accuracy "
            "needed, and it trains the internal pacing clock you race by."
        ),
    },
    {
        "id": "ftm_kenyan_fartlek",
        "custom_only": True,
        "distances": _ANY_GOAL,
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Kenyan Fartlek",
        "structure": "1 min hard / 1 min easy, continuous",
        "description": (
            "Warm up easy. Alternate 1 min hard / 1 min easy as one continuous "
            "block, effort by feel. Cool down easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "A big aerobic-power dose with nothing to measure. The floats never "
            "fully recover you — exactly how your legs feel mid-race."
        ),
    },
    {
        "id": "ftm_broken_tempo",
        "custom_only": True,
        "distances": _ANY_GOAL,
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Broken Tempo",
        "structure": "2 threshold blocks with a short easy jog between",
        "description": (
            "Warm up easy. Run two blocks at threshold effort with a 3-minute "
            "easy jog between them. Cool down easy."
        ),
        "intensity": "medium",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Threshold work that fits real life. The second block on slightly "
            "tired legs quietly rehearses fatigue resistance."
        ),
    },
    {
        "id": "ftm_hour_of_power",
        "custom_only": True,
        "distances": _ANY_GOAL,
        "phases": ["peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Hour of Power",
        "structure": "3 threshold blocks, 3 min easy jog between",
        "description": (
            "Warm up easy. Run three blocks at threshold effort with a 3-minute "
            "easy jog between them. Cool down easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "The peak-phase graduation exam: the biggest sustainable-effort dose "
            "in the book. Keep an easy day either side of it."
        ),
    },
]
