"""Race-specific key workout definitions.

Curated workouts that replace generic interval/tempo sessions during
Build and Peak phases to make training plans feel coached, not generated.

Each entry:
  id            - stable identifier for DB storage
  distances     - list of target_distance values this applies to (km)
  phases        - training phases where it can appear
  type          - maps to existing workout_type (interval, tempo, hill)
  name          - human-readable session name
  structure     - one-liner summary (shown as subtitle)
  description   - full workout with warm-up/cool-down
  intensity     - low / medium / high
  target_zone   - HR zone (1-5)
  pace_zone     - VDOT zone key for pace injection (E, M, T, I, R)
  rationale     - coaching "why" behind this workout
  terrain       - list of terrain tags: ["any"], ["hilly"], or ["flat"]
                  (only meaningful for trail workouts; road = ["any"])
"""

from typing import Dict, List

from app.core.training.key_workout_data_long import WORKOUTS_LONG

# Short-distance workouts (5K, 10K, Half Marathon)
_WORKOUTS_SHORT: List[Dict] = [
    # -- 5K --
    {
        "id": "5k_vo2max_400s",
        "distances": [5.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "VO2max 400m Repeats",
        "structure": "10-12 x 400m at 5K pace with 90s recovery jogs",
        "description": (
            "Warm up 2km easy. Run 10-12 x 400m at 5K pace with 90s easy jog "
            "recovery between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "Develops VO2max and running economy at race-specific speed. "
            "Short reps keep form sharp while accumulating time at intensity."
        ),
    },
    {
        "id": "5k_race_pace_3km",
        "distances": [5.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Race-Pace 3km Block",
        "structure": "2 x 1.5km at 5K goal pace with 3min recovery",
        "description": (
            "Warm up 2km easy. Run 2 x 1.5km at 5K goal pace with 3 min "
            "easy jog recovery. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "I",
        "rationale": (
            "Teaches you to sustain 5K race pace in extended blocks. "
            "Builds confidence for holding pace in the middle km of the race."
        ),
    },
    {
        "id": "5k_cruise_intervals",
        "distances": [5.0],
        "phases": ["build"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Cruise Intervals",
        "structure": "4 x 1km at threshold pace with 60s recovery",
        "description": (
            "Warm up 2km easy. Run 4 x 1km at threshold pace with "
            "60 seconds easy jog between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Accumulates threshold-pace volume in manageable chunks. "
            "Builds the lactate clearance capacity that underpins 5K racing."
        ),
    },
    {
        "id": "5k_threshold_run",
        "distances": [5.0],
        "phases": ["build"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Threshold Run",
        "structure": "3km continuous at threshold pace",
        "description": (
            "Warm up 2km easy. Run 3km continuous at threshold pace — "
            "comfortably hard, you can speak a few words at a time. "
            "Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "A sustained threshold effort trains your body to clear lactate "
            "at a faster pace — the key limiter in 5K performance."
        ),
    },
    {
        "id": "5k_hill_sprints",
        "distances": [5.0],
        "phases": ["build"],
        "type": "hill",
        "terrain": ["any"],
        "name": "Short Hill Sprints",
        "structure": "8-10 x 60s uphill at hard effort with jog-back recovery",
        "description": (
            "Warm up 2km easy. Find a moderate hill (4-6% grade). "
            "Run 8-10 x 60 seconds hard uphill with easy jog back down. "
            "Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "R",
        "rationale": (
            "Develops explosive power and neuromuscular recruitment. "
            "Hill sprints build race-finishing strength with low injury risk."
        ),
    },
    {
        "id": "5k_pyramid",
        "distances": [5.0],
        "phases": ["peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Pyramid Intervals",
        "structure": "200-400-600-800-600-400-200m at 5K pace",
        "description": (
            "Warm up 2km easy. Run pyramid: 200m, 400m, 600m, 800m, 600m, "
            "400m, 200m — all at 5K pace with equal-distance recovery jogs. "
            "Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "The ascending/descending structure teaches pace control across "
            "varying distances — exactly what you'll need in the final km."
        ),
    },

    # -- 10K --
    {
        "id": "10k_cruise_intervals",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Cruise Intervals",
        "structure": "4 x 1.5km at threshold pace with 60s recovery",
        "description": (
            "Warm up 2km easy. Run 4 x 1.5km at threshold pace with "
            "60 seconds easy jog between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Cruise intervals accumulate time at lactate threshold with brief "
            "recoveries, improving your body's ability to clear lactate at 10K pace."
        ),
    },
    {
        "id": "10k_goal_pace_segments",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "10K Goal-Pace Segments",
        "structure": "2 x 3km at 10K goal pace with 3min recovery",
        "description": (
            "Warm up 2km easy. Run 2 x 3km at 10K goal pace with 3 min "
            "standing recovery. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "Practicing sustained race-pace efforts builds the muscular "
            "endurance and mental confidence to hold pace for the full 10K."
        ),
    },
    {
        "id": "10k_tempo_progression",
        "distances": [10.0],
        "phases": ["peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Tempo Progression",
        "structure": "5km starting at easy pace, finishing at 10K pace",
        "description": (
            "Warm up 2km easy. Run 5km as a progression: first km at easy "
            "pace, each subsequent km 10-15 sec/km faster, finishing last km "
            "at 10K goal pace. Cool down 2km easy."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "T",
        "rationale": (
            "Teaches negative-split execution. Running faster on tired legs "
            "mirrors the discipline needed in the second half of a 10K."
        ),
    },
    {
        "id": "10k_fartlek",
        "distances": [10.0],
        "phases": ["build"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Structured Fartlek",
        "structure": "6 x (3min hard / 2min easy) within a 7km run",
        "description": (
            "Warm up 2km easy. Within a continuous run, alternate "
            "6 x (3 min at 10K pace / 2 min easy jog). Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "Fartlek teaches you to surge and recover without stopping — a "
            "crucial skill for handling pace changes in a 10K race."
        ),
    },

    # -- Half Marathon --
    {
        "id": "half_progressive_long",
        "distances": [21.1],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Progressive Long Run",
        "structure": "14-16km: first 10km easy, last 4-6km at marathon pace",
        "description": (
            "Run 14-16km total. Start at easy pace for 10km, then "
            "increase to marathon pace for the final 4-6km. "
            "No warm-up needed — the easy start IS the warm-up."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "The progressive finish teaches your legs to push harder when "
            "tired — exactly what you'll need in the second half of the race."
        ),
    },
    {
        "id": "half_threshold_cruise",
        "distances": [21.1],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Threshold Cruise",
        "structure": "3 x 2km at threshold pace with 90s recovery",
        "description": (
            "Warm up 2km easy. Run 3 x 2km at threshold pace with "
            "90 seconds easy jog recovery. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Extended threshold efforts raise the pace you can sustain for "
            "the full half marathon distance."
        ),
    },
    {
        "id": "half_race_pace_segments",
        "distances": [21.1],
        "phases": ["peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Half Marathon Pace Segments",
        "structure": "3 x 3km at half marathon goal pace with 2min recovery",
        "description": (
            "Warm up 2km easy. Run 3 x 3km at half marathon goal pace "
            "with 2 min easy jog recovery. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "Rehearses race pace in controlled segments. Total race-pace "
            "volume approaches half the race distance for maximum specificity."
        ),
    },
    {
        "id": "half_cutdown_long",
        "distances": [21.1],
        "phases": ["build"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Cut-Down Long Run",
        "structure": "15km: each 5km segment 15s/km faster than the last",
        "description": (
            "Run 15km in three 5km segments. Segment 1 at easy pace, "
            "segment 2 at 15s/km faster, segment 3 at marathon pace."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "Builds the pacing discipline to run a negative split. "
            "Each segment teaches your body to run faster on accumulating fatigue."
        ),
    },

]

# Combined list of all workouts
WORKOUTS: List[Dict] = _WORKOUTS_SHORT + WORKOUTS_LONG
