"""TwoRunComposer — minimum effective dose.

For injury-prone, time-constrained, maintenance, or cross-training-heavy
runners.  Two runs per week: one quality (or easy in base/taper) and one
long run.  The long run is legitimately the bigger share of the week.
"""

from app.domain.frequency import (
    AdaptationPolicy,
    IntensityZone,
    SlotType,
    WorkoutSlot,
)

_PHASE_SLOTS = {
    "base": [
        WorkoutSlot(SlotType.EASY, 0.45, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(SlotType.LONG, 0.55, IntensityZone.EASY, label="Long Run"),
    ],
    "build": [
        WorkoutSlot(
            SlotType.QUALITY,
            0.42,
            IntensityZone.THRESHOLD,
            allows_quality_swap=True,
            label="Quality",
        ),
        WorkoutSlot(SlotType.LONG, 0.58, IntensityZone.EASY, label="Long Run"),
    ],
    "peak": [
        WorkoutSlot(
            SlotType.QUALITY,
            0.45,
            IntensityZone.THRESHOLD,
            allows_quality_swap=True,
            label="Quality",
        ),
        WorkoutSlot(SlotType.LONG, 0.55, IntensityZone.EASY, label="Long Run"),
    ],
    "taper": [
        WorkoutSlot(SlotType.EASY, 0.50, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(SlotType.LONG, 0.50, IntensityZone.EASY, label="Long Run"),
    ],
}

_LONG_RUN_PCT = {
    "base": (0.52, 0.58),
    "build": (0.56, 0.62),
    "peak": (0.56, 0.60),
    "taper": (0.45, 0.50),
}

_QUALITY_BUDGET = {"base": 0, "build": 1, "peak": 1, "taper": 0}


class TwoRunComposer:
    @property
    def frequency(self) -> int:
        return 2

    def slots(self, phase: str) -> list[WorkoutSlot]:
        return list(_PHASE_SLOTS.get(phase, _PHASE_SLOTS["base"]))

    def long_run_pct(self, phase: str) -> tuple[float, float]:
        return _LONG_RUN_PCT.get(phase, _LONG_RUN_PCT["base"])

    def quality_budget(self, phase: str) -> int:
        return _QUALITY_BUDGET.get(phase, 0)

    def adaptation_policy(self) -> AdaptationPolicy:
        return AdaptationPolicy(
            long_run_pct_floor=0.50,
            long_run_pct_cap=0.60,
            medium_long_pct_floor=None,
            protected_slots=[],
            min_quality_count=0,
            max_quality_count=1,
            can_suggest_frequency_change=True,
            frequency_change_direction=1,
        )

    def validate_week(self, distances: list[float], types: list[str]) -> list[str]:
        violations: list[str] = []
        total = sum(distances)
        if total == 0:
            return []
        long_idx = next((i for i, t in enumerate(types) if t == "long"), None)
        if long_idx is not None:
            pct = distances[long_idx] / total
            # 0.65 matches the frequency-aware share ceiling (physiological
            # envelope + long_run_calculator): the single quality partner is
            # physiologically capped, so the long run legitimately carries the
            # rest of a well-formed 2-run week.
            if pct > 0.65:
                violations.append(f"Long run is {pct:.0%} of volume (max 65%)")
        return violations
