"""Key-workout selection: candidate filtering, bracket gating, and overlay.

``KeyWorkoutLibrary`` picks a workout for a (distance, phase, week);
``overlay_key_workout`` installs the chosen workout's description, structure,
and steps onto a generated workout slot.
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.training import workout_steps as _steps_mod
from app.core.training.key_workout_data import WORKOUTS
from app.core.training.key_workout_library.builders import (
    _RUNNING_DISTANCE_FRACTION,
    build_key_workout_steps,
)
from app.core.training.key_workout_library.rewrites import (
    _DISTANCE_REWRITES,
    _STRUCTURE_REWRITES,
    _derive_structure,
    _rewrite_key_workout_description,
)
from app.core.training.road_profile import classify_road
from app.core.training.trail_profile import is_trail_target
from app.core.training.tuning import (
    KEY_WORKOUT_MAX_USES_PER_PLAN,
    KEY_WORKOUT_NO_REPEAT_WINDOW_WEEKS,
    MAX_QUALITY_DAY_SHARE,
    MIN_QUALITY_DAY_CAP_KM,
    PEAK_WORK_FLOOR_TOLERANCE_KM,
)
from app.core.training.vdot_calculator import VDOTCalculator

_logger = logging.getLogger(__name__)


class KeyWorkoutRotationState:
    """Plan-level memory for key-workout variety and progression.

    The weekly builder assembles weeks sequentially but statelessly, so the
    rotation used to be a pure function of (distance, phase, week) — which let
    the same session repeat in consecutive weeks whenever the candidate pool
    and offsets lined up. The generator creates one instance per plan and
    threads it through ``overlay_key_workout`` so selection can (a) skip
    recently-used sessions, (b) cap per-plan reuse, and (c) keep the peak
    interval work set from regressing below the last build week's.

    Purely deterministic — no RNG — so plan generation stays reproducible.
    """

    def __init__(self) -> None:
        # id -> absolute week number the session was last installed.
        self.last_used_week: Dict[str, int] = {}
        # id -> number of times the session has been installed in this plan.
        self.use_counts: Dict[str, int] = {}
        # Largest interval work-set (km) of the most recent build week; the
        # floor peak interval selection must not dip below.
        self.build_interval_work_km: float = 0.0
        self._build_work_week: Optional[int] = None

    def record_use(self, workout_id: str, week_number: int) -> None:
        self.last_used_week[workout_id] = week_number
        self.use_counts[workout_id] = self.use_counts.get(workout_id, 0) + 1

    def record_build_interval_work(self, week_number: int, work_km: float) -> None:
        """Track the interval work-set of the most recent build week.

        Overwrites when a new week starts; takes the max within a week so a
        lighter second interval slot doesn't lower the recorded floor.
        """
        if week_number != self._build_work_week:
            self._build_work_week = week_number
            self.build_interval_work_km = work_km
        else:
            self.build_interval_work_km = max(self.build_interval_work_km, work_km)


def _apply_variety_filter(
    candidates: List[Dict[str, Any]],
    state: Optional[KeyWorkoutRotationState],
    week_number: Optional[int],
) -> List[Dict[str, Any]]:
    """Drop recently-used / over-used candidates while alternatives remain.

    Two soft filters, each applied only when it leaves at least one candidate
    (a pool of one is always allowed to repeat — no filter can conjure
    variety the catalog doesn't have):

    * no-repeat window: skip anything used within the last
      ``KEY_WORKOUT_NO_REPEAT_WINDOW_WEEKS`` weeks;
    * per-plan cap: skip anything already used
      ``KEY_WORKOUT_MAX_USES_PER_PLAN`` times.
    """
    if state is None or week_number is None or len(candidates) < 2:
        return candidates
    fresh = [
        w
        for w in candidates
        if week_number - state.last_used_week.get(w["id"], -(10**9))
        > KEY_WORKOUT_NO_REPEAT_WINDOW_WEEKS
    ]
    pool = fresh or candidates
    under_cap = [
        w
        for w in pool
        if state.use_counts.get(w["id"], 0) < KEY_WORKOUT_MAX_USES_PER_PLAN
    ]
    return under_cap or pool


# Long-ultra-only template: a short headlamp run during the peak phase to
# rehearse darkness pacing and gear. Bracketed via ``brackets`` so it never
# fires for short/standard plans (or road).
_LONG_ULTRA_NIGHT_RUN: Dict[str, Any] = {
    "id": "trail_night_run",
    "distances": [30.0],  # trail-tagged; trail_profile widens this to any bracket
    "brackets": ["long_ultra"],
    "phases": ["peak"],
    "type": "tempo",
    "terrain": ["any"],
    "name": "Headlamp Night Run",
    "structure": "45-60 min easy night run on trails with headlamp and hand torch",
    "description": (
        "After dark: 45-60 min easy effort on a familiar trail loop with a "
        "headlamp (and a backup hand torch). Practice the gear, the depth "
        "perception, and eating/drinking by feel. Run conservatively — a "
        "trip in the dark is the goal to avoid, not to recover from."
    ),
    "intensity": "low",
    "target_zone": 2,
    "pace_zone": "E",
    "rationale": (
        "100-mile races run through the night. Rehearsing in the dark "
        "lets you debug gear, fueling, and pacing while the stakes are low — "
        "not at 2am during the race."
    ),
}

# Backward-compatible alias: tests and internal code import _WORKOUTS.
_WORKOUTS = list(WORKOUTS) + [_LONG_ULTRA_NIGHT_RUN]


# Minimum workout distance for key workouts whose structure (time-based reps,
# technical-terrain blocks) doesn't fit the small budget allocated by the
# phase distribution. Without these floors a 6 × 3-min hill session ends up
# with a 0.65 km warm-up and a sub-3 km displayed total, even though the
# actual work covers ~3 km on its own. Apply by bumping ``actual_distance``
# in :func:`overlay_key_workout` before description / step generation.
_KEY_WORKOUT_MIN_DISTANCE_KM: Dict[str, float] = {
    "trail_elevation_repeats": 5.0,
    "trail_technical_terrain": 4.5,
    "trail_power_hike": 6.0,
    "trail_downhill_technique": 5.0,
    "5k_hill_sprints": 4.0,
    "trail_pyramid_intervals": 5.0,
    "trail_ladder_intervals": 5.0,
    # 5 km of continuous work plus warm-up/cool-down never fits a smaller slot.
    "time_trial_5k": 7.0,
}

# Minimum day budget (km) a slot must offer before these sessions are eligible
# for selection. Unlike ``_KEY_WORKOUT_MIN_DISTANCE_KM`` (which bumps the
# session up to a workable size), a budget floor rejects the candidate: a
# km-rep session on a slot that can't hold its reps plus real bookends would
# have its identity rewritten away ("3 x 1 km" shrinking to "3 x 0.5 km"),
# and bumping it instead would blow up a low-volume week. Undersized slots
# fall through to the next candidate in rotation (typically a duration-based
# session, which fits small budgets by design).
_KEY_WORKOUT_MIN_BUDGET_KM: Dict[str, float] = {
    # Canonical 3 × 1 km reps + the hard-profile bookends (a 5.0 km slot only
    # leaves ~2.8 km of work — two reps — so the floor sits where three fit).
    "5k_vo2max_1000s": 5.5,
    "10k_vo2max_1000s": 5.5,
    "half_km_intervals": 5.5,
    "marathon_km_intervals": 5.5,
    # 2 × 1600 m + bookends.
    "10k_mile_repeats": 5.5,
    "half_mile_repeats": 5.5,
    "10k_broken_miles": 6.0,
    "trail_flat_broken_miles": 6.0,
    # 2 × 2 km canonical MP blocks + tempo bookends.
    "marathon_mp_blocks": 6.5,
    # Fixed prescriptions whose priced steps overflow smaller slots by
    # kilometres (rep-count floors, fixed rep sets, or fixed session times).
    # Floor ≈ the smallest budget where the built session prices at ~budget.
    "marathon_yasso_800s": 7.0,
    "marathon_mp_cutdown": 6.5,
    "10k_pyramid_intervals": 6.5,
    "10k_rolling_500s": 6.5,
    "trail_rolling_500s": 6.5,
    "trail_flat_rolling_500s": 6.5,
    "trail_pyramid_intervals": 10.0,
    "trail_ladder_intervals": 10.0,
    "trail_flat_pyramid": 5.5,
    "trail_power_hike": 7.0,
    "trail_flat_power_walk": 9.0,
    "trail_base_hike_run": 6.0,
    "trail_hill_pyramid": 6.5,
    "trail_flat_over_under_intervals": 6.5,
    # Taper sharpeners: the easy bulk + touches price well past a token slot,
    # which would push the sharpener to (or past) the shrunken race-week long
    # run on very low-volume plans. Undersized slots keep the generic
    # sharpener instead.
    "taper_5k10k_sharpener": 3.0,
    "taper_half_sharpener": 3.0,
    "taper_marathon_sharpener": 3.5,
}


# Sessions installed only by the intensive-weekend post-pass (via ``force_id``).
# They presuppose the weekend context (e.g. "fatigued from yesterday"), so they
# are excluded from the normal ``week_in_phase`` rotation to avoid appearing as
# standalone sessions and to keep existing rotation expectations stable.
_ITW_ONLY_IDS = frozenset({"trail_hike_run_long", "trail_b2b_day2"})

# Backyard sessions are parameterised by the runner's loop length and rest
# budget — neither of which the rotation's (distance, phase, terrain)
# interface can express — so the backyard week post-pass installs them
# directly. They stay in the catalog for ``get_by_id`` resolution only.
_BACKYARD_ONLY_IDS = frozenset(
    {
        "backyard_loop_simulation",
        "backyard_night_simulation",
        "backyard_dress_rehearsal",
        "backyard_turnaround_drill",
        "backyard_loop_repeats",
        "backyard_b2b_day2",
    }
)

# Every session the rotation must never surface on its own: both families are
# installed by a post-pass that already knows which one it wants.
_FORCE_ONLY_IDS = _ITW_ONLY_IDS | _BACKYARD_ONLY_IDS


_BRACKET_RESTRICTIONS: Dict[str, list] = {
    "trail_back_to_back": ["ultra", "long_ultra"],
    "trail_long_race_simulation": ["ultra", "long_ultra"],
    "trail_flat_long_race_sim": ["ultra", "long_ultra"],
    "trail_flat_long_fueling": ["standard", "ultra", "long_ultra"],
    "trail_power_hike": ["standard", "ultra", "long_ultra"],
    "trail_time_on_feet": ["standard", "ultra", "long_ultra"],
}


# Deterministic rotation-start weighting. Build and peak get distinct offsets so
# one plan showcases different sessions in each phase; the type weighting keeps
# the two quality slots in a week from locking onto parallel positions.
_PHASE_ROTATION_WEIGHT = {"base": 0, "build": 1, "peak": 2}
_TYPE_ROTATION_WEIGHT = {"interval": 0, "tempo": 1, "hill": 2, "long": 3}


def _rotation_offset(target_distance: float, phase: str, workout_type: str) -> int:
    """Stable rotation-start offset for the candidate list.

    A pure function of the selection inputs — same inputs always yield the same
    offset — so plan generation stays reproducible while the starting window
    varies by distance, phase, and workout type.
    """
    return (
        int(round(target_distance))
        + _PHASE_ROTATION_WEIGHT.get(phase, 0) * 3
        + _TYPE_ROTATION_WEIGHT.get(workout_type, 0)
    )


def _bracket_allowed(workout: Dict[str, Any], bracket: str) -> bool:
    explicit = workout.get("brackets")
    if explicit is not None:
        return bracket in explicit
    restriction = _BRACKET_RESTRICTIONS.get(workout.get("id", ""))
    if restriction is not None:
        return bracket in restriction
    return True


# Canonical catalog distance per road band — non-canonical road targets
# (e.g. a 28 km race) draw their band's catalog instead of matching nothing.
_ROAD_BAND_CATALOG_KM = {"5k": 5.0, "10k": 10.0, "half": 21.1, "marathon": 42.2}


def _trail_aware_distance_filter(
    target_distance: float,
    trail_profile,
) -> List[Dict[str, Any]]:
    """Return workouts whose ``distances`` list matches the goal.

    For trail/ultra plans, every workout tagged with the legacy 30.0 sentinel
    is considered eligible (subject to bracket gating below). This unlocks
    the existing 15+ trail workout templates for 50/80/163 km plans without
    requiring a per-distance fan-out in every workout entry.

    Road plans bucket the target into its :func:`classify_road` band and use
    the band's canonical distance: catalog entries list exact floats
    (5/10/21.1/42.2), so a 28 km road race would otherwise match zero key
    workouts and every quality slot would fall back to the generic builders.
    """
    if trail_profile is not None:
        return [
            w
            for w in _WORKOUTS
            if 30.0 in w["distances"] or target_distance in w["distances"]
        ]
    if is_trail_target(target_distance, trail_profile):
        # Legacy 30 km trail sentinel: exact matching only — bucketing it
        # into the marathon road band would leak road sessions into trail.
        return [w for w in _WORKOUTS if target_distance in w["distances"]]
    catalog_km = _ROAD_BAND_CATALOG_KM[classify_road(target_distance)]
    return [
        w
        for w in _WORKOUTS
        if target_distance in w["distances"] or catalog_km in w["distances"]
    ]


def _filter_candidates(
    workout_type: str,
    target_distance: float,
    phase: str,
    terrain: Optional[str],
    trail_profile,
    budget_km: Optional[float] = None,
) -> List[Dict[str, Any]]:
    candidates = [
        w
        for w in _trail_aware_distance_filter(target_distance, trail_profile)
        if phase in w["phases"]
        and w["type"] == workout_type
        and w["id"] not in _FORCE_ONLY_IDS
    ]

    # Budget gating — sessions whose fixed reps can't fit the day's allocation
    # are skipped rather than shrunk past recognition (see
    # _KEY_WORKOUT_MIN_BUDGET_KM). Only applied when the caller knows the
    # budget; catalog-browsing callers pass None and see everything.
    if budget_km is not None and budget_km > 0:
        candidates = [
            w
            for w in candidates
            if budget_km >= _KEY_WORKOUT_MIN_BUDGET_KM.get(w["id"], 0.0)
        ]

    # Terrain filter — flat-only or hilly/any otherwise.
    if terrain == "flat" or (
        terrain is None and trail_profile and trail_profile.elevation_class == "flat"
    ):
        candidates = [w for w in candidates if "flat" in w.get("terrain", ["any"])]
    elif trail_profile is not None or terrain is not None:
        candidates = [
            w
            for w in candidates
            if "any" in w.get("terrain", ["any"])
            or "hilly" in w.get("terrain", ["any"])
        ]

    # Bracket gating — ultra-specific workouts (e.g. back-to-back) only fire
    # for ultra/long_ultra plans.
    if trail_profile is not None:
        candidates = [
            w for w in candidates if _bracket_allowed(w, trail_profile.bracket)
        ]

    return candidates


def overlay_key_workout(
    workout: Dict[str, Any],
    workout_type: str,
    phase: str,
    target_distance: float,
    week_in_phase: int,
    terrain: Optional[str] = None,
    pace_zones: Optional[Dict] = None,
    trail_profile=None,
    force_id: Optional[str] = None,
    max_distance: Optional[float] = None,
    slot_index: int = 0,
    weekly_km: Optional[float] = None,
    state: Optional[KeyWorkoutRotationState] = None,
    week_number: Optional[int] = None,
) -> None:
    """Attach key workout metadata, description, and steps for quality sessions.

    Replaces any existing ``segments`` with parsed ``steps`` so the template
    always renders session blocks that match the ``structure`` one-liner.

    When ``force_id`` is given, that specific key workout is installed
    (bypassing the ``week_in_phase`` rotation and the candidate filters) — used
    by the intensive-weekend post-pass to pin a chosen session.

    ``max_distance`` is the physiological ceiling (km) the resulting session may
    occupy — typically ``MAX_KEY_WORKOUT_VS_LONG_RUN * long_run``. A fixed
    library prescription whose steps would exceed it is trimmed (reps dropped,
    not rewritten short) so quality work never reaches the long run; sessions
    already within the ceiling keep their full prescribed length.

    ``slot_index`` is the 0-based count of same-type quality slots already
    filled this week. Without it, a week granted two slots of one type
    (e.g. marathon peak's ``{"tempo": 2}``) selects the identical session
    twice — same inputs, same rotation index.

    ``weekly_km`` enables the Daniels intensity-volume caps: a session's
    I/R/T work set is trimmed to its weekly-share ceiling, and an
    intensity-led session's total is bounded by ``MAX_QUALITY_DAY_SHARE`` of
    the week (M/E-dominated sessions — MP long runs, fueling runs — are
    exempt from the day-share bound).

    ``state`` + ``week_number`` (both plan-generator supplied) enable the
    variety/progression pass: the no-repeat window and per-plan use cap on
    selection, and the peak-phase invariant that an interval day's work set
    never drops below the last build week's (a rotation that would regress —
    e.g. 4 × 400 in build followed by 3 × 500 in peak — advances to the next
    candidate instead).
    """
    if workout_type not in ("interval", "tempo", "hill", "long"):
        return
    if phase not in ("base", "build", "peak", "taper"):
        return
    if workout.get("duration_min"):
        return

    if force_id is not None:
        forced = KeyWorkoutLibrary.get_by_id(force_id)
        candidates = [forced] if forced else []
    else:
        candidates = KeyWorkoutLibrary.ordered_candidates(
            target_distance,
            phase,
            week_in_phase,
            workout_type,
            terrain=terrain,
            trail_profile=trail_profile,
            slot_index=slot_index,
            budget_km=workout.get("distance") or None,
            state=state,
            week_number=week_number,
        )
    if not candidates:
        return

    # Peak interval days must not regress below the last build week's work
    # set. When the first rotation candidate would, walk the remaining
    # candidates (still deterministic — rotation order) and install the first
    # that holds the line; if none can, keep the biggest available session.
    work_floor_km = 0.0
    if (
        state is not None
        and force_id is None
        and phase == "peak"
        and workout_type == "interval"
    ):
        work_floor_km = state.build_interval_work_km

    key_wk = candidates[0]
    if work_floor_km > 0 and state is not None:
        # The variety filter can leave only intrinsically-small sessions in
        # the pool (e.g. every big peak session was just used in late build),
        # so when the filtered pool can't hold the line, widen the retry to
        # the unfiltered rotation — still refusing an immediate repeat of
        # last week's session, which outranks the work floor.
        widened = KeyWorkoutLibrary.ordered_candidates(
            target_distance,
            phase,
            week_in_phase,
            workout_type,
            terrain=terrain,
            trail_profile=trail_profile,
            slot_index=slot_index,
            budget_km=workout.get("distance") or None,
        )
        seen = {c["id"] for c in candidates}
        last_week_ids = {
            wid
            for wid, wk in state.last_used_week.items()
            if week_number is not None and wk == week_number - 1
        }
        pool = candidates + [
            c for c in widened if c["id"] not in seen and c["id"] not in last_week_ids
        ]
        best_wk, best_work = None, -1.0
        for candidate in pool:
            trial = dict(workout)
            _install_key_workout(
                trial, candidate, workout_type, pace_zones, max_distance, weekly_km
            )
            work = sum(_steps_mod.work_km_by_group(trial["steps"]).values())
            if work >= work_floor_km - PEAK_WORK_FLOOR_TOLERANCE_KM:
                best_wk = candidate
                break
            if work > best_work:
                best_wk, best_work = candidate, work
        key_wk = best_wk or key_wk

    _install_key_workout(
        workout, key_wk, workout_type, pace_zones, max_distance, weekly_km
    )

    if state is not None and week_number is not None:
        state.record_use(key_wk["id"], week_number)
        if phase == "build" and workout_type == "interval":
            state.record_build_interval_work(
                week_number,
                sum(_steps_mod.work_km_by_group(workout["steps"]).values()),
            )


def _install_key_workout(
    workout: Dict[str, Any],
    key_wk: Dict[str, Any],
    workout_type: str,
    pace_zones: Optional[Dict],
    max_distance: Optional[float],
    weekly_km: Optional[float],
) -> None:
    """Install one chosen key workout onto a slot (prose, steps, caps).

    The build/trim/reconcile pipeline shared by the normal overlay path and
    the peak-invariant candidate loop (which builds trial installs on dict
    copies before committing one).
    """
    if pace_zones:
        key_wk = KeyWorkoutLibrary.inject_vdot_paces(key_wk, pace_zones)

    actual_distance = workout.get("distance", 0)
    floor = _KEY_WORKOUT_MIN_DISTANCE_KM.get(key_wk["id"], 0)
    if floor > 0:
        actual_distance = max(actual_distance, floor)
    frac = _RUNNING_DISTANCE_FRACTION.get(key_wk["id"])
    if frac is not None and actual_distance > 0:
        actual_distance = round(actual_distance * frac, 1)
    workout["distance"] = actual_distance
    # The rewrite lambdas size warm-ups through _wucd_m; scope the hard/tempo
    # profile to the session type so the prose cites the same bookends the
    # step builders produce (build_key_workout_steps scopes itself the same
    # way).
    with _steps_mod.wucd_profile(key_wk.get("type")):
        description = key_wk["description"]
        if actual_distance > 0:
            description = _rewrite_key_workout_description(
                description,
                key_wk["id"],
                actual_distance,
            )

        rewritten = actual_distance > 0 and key_wk["id"] in _DISTANCE_REWRITES

        workout["description"] = description
        workout["key_workout_id"] = key_wk["id"]
        workout["key_workout_name"] = key_wk["name"]
        if key_wk["id"] in _STRUCTURE_REWRITES:
            workout["structure"] = _STRUCTURE_REWRITES[key_wk["id"]](actual_distance)
        elif rewritten:
            workout["structure"] = _derive_structure(description)
        else:
            workout["structure"] = key_wk["structure"]
    workout["key_workout_rationale"] = key_wk["rationale"]

    # Propagate the key workout's own intensity so the card classification
    # matches the session — without this the registry default (e.g. "high" for
    # interval/hill, "medium" for tempo) is kept even when the key workout is
    # intentionally lighter (base-phase strides have intensity="low" but were
    # shown as "high" because the overlay never overwrote the builder default).
    if "intensity" in key_wk:
        workout["intensity"] = key_wk["intensity"]

    # Structured-first step generation, shared with rebuild_key_workout. The
    # fractional/prose runs become a single block; only genuinely unparseable
    # prose reaches the hardened parser fallback.
    workout["steps"] = build_key_workout_steps(
        key_wk,
        workout["structure"],
        actual_distance,
        workout_type,
        pace_zones,
    )

    # Physiological ceiling: a fixed prescription (e.g. 8 × 500 m, or a
    # time-defined hike-run) can run longer than the runner's long run on a
    # low-mileage plan. Trim it to ``max_distance`` by dropping reps so the
    # quality day never reaches the long run, while leaving sessions that
    # already fit at their full prescribed length.
    if max_distance and max_distance > 0:
        workout["steps"] = _steps_mod.fit_steps_to_distance(
            workout["steps"], max_distance
        )

    # Intensity-volume safety caps (Daniels): bound the I/R/T work set by its
    # weekly share, then bound an intensity-led session's total by the
    # quality-day share. Sessions whose work is predominantly M/E-pace (MP
    # long runs, race rehearsals) keep their size — the big day is the point.
    if weekly_km and weekly_km > 0:
        workout["steps"] = _steps_mod.fit_steps_to_intensity_caps(
            workout["steps"], weekly_km
        )
        capped_work = sum(_steps_mod.work_km_by_group(workout["steps"]).values())
        if capped_work > _steps_mod.exempt_work_km(workout["steps"]):
            day_cap = max(MIN_QUALITY_DAY_CAP_KM, weekly_km * MAX_QUALITY_DAY_SHARE)
            workout["steps"] = _steps_mod.fit_steps_to_distance(
                workout["steps"], round(day_cap, 1)
            )

    # Reconcile displayed total with what the runner will actually cover —
    # duration-based reps (e.g. 6 × 3 min hard) contributed nothing to the
    # phase-allocated budget, so the pre-overlay ``distance`` undercounts
    # quality work. Recompute from the executable steps (pace × time fills
    # in for time-based reps) so weekly mileage and the workout card match.
    # ``workout['distance']`` is what the runner will actually cover;
    # ``actual_distance`` is the budget the description and steps were
    # rendered/parsed against. They differ when duration-based reps add
    # mileage on top of the budgeted warm-up + cool-down (e.g. 6 × 3-min
    # hill repeats). The description and step list stay rendered against
    # ``actual_distance`` — that's the value baked into the formulas
    # (warm-up size, main_km splits) and the parser (implicit wu/cd) — so
    # the cited numbers match the steps. The displayed total reflects
    # actual coverage so weekly mileage adds up.
    steps_total_km, fully_priced = _steps_mod.compute_distance_from_steps_checked(
        workout["steps"]
    )
    if steps_total_km > 0:
        if fully_priced:
            workout["distance"] = round(steps_total_km, 1)
        else:
            # Some duration reps couldn't be priced, so the steps total is a
            # lower bound. Never shrink the session below its budget on
            # incomplete math (this halved fartleks to warm-up + cool-down).
            # This path should be rare (every builder is expected to emit
            # priceable steps) — log it so pricing regressions surface.
            _logger.warning(
                "key workout %s not fully priced: steps=%.1f km, budget=%.1f km",
                key_wk["id"],
                steps_total_km,
                actual_distance,
            )
            workout["distance"] = round(max(actual_distance, steps_total_km), 1)

    workout.pop("segments", None)


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
        trail_profile=None,
        slot_index: int = 0,
        budget_km: Optional[float] = None,
        state: Optional[KeyWorkoutRotationState] = None,
        week_number: Optional[int] = None,
    ) -> Optional[Dict]:
        """Select a key workout for the given distance, phase, and week.

        Args:
            target_distance: Race distance in km.
            phase:           Training phase (base, build, peak, taper).
            week_in_phase:   Zero-indexed week within the current phase.
            workout_type:    Requested workout type (interval, tempo, hill).
            terrain:         Terrain access string ('flat' or rolling/hilly/
                             mountainous). Only affects trail selection.
            trail_profile:   Preferred input for trail/ultra plans. When
                             present, trail-tagged workouts (those listing
                             30.0 in their ``distances``) become eligible
                             for any trail bracket and are further filtered
                             by the workout's optional ``brackets`` field.
            state:           Optional plan-level rotation state; enables the
                             no-repeat window and the per-plan use cap.
            week_number:     Absolute plan week (1-based), required for the
                             window arithmetic when ``state`` is passed.

        Returns:
            A workout dict or None if no key workout applies.
        """
        ordered = cls.ordered_candidates(
            target_distance,
            phase,
            week_in_phase,
            workout_type,
            terrain=terrain,
            trail_profile=trail_profile,
            slot_index=slot_index,
            budget_km=budget_km,
            state=state,
            week_number=week_number,
        )
        return ordered[0] if ordered else None

    @classmethod
    def ordered_candidates(
        cls,
        target_distance: float,
        phase: str,
        week_in_phase: int,
        workout_type: str = "interval",
        terrain: Optional[str] = None,
        trail_profile=None,
        slot_index: int = 0,
        budget_km: Optional[float] = None,
        state: Optional[KeyWorkoutRotationState] = None,
        week_number: Optional[int] = None,
    ) -> List[Dict]:
        """Rotation-ordered candidate list for a slot (best pick first).

        Same filtering as :meth:`get_for_phase`; callers that may need to
        reject the first pick (the peak work-set invariant) walk the rest in
        order so retries stay deterministic.
        """
        # Key workouts fire in base (light strides/fartlek only — the catalog
        # gates which sessions are base-eligible via their ``phases`` list),
        # build, peak, and taper (race-distance-specific sharpeners tagged
        # ``taper``; everything else is gated out by its ``phases`` list).
        if phase not in ("base", "build", "peak", "taper"):
            return []

        candidates = _filter_candidates(
            workout_type,
            target_distance,
            phase,
            terrain,
            trail_profile,
            budget_km=budget_km,
        )
        candidates = _apply_variety_filter(candidates, state, week_number)
        if not candidates:
            return []

        # Rotate through candidates, but start the rotation at a deterministic
        # per-(distance, phase, type) offset rather than always at index 0.
        # Walking the catalog from a fixed front meant freshly-appended sessions
        # (which land at the tail) only surfaced in long phases; a varied start
        # window spreads the catalog so build and peak — and different race
        # distances — showcase different sessions, while staying fully
        # reproducible (a pure function of the inputs, no salted hashing).
        # ``slot_index`` advances the rotation for a second same-type slot in
        # the same week so it lands on a different candidate than the first.
        offset = _rotation_offset(target_distance, phase, workout_type)
        start = (week_in_phase + offset + slot_index) % len(candidates)
        return candidates[start:] + candidates[:start]

    @classmethod
    def get_by_id(cls, workout_id: str) -> Optional[Dict]:
        """Return the key workout with the given id, or None.

        Bypasses phase/terrain/bracket filtering and rotation — the caller
        (intensive-weekend post-pass) has already chosen the session.
        """
        for w in _WORKOUTS:
            if w.get("id") == workout_id:
                return w
        return None

    @classmethod
    def get_all_for_distance(
        cls, target_distance: float, terrain: Optional[str] = None, trail_profile=None
    ) -> List[Dict]:
        """Return all key workouts for a race distance."""
        workouts = [
            w
            for w in _trail_aware_distance_filter(target_distance, trail_profile)
            if w["id"] not in _FORCE_ONLY_IDS
        ]
        if terrain == "flat" or (
            terrain is None
            and trail_profile
            and trail_profile.elevation_class == "flat"
        ):
            workouts = [w for w in workouts if "flat" in w.get("terrain", ["any"])]
        elif terrain is not None or trail_profile is not None:
            workouts = [
                w
                for w in workouts
                if "any" in w.get("terrain", ["any"])
                or "hilly" in w.get("terrain", ["any"])
            ]
        if trail_profile is not None:
            workouts = [
                w for w in workouts if _bracket_allowed(w, trail_profile.bracket)
            ]
        return workouts

    @classmethod
    def inject_vdot_paces(cls, workout: Dict, vdot_zones: Optional[Dict]) -> Dict:
        """Enrich a workout description with specific VDOT-based paces.

        Args:
            workout:    Workout dict (not mutated -- returns a copy).
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
