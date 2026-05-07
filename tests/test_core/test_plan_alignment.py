"""End-to-end invariant: description, steps, distance and weekly total
all stay aligned for every workout in a generated plan, across every
representative scenario.

The invariant the user trusts:

    For each workout:
      * sum(step distances)  ==  workout['distance']  (within rounding)
      * any distance number cited in the description matches workout['distance']
        (or a step within the workout, where the description names a sub-block)

    For each week:
      * week['total_km']  ==  round(sum of workout distances, 1)
"""

import re

import pytest

from app.core.generators.plan_generator import TrainingPlanGenerator
from app.core.training.trail_profile import classify_trail
from app.core.training.workout_steps import _compute_distance_from_steps


def _build_road_plan(target_distance, weeks, runs, current_km):
    return TrainingPlanGenerator().generate_plan(
        current_km=current_km,
        target_distance=target_distance,
        weeks=weeks,
        max_runs_per_week=runs,
    )


def _build_trail_plan(distance, elevation, weeks, runs, current_km):
    profile = classify_trail(distance, elevation)
    return TrainingPlanGenerator().generate_plan(
        current_km=current_km,
        target_distance=distance,
        weeks=weeks,
        max_runs_per_week=runs,
        trail_profile=profile,
    )


_CHECKPOINT_TRIGGER_RE = re.compile(
    r"(gel|fuel|nutrition|water|checkpoint)",
    re.IGNORECASE,
)


def _km_in_text(text):
    """Distances cited in description that must align with a step or the
    total. Excludes informational checkpoint markers (gel-take points,
    fueling cadence) — those describe a moment within the run, not a
    workout dimension.
    """
    text = text or ""
    # Split on sentences; if a sentence mentions a checkpoint trigger
    # (gel/fueling/nutrition/water), drop all distances inside it.
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if _CHECKPOINT_TRIGGER_RE.search(sentence):
            continue
        out.extend(float(m) for m in re.findall(r"(\d+\.\d+)\s*km", sentence))
    return out


def _step_distances_km(steps):
    """Distinct per-step km for cross-checking description fragments."""
    out = []
    for s in steps or []:
        if s.get("distance_m"):
            out.append(s["distance_m"] / 1000.0)
    return out


_PLANS = [
    pytest.param(("road", 10.0, 8, 4, 25.0), id="10k-8wk"),
    pytest.param(("road", 21.1, 12, 5, 35.0), id="half-12wk"),
    pytest.param(("road", 42.2, 16, 5, 45.0), id="marathon-16wk"),
    pytest.param(("trail", 30.0, 1200.0, 12, 5, 35.0), id="trail-hilly-30km"),
    pytest.param(("trail", 50.0, 1500.0, 16, 5, 40.0), id="trail-ultra-50km"),
    pytest.param(("trail", 50.0, 200.0, 16, 5, 40.0), id="trail-flat-50km"),
    pytest.param(("trail", 80.0, 4500.0, 24, 6, 50.0), id="trail-mountain-80km"),
]


@pytest.fixture(params=_PLANS)
def plan(request):
    spec = request.param
    if spec[0] == "road":
        _, dist, weeks, runs, base = spec
        return _build_road_plan(dist, weeks, runs, base)
    _, dist, elev, weeks, runs, base = spec
    return _build_trail_plan(dist, elev, weeks, runs, base)


class TestStepsMatchDistance:
    """sum(step distances) is the truth; workout['distance'] must match it."""

    def test_steps_total_matches_distance(self, plan):
        for week in plan:
            for w in week.get("daily_workouts", []):
                if not w.get("steps"):
                    continue
                d = w.get("distance", 0) or 0
                if d <= 0:
                    continue
                steps_total = _compute_distance_from_steps(w["steps"])
                if steps_total <= 0:
                    continue
                assert abs(d - steps_total) <= 0.15, (
                    f"week {week['week']} day {w.get('day')} "
                    f"{w.get('type')} ({w.get('key_workout_id', '-')}): "
                    f"distance={d} vs steps_sum={steps_total:.2f}"
                )


class TestDescriptionMatchesDistance:
    """Numbers cited in the description must match either the workout
    total or a step distance within the workout.
    """

    def test_description_distances_resolve(self, plan):
        for week in plan:
            for w in week.get("daily_workouts", []):
                d = w.get("distance", 0) or 0
                if d <= 0:
                    continue
                desc = w.get("description") or ""
                cited = _km_in_text(desc)
                if not cited:
                    continue
                step_kms = _step_distances_km(w.get("steps", []))
                resolvable = {round(d, 1)} | {round(x, 1) for x in step_kms}
                # Step counts can be repeated (e.g. 4 × 2.0 km); allow a
                # 0.15 km tolerance per number against the {distance} ∪
                # {step distances} set.
                for n in cited:
                    matched = any(abs(n - r) <= 0.15 for r in resolvable)
                    assert matched, (
                        f"week {week['week']} day {w.get('day')} "
                        f"{w.get('type')} ({w.get('key_workout_id', '-')}): "
                        f"description cites {n} km but workout total is {d} "
                        f"and step distances are {sorted(step_kms)}\n"
                        f"  desc: {desc[:200]}"
                    )


class TestWeeklyTotalAligns:
    """week['total_km'] is the rounded sum of daily distances."""

    def test_weekly_total_matches_sum(self, plan):
        for week in plan:
            workouts = week.get("daily_workouts", [])
            summed = round(sum(w.get("distance", 0) or 0 for w in workouts), 1)
            stated = round(week.get("total_km", 0) or 0, 1)
            assert abs(summed - stated) <= 0.1, (
                f"week {week['week']}: total_km={stated} vs sum={summed}"
            )
