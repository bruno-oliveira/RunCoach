"""Distance-driven key-workout text: prose/structure rewrites + reconciliation.

Each key workout's description and one-line structure are regenerated from the
*actual* assigned distance so the displayed numbers, the executable steps, and
the prose never drift apart.
"""

import re
from typing import Any, Callable, Dict, Optional

from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training.workout_steps.primitives import _wucd_m
from app.utils import format_km, truncate_km


def _wu_cd(d: float) -> tuple:
    """Return (warmup_km, cooldown_km) matching the executable steps exactly.

    Both the description and the step list derive their warm-up / cool-down
    length from the same :func:`_wucd_m` helper, which snaps to whole 100 m
    increments. Converting those metres to kilometres therefore yields a clean
    one-decimal value (e.g. 700 m -> 0.7 km) that never reads as 1.075 km and
    never disagrees with the number baked into the executable step. The
    :func:`truncate_km` call is belt-and-braces: the snapped value is already
    one-decimal, so it changes nothing but documents the contract.
    """
    total_m = int(round(d * 1000))
    wu_m = _wucd_m(total_m)
    wu_km = truncate_km(wu_m / 1000.0)
    return (wu_km, wu_km)


def _mp_cutdown_reps(d: float) -> int:
    """2km-rep count for marathon_mp_cutdown, bucketed by distance.

    Each rep is 2km of work + ~0.3km recovery jog (~2.3km total).
    Combined with ~10% warmup + ~10% cooldown of d, the buckets ensure
    the structure fits inside the assigned budget.
    """
    if d < 8:
        return 2
    if d < 12:
        return 3
    if d < 16:
        return 4
    if d < 20:
        return 5
    return 6


def _km_rep_distance(d: float, reps: int) -> float:
    """Per-rep work distance (km) for the km-rep family, mirroring the steps.

    ``build_km_rep_steps`` is the executable source of truth: it strips the
    warm-up / cool-down, divides the remaining budget across ``reps`` (with a
    200 m floor), then snaps to 100 m at/above 1 km or 50 m below. The prose
    rewrites for this family (``marathon_tempo_cutdown``,
    ``5k_race_pace_3km``, ``half_race_pace_segments``) must cite that exact
    figure, otherwise the description claims a different rep distance than the
    runner is told to execute. This helper reproduces that arithmetic so the
    two never diverge — replacing the old per-description ``(d - wu - cd) /
    reps`` expressions, which skipped the 50/100 m snapping (and, for the
    cutdown, applied a cosmetic ``max(1.0, …)`` floor the steps never honoured).
    """
    total_m = int(round(d * 1000))
    wu_m = _wucd_m(total_m)
    work_m = max(0, total_m - 2 * wu_m)
    if work_m <= 0 or reps <= 0:
        return 0.0
    rep_m = max(200, int(round(work_m / reps)))
    if rep_m >= 1000:
        rep_m = int(round(rep_m / 100.0)) * 100
    else:
        rep_m = int(round(rep_m / 50.0)) * 50
    return rep_m / 1000.0


def _vo2max_400_reps(d: float) -> int:
    """Scale 400m VO2max reps to fit distance d.

    Each rep is ~0.4km work + ~0.3km easy jog recovery (~0.7km total).
    Reps clamped to [4, 12] so the workout stays recognizable.
    """
    wu, cd = _wu_cd(d)
    main_km = max(0.0, d - wu - cd)
    reps = round(main_km / 0.7)
    return max(4, min(12, reps))


def _yasso_800_reps(d: float) -> int:
    """800m rep count for marathon_yasso_800s (each rep ~1.6km incl. recovery).

    Mirrors the description rewrite so steps and prose agree.
    """
    wu, cd = _wu_cd(d)
    return max(6, min(10, round((d - wu - cd) / 1.6)))


def _pyramid_pattern(d: float) -> str:
    """Pick a pyramid pattern that fits within distance d.

    Equal-distance recovery jogs roughly double the work-km cost, so a
    full 3.2km of reps needs ~6.4km of main-set room.
    """
    wu, cd = _wu_cd(d)
    main_km = max(0.0, d - wu - cd)
    if main_km >= 6.0:
        return "200m, 400m, 600m, 800m, 600m, 400m, 200m"
    if main_km >= 3.4:
        return "200m, 400m, 600m, 400m, 200m"
    return "200m, 400m, 400m, 200m"


def _fartlek_reps(
    d: float,
    on_min: int = 3,
    off_min: int = 2,
    pace_min_per_km: float = 6.0,
    default: int = 8,
    lo: int = 2,
    hi: int = 10,
) -> int:
    """Scale fartlek rep count to fit distance d.

    A "set" of (on_min hard / off_min easy) covers roughly
    ``(on_min + off_min) / pace_min_per_km`` km. Reps are capped to a sane
    range so structures stay recognizable across distances.
    """
    wu, cd = _wu_cd(d)
    main_km = max(0.0, d - wu - cd)
    set_km = (on_min + off_min) / pace_min_per_km
    if set_km <= 0:
        return default
    reps = round(main_km / set_km)
    return max(lo, min(hi, reps))


def _vo2max_km_reps(
    d: float,
    rep_km: float = 1.0,
    recovery_km: float = 0.4,
    default: int = 5,
    lo: int = 3,
    hi: int = 7,
) -> int:
    """Scale the rep count of a km-based VO2max session to the run budget.

    One rep is ``rep_km`` of work plus ``recovery_km`` of jog. Reps are
    clamped so the session stays a recognisable VO2max set across distances.
    """
    wu, cd = _wu_cd(d)
    main_km = max(0.0, d - wu - cd)
    set_km = rep_km + recovery_km
    if set_km <= 0:
        return default
    reps = round(main_km / set_km)
    return max(lo, min(hi, reps))


def _over_under_reps(
    d: float,
    over_min: float = 1.5,
    under_min: float = 2.5,
    pace_min_per_km: float = 5.5,
    default: int = 6,
    lo: int = 4,
    hi: int = 8,
) -> int:
    """Scale over-under rep count to the run's distance budget.

    One rep is one (over + under) couplet covering roughly
    ``(over_min + under_min) / pace_min_per_km`` km at threshold-ish pace.
    Reps are clamped so the session stays a recognisable over-under (too few
    is pointless, too many turns it into a tempo) and never overruns the
    warm-up/cool-down-adjusted main block.
    """
    wu, cd = _wu_cd(d)
    main_km = max(0.0, d - wu - cd)
    set_km = (over_min + under_min) / pace_min_per_km
    if set_km <= 0:
        return default
    reps = round(main_km / set_km)
    return max(lo, min(hi, reps))


def _proprioception_circuit_cadence(d: float) -> str:
    """Phrase the agility-circuit cadence so it fits the run distance.

    The canonical session is ~8 km with a circuit every ~2 km. For smaller
    budgets the cadence scales (dropping to a single mid-run circuit when the
    run is too short to space several) so the text never contradicts the
    distance — e.g. no "every 2km" on a 1.3 km run.
    """
    circuits = max(1, int(round(d / 2.0)))
    if circuits == 1:
        return "Midway, stop for"
    return f"Every ~{d / circuits:.0f}km, stop for"


# Each entry generates a complete description from the actual distance.
_DISTANCE_REWRITES: Dict[str, Callable[[float], str]] = {
    "5k_vo2max_400s": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run {_vo2max_400_reps(d)} x 400m at 5K pace "
        f"with 90s easy jog recovery between reps. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "5k_race_pace_3km": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run 2 x {format_km(_km_rep_distance(d, 2))}km "
        f"at 5K goal pace with 3 min easy jog recovery. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "5k_cruise_intervals": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run 4 x {format_km((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 4)}km "
        f"at threshold pace with 60 seconds easy jog between reps. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "5k_threshold_run": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. "
        f"Run {format_km(d - _wu_cd(d)[0] - _wu_cd(d)[1])}km continuous at threshold pace "
        f"— comfortably hard, you can speak a few words at a time. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "5k_pyramid": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run pyramid: {_pyramid_pattern(d)} "
        f"— all at 5K pace with equal-distance recovery jogs. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "marathon_mp_long": lambda d: (
        f"Run {format_km(d)}km: first {format_km(d * 0.60)}km easy, "
        f"last {format_km(d * 0.40)}km at marathon pace. "
        f"Take a gel at {format_km(d * 0.32)}km and {format_km(d * 0.64)}km to practice race fueling."
    ),
    "marathon_progressive_long": lambda d: (
        f"Run {format_km(d)}km: first {format_km(d * 0.67)}km easy, "
        f"last {format_km(d * 0.33)}km at marathon pace. "
        f"Run the finish as 2km segments, each 5-10s/km faster than the last. "
        f"Practice fueling every 5km."
    ),
    "marathon_peak_progressive": lambda d: (
        f"Run {format_km(d)}km: first {format_km(d * 0.57)}km easy, "
        f"last {format_km(d * 0.43)}km at marathon pace. "
        f"Run the finish as 3km segments, each 5-10s/km faster than the last."
    ),
    "marathon_easy_long_fueling": lambda d: (
        f"Run {format_km(d)}km continuous at easy conversational pace. "
        f"Take a gel or fuel every 5km starting at km 10. Practice your exact race-day nutrition strategy. "
        f"Walk 1 min after each fuel stop if needed."
    ),
    "marathon_tempo_cutdown": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. "
        f"Run 2 x {format_km(_km_rep_distance(d, 2))}km at threshold pace with 3 min easy jog recovery. "
        f"Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "marathon_mp_cutdown": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. "
        f"Run {_mp_cutdown_reps(d)} x 2km "
        f"alternating between marathon pace and threshold pace "
        f"with 90s jog recovery between each. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "half_progressive_long": lambda d: (
        f"Run {format_km(d)}km: first {format_km(d * 0.65)}km easy, "
        f"last {format_km(d * 0.35)}km at marathon pace. "
        f"No warm-up needed — the easy start IS the warm-up."
    ),
    "half_cutdown_long": lambda d: (
        f"Run {format_km(d)}km: first {format_km(d / 3)}km easy, "
        f"last {format_km(d * 2 / 3)}km at marathon pace. "
        f"Run as 3 segments, each 15s/km faster than the last."
    ),
    "half_race_pace_segments": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. "
        f"Run 3 x {format_km(_km_rep_distance(d, 3))}km "
        f"at half marathon goal pace with 2 min easy jog recovery. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "half_threshold_cruise": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. "
        f"Run 3 x {format_km((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 3)}km "
        f"at threshold pace with 90 seconds easy jog recovery. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "trail_flat_surge_fartlek": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. "
        f"Run {_fartlek_reps(d)} x (3 min at hill-repeat effort / 2 min easy jog) on varied terrain "
        f"(grass, dirt path, or trail). Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "trail_flat_soft_surface": lambda d: (
        f"Run {format_km(d)}km continuous at easy effort on soft surface "
        f"(grass, dirt trails, beach, or gravel paths). "
        f"The soft surface increases energy cost 10-15% vs pavement. "
        f"Walk 2 min every 45 min. Practice race fueling."
    ),
    "trail_time_on_feet": lambda d: (
        f"Run {format_km(d)}km on trails at easy conversational effort. "
        f"Walk steep uphills (>15% grade) to conserve energy. Practice race fueling every 30 min."
    ),
    "trail_back_to_back": lambda d: (
        f"Saturday: {format_km(d * 0.57)}km trail run at easy effort on hilly terrain. "
        f"Sunday: {format_km(d * 0.43)}km trail run at easy effort on fatigued legs. "
        f"Practice race fueling on both days."
    ),
    "trail_technical_terrain": lambda d: (
        f"Find a technical trail with rocks, roots, and uneven surface. "
        f"Run {format_km(d)}km at moderate effort, focusing on foot placement, "
        f"quick cadence, and staying light on your feet."
    ),
    "10k_goal_pace_segments": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. "
        f"Run 2 x {format_km((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 2)}km "
        f"at 10K goal pace with 3 min standing recovery. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "5k_vo2max_1000s": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run {_vo2max_km_reps(d, default=5)} x "
        f"{format_km((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / _vo2max_km_reps(d, default=5))}km "
        f"at 5K goal pace with 2-3 min easy jog recovery between reps. "
        f"Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "10k_vo2max_1000s": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run {_vo2max_km_reps(d, default=5)} x "
        f"{format_km((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / _vo2max_km_reps(d, default=5))}km "
        f"at a pace between your 5K and 10K effort, with 2 min easy jog "
        f"recovery between reps. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "half_km_intervals": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run {_vo2max_km_reps(d, default=5)} x "
        f"{format_km((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / _vo2max_km_reps(d, default=5))}km "
        f"at 10K goal pace with 90 sec easy jog recovery between reps. "
        f"Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "marathon_km_intervals": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run {_vo2max_km_reps(d, default=6)} x "
        f"{format_km((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / _vo2max_km_reps(d, default=6))}km "
        f"at 10K goal pace with 90 sec easy jog recovery between reps. "
        f"Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "10k_tempo_progression": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. "
        f"Run {format_km(d - _wu_cd(d)[0] - _wu_cd(d)[1])}km as a progression: "
        f"first km at easy pace, each subsequent km 10-15 sec/km faster, "
        f"finishing last km at 10K goal pace. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "10k_cruise_intervals": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run 4 x {format_km((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 4)}km "
        f"at threshold pace with 60 seconds easy jog between reps. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "10k_fartlek": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Within a continuous run, "
        f"alternate {_fartlek_reps(d, default=6, lo=2, hi=8)} x (3 min at 10K pace / 2 min easy jog). "
        f"Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "10k_over_unders": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run a continuous block of "
        f"{_over_under_reps(d, default=5)} x (1 min just over threshold / "
        f"2 min just under) -- no easy jog between, stay working the whole "
        f"time. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "half_over_unders": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run a continuous block of "
        f"{_over_under_reps(d, default=6)} x (90 sec just over threshold / "
        f"2.5 min just under) -- no easy jog between, hold the effort the "
        f"whole way through. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "marathon_over_unders": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run a continuous block of "
        f"{_over_under_reps(d, default=6)} x (2 min just over threshold / "
        f"3 min just under) -- no easy jog between, hold the effort "
        f"throughout. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "5k_hill_sprints": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Find a moderate hill (4-6% grade). "
        f"Run 8-10 x 60 seconds hard uphill with easy jog back down. "
        f"Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "marathon_yasso_800s": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. "
        f"Run {max(6, min(10, round((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 1.6))):g} x 800m "
        f"at VO2max pace with equal-time recovery jog. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "trail_elevation_repeats": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy on flat. Find a trail hill (6-10% grade). "
        f"Run 6-8 x 3 min hard uphill, driving arms and shortening stride. "
        f"Jog back down for recovery. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "trail_power_hike": lambda d: (
        "On a hilly trail loop: power-hike steep uphills for 5 min "
        "(arms pumping, long strides), then run the flats and downhills. "
        "Repeat 5 times. Plan for ~60-75 min total."
    ),
    "trail_downhill_technique": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km on flat. "
        f"Find a trail descent (5-8% grade, 400-600m). Run 6-8 downhill repeats "
        f"focusing on quick cadence, slight forward lean, and soft landings. "
        f"Hike back up for recovery. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "trail_flat_power_walk": lambda d: (
        "Alternate 5 min maximum-effort power walking with 5 min easy running "
        "x 6 sets. Plan for ~60 min total. Max-effort power walking at "
        "9-10 min/km builds the specific muscular endurance for race-day hiking."
    ),
    "trail_flat_proprioception": lambda d: (
        f"Run {format_km(d)}km alternating surfaces (pavement, grass, gravel, dirt). "
        f"{_proprioception_circuit_cadence(d)} a 2-min agility circuit: "
        f"10 single-leg hops each side, 20m lateral shuffles, 20m backward running."
    ),
    # -- Long-run variants (Half Marathon) --
    "half_long_alternating_mp": lambda d: (
        f"Run {format_km(d)}km alternating 2 km easy and 2 km at "
        f"marathon pace. No rest between blocks. The switching rehearses "
        f"race-pace discipline on fatigued legs."
    ),
    "half_long_fast_finish": lambda d: (
        f"Run {format_km(d)}km with the first portion at easy pace, "
        f"then accelerate into the final 3 km at threshold pace. "
        f"Build effort into the last kilometer."
    ),
    "half_long_rolling_hills": lambda d: (
        f"Run {format_km(d)}km on a rolling hills route. "
        f"Keep effort even — push on the climbs, float on the descents. "
        f"Do NOT chase pace on the flats."
    ),
    # -- Long-run variants (Marathon) --
    "marathon_long_alternating_mp": lambda d: (
        f"Run {format_km(d)}km alternating 3 km easy and 3 km at "
        f"marathon pace. No stops. The back-to-back pace changes simulate "
        f"late-race moments where you must hold form."
    ),
    "marathon_long_fast_finish": lambda d: (
        f"Run {format_km(d)}km easy, then finish with the last 4 km "
        f"at threshold pace. Build effort kilometer by kilometer — the "
        f"last km should be your fastest."
    ),
    "marathon_long_depletion": lambda d: (
        f"Run {format_km(d)}km fasted (pre-breakfast). Water only "
        f"during the run — no carbs. Keep effort conservative; run slower "
        f"than your normal long-run pace."
    ),
    "marathon_long_rolling_hills": lambda d: (
        f"Run {format_km(d)}km on a rolling hills route. Hold even "
        f"effort throughout — the hills become natural fartlek intervals "
        f"without breaking rhythm."
    ),
    # -- Long-run variants (10K) --
    "10k_long_fast_finish": lambda d: (
        f"Run {format_km(d)}km easy, then finish with the last 2 km "
        f"at threshold pace. A miniature version of the classic "
        f"marathon fast-finish long run."
    ),
    # -- Long-run variants (Trail 30K — hilly) --
    "trail_long_fast_finish": lambda d: (
        f"Run {format_km(d)}km on trails at easy effort. In the "
        f"final 3 km, pick up to tempo effort — push the climbs, float "
        f"the descents. Finish with purpose, not a sprint."
    ),
    "trail_long_rolling_hills": lambda d: (
        f"Run {format_km(d)}km on the hilliest trail you can find. "
        f"Keep effort even throughout — push the climbs at threshold effort, "
        f"recover on the descents. Walk uphills steeper than 15% grade."
    ),
    "trail_long_race_simulation": lambda d: (
        f"Run {format_km(d)}km on trails that approximate race "
        f"terrain. Run at planned race effort — walk uphills you plan to "
        f"walk on race day. Practice your exact fueling strategy: take "
        f"nutrition every 30 min. Treat this as a dress rehearsal."
    ),
    # -- Long-run variants (Trail 30K — flat) --
    "trail_flat_long_fast_finish": lambda d: (
        f"Run {format_km(d)}km on the softest surface available "
        f"(grass, dirt, gravel). In the final 3 km, pick up to tempo "
        f"effort. The soft surface adds 10-15% metabolic cost, partially "
        f"compensating for lack of hills."
    ),
    "trail_flat_long_fueling": lambda d: (
        f"Run {format_km(d)}km at easy conversational pace. Take "
        f"your planned race nutrition every 30 min starting at minute 30. "
        f"Test exactly what you'll eat and drink on race day. Walk 1 min "
        f"after each fuel stop if needed."
    ),
    "trail_flat_long_race_sim": lambda d: (
        f"Run {format_km(d)}km alternating surfaces (grass, dirt, "
        f"gravel, pavement) every 2-3 km. Run at planned race effort. "
        f"Practice your exact fueling strategy. Treat this as a dress "
        f"rehearsal for race day."
    ),
    # -- Intensive-Weekend sessions --
    "trail_pyramid_intervals": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run a pyramid — 400m, 800m, 1200m, "
        f"800m, 400m — at strong trail (threshold) effort with equal-distance "
        f"jog recovery between reps. Cool down {format_km(_wu_cd(d)[1])}km easy."
    ),
    "trail_ladder_intervals": lambda d: (
        f"Warm up {format_km(_wu_cd(d)[0])}km easy. Run an ascending ladder — 400m, "
        f"800m, 1200m, 1600m — at strong trail (threshold) effort with "
        f"equal-distance jog recovery between reps. Cool down "
        f"{format_km(_wu_cd(d)[1])}km easy."
    ),
    "trail_hike_run_long": lambda d: (
        f"Run {format_km(d)}km on trails alternating ~9 min easy running with ~1 min "
        f"power-hiking — hike the climbs, run the flats and descents. "
        f"Practice race fueling every 30 min."
    ),
    "trail_b2b_day2": lambda d: (
        f"Run {format_km(d)}km at easy conversational effort on legs fatigued from "
        f"yesterday's quality session. Hold the pace back and fuel every "
        f"30 min — the second day rehearses late-race fatigue."
    ),
}


_STRUCTURE_REWRITES: Dict[str, Callable[[float], str]] = {
    # Half Marathon long runs
    "half_long_alternating_mp": lambda d: (
        f"{format_km(d)}km alternating 2km easy / 2km marathon pace"
    ),
    "half_long_fast_finish": lambda d: f"{format_km(d)}km with last 3km at threshold pace",
    "half_long_rolling_hills": lambda d: f"{format_km(d)}km on rolling hills at even effort",
    # Marathon long runs
    "marathon_long_alternating_mp": lambda d: (
        f"{format_km(d)}km alternating 3km easy / 3km marathon pace"
    ),
    "marathon_long_fast_finish": lambda d: (
        f"{format_km(d)}km easy with last 4km at threshold pace"
    ),
    "marathon_long_depletion": lambda d: f"{format_km(d)}km fasted long run — water only",
    "marathon_long_rolling_hills": lambda d: (
        f"{format_km(d)}km on rolling hills at steady effort"
    ),
    # 10K long run
    "10k_long_fast_finish": lambda d: f"{format_km(d)}km easy with last 2km at threshold pace",
    # Trail hilly long runs
    "trail_long_fast_finish": lambda d: (
        f"{format_km(d)}km trail with last 3km at tempo effort"
    ),
    "trail_long_rolling_hills": lambda d: f"{format_km(d)}km on hilly trail at even effort",
    "trail_long_race_simulation": lambda d: (
        f"{format_km(d)}km trail at race effort with fueling every 30min"
    ),
    # Trail flat long runs
    "trail_flat_long_fast_finish": lambda d: (
        f"{format_km(d)}km soft-surface with last 3km at tempo"
    ),
    "trail_flat_long_fueling": lambda d: (
        f"{format_km(d)}km easy with nutrition practice every 30min"
    ),
    "trail_flat_long_race_sim": lambda d: (
        f"{format_km(d)}km varied-surface at race effort with fueling"
    ),
    # Trail flat tempo (soft surface)
    "trail_flat_soft_surface": lambda d: (
        f"{format_km(d)}km continuous at easy effort on soft surface"
    ),
    # Intensive-Weekend long sessions (distance-bearing structure one-liners)
    "trail_hike_run_long": lambda d: f"{format_km(d)}km alternating run / power-hike blocks",
    "trail_b2b_day2": lambda d: f"{format_km(d)}km easy on fatigued legs",
}


def _rewrite_key_workout_description(
    description: str, workout_id: str, actual_distance: float
) -> str:
    """Generate a distance-appropriate description for a key workout."""
    rewrite_fn = _DISTANCE_REWRITES.get(workout_id)
    if not rewrite_fn:
        return description
    return rewrite_fn(actual_distance)


def _derive_structure(description: str) -> str:
    """Strip warm-up/cool-down sentences to get a structure one-liner."""
    s = re.sub(r"Warm up [\d.]+km easy[^.]*\.\s*", "", description)
    s = re.sub(r"\s*Cool down [\d.]+km easy[^.]*\.", "", s)
    s = re.sub(r"^Run\s+", "", s.strip())
    s = re.sub(r"^Find a[^.]*\.\s*", "", s.strip())
    return s.strip()


def reconcile_key_workout_text(
    workout: Dict[str, Any], pace_zones: Optional[Dict] = None
) -> bool:
    """Re-render description+structure from current ``workout['distance']``.

    Returns True if the workout had a key-workout overlay and was rewritten,
    False otherwise. Callers use this after any operation that mutates a
    key workout's distance (scaling, capping, transfer, adaptation) so that
    the description, structure and distance stay in lockstep.

    When ``pace_zones`` is given, VDOT paces are injected into the regenerated
    text so the prescription keeps its specific paces (e.g. "5K pace
    (4:30/km)") rather than degrading to generic labels.
    """
    kid = workout.get("key_workout_id")
    if not kid:
        return False
    d = workout.get("distance", 0) or 0
    if d <= 0:
        return False

    def _with_paces(text: str) -> str:
        if not pace_zones:
            return text
        wtype = workout.get("type") or "interval"
        return VDOTCalculator.inject_paces_into_description(text, pace_zones, wtype)

    if kid in _DISTANCE_REWRITES:
        description = _DISTANCE_REWRITES[kid](d)
        if kid in _STRUCTURE_REWRITES:
            structure = _STRUCTURE_REWRITES[kid](d)
        else:
            structure = _derive_structure(description)
        workout["description"] = _with_paces(description)
        workout["structure"] = _with_paces(structure)
    elif kid in _STRUCTURE_REWRITES:
        workout["structure"] = _with_paces(_STRUCTURE_REWRITES[kid](d))
    return True
