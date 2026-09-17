"""FourRunComposer — the step-up.

Pfitzinger Level 1 starting structure, recreational runners with time
for a 4th day.  The second easy run distributes volume so the long run
drops to a healthy 35%.
"""

from app.domain.frequency import (
    AdaptationPolicy,
    IntensityZone,
    SlotType,
    WorkoutSlot,
)

_PHASE_SLOTS = {
    "base": [
        WorkoutSlot(SlotType.EASY, 0.22, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(SlotType.EASY, 0.25, IntensityZone.EASY, label="Easy 2"),
        WorkoutSlot(SlotType.EASY, 0.23, IntensityZone.EASY, label="Easy 3"),
        WorkoutSlot(SlotType.LONG, 0.30, IntensityZone.EASY, label="Long Run"),
    ],
    "build": [
        WorkoutSlot(SlotType.EASY, 0.20, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(
            SlotType.QUALITY,
            0.20,
            IntensityZone.VO2MAX,
            allows_quality_swap=True,
            label="Quality",
        ),
        WorkoutSlot(SlotType.EASY, 0.25, IntensityZone.EASY, label="Easy 2"),
        WorkoutSlot(SlotType.LONG, 0.35, IntensityZone.EASY, label="Long Run"),
    ],
    "peak": [
        WorkoutSlot(SlotType.EASY, 0.20, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(
            SlotType.QUALITY,
            0.20,
            IntensityZone.VO2MAX,
            allows_quality_swap=True,
            label="Quality",
        ),
        WorkoutSlot(SlotType.EASY, 0.25, IntensityZone.EASY, label="Easy 2"),
        WorkoutSlot(SlotType.LONG, 0.35, IntensityZone.EASY, label="Long Run"),
    ],
    "taper": [
        WorkoutSlot(SlotType.EASY, 0.25, IntensityZone.EASY, label="Easy"),
        WorkoutSlot(
            SlotType.QUALITY,
            0.20,
            IntensityZone.THRESHOLD,
            allows_quality_swap=True,
            label="Sharpener",
        ),
        WorkoutSlot(SlotType.EASY, 0.25, IntensityZone.EASY, label="Easy 2"),
        WorkoutSlot(SlotType.LONG, 0.30, IntensityZone.EASY, label="Long Run"),
    ],
}

_LONG_RUN_PCT = {
    "base": (0.27, 0.32),
    "build": (0.30, 0.37),
    "peak": (0.32, 0.38),
    "taper": (0.25, 0.32),
}

_QUALITY_BUDGET = {"base": 0, "build": 1, "peak": 1, "taper": 1}


class FourRunComposer:
    @property
    def frequency(self) -> int:
        return 4

    def slots(self, phase: str) -> list[WorkoutSlot]:
        return list(_PHASE_SLOTS.get(phase, _PHASE_SLOTS["base"]))

    def long_run_pct(self, phase: str) -> tuple[float, float]:
        return _LONG_RUN_PCT.get(phase, _LONG_RUN_PCT["base"])

    def quality_budget(self, phase: str) -> int:
        return _QUALITY_BUDGET.get(phase, 0)

    def adaptation_policy(self) -> AdaptationPolicy:
        return AdaptationPolicy(
            long_run_pct_floor=0.25,
            long_run_pct_cap=0.40,
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
            if pct > 0.42:
                violations.append(f"Long run is {pct:.0%} of volume (max 40%)")
        return violations
