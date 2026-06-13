"""Road key workout definitions: 5K / 10K / Half / Marathon.

Long-run variants (``type: "long"``) carry a ``steps_builder`` field resolved at
request time. See key_workout_data.py for full field documentation.
"""

from typing import Dict, List

ROAD_LONG: List[Dict] = [
    # -- Long-run variants (Half Marathon) --
    {
        "id": "half_long_alternating_mp",
        "distances": [21.1],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["any"],
        "name": "Alternating Marathon-Pace Long",
        "structure": "Long run alternating 2km easy / 2km at marathon pace",
        "description": (
            "Run your long-run distance alternating 2 km easy and 2 km at "
            "marathon pace. No rest between blocks. The switching rehearses "
            "race-pace discipline on fatigued legs."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "Blends aerobic volume with race-pace specificity in a single "
            "session. The forced switch between paces trains mental focus."
        ),
        "steps_builder": "alternating_mp",
    },
    {
        "id": "half_long_fast_finish",
        "distances": [21.1],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["any"],
        "name": "Fast-Finish Long Run",
        "structure": "Long run with the last 3 km at threshold pace",
        "description": (
            "Run your long-run distance with the first portion at easy pace, "
            "then accelerate into the final 3 km at threshold pace. "
            "Build effort into the last kilometer."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "T",
        "rationale": (
            "Fast-finish runs teach your legs to change gears when tired — "
            "the biggest predictor of a strong negative-split race."
        ),
        "steps_builder": "fast_finish",
    },
    {
        "id": "half_long_rolling_hills",
        "distances": [21.1],
        "phases": ["build"],
        "type": "long",
        "terrain": ["any"],
        "name": "Rolling Hills Long Run",
        "structure": "Long run on a rolling hills route at even effort",
        "description": (
            "Run your long-run distance on a rolling hills route. "
            "Keep effort even — push on the climbs, float on the descents. "
            "Do NOT chase pace on the flats."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "Even on a flat race course, rolling-hill long runs build "
            "stride-cycle strength and cardiovascular variability that "
            "flat-only runs can't replicate."
        ),
        "steps_builder": "rolling_hills",
    },
    # -- Long-run variants (Marathon) --
    {
        "id": "marathon_long_alternating_mp",
        "distances": [42.2],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["any"],
        "name": "Alternating Marathon-Pace Long",
        "structure": "Long run alternating 3km easy / 3km at marathon pace",
        "description": (
            "Run your long-run distance alternating 3 km easy and 3 km at "
            "marathon pace. No stops. The back-to-back pace changes simulate "
            "late-race moments where you must hold form."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "M",
        "rationale": (
            "A classic Runna/Daniels-style workout. Gets race-pace volume "
            "into a long run without running it all fast — lower injury risk, "
            "higher specificity."
        ),
        "steps_builder": "alternating_mp_3k",
    },
    {
        "id": "marathon_long_fast_finish",
        "distances": [42.2],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["any"],
        "name": "Fast-Finish Long Run",
        "structure": "Long run with the last 4 km at threshold pace",
        "description": (
            "Run your long-run distance easy, then finish with the last 4 km "
            "at threshold pace. Build effort kilometer by kilometer — the "
            "last km should be your fastest."
        ),
        "intensity": "medium",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Running fast on fatigued legs teaches the specific neuromuscular "
            "and metabolic skill of finishing a marathon strong."
        ),
        "steps_builder": "fast_finish_4k",
    },
    {
        "id": "marathon_long_depletion",
        "distances": [42.2],
        "phases": ["build"],
        "type": "long",
        "terrain": ["any"],
        "name": "Depletion Long Run",
        "structure": "Fasted long run at easy effort — water only",
        "description": (
            "Run your long-run distance fasted (pre-breakfast). Water only "
            "during the run — no carbs. Keep effort conservative; run slower "
            "than your normal long-run pace."
        ),
        "intensity": "low",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Depletion runs drive mitochondrial adaptation and fat oxidation "
            "— a critical but often-missed training stimulus for marathoners."
        ),
        "steps_builder": "depletion",
    },
    {
        "id": "marathon_long_rolling_hills",
        "distances": [42.2],
        "phases": ["build"],
        "type": "long",
        "terrain": ["any"],
        "name": "Rolling Hills Long Run",
        "structure": "Long run on a rolling hills route at steady effort",
        "description": (
            "Run your long-run distance on a rolling hills route. Hold even "
            "effort throughout — the hills become natural fartlek intervals "
            "without breaking rhythm."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "Rolling terrain forces natural effort variation and recruits "
            "muscle fibers that flat running misses — making you more "
            "resilient on race day, regardless of course profile."
        ),
        "steps_builder": "rolling_hills",
    },
    # -- Long-run variants (10K) --
    {
        "id": "10k_long_fast_finish",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["any"],
        "name": "Fast-Finish Long Run",
        "structure": "Long run with the last 2 km at threshold pace",
        "description": (
            "Run your long-run distance easy, then finish with the last 2 km "
            "at threshold pace. A miniature version of the classic "
            "marathon fast-finish long run."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "T",
        "rationale": (
            "Short fast-finish long runs develop the 10K-specific skill of "
            "holding form when tired — exactly what you need in the final 2 km."
        ),
        "steps_builder": "fast_finish_2k",
    },
    # -- Marathon --
    {
        "id": "marathon_mp_long",
        "distances": [42.2],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Marathon-Pace Long Run",
        "structure": "25km: first 15km easy, last 10km at marathon pace",
        "description": (
            "Run 25km total. First 15km at easy pace, then shift to "
            "marathon goal pace for the final 10km. Take a gel at 8km "
            "and 16km to practice race fueling."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "The gold-standard marathon workout. Running 10km at MP on "
            "tired legs simulates the last third of race day."
        ),
    },
    {
        "id": "marathon_yasso_800s",
        "distances": [42.2],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Yasso 800s",
        "structure": "8-10 x 800m at VO2max pace with equal-time recovery jog",
        "description": (
            "Warm up 2km easy. Run 8-10 x 800m at VO2max pace. "
            "Recovery jog between reps should take the same time as the "
            "rep itself. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "Yasso 800s are a marathon classic -- they boost VO2max while "
            "providing a rough predictor of marathon finishing time."
        ),
    },
    {
        "id": "marathon_km_intervals",
        "distances": [42.2],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "10K-Pace Intervals",
        "structure": "5-7 x ~1km at 10K pace with 90s jog recovery",
        "description": (
            "Warm up 2km easy. Run 6 x 1km at 10K goal pace with 90 sec easy "
            "jog recovery between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "A speed-reserve session that keeps fast running in the legs "
            "through a marathon block. Rotated with Yasso 800s, it gives the "
            "build phase two distinct interval days instead of one repeated."
        ),
    },
    {
        "id": "marathon_progressive_long",
        "distances": [42.2],
        "phases": ["build"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Progressive Long Run",
        "structure": "28-30km: first 20km easy, last 8-10km descending pace",
        "description": (
            "Run 28-30km. First 20km at easy pace. Then run each "
            "subsequent 2km segment 5-10s/km faster, finishing the last "
            "2km at marathon pace. Practice fueling every 5km."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "Long progressive runs build the aerobic endurance AND the "
            "pacing discipline to finish strong on race day."
        ),
    },
    {
        "id": "marathon_tempo_cutdown",
        "distances": [42.2],
        "phases": ["peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Lactate-Clearing Tempo",
        "structure": "2 x 5km at threshold pace with 3min recovery",
        "description": (
            "Warm up 3km easy. Run 2 x 5km at threshold pace with "
            "3 min easy jog recovery. Cool down 3km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Extended tempo work at threshold pace raises your lactate "
            "clearance ceiling -- the key physiological limiter in a marathon."
        ),
    },
    {
        "id": "marathon_over_unders",
        "distances": [42.2],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Threshold Over-Unders",
        "structure": "6 x (2 min just over threshold / 3 min just under), continuous",
        "description": (
            "Warm up 3km easy. Run a continuous block of 6 x (2 min just over "
            "threshold / 3 min just under threshold) -- no easy jog between, "
            "hold the effort throughout. Cool down 3km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Over-unders raise the pace you can hold at threshold and teach "
            "lactate clearance on the move -- so marathon pace settles into a "
            "comfortable rhythm well below your new ceiling."
        ),
    },
    {
        "id": "marathon_mp_cutdown",
        "distances": [42.2],
        "phases": ["peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Race-Pace Cut-Down",
        "structure": "5 x 2km: alternate MP and T-pace with 90s recovery",
        "description": (
            "Warm up 2km easy. Run 5 x 2km alternating between "
            "marathon pace and threshold pace, with 90s jog recovery "
            "between each. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Teaches your body to switch between marathon cruising and "
            "threshold effort -- useful for surging past aid stations or hills."
        ),
    },
    {
        "id": "marathon_easy_long_fueling",
        "distances": [42.2],
        "phases": ["build"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Easy Long with Fueling",
        "structure": "30-32km all easy pace, practice nutrition every 5km",
        "description": (
            "Run 30-32km at easy conversational pace. Take a gel or fuel "
            "every 5km starting at km 10. Practice your exact race-day "
            "nutrition strategy. Walk 1 min after each fuel stop if needed."
        ),
        "intensity": "low",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "The longest run in marathon prep. Builds aerobic endurance and "
            "trains your gut to absorb fuel under exercise stress -- a key "
            "limiter in marathon performance."
        ),
    },
    {
        "id": "marathon_peak_progressive",
        "distances": [42.2],
        "phases": ["peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Peak Progressive Long",
        "structure": "28km: first 16km easy, last 12km descending to marathon pace",
        "description": (
            "Run 28km total. First 16km at easy pace. Then run each "
            "subsequent 3km segment 5-10s/km faster, finishing the last "
            "3km at marathon pace. Take gels at km 8 and km 20."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "The capstone workout before taper. A longer finish-fast segment "
            "than the build-phase progressive run teaches your body to run "
            "marathon pace on deeply fatigued legs."
        ),
    },
]
