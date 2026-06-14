"""Regression guard: every distance shown to the runner has at most one
decimal place, and is *truncated* (never rounded) from the underlying value.

Background
----------
Warm-up / cool-down splits are derived from integer-metre arithmetic
(``int(round(total_m * 0.25))``), which routinely produced 3-decimal
kilometre figures such as ``0.775 km`` or ``1.875 km`` in workout
descriptions, segment cards and step labels. The fix introduced a single
formatting authority — ``app.utils.format_km`` / ``truncate_km`` — and snapped
warm-up/cool-down distances to whole 100 m increments so the displayed number
never exceeds one decimal and never disagrees with the executable step.

These tests pin that behaviour so it cannot silently regress:

  * ``format_km`` / ``truncate_km`` truncate rather than round.
  * No description or structure string emitted by either plan family contains
    a number with two or more decimal places.
  * Every performance training zone carries a non-empty ``pace_formatted`` and
    ``pace_range_formatted`` (the zone table that was previously blank).
"""

import re

import pytest

from app.contexts.plan.generators.fitness_plan_generator import FitnessPlanGenerator
from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.utils import format_km, truncate_km

# Matches a decimal number with two or more fractional digits (e.g. 0.775,
# 1.875). Pace tokens like "5:07" use a colon, not a dot, so they don't match.
_MULTI_DECIMAL = re.compile(r"\d+\.\d{2,}")


class TestFormatKmTruncates:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.775, "0.7"),
            (1.075, "1.0"),
            (1.875, "1.8"),
            (9.99, "9.9"),
            (13.0, "13.0"),
            (5.55, "5.5"),
            (0.0, "0.0"),
            (0.04, "0.0"),
        ],
    )
    def test_format_km_truncates_not_rounds(self, value, expected):
        assert format_km(value) == expected

    @pytest.mark.parametrize("value", [None, 0, -3.2])
    def test_format_km_non_positive_is_zero(self, value):
        assert format_km(value) == "0.0"

    def test_truncate_km_never_exceeds_input(self):
        # Truncation must never report more distance than actually prescribed.
        for thousandths in range(0, 30001):
            v = thousandths / 1000.0
            assert truncate_km(v) <= v + 1e-9


def _performance_plans():
    gen = PerformancePlanGenerator()
    plans = []
    for dist in (5.0, 10.0, 21.1, 42.2):
        for wk_km in (15.0, 40.0, 80.0):
            for rpw in (3, 5):
                for cp, gp in ((5.5, 5.0), (7.0, 6.5)):
                    try:
                        plans.append(
                            gen.generate_plan(
                                target_distance=dist,
                                current_pace=cp,
                                goal_pace=gp,
                                weeks=12,
                                current_weekly_km=wk_km,
                                runs_per_week=rpw,
                                max_heart_rate=185,
                            )
                        )
                    except Exception:
                        continue
    return plans


def _fitness_plans():
    gen = FitnessPlanGenerator()
    plans = []
    for wk_km in (12.0, 35.0, 75.0):
        for rpw in (3, 5):
            for vdot in (None, 45, 55):
                for focus in ("general_fitness", "5k", "half_marathon", "marathon"):
                    try:
                        plans.append(
                            gen.generate_plan(
                                current_weekly_km=wk_km,
                                weeks=12,
                                runs_per_week=rpw,
                                vdot=vdot,
                                max_heart_rate=185,
                                focus_area=focus,
                            )
                        )
                    except Exception:
                        continue
    return plans


def _iter_workouts(plan):
    for week in plan.get("weekly_plans", []):
        for w in week.get("daily_workouts", []):
            yield week, w


def _multi_decimal_offenders(plan):
    offenders = []
    for week, w in _iter_workouts(plan):
        for field in ("description", "structure"):
            text = w.get(field) or ""
            for token in _MULTI_DECIMAL.findall(text):
                offenders.append((week.get("week"), w.get("type"), field, token, text))
        for seg in w.get("segments", []) or []:
            d = seg.get("distance_km")
            if d is not None and round(d, 1) != d:
                offenders.append(
                    (week.get("week"), w.get("type"), "segment", seg.get("name"), d)
                )
    return offenders


class TestNoMultiDecimalDistances:
    def test_performance_plans_have_one_decimal_distances(self):
        plans = _performance_plans()
        assert plans, "expected at least one performance plan to generate"
        offenders = []
        for plan in plans:
            offenders.extend(_multi_decimal_offenders(plan))
        assert not offenders, f"multi-decimal distances found: {offenders[:10]}"

    def test_fitness_plans_have_one_decimal_distances(self):
        plans = _fitness_plans()
        assert plans, "expected at least one fitness plan to generate"
        offenders = []
        for plan in plans:
            offenders.extend(_multi_decimal_offenders(plan))
        assert not offenders, f"multi-decimal distances found: {offenders[:10]}"


class TestPerformanceZonesCarryFormattedPaces:
    def test_every_zone_has_formatted_pace_and_band(self):
        plans = _performance_plans()
        assert plans
        for plan in plans:
            for zone_name, zone in plan["training_zones"].items():
                pf = zone.get("pace_formatted")
                prf = zone.get("pace_range_formatted")
                assert pf and pf != "--", f"{zone_name} missing pace_formatted"
                assert prf and prf != "--", (
                    f"{zone_name} missing pace_range_formatted"
                )


class TestKeyWorkoutOverlayRendering:
    """Directly exercise the key-workout overlay across a fine grid of budgets.

    This is the surface where the 3-decimal warm-up originally appeared
    (``Warm up 1.075km easy``): warm-up length comes from integer-metre
    arithmetic, and at small budgets ``int(round(total_m * 0.25))`` lands on
    values like 775 m or 1075 m. Sweeping budgets in 0.1 km steps guarantees we
    hit those boundary values directly, independent of which overlay a full
    plan happens to select.
    """

    def _budgets(self):
        # 1.5 km .. 24.0 km in 0.1 km steps — dense enough to land on the
        # metre values that previously produced 3-decimal kilometre splits.
        return [round(1.5 + i * 0.1, 1) for i in range(0, 226)]

    def test_no_overlay_description_has_multi_decimal_distance(self):
        from app.core.training.key_workout_library import (
            _WORKOUTS,
            overlay_key_workout,
        )

        offenders = []
        for workout in _WORKOUTS:
            phases = [p for p in workout["phases"] if p in ("build", "peak")]
            wtype = workout["type"]
            if not phases or wtype not in ("interval", "tempo", "hill", "long"):
                continue
            for budget in self._budgets():
                wo = {"distance": budget, "type": wtype}
                try:
                    overlay_key_workout(
                        wo,
                        wtype,
                        phases[0],
                        30.0,
                        0,
                        terrain="flat",
                        trail_profile=None,
                        force_id=workout["id"],
                    )
                except Exception:
                    continue
                for field in ("description", "structure"):
                    text = wo.get(field) or ""
                    for token in _MULTI_DECIMAL.findall(text):
                        offenders.append((workout["id"], budget, field, token, text))
        assert not offenders, (
            f"overlay produced multi-decimal distances: {offenders[:10]}"
        )

