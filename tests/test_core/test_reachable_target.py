"""Reachability-first capacity model: the resolver and its integration.

The audit this file locks in: a weekly mileage target the runner's frequency
cannot carry is not a plan but a wish — the week builder trims or craters, and
plan-vs-target fidelity is lost before adaptation ever sees the plan.

Two layers, mirroring the implementation:

* **The resolver** (:func:`resolve_reachable_target`) is pure, so it is
  co-evolved here against a realistic matrix — frequencies 1-7, bases 10-80 km,
  and targets drawn from the progression model itself across the race range —
  asserting the invariants that make it safe to call from anywhere: never above
  capacity, never below a sensible floor, monotone in frequency, deterministic.
* **The integration** (the reachability gate in ``plan_generator``) is asserted
  on generated plans: the target the scaler sees never overshoots what the
  schedule can deliver, and when the gate binds, the delivered peak week lands
  on the reachable target within builder rounding.
"""

import logging

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.periodization import mileage_progression as mp
from app.core.training.profiles.trail_profile import classify_trail

# The resolver's contract: a week under half a typical session is not a week.
FLOOR_SESSION_FRACTION = 0.5
# Builder rounding: the delivered peak may wobble ~1 km around the reachable
# target once per-run caps and the 10% pass have had their say.
PEAK_DELIVERY_SLACK_RATIO = 1.05


def _target_for(base: float, distance: float, weeks: int, runs: int) -> float:
    """The progression model's peak for one matrix cell."""
    return max(mp.calculate_weekly_progression(base, distance, weeks, runs))


# ── The resolver: co-evolution matrix ──────────────────────────────────────


@pytest.mark.parametrize("runs", range(1, 8))
@pytest.mark.parametrize("base", (10.0, 20.0, 40.0, 60.0, 80.0))
@pytest.mark.parametrize("distance", (10.0, 21.1, 42.2, 50.0, 100.0, 163.0))
@pytest.mark.parametrize("weeks", (6, 8, 12, 16, 24))
def test_reachable_target_never_exceeds_capacity(
    base: float, distance: float, weeks: int, runs: int
):
    """Across the matrix, the reachable target respects every invariant."""
    trail_profile = (
        classify_trail(distance, 2000.0) if distance not in (10.0, 21.1, 42.2) else None
    )
    if trail_profile is not None:
        # The progression model refuses shorter timelines for trail brackets;
        # give those cells a timeline the model accepts.
        from app.core.training.profiles.trail_profile import trail_min_weeks

        weeks = max(weeks, trail_min_weeks(trail_profile))
    session_km = mp.typical_session_length_km(trail_profile)
    target = _target_for(base, distance, weeks, runs)
    reachable, cap_reason, diag = mp.resolve_reachable_target(
        target, runs, session_km, base_km=base
    )

    assert reachable <= diag["capacity"] + 1e-9, (
        f"{base}/{distance}/{weeks}w/{runs}r: reachable {reachable} exceeds "
        f"capacity {diag['capacity']}"
    )
    assert reachable <= target + 1e-9, "a cap must never raise the target"
    # A week below half a session is not a training week — but the floor can
    # never push the result above the request either.
    floor = min(target, FLOOR_SESSION_FRACTION * session_km)
    assert reachable >= floor - 1e-9, (
        f"{base}/{distance}/{weeks}w/{runs}r: reachable {reachable} below the "
        f"sensible floor {floor}"
    )
    if cap_reason is None:
        assert reachable == pytest.approx(target)
    else:
        assert cap_reason in ("frequency_capacity", "base_volume_ceiling")
    assert diag["requested"] == pytest.approx(target)
    assert diag["reachable"] == pytest.approx(reachable)
    # The scaled ramp's start never sits above its own peak.
    assert diag["scaled_from_start"] <= diag["scaled_from_peak"] + 1e-9


@pytest.mark.parametrize("base", (10.0, 25.0, 50.0, 80.0))
@pytest.mark.parametrize("distance", (10.0, 21.1, 42.2))
def test_reachable_target_is_monotone_in_frequency(base: float, distance: float):
    """Higher frequency -> capacity never falls, so reachability never tightens.

    Held against a fixed target (the largest the matrix cell produces), so the
    only thing moving is the resolver's capacity.
    """
    session_km = mp.typical_session_length_km()
    target = _target_for(base, distance, 16, 7)
    previous_reachable = 0.0
    previous_capacity = 0.0
    for runs in range(1, 8):
        reachable, _, diag = mp.resolve_reachable_target(
            target, runs, session_km, base_km=base
        )
        assert diag["capacity"] >= previous_capacity - 1e-9
        assert reachable >= previous_reachable - 1e-9
        previous_reachable = reachable
        previous_capacity = diag["capacity"]


def test_reachable_target_is_deterministic():
    """Same inputs, same outputs — the resolver is a pure function."""
    args = (60.0, 3, mp.typical_session_length_km())
    first = mp.resolve_reachable_target(*args, base_km=40.0)
    second = mp.resolve_reachable_target(*args, base_km=40.0)
    assert first == second


def test_reachable_target_passes_through_when_below_capacity():
    """A target the schedule can carry stands unchanged, with no cap reason."""
    reachable, cap_reason, diag = mp.resolve_reachable_target(
        26.0, 2, mp.MAX_EASY_RUN_KM, base_km=15.0
    )
    assert cap_reason is None
    assert reachable == pytest.approx(26.0)
    assert diag["capacity"] == pytest.approx(mp.weekly_capacity(2, mp.MAX_EASY_RUN_KM))


def test_reachable_target_caps_at_frequency_capacity():
    """A peak above frequency x typical session is scaled down to capacity."""
    reachable, cap_reason, diag = mp.resolve_reachable_target(
        51.0, 2, mp.MAX_EASY_RUN_KM, base_km=10.0
    )
    assert cap_reason == "frequency_capacity"
    assert reachable == pytest.approx(diag["capacity"])
    assert diag["requested"] == pytest.approx(51.0)
    assert diag["scaled_from_start"] == pytest.approx(10.0)
    assert diag["scaled_from_peak"] == pytest.approx(reachable)


def test_reachable_target_pins_at_base_when_base_binds():
    """A high-volume runner's base raises the capacity floor: hold, don't detrain."""
    reachable, cap_reason, diag = mp.resolve_reachable_target(
        60.0, 2, mp.MAX_EASY_RUN_KM, base_km=45.0
    )
    assert cap_reason == "base_volume_ceiling"
    assert reachable == pytest.approx(45.0)
    assert diag["capacity"] == pytest.approx(45.0)


def test_cap_progression_preserves_ramp_shape_above_base():
    """The cap compresses the ramp above the base proportionally, never below it."""
    progression = [20.0, 22.0, 24.2, 26.6, 29.3, 20.0]
    capped = mp.cap_progression_to_peak(progression, 24.0, base_km=20.0)
    assert max(capped) == pytest.approx(24.0)
    # Weeks at or below the base pass through untouched.
    assert capped[0] == pytest.approx(20.0)
    assert capped[5] == pytest.approx(20.0)
    # Proportional spacing above the base: the ratios between successive
    # excesses are preserved by the single common factor.
    excesses = [w - 20.0 for w in capped[1:4]]
    ratios = [b / a for a, b in zip(excesses, excesses[1:])]
    original_excesses = [2.0, 4.2, 6.6]
    original = [b / a for a, b in zip(original_excesses, original_excesses[1:])]
    assert ratios == pytest.approx(original, rel=0.06)
    # And the input is never mutated.
    assert progression[4] == pytest.approx(29.3)


# ── The integration: generated plans honour the reachable target ───────────


def _weekly_targets(base, distance, weeks, runs):
    progression = mp.calculate_weekly_progression(base, distance, weeks, runs)
    session_km = mp.typical_session_length_km(None)
    peak = max(progression, default=0.0)
    reachable, cap_reason, _diag = mp.resolve_reachable_target(
        peak, runs, session_km, base_km=base
    )
    if cap_reason is not None:
        progression = mp.cap_progression_to_peak(progression, reachable, base)
    return progression


@pytest.mark.parametrize(
    "base,distance,weeks,runs",
    (
        (15.0, 10.0, 8, 2),
        (20.0, 21.1, 12, 2),
        (25.0, 21.1, 12, 3),
        (40.0, 42.2, 18, 4),  # the gate binds here: 76 km raw peak -> 56 km
    ),
)
def test_generated_weeks_never_overshoot_the_reachable_target(
    base: float, distance: float, weeks: int, runs: int
):
    """No loading week is planned past its (reachable) target by more than 5%.

    The audit's overshoot claim, stated as the invariant it implies: once the
    scaler sees a reachable target, the plan may fall short (the builder drops
    volume it cannot place) but must not silently promise more than the
    schedule can hold. Race week is exempt — the race itself is the goal, not
    a week the scaler sized.
    """
    plan = TrainingPlanGenerator().generate_plan(base, distance, weeks, runs)
    targets = _weekly_targets(base, distance, weeks, runs)
    for week, target in zip(plan, targets):
        if week.get("is_recovery") or week.get("is_race_week") or target <= 0:
            continue
        actual = week.get("total_km") or 0
        assert actual <= target * PEAK_DELIVERY_SLACK_RATIO + 0.1, (
            f"week {week['week']}: planned {actual} km against a reachable "
            f"target of {target:.1f} km"
        )


def test_when_the_gate_binds_the_delivered_peak_lands_on_the_reachable_target():
    """The audit's fidelity claim, on a case where the cap actually binds.

    A 4-run marathon plan from a 40 km base modelled a 76 km peak — 1.9 km per
    session beyond what the frequency can carry. The reachable peak is 56 km,
    and the delivered peak week must land on it (it used to overshoot its own
    slots by ~26% before being trimmed down).
    """
    base, distance, weeks, runs = 40.0, 42.2, 18, 4
    plan = TrainingPlanGenerator().generate_plan(base, distance, weeks, runs)
    targets = _weekly_targets(base, distance, weeks, runs)
    reachable_peak = max(targets)
    assert reachable_peak == pytest.approx(mp.weekly_capacity(runs, mp.MAX_EASY_RUN_KM))
    delivered_peak = max(
        w["total_km"]
        for w in plan
        if not w.get("is_recovery") and not w.get("is_race_week")
    )
    assert delivered_peak <= reachable_peak * PEAK_DELIVERY_SLACK_RATIO + 0.1


def test_weekly_shortfall_is_logged_with_week_target_and_actual():
    """A loading week >25% short of its reachable target warns with joinable data.

    This is the telemetry downstream (plan-vs-actual adherence) reacts to: the
    week index, the target and the actual are all in the message, along with
    the plan's generation signature.

    The capture attaches its own handler to the generator's logger rather than
    using ``caplog``: the ``test_db`` fixture runs Alembic, whose
    ``fileConfig`` disables already-created loggers for the rest of the
    session, which silently empties ``caplog`` depending on test order.
    """
    logger = logging.getLogger("app.contexts.plan.generators.plan_generator")
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture(level=logging.WARNING)
    was_disabled, was_level = logger.disabled, logger.level
    logger.disabled = False
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)
    try:
        # A cell the layout genuinely cannot serve (a 5 km/week base at 2
        # runs/week): the plan is faithful to the runner's volume and still
        # lands >25% short of the reachable target, which is exactly what the
        # telemetry exists to surface. (The former HM@2-runs cell stopped
        # shortfaling — the low-frequency layout work closed its gap.)
        plan = TrainingPlanGenerator().generate_plan(5.0, 5.0, 8, 2)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(was_level)
        logger.disabled = was_disabled

    targets = _weekly_targets(5.0, 5.0, 8, 2)
    shortfalls = [
        (i + 1, targets[i], w.get("total_km") or 0)
        for i, w in enumerate(plan)
        if i < len(targets)
        and not w.get("is_recovery")
        and not w.get("is_race_week")
        and w.get("phase") != "taper"
        and targets[i] > 0
        and (w.get("total_km") or 0) < targets[i] * 0.75
    ]
    assert shortfalls, "expected at least one >25% weekly shortfall in this plan"
    messages = [r.getMessage() for r in records if r.levelno >= logging.WARNING]
    shortfall_messages = [
        m for m in messages if m.startswith("Weekly mileage shortfall")
    ]
    assert shortfall_messages, messages
    for week_num, target, actual in shortfalls:
        matching = [m for m in shortfall_messages if f"week {week_num} " in m]
        assert matching, (
            f"no shortfall warning for week {week_num}: {shortfall_messages}"
        )
        assert f"{actual:.1f} km" in matching[0]
        assert f"{target:.1f} km" in matching[0]
        assert "5 km base" in matching[0]
