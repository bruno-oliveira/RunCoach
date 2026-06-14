"""Trail key workout definitions: 30K hilly/flat, long variants, intensive weekend.

See key_workout_data.py for full field documentation.
"""

from typing import Dict, List

TRAIL_LONG: List[Dict] = [
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
        "structure": "Trail run at easy effort, walk steep uphills",
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
        "structure": "Back-to-back trail runs at easy effort, practice fueling",
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
        "steps_builder": "back_to_back",
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
    # BASE PHASE — flat terrain has zero base-phase quality entries currently.
    # These fill the slot so flat-terrain runners get light quality in weeks 1-7.
    {
        "id": "trail_flat_base_strides",
        "distances": [30.0],
        "phases": ["base"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Easy Run + Trail Strides",
        "structure": "easy run + 6 × 20s fast strides on grass or dirt",
        "description": (
            "Run easy on the softest surface you can find — grass, dirt, "
            "gravel path. Finish with 6 × 20 second strides: accelerate "
            "smoothly to a quick but relaxed pace, hold 20 seconds, then "
            "walk or jog easy for 60 seconds before the next. Focus on "
            "light landings and quick turnover, not power output."
        ),
        "intensity": "low",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Strides on soft surfaces rehearse the proprioceptive demands "
            "of trail running without requiring actual hills or technical "
            "terrain. The accelerations keep leg speed alive through the "
            "aerobic base phase and prime the neuromuscular patterns for "
            "the quality work to come."
        ),
    },
    {
        "id": "trail_flat_base_fartlek",
        "distances": [30.0],
        "phases": ["base"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Relaxed Flat Fartlek",
        "structure": "easy run with 6 × (2min effort / 3min easy)",
        "description": (
            "On a flat trail, dirt path, or grass: run easy for the bulk "
            "of the session, then weave in 6 × (2 minutes at a comfortably "
            "strong effort / 3 minutes easy jog). The effort should feel "
            "like you're working but never hurting — think brisk, not all-out."
        ),
        "intensity": "low",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "A relaxed fartlek introduces sustained effort while staying "
            "fully within the aerobic base. The generous easy floats keep "
            "lactate low; the short pickups break the monotony of pure "
            "easy running and maintain the aerobic gear-changing that "
            "trail pacing constantly demands."
        ),
    },
    # BUILD + PEAK PHASE — interval slot (currently only 2 candidates rotating)
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
        "id": "trail_flat_over_under_intervals",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["flat"],
        "name": "Over-Under Intervals",
        "structure": "6 x (3min hard / 2min steady) with 2min easy jog between sets",
        "description": (
            "Warm up 2km easy. Run 6 sets: 3 min hard (Zone 4-5 effort), "
            "immediately into 2 min steady (Zone 3-4 effort), then 2 min easy jog. "
            "Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Mimics the changing metabolic demand of climbing and settling "
            "without needing hills. Builds flat-terrain trail resilience."
        ),
    },
    {
        "id": "trail_flat_soft_surface",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Soft-Surface Time-on-Feet",
        "structure": "Easy run on grass/dirt/sand, fuel every 30min",
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
        "structure": "5min power walk / 5min easy run intervals",
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
    # Additional flat-terrain interval candidates — build/peak
    {
        "id": "trail_flat_rolling_500s",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["flat"],
        "name": "Flat Rolling 500s",
        "structure": "8 × 0.5km at trail race effort with short jog recovery",
        "description": (
            "On a flat path or grass loop, run 8 efforts of about half a "
            "kilometre at trail race effort — work hard enough that talking "
            "in full sentences is not possible, but you're not sprinting. "
            "Keep the recovery short (a jog, not a stop) and keep moving "
            "between reps. This is continuous quality work, not a track session."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Rolling efforts with minimal recovery train you to hold race "
            "effort on already-working legs — the flat-terrain equivalent "
            "of cresting a climb and keeping the pace rather than collapsing "
            "into recovery. The continuous format builds specific aerobic "
            "resilience for sustained trail efforts."
        ),
    },
    {
        "id": "trail_flat_broken_miles",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["flat"],
        "name": "Broken Miles",
        "structure": "3 × broken mile: 3 hard efforts, 60s rest within + 3min between miles",
        "description": (
            "On flat soft-surface terrain, run 3 broken miles: each mile "
            "is 3 hard efforts at strong trail pace with 60 seconds "
            "recovery between each effort. Take 3 minutes easy jog between "
            "miles. The quality per rep is higher than a continuous mile "
            "would allow, without the toll of actual hill repeats."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "T",
        "rationale": (
            "Broken miles on flat terrain accumulate high-intensity work "
            "in manageable chunks, mimicking the effort bursts of climbing "
            "sections. The in-rep rest trains recovery without switching "
            "off — a skill that translates directly to cresting a climb "
            "and continuing to move efficiently."
        ),
    },
    {
        "id": "trail_flat_pyramid",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["flat"],
        "name": "Flat-Trail Pyramid",
        "structure": "Pyramid: short-medium-long-medium-short efforts at trail pace",
        "description": (
            "Warm up easy. Run a pyramid of efforts at trail race effort: "
            "2 minutes, 4 minutes, 6 minutes, 4 minutes, 2 minutes — with "
            "equal-duration easy jog recovery between each. Keep the effort "
            "level consistent throughout; don't sprint the short reps or "
            "sandbag the long one. Cool down easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "The ascending/descending time structure trains you to manage "
            "effort as fatigue builds and then teaches you to find pace "
            "again on the way down — replicating the pattern of a long "
            "climb followed by the legs loosening on the descent."
        ),
    },
    {
        "id": "trail_flat_vo2max_intervals",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["flat"],
        "name": "VO2max Intervals",
        "structure": "5-6 × 3min at hard effort with 2min easy jog recovery",
        "description": (
            "Warm up easy. Run 5-6 × 3 minutes at the hardest effort you "
            "can sustain for the full 3 minutes — Zone 4-5, breathing hard "
            "but controlled. Take 2 minutes easy jog between each. Focus "
            "on driving the arms and maintaining tall posture as you "
            "fatigue. Cool down easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "T",
        "rationale": (
            "VO2max intervals raise the aerobic ceiling — the pace your "
            "cardiovascular system can sustain. For a flat-terrain runner "
            "training for a hilly race, this is the primary mechanism for "
            "building climbing capacity when hills aren't accessible."
        ),
    },
    # Additional flat-terrain tempo candidates — build/peak
    {
        "id": "trail_flat_threshold_blocks",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Threshold Blocks",
        "structure": "3 × 8min at threshold effort with 3min easy jog recovery",
        "description": (
            "On flat terrain (grass, dirt, or firm trail), run 3 × 8 minutes "
            "at threshold effort — the pace where you could speak a few words "
            "but not a sentence. Take 3 minutes easy jog between each block. "
            "Don't start the first rep too fast: find the effort, then hold it."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Threshold blocks build the lactate clearance rate that underpins "
            "sustained trail-race effort. Flat terrain lets you isolate the "
            "metabolic stimulus cleanly — the same aerobic adaptation you'd "
            "get from sustained climbing, trained without the hills."
        ),
    },
    {
        "id": "trail_flat_progressive_tempo",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Progressive Effort Run",
        "structure": "Continuous run starting easy, finishing at trail race effort",
        "description": (
            "Run a continuous effort that progresses through three gears: "
            "the first third easy (Zone 2), the middle third steady (Zone 3), "
            "the final third at trail race effort (Zone 4). No stopping or "
            "rest — the transition between gears should be smooth and felt "
            "rather than timed. This teaches pacing discipline through fatigue."
        ),
        "intensity": "medium",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Progressive efforts train the race skill of holding back early "
            "and finding pace later. Trail races are most commonly blown by "
            "runners who go too hard in the first third — this workout "
            "builds the internal calibration to prevent exactly that."
        ),
    },
    {
        "id": "trail_flat_over_unders",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Flat Over-Unders",
        "structure": "5 × (2min over threshold / 3min under threshold), continuous",
        "description": (
            "Warm up easy. Run a continuous block of 5 × (2 minutes just over "
            "threshold effort / 3 minutes just under threshold effort) — no "
            "easy jog between, stay working the whole time. The 'over' section "
            "should feel genuinely hard; the 'under' should feel like relief "
            "without ever becoming easy. Cool down easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Over-unders push lactate production above clearance rate and "
            "then force clearance while still running hard. This is the "
            "flat-ground simulation of surging on a climb and then holding "
            "effort on the subsequent descent — the core metabolic pattern "
            "of hilly trail racing."
        ),
    },
    {
        "id": "trail_flat_steady_state",
        "distances": [30.0],
        "phases": ["build"],
        "type": "tempo",
        "terrain": ["flat"],
        "name": "Steady-State Tempo",
        "structure": "20-30min continuous at comfortably hard effort",
        "description": (
            "After an easy warm-up, run 20-30 minutes at a comfortably "
            "hard, sustained effort — the pace where you're breathing "
            "deeply but rhythmically, and holding a conversation would "
            "require effort. Keep the effort even throughout; don't drift "
            "faster as you warm up. Cool down easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Continuous threshold running builds the aerobic capacity to "
            "sustain effort for the duration of a trail race. The flat "
            "surface lets you hold an even pace that would be interrupted "
            "by climbs on technical terrain — useful for ingraining the "
            "sensation of sustained effort that carries over to race day."
        ),
    },
    # -- Long-run variants (Trail 30K — hilly) --
    {
        "id": "trail_long_fast_finish",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["hilly"],
        "name": "Trail Fast-Finish Long Run",
        "structure": "Long run with the last 3 km at tempo effort on trail",
        "description": (
            "Run your long-run distance on trails at easy effort. In the "
            "final 3 km, pick up to tempo effort — push the climbs, float "
            "the descents. Finish with purpose, not a sprint."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "T",
        "rationale": (
            "Finishing a trail long run strong teaches your legs to change "
            "gears in the final hour — the difference between holding pace "
            "and fading in a 30K trail race."
        ),
        "steps_builder": "fast_finish",
    },
    {
        "id": "trail_long_rolling_hills",
        "distances": [30.0],
        "phases": ["build"],
        "type": "long",
        "terrain": ["hilly"],
        "name": "Trail Rolling Hills Long Run",
        "structure": "Long run on a hilly trail route at even effort",
        "description": (
            "Run your long-run distance on the hilliest trail you can find. "
            "Keep effort even throughout — push the climbs at threshold effort, "
            "recover on the descents. Walk uphills steeper than 15% grade."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "Running long on hilly terrain is the most race-specific long run "
            "for trail. The repeated climb-descend cycles build the exact "
            "muscular endurance you need on race day."
        ),
        "steps_builder": "rolling_hills",
    },
    {
        "id": "trail_long_race_simulation",
        "distances": [30.0],
        "phases": ["peak"],
        "type": "long",
        "terrain": ["hilly"],
        "name": "Race Simulation Long Run",
        "structure": "Long run at race effort with fueling every 30 min",
        "description": (
            "Run your long-run distance on trails that approximate race "
            "terrain. Run at planned race effort — walk uphills you plan to "
            "walk on race day. Practice your exact fueling strategy: take "
            "nutrition every 30 min. Treat this as a dress rehearsal."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "The capstone peak workout. A full race-effort rehearsal builds "
            "confidence and tests your fueling, pacing, and gear strategy "
            "before taper begins."
        ),
        "steps_builder": "rolling_hills",
    },
    # -- Long-run variants (Trail 30K — flat) --
    {
        "id": "trail_flat_long_fast_finish",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["flat"],
        "name": "Soft-Surface Fast-Finish Long",
        "structure": "Long run on soft surface with the last 3 km at tempo effort",
        "description": (
            "Run your long-run distance on the softest surface available "
            "(grass, dirt, gravel). In the final 3 km, pick up to tempo "
            "effort. The soft surface adds 10-15% metabolic cost, partially "
            "compensating for lack of hills."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "T",
        "rationale": (
            "Fast-finish runs on soft surfaces combine the metabolic demand "
            "of trail with the gear-change skill needed in the final hour "
            "of a 30K race."
        ),
        "steps_builder": "fast_finish",
    },
    {
        "id": "trail_flat_long_fueling",
        "distances": [30.0],
        "phases": ["build"],
        "type": "long",
        "terrain": ["flat"],
        "name": "Fueling Practice Long Run",
        "structure": "Long run at easy effort, practice nutrition every 30 min",
        "description": (
            "Run your long-run distance at easy conversational pace. Take "
            "your planned race nutrition every 30 min starting at minute 30. "
            "Test exactly what you'll eat and drink on race day. Walk 1 min "
            "after each fuel stop if needed."
        ),
        "intensity": "low",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Gut training is as important as leg training for a 30K. "
            "Practicing your fueling plan under exercise stress prevents "
            "the GI issues that ruin trail races."
        ),
        "steps_builder": "depletion",
    },
    {
        "id": "trail_flat_long_race_sim",
        "distances": [30.0],
        "phases": ["peak"],
        "type": "long",
        "terrain": ["flat"],
        "name": "Race Simulation Long Run",
        "structure": "Long run at race effort on varied surfaces with fueling",
        "description": (
            "Run your long-run distance alternating surfaces (grass, dirt, "
            "gravel, pavement) every 2-3 km. Run at planned race effort. "
            "Practice your exact fueling strategy. Treat this as a dress "
            "rehearsal for race day."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "Even without hills, a dress-rehearsal long run on varied "
            "surfaces tests your pacing, fueling, and mental approach "
            "before taper begins."
        ),
        "steps_builder": "rolling_hills",
    },
    # -- Intensive-Weekend trail sessions --
    # Saturday quality (pyramid/ladder, terrain-agnostic) + Sunday long on
    # fatigued legs (hike-run for ultras, easy back-to-back otherwise). These
    # are installed by the intensive-weekend post-pass (by id) and also join
    # the normal trail rotation for build/peak interval weeks.
    {
        "id": "trail_pyramid_intervals",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Trail-Pace Pyramid",
        "structure": "400-800-1200-800-400m pyramid at trail pace",
        "description": (
            "Warm up 2km easy. Run a pyramid — 400m, 800m, 1200m, 800m, 400m "
            "— at strong trail (threshold) effort with equal-distance jog "
            "recovery between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "The ascending/descending structure rehearses surging on the "
            "climbs and settling after — the exact effort-shifting a trail "
            "race demands. Trail pace keeps it specific, not track-fast."
        ),
        "steps_builder": "pyramid_trail",
    },
    {
        "id": "trail_ladder_intervals",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Trail-Pace Ladder",
        "structure": "400-800-1200-1600m ascending ladder at trail pace",
        "description": (
            "Warm up 2km easy. Run an ascending ladder — 400m, 800m, 1200m, "
            "1600m — at strong trail (threshold) effort with equal-distance "
            "jog recovery between reps. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Lengthening reps train you to hold strong effort as fatigue "
            "builds — the skill of staying composed deep into a climb."
        ),
        "steps_builder": "ladder_trail",
    },
    {
        "id": "trail_hike_run_long",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["hilly"],
        "brackets": ["ultra", "long_ultra"],
        "name": "Hike-Run Long Session",
        "structure": "Long run alternating running and power-hiking blocks",
        "description": (
            "Long trail session alternating ~9 min easy running with ~1 min "
            "power-hiking. On real climbs, hike; on flats and descents, run. "
            "Practice race fueling every 30 min. Build time on feet, not pace."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Ultras are run-hike efforts, not all-run. Rehearsing the "
            "transition trains efficient power-hiking and the muscular "
            "endurance for all-day time on feet."
        ),
        "steps_builder": "hike_run",
    },
    {
        "id": "trail_b2b_day2",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["any"],
        "brackets": ["standard", "ultra", "long_ultra"],
        "name": "Back-to-Back Long (Day 2)",
        "structure": "Long run at easy effort on legs fatigued from yesterday",
        "description": (
            "Run at easy conversational effort on legs already tired from "
            "yesterday's quality session. Hold back the pace and practice "
            "race fueling every 30 min. The second day simulates late-race "
            "fatigue better than any single long run."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Back-to-back running is the hallmark of trail/ultra prep. "
            "Starting a long run already fatigued is the closest training "
            "proxy for the final hours of a long trail race."
        ),
        "steps_builder": "b2b_day2",
    },
    # ---- New named workouts: hilly terrain --------------------------------
    {
        "id": "trail_broken_climbs",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "hill",
        "terrain": ["hilly"],
        "name": "Broken Climbs",
        "structure": "6 × broken climb: 3 × 90s hard uphill, 60s easy between, 3min jog between sets",
        "description": (
            "Warm up 2km easy on flat or gentle terrain. Find a sustained hill "
            "(6-10% grade). Run 6 sets of broken climbs: within each set, run "
            "3 × 90 seconds hard uphill with 60 seconds easy power-hike or jog "
            "between the reps; then take 3 minutes easy jog between sets. "
            "Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "T",
        "rationale": (
            "Broken climbs accumulate high-intensity uphill work in short "
            "chunks, pushing each rep to full effort without the drop-off that "
            "comes from sustained all-out climbing. The short recovery within "
            "each set keeps lactate elevated; the longer rest between sets "
            "allows enough recovery to keep the quality honest rep after rep."
        ),
    },
    {
        "id": "trail_rolling_500s",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "interval",
        "terrain": ["hilly"],
        "name": "Rolling 500s",
        "structure": "8 × 0.5km at trail race effort, 0.2km easy jog recovery",
        "description": (
            "Warm up 2km easy. On a rolling trail loop, run 8 efforts of 0.5km "
            "at trail race effort — push hard uphill within the effort, hold "
            "pace on flats, float the brief descents — with 0.2km easy jog "
            "recovery between each. Keep moving between reps, no standing. "
            "Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Trail races don't have flat, uniform reps — effort shifts "
            "constantly with the terrain. Rolling efforts on varied ground train "
            "you to manage pace and effort through micro-climbs and descents, "
            "which is exactly what race day demands."
        ),
    },
    {
        "id": "trail_stacked_efforts",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["hilly"],
        "name": "Stacked Efforts",
        "structure": "3 × 10min at trail race effort with 3min easy jog recovery",
        "description": (
            "Warm up 2km easy. Run 3 × 10 minutes at trail race effort on "
            "hilly terrain — let the gradient dictate pace, keep effort "
            "constant through climbs and descents. Take 3 minutes easy jog "
            "recovery between efforts. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Ten-minute efforts at race intensity on real terrain are the "
            "closest training proxy to race day. They build the mental and "
            "muscular endurance to sustain effort through climbing sections "
            "without blowing up — the key skill for hilly trail racing."
        ),
    },
    {
        "id": "trail_climb_surge_fartlek",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["hilly"],
        "name": "Climb Surge Fartlek",
        "structure": "60-75min: surge every climb, float every descent",
        "description": (
            "Go out for 60-75 minutes on hilly trails. Every time you hit a "
            "climb, surge to Zone 4 effort (hard but not all-out). Every time "
            "you hit a descent or flat, float back to easy Zone 2. Alternate "
            "naturally with the terrain — this is fartlek, not a structured "
            "rep session. The longer and steeper the climb, the harder you push."
        ),
        "intensity": "high",
        "target_zone": 4,
        "pace_zone": "T",
        "rationale": (
            "Trail fartlek on actual climbs teaches you to surge when it's "
            "hard and recover on the relief — the natural rhythm of a well-run "
            "trail race. It builds specific uphill power and the aerobic "
            "capacity to absorb repeated surges without compounding fatigue."
        ),
    },
    {
        "id": "trail_downhill_broken_miles",
        "distances": [30.0],
        "phases": ["build"],
        "type": "interval",
        "terrain": ["hilly"],
        "name": "Broken Downhill Miles",
        "structure": "4 × broken mile descent: 3 fast downhill efforts, hike up to reset",
        "description": (
            "Find a descent of 0.4-0.6km at 5-8% grade. Run 4 broken miles: "
            "each broken mile is 3 fast downhill efforts (controlled but "
            "moving, quick cadence, soft landings), hiking back up between "
            "each effort. Take 3 minutes easy between broken miles. "
            "Warm up 2km easy, cool down 2km easy."
        ),
        "intensity": "medium",
        "target_zone": 3,
        "pace_zone": "E",
        "rationale": (
            "Controlled fast descents build the eccentric quad strength and "
            "the technical confidence to pass people on the way down — the "
            "biggest time-saver in trail racing. The broken format allows "
            "more total volume of quality descending than a continuous "
            "downhill segment would."
        ),
    },
    {
        "id": "trail_hill_pyramid",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "hill",
        "terrain": ["hilly"],
        "name": "Hill Pyramid",
        "structure": "Uphill pyramid: 1-2-3-4-3-2-1 min at hard effort, jog down",
        "description": (
            "Warm up 2km easy. Find a hill (6-10% grade). Run an uphill "
            "pyramid — 1, 2, 3, 4, 3, 2, 1 minutes hard — jogging back down "
            "to the start between each rep. Drive arms, shorten stride, stay "
            "upright. Cool down 2km easy."
        ),
        "intensity": "high",
        "target_zone": 5,
        "pace_zone": "T",
        "rationale": (
            "The ascending rep length forces you to manage effort over "
            "progressively longer climbs; the descending half builds confidence "
            "and repetition after already-tired legs. The 4-minute peak rep "
            "matches a typical major climb in a 30K trail race."
        ),
    },
    # ---- New named workouts: base phase trail -----------------------------
    {
        "id": "trail_base_hike_run",
        "distances": [30.0],
        "phases": ["base"],
        "type": "hill",
        "terrain": ["hilly"],
        "name": "Easy Hike-Run on Hills",
        "structure": "60min alternating: run flats, power-hike uphills",
        "description": (
            "Go out for 60 minutes on hilly terrain at easy effort. Run the "
            "flats and gentle slopes; power-hike anything steeper than about "
            "8%. Keep heart rate in Zone 1-2 the whole session. This is "
            "deliberate and unhurried — build the habit before the load arrives."
        ),
        "intensity": "low",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Establishing the run-hike rhythm early in base training means "
            "it's automatic by race day. The hilly terrain builds structural "
            "resilience in the ankles, quads, and connective tissue at a "
            "load the aerobic system can handle without stress."
        ),
    },
    {
        "id": "trail_base_surges",
        "distances": [30.0],
        "phases": ["base"],
        "type": "interval",
        "terrain": ["any"],
        "name": "Easy Run with Trail Surges",
        "structure": "easy run + 6 × 30s uphill surges",
        "description": (
            "Run easy for the bulk of the session on trails or roads. Finish "
            "with 6 × 30 second uphill surges on any available gradient — "
            "accelerate smoothly to a strong but not all-out effort, then "
            "walk or jog easy back down. Focus on smooth mechanics, not speed."
        ),
        "intensity": "low",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "A handful of uphill surges keeps the legs awake through base "
            "phase aerobic building without adding meaningful fatigue. "
            "They prime the neuromuscular patterns for the hill work to come "
            "and stop the legs going stale from pure easy running."
        ),
    },
]
