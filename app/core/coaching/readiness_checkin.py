"""Pure scoring for the morning readiness check-in.

Turns a runner's self-reported morning inputs (sleep, energy, soreness, stress)
into a single 0–100 readiness score plus a human-readable band and the concrete
"drivers" behind a rough morning — the raw material the Coach's Note voices as
*"you slept 5h and your legs are heavy…"*.

No I/O, no ORM: inputs in, an assessment out. Every input is optional; the score
is the weighted average of whichever components were provided, so a 15-second
"slept badly, legs sore" capture still scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ReadinessAssessment:
    """The distilled readiness verdict for one morning.

    ``score`` is 0–100 (higher = fresher) or ``None`` when no inputs were given.
    ``band`` is a coarse label; ``drivers`` are short phrases naming the inputs
    that dragged the score down, for the coaching voice to weave in.
    """

    score: Optional[float]
    band: str  # "primed" | "good" | "ok" | "run_down" | "depleted" | "unknown"
    label: str  # human-facing, e.g. "Primed", "Running on empty"
    drivers: List[str] = field(default_factory=list)

    @property
    def is_low(self) -> bool:
        """Rough enough that today's hard session should be reconsidered."""
        return self.score is not None and self.score < _LOW_THRESHOLD

    @property
    def is_high(self) -> bool:
        """Fresh enough to flag as primed for a quality session."""
        return self.score is not None and self.score >= _HIGH_THRESHOLD


# Score bands. Kept here so the voice, the nudge, and the UI all agree on what
# "low" means.
_LOW_THRESHOLD = 45.0
_HIGH_THRESHOLD = 75.0

# Per-component weights (only counted when the component is provided). Sleep
# quality, energy, and soreness are the core felt signals; hours and stress
# refine.
_WEIGHTS = {
    "sleep_quality": 1.0,
    "energy": 1.0,
    "soreness": 1.0,
    "sleep_hours": 0.8,
    "stress": 0.6,
}


def _likert_up(value: int) -> float:
    """A 1–5 'higher is better' scale → 0–1."""
    return (_clamp_likert(value) - 1) / 4.0


def _likert_down(value: int) -> float:
    """A 1–5 'higher is worse' scale (soreness, stress) → 0–1 goodness."""
    return (5 - _clamp_likert(value)) / 4.0


def _clamp_likert(value: int) -> int:
    return max(1, min(5, int(value)))


def _sleep_hours_subscore(hours: float) -> float:
    """Map hours slept to a 0–1 sub-score. 7h+ is full marks; short nights fall
    off steeply because that is what most compromises a hard session."""
    if hours >= 7:
        return 1.0
    if hours >= 6:
        return 0.75
    if hours >= 5:
        return 0.5
    if hours >= 4:
        return 0.28
    return 0.1


def score_checkin(
    *,
    sleep_hours: Optional[float] = None,
    sleep_quality: Optional[int] = None,
    energy: Optional[int] = None,
    soreness: Optional[int] = None,
    stress: Optional[int] = None,
) -> ReadinessAssessment:
    """Score a morning check-in into a :class:`ReadinessAssessment`."""
    subscores: dict[str, float] = {}
    if sleep_quality is not None:
        subscores["sleep_quality"] = _likert_up(sleep_quality)
    if energy is not None:
        subscores["energy"] = _likert_up(energy)
    if soreness is not None:
        subscores["soreness"] = _likert_down(soreness)
    if stress is not None:
        subscores["stress"] = _likert_down(stress)
    if sleep_hours is not None:
        subscores["sleep_hours"] = _sleep_hours_subscore(sleep_hours)

    if not subscores:
        return ReadinessAssessment(score=None, band="unknown", label="No check-in")

    weight_sum = sum(_WEIGHTS[k] for k in subscores)
    weighted = sum(_WEIGHTS[k] * v for k, v in subscores.items())
    score = round((weighted / weight_sum) * 100, 1)

    band, label = _band_for(score)
    return ReadinessAssessment(
        score=score,
        band=band,
        label=label,
        drivers=_drivers(
            sleep_hours=sleep_hours,
            sleep_quality=sleep_quality,
            energy=energy,
            soreness=soreness,
            stress=stress,
        ),
    )


def _band_for(score: float) -> tuple[str, str]:
    if score >= _HIGH_THRESHOLD:
        return "primed", "Primed"
    if score >= 60:
        return "good", "Good to go"
    if score >= _LOW_THRESHOLD:
        return "ok", "A bit flat"
    if score >= 30:
        return "run_down", "Run-down"
    return "depleted", "Running on empty"


def _drivers(
    *,
    sleep_hours: Optional[float],
    sleep_quality: Optional[int],
    energy: Optional[int],
    soreness: Optional[int],
    stress: Optional[int],
) -> List[str]:
    """Short human phrases naming what's dragging readiness down today.

    Ordered by how much they should shape today's session. Used verbatim by the
    coaching voice, so they read as sentence fragments ("your legs are heavy").
    """
    out: List[str] = []
    if sleep_hours is not None and sleep_hours < 6:
        out.append(f"you slept {_fmt_hours(sleep_hours)}")
    if sleep_quality is not None and sleep_quality <= 2:
        out.append("your sleep was broken")
    if soreness is not None and soreness >= 4:
        out.append("your legs are heavy")
    if energy is not None and energy <= 2:
        out.append("your energy is low")
    if stress is not None and stress >= 4:
        out.append("you're under real stress")
    return out


def _fmt_hours(hours: float) -> str:
    """`5.0` → `5h`, `5.5` → `5.5h`."""
    rounded = round(hours, 1)
    if rounded == int(rounded):
        return f"{int(rounded)}h"
    return f"{rounded}h"
