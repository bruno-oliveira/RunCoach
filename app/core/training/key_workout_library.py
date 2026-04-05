"""Race-specific key workout library.

Curated workouts that replace generic interval/tempo sessions during
Build and Peak phases to make training plans feel coached, not generated.
"""

from typing import Dict, List, Optional

from app.core.training.hr_zone_calculator import WORKOUT_ZONE_MAP
from app.core.training.vdot_calculator import VDOTCalculator


# ---------------------------------------------------------------------------
# Workout catalogue
# ---------------------------------------------------------------------------
# Each entry:
#   id            – stable identifier for DB storage
#   distances     – list of target_distance values this applies to (km)
#   phases        – training phases where it can appear
#   type          – maps to existing workout_type (interval, tempo, hill)
#   name          – human-readable session name
#   structure     – one-liner summary (shown as subtitle)
#   description   – full workout with warm-up/cool-down
#   intensity     – low / medium / high
#   target_zone   – HR zone (1-5)
#   pace_zone     – VDOT zone key for pace injection (E, M, T, I, R)
#   rationale     – coaching "why" behind this workout
#   terrain       – list of terrain tags: ["any"], ["hilly"], or ["flat"]
#                   (only meaningful for trail workouts; road = ["any"])
# ---------------------------------------------------------------------------

_WORKOUTS: List[Dict] = [
    # ── 5K ─────────────────────────────────────────────────────────────
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

    # ── 10K ────────────────────────────────────────────────────────────
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
        "pace_zone": "T",
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
        "pace_zone": "T",
        "rationale": (
            "Fartlek teaches you to surge and recover without stopping — a "
            "crucial skill for handling pace changes in a 10K race."
        ),
    },

    # ── Half Marathon ──────────────────────────────────────────────────
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

    # ── Marathon ───────────────────────────────────────────────────────
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
            "Yasso 800s are a marathon classic — they boost VO2max while "
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
            "clearance ceiling — the key physiological limiter in a marathon."
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
            "threshold effort — useful for surging past aid stations or hills."
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
            "trains your gut to absorb fuel under exercise stress — a key "
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

    # ── Trail (30.0) ──────────────────────────────────────────────────
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
            "races. Training the technique — and the quads — specifically "
            "prevents race-day blowups on descents."
        ),
    },

    # ── Trail Flat-Terrain Alternatives ───────────────────────────────
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
            "recovery. Focus on driving arms and powerful stride — simulate "
            "the effort of climbing even on flat ground. "
            "2km warm-up, 2km cool-down."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "T",
        "rationale": (
            "Same cardiovascular stimulus as hill repeats — the heart doesn't "
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


class KeyWorkoutLibrary:
    """Provides race-specific key workout selection for plan generation."""

    @classmethod
    def get_for_phase(
        cls,
        target_distance: float,
        phase: str,
        week_in_phase: int,
        workout_type: str = "interval",
        terrain: Optional[str] = None,
    ) -> Optional[Dict]:
        """Select a key workout for the given distance, phase, and week.

        Args:
            target_distance: Race distance in km.
            phase:           Training phase (base, build, peak, taper).
            week_in_phase:   Zero-indexed week within the current phase.
            workout_type:    Requested workout type (interval, tempo, hill).
            terrain:         Terrain access ('flat' or None/hilly). Only
                             affects trail (30km) workout selection.

        Returns:
            A workout dict or None if no key workout applies.
        """
        # Key workouts only during build and peak
        if phase not in ("build", "peak"):
            return None

        candidates = [
            w for w in _WORKOUTS
            if target_distance in w["distances"]
            and phase in w["phases"]
            and w["type"] == workout_type
        ]

        # Filter by terrain for trail workouts
        if terrain == "flat":
            candidates = [w for w in candidates if "flat" in w.get("terrain", ["any"])]
        else:
            candidates = [
                w for w in candidates
                if "any" in w.get("terrain", ["any"])
                or "hilly" in w.get("terrain", ["any"])
            ]

        if not candidates:
            return None

        # Rotate through candidates using week_in_phase
        return candidates[week_in_phase % len(candidates)]

    @classmethod
    def get_all_for_distance(cls, target_distance: float, terrain: Optional[str] = None) -> List[Dict]:
        """Return all key workouts for a race distance."""
        workouts = [w for w in _WORKOUTS if target_distance in w["distances"]]
        if terrain == "flat":
            workouts = [w for w in workouts if "flat" in w.get("terrain", ["any"])]
        elif terrain is not None:
            workouts = [
                w for w in workouts
                if "any" in w.get("terrain", ["any"])
                or "hilly" in w.get("terrain", ["any"])
            ]
        return workouts

    @classmethod
    def inject_vdot_paces(cls, workout: Dict, vdot_zones: Optional[Dict]) -> Dict:
        """Enrich a workout description with specific VDOT-based paces.

        Args:
            workout:    Workout dict (not mutated — returns a copy).
            vdot_zones: Output of ``VDOTCalculator.get_pace_zones()``.

        Returns:
            Copy of workout with pace-enriched description.
        """
        if not vdot_zones:
            return workout

        enriched = dict(workout)
        enriched["description"] = VDOTCalculator.inject_paces_into_description(
            enriched["description"], vdot_zones, enriched["type"]
        )
        enriched["structure"] = VDOTCalculator.inject_paces_into_description(
            enriched["structure"], vdot_zones, enriched["type"]
        )
        return enriched
