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
    # -- Taper sharpeners ----------------------------------------------------
    # One per race-distance family so the taper isn't the same generic cruise
    # template for every plan. Deliberately duration-based (no literal
    # distances in the prose) so they fit any race-week slot: the easy bulk
    # absorbs the budget, the touches keep the legs primed without fatigue.
    {
        "id": "taper_5k10k_sharpener",
        "distances": [5.0, 10.0],
        "phases": ["taper"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Race-Pace Touches + Strides",
        "structure": "easy run + 4 × 1 min at goal race effort + 4 × 20-second strides",
        "description": (
            "Run easy for most of the session, then touch goal race effort "
            "4 times for 1 minute each, with 2 minutes very easy between. "
            "Finish with 4 × 20-second relaxed strides, walking or jogging a "
            "minute between each. Crisp but never taxing — you should end "
            "feeling springy, not worked."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "10K",
        "rationale": (
            "The taper's job is freshness without flatness. A minute at race "
            "effort is long enough to rehearse the rhythm and short enough to "
            "cost nothing, and strides keep turnover sharp for race day."
        ),
    },
    {
        "id": "taper_half_sharpener",
        "distances": [21.1],
        "phases": ["taper"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Half-Marathon Pace Touches",
        "structure": "easy run + 2 × 5 min at half-marathon effort",
        "description": (
            "Run easy for most of the session, then settle into half-marathon "
            "effort twice for 5 minutes each, with 2 minutes very easy "
            "between. Lock in goal rhythm — smooth, controlled, exactly the "
            "effort you plan to race — then cruise home easy."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "T",
        "rationale": (
            "Two short blocks at goal effort keep the race rhythm calibrated "
            "through the taper while the volume drop does its work. Long "
            "enough to feel the pace, short enough to leave nothing behind."
        ),
    },
    {
        "id": "taper_marathon_sharpener",
        "distances": [42.2],
        "phases": ["taper"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Marathon-Pace Blocks + Strides",
        "structure": "easy run + 2 × 6 min at marathon effort + 4 × 20-second strides",
        "description": (
            "Run easy for most of the session, then run 2 × 6 minutes at "
            "marathon effort with 2 minutes very easy between — dial in the "
            "exact rhythm you'll hold on race day. Finish with 4 × 20-second "
            "relaxed strides with a minute of walking or jogging between "
            "each."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "Marathon pace should feel automatic by race week. Short MP "
            "blocks rehearse it without meaningful fatigue, and a few strides "
            "keep the legs elastic while overall volume winds down."
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
        "id": "5k_vo2max_1000s",
        "distances": [5.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "VO2max 1km Repeats",
        "structure": "5-7 × ~1km at 5K pace with 2-3min jog recovery",
        "description": (
            "Warm up 2km easy. Run 5 × 1km at 5K goal pace with 2-3 min easy "
            "jog recovery between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "Longer VO2max reps hold you at maximal aerobic effort for longer "
            "than 400s do, building the sustained power that 5K racing demands. "
            "Rotated with the 400m session, it keeps build-phase speed varied."
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
    {
        "id": "5k_thirty_thirties",
        "distances": [5.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "30-30 Intervals",
        "structure": "14-20 × (30s hard / 30s easy)",
        "description": (
            "Warm up 2km easy. Run 14-20 × (30 seconds hard at VO2max effort / "
            "30 seconds easy jog) as one continuous block. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "The short, frequent surges let you accumulate a big chunk of time "
            "at VO2max while the 30-second floats keep the legs turning over — "
            "you bank far more high-end aerobic work than a few long reps allow, "
            "with less of the form breakdown that comes from grinding."
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
        "id": "10k_vo2max_1000s",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "VO2max 1km Repeats",
        "structure": "5-7 × ~1km at 5K-10K pace with 2min jog recovery",
        "description": (
            "Warm up 2km easy. Run 5 × 1km at a pace between your 5K and 10K "
            "effort, with 2 min easy jog recovery between reps. Cool down "
            "2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "Raises the aerobic ceiling that caps 10K pace. Rotated with the "
            "fartlek, it gives the build phase a true hard-interval day "
            "alongside the surge-and-float session."
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
    {
        "id": "10k_rolling_500s",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Rolling 500s",
        "structure": "8 × 0.5km rolling — no full stop, 200m easy jog between each",
        "description": (
            "Warm up 2km easy. Run 8 × 0.5km at 10K pace with only 200m easy "
            "jog recovery between each — keep moving the whole time, no standing "
            "around. The continuous rolling format accumulates quality work without "
            "the legs going cold between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "The short recovery keeps lactate elevated between reps, forcing "
            "adaptation to running at race pace on already-working legs. "
            "Rolling 500s build the aerobic ceiling and mental toughness "
            "needed to sustain 10K pace through the back half of the race."
        ),
    },
    {
        "id": "10k_broken_miles",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Broken Miles",
        "structure": "3 × broken mile: 3 hard 0.4km efforts, 60s rest within + 3min between miles",
        "description": (
            "Warm up 2km easy. Run 3 'broken miles': each mile is 3 hard "
            "efforts of about 0.4km at 5K pace with 60 seconds rest between "
            "the efforts. Take 3 minutes easy jog between each broken mile. "
            "Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "Broken miles let you accumulate mile-effort work in short chunks, "
            "so the quality per rep is higher than you could hold for a full "
            "mile. The within-rep rest teaches economy at speed; the between-set "
            "rest lets you repeat it three times with full intent."
        ),
    },
    {
        "id": "10k_200m_repeats",
        "distances": [10.0],
        "phases": ["peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "200m Speed Repeats",
        "structure": "12-16 × 0.2km at mile pace with 0.2km jog recovery",
        "description": (
            "Warm up 2km easy. Run 12-16 short efforts of 0.2km at mile pace — "
            "fast but controlled — with 0.2km easy jog recovery between each. "
            "Focus on quick turnover and relaxed mechanics, not white-knuckle "
            "sprinting. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "R",
        "rationale": (
            "Short, fast reps close to the race develop neuromuscular efficiency "
            "and leg speed. In the taper window, these refresh the nervous system "
            "without adding heavy aerobic load — you arrive at the start line "
            "sharp and bouncy."
        ),
    },
    {
        "id": "10k_pyramid_intervals",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Pyramid Intervals",
        "structure": "400-600-800-1000-800-600-400m at 5K-10K pace",
        "description": (
            "Warm up 2km easy. Run a pyramid — 400m, 600m, 800m, 1000m, 800m, "
            "600m, 400m — at a pace between your 5K and 10K effort, with "
            "equal-distance jog recovery between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "The ascending and descending structure trains you to shift gears "
            "and maintain quality as fatigue builds — both on the way up and on "
            "the way down. The 1000m peak rep is the key stimulus; the shorter "
            "reps around it sharpen speed at the edges."
        ),
    },
    {
        "id": "10k_mile_up_overs",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Mile Up & Overs",
        "structure": "4 × 1.6km — alternate just over / just under 10K pace",
        "description": (
            "Warm up 2km easy. Run 4 efforts of 1.6km alternating intensity: "
            "odd reps (1st, 3rd) just over 10K pace, even reps (2nd, 4th) just "
            "under 10K pace. 90 seconds easy jog recovery between efforts. "
            "Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "Alternating over and under the target race pace brackets the exact "
            "race effort so you experience what 10K pace feels like both fast and "
            "slow — building the internal feel that makes race-day pacing "
            "automatic rather than a guessing game."
        ),
    },
    {
        "id": "10k_thirty_thirties",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "30-30 Intervals",
        "structure": "14-20 × (30s hard / 30s easy)",
        "description": (
            "Warm up 2km easy. Run 14-20 × (30 seconds hard at VO2max effort / "
            "30 seconds easy jog) as one continuous block. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "Frequent short surges pile up time at VO2max while the 30-second "
            "floats keep your turnover quick and your form intact — a high "
            "aerobic-power dose that complements the longer 10K rep sessions "
            "without grinding you down."
        ),
    },
    {
        "id": "10k_mile_repeats",
        "distances": [10.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Threshold Mile Repeats",
        "structure": "3-5 × 1600m at threshold with 90s recovery",
        "description": (
            "Warm up 2km easy. Run 3-5 × 1600m (1 mile) at threshold pace with "
            "90 seconds easy jog recovery between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Mile-long reps at threshold accumulate a large volume of "
            "lactate-clearance work in pieces just long enough to be specific to "
            "10K racing, while the short recoveries keep the overall effort "
            "honest — raising the pace you can hold before fatigue bites."
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
        "id": "half_km_intervals",
        "distances": [21.1],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "10K-Pace Intervals",
        "structure": "5-7 × ~1km at 10K pace with 90s jog recovery",
        "description": (
            "Warm up 2km easy. Run 5 × 1km at 10K goal pace with 90 sec easy "
            "jog recovery between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "Faster-than-race-pace reps lift your speed reserve so half-marathon "
            "pace feels more comfortable. Gives the build phase a sharp interval "
            "day to rotate against the cut-down long run."
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
    {
        "id": "half_mile_repeats",
        "distances": [21.1],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Mile Repeats at 10K Pace",
        "structure": "3-6 × 1600m at 10K pace with 90s recovery",
        "description": (
            "Warm up 2km easy. Run 3-6 × 1600m (1 mile) at 10K goal pace with "
            "90 seconds easy jog recovery between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "Reps a touch faster than half-marathon pace stretch your speed "
            "reserve, so goal pace settles in as comfortable rather than "
            "threatening. The mile length makes the work specific without the "
            "neuromuscular cost of short, sharp intervals."
        ),
    },
    # -- Runna-inspired sessions (on-off ks, rolling surges, ladders,
    #    compound sets, time trial, race rehearsal) ---------------------------
    {
        "id": "half_on_off_ks",
        "distances": [21.1, 42.2],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "On-Off Kilometers",
        "structure": "3-5 × (1 km at threshold / 1 km easy float), continuous",
        "description": (
            "Warm up 1km easy. Run 3-5 × (1 km at threshold pace / 1 km easy "
            "float) as one continuous block — the float is genuinely easy, "
            "reset and go again. Cool down 1km easy."
        ),
        "intensity": "medium",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Alternating full kilometres on and off teaches you to relax "
            "between efforts without stopping — the metronome for holding "
            "goal pace through a race's surges and recoveries."
        ),
    },
    {
        "id": "rolling_400s",
        "distances": [10.0, 21.1, 42.2],
        "phases": ["build"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Rolling 400s",
        "structure": "4-10 × (400 m surge at 10K effort / 600 m steady float)",
        "description": (
            "Warm up 1km easy. Run 4-10 × (400 m surge at 10K effort / 600 m "
            "steady float) with no full stops — keep the float honest, not a "
            "jog-recovery. Cool down 1km easy."
        ),
        "intensity": "medium",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "Rolling surges inside a continuous run build gear-changing "
            "without the full cost of a track session — the steady floats "
            "keep the aerobic engine loaded the whole way."
        ),
    },
    {
        "id": "tempo_2_1_1",
        "distances": [21.1, 42.2],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "Tempo 2-1-1",
        "structure": "2 km + 1 km + 1 km at threshold with 500 m floats",
        "description": (
            "Warm up 1km easy. Run 2 km, 1 km, then 1 km at threshold pace "
            "with 500 m easy floats between. The shrinking reps let you "
            "finish strong. Cool down 1km easy."
        ),
        "intensity": "medium",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "A descending ladder front-loads the longest rep while you're "
            "fresh and rewards you with shorter ones as fatigue builds — "
            "threshold volume that ends on a win, not a grind."
        ),
    },
    {
        "id": "intervals_400s_into_200s",
        "distances": [5.0, 10.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "400s into 200s",
        "structure": "3-8 × 400m at 5K effort, then 4-8 × 200m fast, 200m jogs",
        "description": (
            "Warm up 1km easy. Run 3-8 × 400m at 5K effort with 200 m jog, "
            "then 4-8 × 200m fast-and-relaxed with 200 m jog. The 200s should "
            "feel quicker than the 400s — finish the session faster than you "
            "started. Cool down 1km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "Dropping to faster, shorter reps once the 400s have loaded the "
            "legs trains a finishing kick on tired legs — the compound set "
            "does what neither block alone can."
        ),
    },
    {
        "id": "intervals_800s_into_400s",
        "distances": [10.0, 21.1],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "800s into 400s",
        "structure": "2-5 × 800m at 5K-10K effort, then 3-6 × 400m quicker",
        "description": (
            "Warm up 1km easy. Run 2-5 × 800m at 5K-10K effort with 200 m "
            "jog, then 3-6 × 400m slightly quicker with 200 m jog. Shifting "
            "gears when already tired is the point. Cool down 1km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "I",
        "rationale": (
            "The 800s accumulate VO2max time; the closing 400s ask for a "
            "gear change on fatigued legs — the exact demand of the last "
            "kilometre of a 10K or a half's finishing push."
        ),
    },
    {
        "id": "time_trial_5k",
        "distances": [10.0, 21.1, 42.2],
        "phases": ["build"],
        "type": "tempo",
        "terrain": ["any"],
        "name": "5K Time Trial",
        "structure": "5 km time trial at even, honest max effort",
        "description": (
            "Warm up easy with a few strides. Run a 5 km time trial: even, "
            "honest max effort — start controlled, empty the tank over the "
            "final kilometre. Note your time. Cool down very easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "10K",
        "rationale": (
            "A mid-plan benchmark: the time tells you whether training "
            "paces still match your fitness, and racing solo rehearses "
            "pacing discipline no interval session can."
        ),
    },
    {
        "id": "race_practice_long",
        "distances": [21.1, 42.2],
        "phases": ["peak"],
        "type": "long",
        "terrain": ["any"],
        "name": "Race Practice Long Run",
        "structure": "60% easy, final 40% at goal race pace — full race rehearsal",
        "description": (
            "Race rehearsal: run the first 60% easy and the final 40% at "
            "goal race pace. Wear your race kit and shoes, and fuel exactly "
            "as you will on race day."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "M",
        "rationale": (
            "Everything gets tested — kit, shoes, fueling, and holding goal "
            "pace on tired legs. Come race day, nothing is new."
        ),
    },
]

# Combined list of all workouts
WORKOUTS: List[Dict] = _WORKOUTS_SHORT + WORKOUTS_LONG
