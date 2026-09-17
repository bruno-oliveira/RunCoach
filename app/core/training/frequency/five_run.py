"""FiveRunComposer — the sweet spot.

Intermediate to advanced runners.  The structure most coaches converge on
for half/full marathon.  Supports 80/20 polarization naturally.  Introduces
the Pfitzinger medium-long run as a distinct session bridging easy and long.
"""

from app.domain.frequency import (
    AdaptationPolicy,
    IntensityZone,
    SlotType,
    WorkoutSlot,
)

_PHASE_SLOTS = {
    "base": [
        WorkoutSlot(SlotType.EASY, 0.20, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(SlotType.EASY, 0.20, IntensityZone.EASY, label="Easy 2"),
        WorkoutSlot(
            SlotType.MEDIUM_LONG,
            0.20,
            IntensityZone.MODERATE,
            label="Medium-Long",
        ),
        WorkoutSlot(SlotType.EASY, 0.10, IntensityZone.EASY, label="Easy 3"),
        WorkoutSlot(SlotType.LONG, 0.30, IntensityZone.EASY, label="Long Run"),
    ],
    "build": [
        WorkoutSlot(SlotType.EASY, 0.15, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(
            SlotType.QUALITY,
            0.15,
            IntensityZone.VO2MAX,
            allows_quality_swap=True,
            label="Quality 1",
        ),
        WorkoutSlot(
            SlotType.MEDIUM_LONG,
            0.20,
            IntensityZone.MODERATE,
            label="Medium-Long",
        ),
        WorkoutSlot(
            SlotType.QUALITY,
            0.15,
            IntensityZone.THRESHOLD,
            allows_quality_swap=True,
            label="Quality 2",
        ),
        WorkoutSlot(SlotType.LONG, 0.35, IntensityZone.EASY, label="Long Run"),
    ],
    "peak": [
        WorkoutSlot(SlotType.EASY, 0.12, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(
            SlotType.QUALITY,
            0.15,
            IntensityZone.VO2MAX,
            allows_quality_swap=True,
            label="Quality 1",
        ),
        WorkoutSlot(
            SlotType.MEDIUM_LONG,
            0.20,
            IntensityZone.MODERATE,
            label="Medium-Long",
        ),
        WorkoutSlot(
            SlotType.QUALITY,
            0.15,
            IntensityZone.THRESHOLD,
            allows_quality_swap=True,
            label="Quality 2",
        ),
        WorkoutSlot(SlotType.LONG, 0.38, IntensityZone.EASY, label="Long Run"),
    ],
    "taper": [
        WorkoutSlot(SlotType.EASY, 0.20, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(
            SlotType.QUALITY,
            0.15,
            IntensityZone.THRESHOLD,
            allows_quality_swap=True,
            label="Quality",
        ),
        WorkoutSlot(
            SlotType.MEDIUM_LONG,
            0.18,
            IntensityZone.MODERATE,
            label="Medium-Long",
        ),
        WorkoutSlot(SlotType.EASY, 0.19, IntensityZone.EASY, label="Easy 2"),
        WorkoutSlot(SlotType.LONG, 0.28, IntensityZone.EASY, label="Long Run"),
    ],
}

_LONG_RUN_PCT = {
    "base": (0.25, 0.32),
    "build": (0.30, 0.36),
    "peak": (0.32, 0.38),
    "taper": (0.22, 0.30),
}

_QUALITY_BUDGET = {"base": 0, "build": 2, "peak": 2, "taper": 1}


class FiveRunComposer:
    @property
    def frequency(self) -> int:
        return 5

    def slots(self, phase: str) -> list[WorkoutSlot]:
        return list(_PHASE_SLOTS.get(phase, _PHASE_SLOTS["base"]))

    def long_run_pct(self, phase: str) -> tuple[float, float]:
        return _LONG_RUN_PCT.get(phase, _LONG_RUN_PCT["base"])

    def quality_budget(self, phase: str) -> int:
        return _QUALITY_BUDGET.get(phase, 0)

    def adaptation_policy(self) -> AdaptationPolicy:
        return AdaptationPolicy(
            long_run_pct_floor=0.25,
            long_run_pct_cap=0.38,
            medium_long_pct_floor=0.15,
            protected_slots=[],
            min_quality_count=0,
            max_quality_count=2,
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
            if pct > 0.40:
                violations.append(f"Long run is {pct:.0%} of volume (max 38%)")
        ml_idx = next((i for i, t in enumerate(types) if t == "medium_long"), None)
        if ml_idx is not None:
            pct = distances[ml_idx] / total
            if pct < 0.12:
                violations.append(f"Medium-long is {pct:.0%} of volume (min 15%)")
        return violations
