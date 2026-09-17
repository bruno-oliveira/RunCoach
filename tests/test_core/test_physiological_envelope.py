"""Physiological-envelope harness: plan generation across the accepted domain.

Complementary to ``test_plan_structure_invariants.py``. That module asks "is
this plan runnable?"; this one asks "is this plan *sensible for a real runner at
this race distance and training frequency*?" — by checking every plan the
generator will accept against ``app.core.training.physiological_envelope``.

Two tiers, deliberately separated:

* **Hard invariants** — must hold for every cell today: generation never raises,
  the structure guard finds nothing fatal, and no plan over-prescribes weekly
  volume past the envelope's upper band.
* **Tracked gaps** — known, measured deviations pinned per
  ``(distance, runs/week)`` cell and named after the workstream that closes
  them. The suite fails on any *new* violation, so a regression is caught while
  the tracked gaps are worked through, and the ``KNOWN_GAPS`` table is the
  honest inventory of what is still wrong.

The matrix here is the *accepted* domain — the same bounds the request schema
and ``DISTANCE_CONSTRAINTS`` allow — not just the happy middle of it.
"""

from typing import Any, Dict, FrozenSet, List, Set, Tuple

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.generators.plan_structure_guard import check_plan_structure
from app.core.training import long_run_calculator, mileage_progression
from app.core.training import physiological_envelope as env
from app.core.training.strength_plan import derive_experience_level
from app.core.training.tuning import ROAD_LONG_RUN_CAPS

# distance -> (minimum base km, minimum weeks, maximum weeks)
MATRIX: Dict[float, Tuple[float, int, int]] = {
    5.0: (5.0, 6, 16),
    10.0: (10.0, 6, 16),
    21.1: (15.0, 8, 20),
    42.2: (25.0, 12, 24),
}
RUN_FREQUENCIES = (2, 3, 4, 5, 6)
_BASE_CANDIDATES = (10.0, 25.0, 50.0, 75.0, 100.0, 150.0, 200.0)

# A long-run regression this deep between loading weeks is a progression fault,
# A loading-week long-run regression this deep is a progression fault rather
# than week-to-week wobble. The defect it was written to catch (the ratio
# restarting at each phase boundary) dropped the long run 26-28%; a high-base
# "hold" plan deliberately undulates the week +/-4%, which moves the long run by
# at most ~8% with it. 10% separates the two.
LONG_RUN_DROP_TOLERANCE = 0.10
# Delivered peak below this fraction of the modelled target means the week
# layout cannot hold what the periodisation model asked for (D1 residual).
PEAK_RECONCILIATION_FLOOR = 0.85

NON_RUNNING_TYPES = ("rest", "recovery")
QUALITY_TYPES = ("tempo", "interval", "hill")

# --- Tracked gaps -----------------------------------------------------------
# kind -> distance -> frequencies where the gap is known to exist today.
# Every entry is a measured deviation, not a guess.
KNOWN_GAPS: Dict[str, Dict[float, FrozenSet[int]]] = {
    # D5 — at 2 runs the week is 1 long + 1 quality pinned against each other;
    # the long run wobbles ±12-16% between loading weeks.  At 3+ runs on 5K the
    # long run is so short (<8 km) that small phase-transition volume shifts
    # exceed the 10% tolerance.  At 3 runs on longer distances, the single easy
    # slot is capped (volume-scaled easy cap), so the long run absorbs volume
    # swings at phase transitions, creating >10% drops when quality volume
    # increases in build phase.
    "long_run_material_drop": {
        5.0: frozenset({2, 4}),
        10.0: frozenset({2, 5}),
        21.1: frozenset({2, 5}),
        42.2: frozenset({2}),
    },
    # The contracted long-run cap is tight for 5K (floor ~8 km) — at 4 runs
    # with high base mileage the per-run distribution pushes past it.  The HM
    # cell at 5 runs is a pinning overlay whose prescription lands just past
    # the cap computed at the volume the week delivers.
    "long_run_over_contract_cap": {
        5.0: frozenset({4}),
        21.1: frozenset({5}),
    },
    # Volume-scaled easy cap correctly prevents easy runs from becoming second
    # long runs, but at ≤3 runs/week there aren't enough slots to absorb the
    # full model volume once easy runs are capped.  At 4+ runs on longer
    # distances the quality allocation can still leave a shortfall when the
    # volume target is aggressive relative to the per-run ceilings.  This is
    # the expected trade-off: healthy run distribution > hitting volume targets.
    "peak_shortfall": {
        5.0: frozenset({2, 3, 4, 5, 6}),
        10.0: frozenset({2}),
        21.1: frozenset({2, 3}),
        42.2: frozenset({2, 4}),
    },
    # Low-volume corner cases: at low base mileage split over many runs the
    # per-run distance falls below the viable floor.  The plan is faithful to
    # what the runner actually runs; the frequency advisory fires.
    "sub_viable_run": {
        5.0: frozenset({2}),
        10.0: frozenset({3}),
        21.1: frozenset({5, 6}),
    },
}


def bases_for(distance_km: float) -> List[float]:
    """The accepted base-mileage values for a race distance."""
    minimum = MATRIX[distance_km][0]
    return sorted({minimum} | {b for b in _BASE_CANDIDATES if b >= minimum})


def weeks_for(distance_km: float) -> List[int]:
    """Weeks across the accepted range, stepping by two to bound runtime."""
    _, minimum, maximum = MATRIX[distance_km]
    return list(range(minimum, maximum + 1, 2))


def _running(week: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        w
        for w in week.get("daily_workouts", [])
        if w.get("type") not in NON_RUNNING_TYPES and (w.get("distance") or 0) > 0
    ]


def _long_run(week: Dict[str, Any]) -> float:
    return max(
        (w.get("distance") or 0 for w in _running(week) if w.get("type") == "long"),
        default=0,
    )


def _loading_weeks(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Weeks that are neither a deload nor the taper.

    Taper weeks are excluded deliberately: the taper's job is to bring volume
    and the long run *down* toward race day, so treating its drawdown as a
    progression fault (or as a candidate for the plan's peak week) inverts the
    intent. Deloads are excluded for the same reason.
    """
    return [
        w
        for w in plan
        if not w.get("is_recovery")
        and not w.get("is_race_week")
        and w.get("phase") != "taper"
    ]


def collect_gaps(distance_km: float, runs: int, base: float, weeks: int) -> Set[str]:
    """Envelope violations for one generated plan, as a set of gap kinds."""
    plan = TrainingPlanGenerator().generate_plan(
        base, distance_km, weeks, max_runs_per_week=runs
    )
    found: Set[str] = set()
    loading = _loading_weeks(plan)
    if not loading:
        return {"no_loading_week"}

    peak = max(w.get("total_km") or 0 for w in loading)

    lo, hi = env.peak_week_band(distance_km, runs)
    if peak > hi + 0.05:
        found.add("peak_above_band")
    # Only meaningful at 4+ runs. At 2-3 runs a high-base runner *cannot* hold
    # their volume inside the per-run caps, so the plan correctly prescribes
    # less than they already run — and says so: ``assess_frequency_volume_adequacy``
    # fires exactly there with "add a training day". Flagging it would mark a
    # documented, advised trade-off as a defect.
    if runs >= 4 and base >= lo and peak < lo - 0.05:
        found.add("peak_below_band_despite_base")

    peak_long = max((_long_run(w) for w in plan), default=0)
    if peak_long > ROAD_LONG_RUN_CAPS[distance_km]["advanced"] * 1.75 + 0.05:
        # A second, looser reading of the same concern: the *published* band for
        # a well-adapted runner. Not a contract — ``long_run_cap`` above is —
        # but a plan carrying a single run this far past its static tier cap is
        # worth a look regardless of how much weekly volume funded it.
        found.add("long_run_well_over_tier_cap")
    contract_cap = long_run_calculator.long_run_cap(
        distance_km,
        derive_experience_level(base) if base else "beginner",
        weekly_km=max(w.get("total_km") or 0 for w in loading),
    )
    if peak_long > contract_cap + 0.5:
        # The real contract: ``long_run_cap`` scales with weekly volume, so the
        # static tier table (8 km for a 5K) is its floor, not its value. This is
        # the same bound ``fill_shortfall`` enforces, so exceeding it means a
        # prescriptive long-run overlay slipped past the clamp.
        found.add("long_run_over_contract_cap")

    share_ceiling = env.long_run_share_ceiling(runs)
    for week in plan:
        if week.get("is_recovery"):
            continue
        total = week.get("total_km") or 0
        long_km = _long_run(week)
        if total > 0 and long_km > 0 and long_km / total > share_ceiling + 0.005:
            found.add("share_over_ceiling")
            break

    # Long-run progression is compared across *loading* weeks only — a deload
    # dips by design and the taper is a deliberate drawdown, so neither is a
    # progression fault. What must never happen is the long run shrinking from
    # one loading week to the next (which it did at every phase boundary before
    # the ratio was floored).
    previous: float | None = None
    for week in _loading_weeks(plan):
        long_km = _long_run(week)
        if (
            previous is not None
            and long_km > 0
            and long_km < previous * (1 - LONG_RUN_DROP_TOLERANCE) - 0.05
        ):
            found.add("long_run_material_drop")
            break
        if long_km:
            previous = long_km

    # Intensity is what build and peak exist for, so a quality-free week there is
    # a real defect. Base is excluded on purpose: ``_phase_quality_count`` gives
    # base weeks no quality below 4 runs or 20 km/week, and that is deliberate
    # phase policy (a 5 km/week runner has no room for a threshold block) rather
    # than a miscalculation.
    for week in plan:
        if week.get("phase") not in ("build", "peak") or week.get("is_recovery"):
            continue
        if not any(w["type"] in QUALITY_TYPES for w in _running(week)):
            found.add("no_quality_session")
            break

    # Only meaningful when the runner's base could actually fill every slot at
    # the viable floor. At a 5 km/week base split over three runs the average is
    # 1.7 km: the plan is *faithful* to what they run, and shrinking the week
    # below their real volume (or dropping to two runs, which the request layer
    # allows for 5K/10K) would be worse, not better. The generator already
    # reduces frequency toward that floor; where it cannot reach it, the honest
    # answer is a product decision about the 5K minimum base, not a bug.
    base_can_fill_every_slot = base >= env.MIN_VIABLE_RUN_KM * runs
    if base_can_fill_every_slot:
        for week in plan:
            if week.get("is_recovery") or week.get("phase") == "taper":
                continue
            if any(
                (w.get("distance") or 0) < env.MIN_VIABLE_RUN_KM - 0.05
                for w in _running(week)
            ):
                found.add("sub_viable_run")
                break

    target = mileage_progression.calculate_weekly_progression(
        base, distance_km, weeks, runs
    )
    candidates = [
        (i, target[i])
        for i, week in enumerate(plan)
        if i < len(target)
        and not week.get("is_recovery")
        and not week.get("is_race_week")
        and target[i] > 0
    ]
    if candidates:
        index, target_peak = max(candidates, key=lambda pair: pair[1])
        delivered = plan[index].get("total_km") or 0
        if delivered < target_peak * PEAK_RECONCILIATION_FLOOR:
            found.add("peak_shortfall")

    return found


def _matrix_ids() -> List[str]:
    ids = []
    for distance in MATRIX:
        for runs in RUN_FREQUENCIES:
            for base in bases_for(distance):
                for weeks in weeks_for(distance):
                    ids.append(f"{distance}km-{runs}r-{base:.0f}base-{weeks}wk")
    return ids


def _matrix():
    for distance in MATRIX:
        for runs in RUN_FREQUENCIES:
            for base in bases_for(distance):
                for weeks in weeks_for(distance):
                    yield distance, runs, base, weeks


# --- Hard invariants --------------------------------------------------------


@pytest.mark.parametrize("case", list(_matrix()), ids=_matrix_ids())
def test_generation_never_raises_and_never_goes_fatal(case):
    """Every accepted input generates a plan with no fatal structural issue."""
    distance, runs, base, weeks = case
    plan = TrainingPlanGenerator().generate_plan(
        base, distance, weeks, max_runs_per_week=runs
    )
    assert plan, "generator returned an empty plan"
    issues = check_plan_structure(plan)
    assert issues["fatal"] == [], issues["fatal"]


@pytest.mark.parametrize("case", list(_matrix()), ids=_matrix_ids())
def test_weekly_volume_is_never_over_prescribed(case):
    """No plan peaks above the envelope's upper band for its frequency.

    This is the safety-relevant direction: under-prescribing at the bottom of
    the domain is expected (the 10% rule and a short timeline see to it, and the
    adequacy advisories exist for that), but *over*-prescribing weekly volume is
    what causes injury. Asserted unconditionally — nothing in the generator may
    exceed the band.
    """
    distance, runs, base, weeks = case
    plan = TrainingPlanGenerator().generate_plan(
        base, distance, weeks, max_runs_per_week=runs
    )
    loading = _loading_weeks(plan)
    assert loading, "plan has no loading week"
    peak = max(w.get("total_km") or 0 for w in loading)
    _, hi = env.peak_week_band(distance, runs)
    assert peak <= hi + 0.05, (
        f"{distance} km at {runs} runs/week from a {base:.0f} km base peaks at "
        f"{peak:.1f} km — above the {hi:.1f} km envelope"
    )


# --- Tracked gaps -----------------------------------------------------------


def test_no_new_envelope_violations():
    """Every envelope violation is one of the tracked, documented gaps.

    Runs the whole matrix once and reports the untracked remainder. A failure
    here means a *new* class of miscalibration, or that a tracked gap grew to a
    cell it was not known to affect.
    """
    unexpected: List[str] = []
    tracked_cells = 0
    for distance, runs, base, weeks in _matrix():
        found = collect_gaps(distance, runs, base, weeks)
        for kind in sorted(found):
            allowed = KNOWN_GAPS.get(kind, {}).get(distance, frozenset())
            if runs in allowed:
                tracked_cells += 1
                continue
            unexpected.append(
                f"{kind}: {distance} km / {runs} runs / {base:.0f} km base / "
                f"{weeks} weeks"
            )
    assert not unexpected, (
        f"{len(unexpected)} untracked envelope violation(s):\n  "
        + "\n  ".join(unexpected[:40])
        + f"\n({tracked_cells} tracked gap cells remain — add them to KNOWN_GAPS "
        "with the change that will close them, or fix them)"
    )


def test_every_tracked_gap_is_still_real():
    """The ``KNOWN_GAPS`` table must not outlive the gaps it documents.

    Guards the other direction: once a workstream lands, a stale allowlist entry
    would let the defect come back unnoticed.
    """
    observed: Dict[str, Dict[float, Set[int]]] = {}
    for distance, runs, base, weeks in _matrix():
        for kind in collect_gaps(distance, runs, base, weeks):
            if runs in KNOWN_GAPS.get(kind, {}).get(distance, frozenset()):
                observed.setdefault(kind, {}).setdefault(distance, set()).add(runs)
    stale = [
        f"{kind}: {distance} km @ {runs} runs"
        for kind, table in KNOWN_GAPS.items()
        for distance, runs_set in table.items()
        for runs in sorted(runs_set)
        if runs not in observed.get(kind, {}).get(distance, set())
    ]
    assert not stale, f"KNOWN_GAPS entries no longer reproduce: {stale}"


# --- The oracle itself ------------------------------------------------------


def test_envelope_module_is_self_consistent():
    """The reference bands must be internally coherent, or every test lies."""
    for distance, (lo, hi) in env.PEAK_WEEK_KM.items():
        assert 0 < lo < hi, f"peak week band inverted for {distance}"
    for distance, (lo, hi) in env.PEAK_LONG_RUN_KM.items():
        assert 0 < lo < hi, f"long-run band inverted for {distance}"
    # More run days can never mean less volume.
    factors = [
        env.FREQUENCY_VOLUME_FACTORS[r] for r in sorted(env.FREQUENCY_VOLUME_FACTORS)
    ]
    assert factors == sorted(factors), "frequency factors must be monotone"
    assert env.FREQUENCY_VOLUME_FACTORS[4] == 1.0, "4 runs is the reference"
    # A long run never becomes the whole week.
    for runs in RUN_FREQUENCIES:
        ceiling = env.long_run_share_ceiling(runs)
        assert 0.2 <= ceiling <= 0.7, f"implausible share ceiling {ceiling} at {runs}"
    # Interpolation fills the gaps between known distances without inverting.
    mid_lo, mid_hi = env.peak_week_band(15.0, 4)
    assert env.PEAK_WEEK_KM[10.0][0] < mid_lo < env.PEAK_WEEK_KM[21.1][0]
    assert env.PEAK_WEEK_KM[10.0][1] < mid_hi < env.PEAK_WEEK_KM[21.1][1]
    # Unknown frequencies degrade to the reference rather than raising.
    assert env.peak_week_band(42.2, 99) == env.peak_week_band(42.2, 4)


# --- Golden reference plans -------------------------------------------------

GOLDEN = {
    "5K / 8 weeks / 20 km base": (20.0, 5.0, 8),
    "half / 12 weeks / 30 km base": (30.0, 21.1, 12),
    "marathon / 16 weeks / 45 km base": (45.0, 42.2, 16),
}


@pytest.mark.parametrize("label", sorted(GOLDEN))
def test_golden_reference_plans_land_inside_the_envelope(label):
    """Realistic 4-run plans land inside the published bands.

    Bands, not snapshots: legitimate tuning must not break these, but drifting
    outside what recreational guidance supports must.
    """
    base, distance, weeks = GOLDEN[label]
    plan = TrainingPlanGenerator().generate_plan(
        base, distance, weeks, max_runs_per_week=4
    )
    peak = max(w.get("total_km") or 0 for w in _loading_weeks(plan))
    lo, hi = env.peak_week_band(distance, 4)
    assert lo - 0.05 <= peak <= hi + 0.05, (
        f"{label}: peak week {peak:.1f} km outside [{lo:.0f}, {hi:.0f}]"
    )
    peak_long = max((_long_run(w) for w in plan), default=0)
    assert peak_long > 0, label
    advanced_cap = ROAD_LONG_RUN_CAPS[distance]["advanced"]
    assert peak_long <= advanced_cap + 0.05, (
        f"{label}: peak long run {peak_long:.1f} km above the {advanced_cap:.0f} km "
        "experience cap"
    )
