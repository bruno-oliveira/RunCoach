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
    # -- Base-phase light quality --------------------------------------------
    # Low-cost neuromuscular / light-aerobic work that maintains leg speed and
    # form during the aerobic build WITHOUT taxing it. These fill the single
    # base-phase quality slot the distribution already schedules. They are
    # deliberately easy: strides and relaxed fartlek, never threshold/VO2max.
    {
        "id": "base_strides",
        "distances": [5.0, 10.0, 21.1, 42.2],
        "phases": ["base"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Easy Run + Strides",
        "structure": "easy run + 6 × 20s strides",
        "description": (
            "Run easy for the bulk of the session, then finish with 6 × 20 "
            "second strides: accelerate smoothly to about 5K-mile effort, hold "
            "relaxed fast form, then walk/jog 60 seconds to full recovery "
            "between each. Strides are about turnover and form, not lung-burn."
        ),
        "intensity": "low",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Strides keep your legs quick and your form sharp through the "
            "aerobic base without adding hard aerobic load. A handful of short "
            "accelerations a week means you don't arrive at the build phase "
            "flat-footed after weeks of only easy running."
        ),
    },
    {
        "id": "base_light_fartlek",
        "distances": [5.0, 10.0, 21.1, 42.2],
        "phases": ["base"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Relaxed Fartlek",
        "structure": "easy run with 6 × (1 min relaxed-quick / 2 min easy)",
        "description": (
            "Within an easy run, play with 6 × (1 minute relaxed-quick / "
            "2 minutes easy). 'Relaxed-quick' is comfortably faster than easy "
            "— think 10K-to-half effort, not a sprint. The long easy floats "
            "keep the whole session aerobic."
        ),
        "intensity": "low",
        "target_zone": 3,
        "pace_zone": "10K",
        "rationale": (
            "A relaxed fartlek nudges the aerobic system and rehearses changing "
            "gears, while the generous easy floats keep it base-appropriate. "
            "It breaks up the monotony of steady base mileage without stealing "
            "from recovery."
        ),
    },
    {
        "id": "base_relaxed_cruise",
        "distances": [21.1, 42.2],
        "phases": ["base"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Relaxed Cruise",
        "structure": "easy run + 2 × 6 min steady (marathon effort)",
        "description": (
            "Warm up easy, then run 2 × 6 minutes at steady marathon effort "
            "with 2 minutes easy between — comfortably controlled, never "
            "straining. Cool down easy. This is an introduction to sustained "
            "effort, not a threshold session."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "Short steady blocks at marathon effort start building the "
            "muscular endurance you'll lean on later, while staying gentle "
            "enough to fit inside the aerobic base without compromising it."
        ),
    },
    {
        "id": "base_hill_strides",
        "distances": [5.0, 10.0, 21.1, 42.2],
        "phases": ["base"],
        "type": "hill",
        "terrain": ["any"],
        "name": "Easy Run + Hill Strides",
        "structure": "easy run + 6 × 15s hill strides",
        "description": (
            "On an easy run, finish with 6 × 15 second hill strides on a "
            "moderate grade (4-6%): drive up smoothly and powerfully for 15 "
            "seconds, then walk down fully recovered before the next. Strong "
            "but never all-out."
        ),
        "intensity": "low",
        "target_zone": 2,
        "pace_zone": "R",
        "rationale": (
            "Hill strides build strength and power with almost no aerobic or "
            "impact cost — the gradient does the work in a few seconds. A "
            "perfect base-phase way to prime the legs for the climbing and "
            "speed work to come."
        ),
    },
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
        "structure": "6 x (3min at 10K pace / 2min easy) within a 7km run",
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
    {
        "id": "10k_over_unders",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Threshold Over-Unders",
        "structure": "5 × (1 min just over threshold / 2 min just under), continuous",
        "description": (
            "Warm up 2km easy. Run a continuous block of 5 × (1 min just "
            "over threshold pace / 2 min just under threshold pace) — no easy "
            "jog between, stay working the whole time. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Over-unders push lactate production during the 'over' and force "
            "your body to clear it while still running hard during the 'under'. "
            "This raises the pace you can hold at threshold — the single biggest "
            "lever for 10K-to-half performance."
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
    {
        "id": "half_over_unders",
        "distances": [21.1],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Threshold Over-Unders",
        "structure": "6 × (90s just over threshold / 2.5 min just under), continuous",
        "description": (
            "Warm up 2km easy. Run a continuous block of 6 × (90 sec just "
            "over threshold / 2.5 min just under threshold) — no easy jog "
            "between, hold the effort the whole way through. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "At half-marathon distance, the limiter is how long you can sit "
            "just under threshold. Over-unders teach you to absorb a surge and "
            "settle back to goal pace without blowing up — exactly what a hilly "
            "or surging race demands."
        ),
    },
]

# Combined list of all workouts
WORKOUTS: List[Dict] = _WORKOUTS_SHORT + WORKOUTS_LONG
