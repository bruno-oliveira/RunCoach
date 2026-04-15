"""Marathon and trail key workout definitions.

See key_workout_data.py for the full field documentation.

Long-run variants (`type: "long"`) carry a `steps_builder` field that points
to a callable in `workout_steps` — KeyWorkoutLibrary resolves it at request
time so we don't duplicate step definitions across entries.
"""

from typing import Dict, List

WORKOUTS_LONG: List[Dict] = [
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

    # -- Trail (30.0) --
    {
        "id": "trail_elevation_repeats",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "hill",
        "terrain": ["hilly"],
        "name": "Elevation Gain Repeats",
        "structure": "6-8 x 3min uphill at hard effort with jog-back recovery",
        "description": (
            "Warm up 2km easy on flat. Find a trail hill (6-10% grade). "
            "Run 6-8 x 3 min hard uphill, focusing on driving arms and "
            "short stride. Jog back down for recovery. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "T",
        "rationale": (
            "Trail races are won on the climbs. Uphill repeats build "
            "the specific leg strength and cardiovascular capacity for "
            "sustained climbing."
        ),
    },
    {
        "id": "trail_time_on_feet",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["hilly"],
        "name": "Time-on-Feet Long Run",
        "structure": "2.5-3 hours on trails at easy effort, walk steep uphills",
        "description": (
            "Run 2.5-3 hours on trails at easy conversational effort. "
            "Walk steep uphills (>15% grade) to conserve energy. "
            "Practice race fueling every 30 min. Focus on time, not pace."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Trail races reward time on feet over speed. This builds the "
            "muscular endurance and fueling discipline for all-day efforts."
        ),
    },
    {
        "id": "trail_technical_terrain",
        "distances": [30.0],
        "phases": ["build"],
        "type": "interval",
        "terrain": ["hilly"],
        "name": "Technical Trail Session",
        "structure": "8km on technical terrain with rocks/roots at moderate effort",
        "description": (
            "Find a technical trail with rocks, roots, and uneven surface. "
            "Run 8km at moderate effort, focusing on foot placement, "
            "quick cadence, and staying light on your feet. "
            "Practice downhill technique: lean slightly forward, quick turnover."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "Technical proficiency prevents falls and saves energy on race "
            "day. Running on varied terrain trains proprioception and agility."
        ),
    },
    {
        "id": "trail_power_hike",
        "distances": [30.0],
        "phases": ["peak"],
        "type": "hill",
        "terrain": ["hilly"],
        "name": "Power-Hike Intervals",
        "structure": "5 x 5min power hiking steep uphill, run flat/down between",
        "description": (
            "On a hilly trail loop: power-hike steep uphills for 5 min "
            "(arms pumping, long strides), then run the flats and downhills. "
            "Repeat 5 times. Total session 60-75 min."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "In long trail races, walking uphills IS the race strategy. "
            "This trains efficient power hiking while maintaining running "
            "rhythm on flat/descending sections."
        ),
    },
    {
        "id": "trail_back_to_back",
        "distances": [30.0],
        "phases": ["peak"],
        "type": "tempo",
        "terrain": ["hilly"],
        "name": "Back-to-Back Long Runs",
        "structure": "Saturday 20-22km + Sunday 15-18km, both easy on trails",
        "description": (
            "Saturday: 20-22km trail run at easy effort on hilly terrain. "
            "Sunday: 15-18km trail run at easy effort on fatigued legs. "
            "Practice race fueling on both days. The second day simulates "
            "late-race fatigue better than any single long run."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Back-to-back long runs are the hallmark of trail/ultra training. "
            "Running on tired legs from the previous day simulates the final "
            "hours of a 30km trail race."
        ),
    },
    {
        "id": "trail_downhill_technique",
        "distances": [30.0],
        "phases": ["build"],
        "type": "interval",
        "terrain": ["hilly"],
        "name": "Downhill Technique Repeats",
        "structure": "6-8 x 400-600m downhill repeats (5-8% grade), hike up",
        "description": (
            "Find a trail descent (5-8% grade, 400-600m). Run 6-8 downhill "
            "repeats focusing on: quick cadence, slight forward lean, and "
            "soft landings. Hike back up for recovery. 2km warm-up, "
            "2km cool-down on flat."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "Downhill running causes the most eccentric muscle damage in trail "
            "races. Training the technique -- and the quads -- specifically "
            "prevents race-day blowups on descents."
        ),
    },

    # -- Trail Flat-Terrain Alternatives --
    {
        "id": "trail_flat_surge_fartlek",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Trail Surge Fartlek",
        "structure": "60-75 min with 8 x 3min hard surges / 2min easy recovery",
        "description": (
            "On varied terrain (grass, dirt path, or trail). Run 8 x 3 min "
            "at hill-repeat effort level (Zone 4-5) with 2 min easy jog "
            "recovery. Focus on driving arms and powerful stride -- simulate "
            "the effort of climbing even on flat ground. "
            "2km warm-up, 2km cool-down."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "T",
        "rationale": (
            "Same cardiovascular stimulus as hill repeats -- the heart doesn't "
            "know it's flat. Effort-matched surges drive VO2max adaptation "
            "without requiring elevation."
        ),
    },
    {
        "id": "trail_flat_soft_surface",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Soft-Surface Time-on-Feet",
        "structure": "2.5-3 hours on grass/dirt/sand at easy effort, fuel every 30min",
        "description": (
            "Find the softest running surface available: grass fields, dirt "
            "trails, beach, gravel paths. Run 2.5-3 hours at easy effort. "
            "The soft surface increases energy cost 10-15% vs pavement, "
            "partially compensating for lack of elevation. Walk 2 min every "
            "45 min. Practice race fueling."
        ),
        "intensity": "low",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Soft-surface running increases metabolic demand closer to trail "
            "effort. Builds time-on-feet endurance without hills."
        ),
    },
    {
        "id": "trail_flat_power_walk",
        "distances": [30.0],
        "phases": ["peak"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Power-Walk Intervals",
        "structure": "60 min: 5min max-effort power walk / 5min easy run x 6",
        "description": (
            "Alternate 5 min of maximum-effort power walking (pumping arms, "
            "longest possible stride) with 5 min easy running x 6 sets. "
            "Total 60 min. Max-effort power walking at 9-10 min/km builds "
            "the specific muscular endurance for race-day hiking sections."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "Power-hiking efficiency is independent of terrain. The walk-run "
            "transition that defines trail racing can be trained on flat ground."
        ),
    },
    {
        "id": "trail_flat_proprioception",
        "distances": [30.0],
        "phases": ["build"],
        "type": "interval",
        "terrain": ["flat"],
        "name": "Proprioception Circuit Run",
        "structure": "8km on varied surfaces + 4 x agility circuit",
        "description": (
            "Run 8km alternating surfaces every 1-2km: pavement, grass, "
            "gravel, dirt. Every 2km, stop for a 2-min agility circuit: "
            "10 single-leg hops each side, 20m lateral shuffles, "
            "20m backward running. Trains the foot-ankle proprioception "
            "that technical trail demands."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "Proprioception training transfers to technical terrain even when "
            "trained on flat varied surfaces. Reduces ankle sprain risk on "
            "race day."
        ),
    },
]
