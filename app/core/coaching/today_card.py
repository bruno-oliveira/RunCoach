"""Pure view model for the Today card — one moment, assembled.

Check-in, today's session and watch status used to live in three places (the
last one behind ``/analytics?tab=today``), but for a runner they are a single
moment in the morning: *what am I doing, how do I feel, is it on my wrist.*
This module builds the middle piece — the session block and the one line of
coaching that sits under it — from primitives.

No I/O, no ORM: the caller resolves today's workout and this turns it into
something a template can render. The advisory is the only real decision here,
and it is deliberately advisory: RunCoach never reshapes a session silently, so
the copy points at *Adjust my plan* rather than claiming today already changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

# Session types that a rough morning should actually change the approach to.
# An easy run on 5h sleep is still an easy run; a threshold session is not.
_HARD_TYPES = frozenset({"tempo", "interval", "vo2max", "threshold", "hill", "race"})

# Bands (from ``readiness_checkin``) that read as "today needs a second look".
_LOW_BANDS = frozenset({"run_down", "depleted"})


@dataclass(frozen=True)
class TodaySession:
    """Today's planned session, formatted for one glance."""

    workout_id: Optional[str]
    workout_type: str
    title: str
    detail: str
    description: Optional[str]
    hr_zone_target: Optional[int]
    hr_zone_label: Optional[str]
    is_rest: bool
    is_hard: bool
    logged: bool
    logged_km: Optional[float]


@dataclass(frozen=True)
class TodayCard:
    """The head-of-plan card: date, session, and the line of coaching under it."""

    date_label: str
    week_number: Optional[int]
    total_weeks: Optional[int]
    phase: Optional[str]
    session: Optional[TodaySession]
    advisory: Optional[str]
    readiness_band: Optional[str]
    readiness_score: Optional[float]
    readiness_label: Optional[str]
    readiness_drivers: List[str] = field(default_factory=list)

    @property
    def has_session(self) -> bool:
        return self.session is not None


def format_date_label(day: date) -> str:
    """``"Sat 26 Jul"`` — built without ``%-d``, which isn't portable."""
    return f"{day.strftime('%a')} {day.day} {day.strftime('%b')}"


def title_for(workout_type: Optional[str]) -> str:
    """``"race_pace"`` → ``"Race Pace"``; empty → ``"Run"``."""
    if not workout_type:
        return "Run"
    return " ".join(part.capitalize() for part in workout_type.split("_"))


def format_detail(distance_km: Optional[float], duration_min: Optional[int]) -> str:
    """``"8.0 km · ≈ 45 min"``, dropping whichever half is missing."""
    parts: List[str] = []
    if distance_km:
        parts.append(f"{distance_km:.1f} km")
    if duration_min:
        parts.append(f"≈ {int(duration_min)} min")
    return " · ".join(parts)


def build_today_card(
    *,
    today: date,
    workout: Optional[Dict[str, Any]],
    week_number: Optional[int] = None,
    total_weeks: Optional[int] = None,
    phase: Optional[str] = None,
    logged_km: Optional[float] = None,
    readiness_band: Optional[str] = None,
    readiness_score: Optional[float] = None,
    readiness_label: Optional[str] = None,
    readiness_drivers: Optional[List[str]] = None,
    fatigue_softened: bool = False,
) -> TodayCard:
    """Assemble the Today card.

    ``workout`` is a ``plan_data`` day dict (``type``/``distance``/…), or
    ``None`` when the plan hasn't started, has finished, or today falls outside
    it. ``logged_km`` is the distance already run today, if any.
    """
    session = _build_session(workout, logged_km) if workout else None
    return TodayCard(
        date_label=format_date_label(today),
        week_number=week_number,
        total_weeks=total_weeks,
        phase=phase,
        session=session,
        advisory=_advisory(session, readiness_band, fatigue_softened),
        readiness_band=readiness_band,
        readiness_score=readiness_score,
        readiness_label=readiness_label,
        readiness_drivers=list(readiness_drivers or []),
    )


def _build_session(workout: Dict[str, Any], logged_km: Optional[float]) -> TodaySession:
    wtype = (workout.get("type") or "rest").lower()
    distance = workout.get("distance") or 0
    is_rest = wtype in ("rest", "off") or (wtype == "recovery" and not distance)
    return TodaySession(
        workout_id=workout.get("id"),
        workout_type=wtype,
        title="Rest day" if is_rest else title_for(wtype),
        detail=format_detail(distance, workout.get("duration_min")),
        description=workout.get("description"),
        hr_zone_target=workout.get("hr_zone_target"),
        hr_zone_label=workout.get("hr_zone_label"),
        is_rest=is_rest,
        is_hard=wtype in _HARD_TYPES,
        logged=bool(logged_km),
        logged_km=round(logged_km, 1) if logged_km else None,
    )


def _advisory(
    session: Optional[TodaySession],
    band: Optional[str],
    fatigue_softened: bool,
) -> Optional[str]:
    """One line under the session — or nothing.

    Silence is the default. A line only earns its place when the morning says
    something the session doesn't already: a rough check-in before a hard day,
    or a run of hard efforts the plan has already softened for.
    """
    if session is None or session.logged:
        return None

    if session.is_rest:
        if band in _LOW_BANDS:
            return "Rest day, and your check-in agrees. Take it properly."
        return None

    if band in _LOW_BANDS:
        if session.is_hard:
            return (
                "You checked in run-down this morning. Hard sessions on a rough "
                "morning rarely land — ease it back, or swap it with "
                "Adjust my plan."
            )
        return "Rough morning — keep this one genuinely easy."

    if band == "ok" and session.is_hard:
        return "A bit flat this morning. Start conservatively and let it come to you."

    if band == "primed" and session.is_hard:
        return "You're fresh this morning — this is the one to commit to."

    if fatigue_softened:
        return "Your last runs came in hard, so today is deliberately softened."

    return None
