"""Plan data -> layout model for the Runna-style sheet.

Pure translation: no ReportLab, no I/O. Keeping it separate means the wording
and grouping decisions (what a card says, where a phase starts, which legend
entries appear) are testable without rendering a PDF, and the renderer stays a
dumb painter of an already-decided layout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.training.trail_profile import TRAIL_SENTINEL_KM
from app.infrastructure.export.plan_export_dto import PlanExportDTO

# --- Layout model ---------------------------------------------------------


@dataclass(frozen=True)
class DayCard:
    """One cell of the calendar grid."""

    kind: str  # key into theme.ACCENTS, or "rest"
    headline: str = ""
    label: str = ""
    strength: bool = False


REST_CARD = DayCard(kind="rest")


@dataclass(frozen=True)
class WeekRow:
    number: int
    cards: Tuple[DayCard, ...]
    tag: str = ""  # "DELOAD", "(RACE)" — sits under the week number


@dataclass(frozen=True)
class PhaseBlock:
    eyebrow: str
    title: str
    subtitle: str
    weeks: Tuple[WeekRow, ...]


@dataclass(frozen=True)
class Chip:
    text: str
    kind: str = "neutral"


@dataclass(frozen=True)
class Cover:
    eyebrow: str
    title_lines: Tuple[str, ...]
    description: str
    stats: Tuple[Chip, ...]
    legend: Tuple[Chip, ...]


@dataclass(frozen=True)
class DetailRow:
    """One row of a reference table: a lead-in and its body text."""

    lead: str
    body: str
    kind: str = "neutral"


@dataclass(frozen=True)
class DetailSection:
    eyebrow: str
    title: str
    subtitle: str
    rows: Tuple[DetailRow, ...]
    columns: int = 1


@dataclass(frozen=True)
class Sheet:
    cover: Cover
    phases: Tuple[PhaseBlock, ...]
    sections: Tuple[DetailSection, ...]
    footer: str


# --- Vocabulary -----------------------------------------------------------

_KIND_BY_TYPE = {
    "easy": "easy",
    "run_walk": "easy",
    "recovery": "recovery",
    "cross_training": "recovery",
    "long": "long",
    "tempo": "quality",
    "threshold": "quality",
    "interval": "quality",
    "intervals": "quality",
    "speed": "quality",
    "hill": "quality",
    "hills": "quality",
    "fartlek": "quality",
    "race_pace": "quality",
    "progression": "quality",
    "strength": "strength",
    "race": "race",
    "rest": "rest",
}

_LABEL_BY_TYPE = {
    "easy": "Easy Run",
    "run_walk": "Run / Walk",
    "recovery": "Recovery",
    "cross_training": "Cross-Train",
    "long": "Long Run",
    "tempo": "Tempo",
    "threshold": "Threshold",
    "interval": "Intervals",
    "intervals": "Intervals",
    "speed": "Speed",
    "hill": "Hills",
    "hills": "Hills",
    "fartlek": "Fartlek",
    "race_pace": "Race Pace",
    "progression": "Progression",
    "strength": "Strength",
    "race": "RACE DAY",
    "rest": "Rest",
}

#: Legend order — matches the order cards are introduced down the sheet.
_LEGEND_ORDER = ("easy", "long", "quality", "recovery", "strength", "race")

_LEGEND_TEXT = {
    "easy": "Easy Run",
    "long": "Long Run",
    "quality": "Quality",
    "recovery": "Recovery",
    "strength": "Strength",
    "race": "Race Day",
}

_PHASE_META = {
    "base": ("Base Building", "aerobic volume, easy running and durability"),
    "beginner": ("Run–Walk Foundation", "build the habit first, the distance second"),
    "build": ("Build", "threshold work and progressively harder long runs"),
    "peak": ("Peak", "race-specific sessions at your sharpest"),
    "sharpen": ("Sharpening", "short, fast work on a rested body"),
    "taper": ("Taper & Race", "volume drops, intensity stays — arrive fresh"),
}

_RACE_NAMES = {5.0: "5K", 10.0: "10K", 21.1: "Half Marathon", 42.2: "Marathon"}


def _fmt_km(km: float) -> str:
    """``6.1`` -> ``6.1K``; ``18.0`` -> ``18K``."""
    return f"{km:g}K"


# --- Card wording ---------------------------------------------------------

_REPS = re.compile(
    r"(\d+)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(km|k|m|min|mins|minutes|sec)\b", re.I
)
_REPS_PAREN = re.compile(r"(\d+)\s*[x×]\s*\(\s*(\d+(?:\.\d+)?)\s*(km|k|m|min)\b", re.I)

_UNIT = {
    "km": "km",
    "k": "km",
    "m": "m",
    "min": "min",
    "mins": "min",
    "minutes": "min",
    "sec": "s",
}

#: Long-run flavours worth naming on the card, longest match first.
_LONG_FLAVOURS = (
    ("race practice", "race sim"),
    ("race rehearsal", "race sim"),
    ("fast-finish", "fast finish"),
    ("fast finish", "fast finish"),
    ("alternating", "alternating"),
    ("progressive", "progressive"),
    ("rolling hills", "hilly"),
    ("hill", "hilly"),
    ("back-to-back", "back-to-back"),
)


def _rep_shape(structure: str) -> str:
    """Compact ``3 × 1 km`` style summary of a session, or ``""``."""
    for pattern in (_REPS_PAREN, _REPS):
        match = pattern.search(structure)
        if match:
            count, value, unit = match.groups()
            return f"{count}×{_trim(value)}{_UNIT[unit.lower()]}"
    return ""


def _trim(value: str) -> str:
    return f"{float(value):g}"


def _long_flavour(name: str, structure: str) -> str:
    haystack = f"{name} {structure}".lower()
    for needle, flavour in _LONG_FLAVOURS:
        if needle in haystack:
            return flavour
    return ""


def _has_strides(day: Dict[str, Any]) -> bool:
    if any(step.get("kind") == "strides" for step in day.get("steps") or []):
        return True
    return "stride" in (day.get("description") or "").lower()


def _session_name(day: Dict[str, Any]) -> str:
    """The title the plan gave this session, or ``""`` for an unnamed one.

    This is the same string the app prints at the top of a workout page and the
    same string the "Key sessions" reference page leads with. The card has to
    carry it too, or the sheet can be read on screen but not on paper: a purple
    card saying "Tempo" gives the reader no way back to the paragraph that
    describes it.
    """
    return str(day.get("key_workout_name") or "").strip()


def _headline(day: Dict[str, Any], kind: str, named: bool = False) -> str:
    """Metric line of a card.

    ``named`` suppresses the character hints (``fast finish``, ``+ strides``):
    on a named card the label underneath already says it, and repeating it
    costs the width the name needs.
    """
    distance = float(day.get("distance") or 0)
    structure = str(day.get("structure") or "")
    name = str(day.get("key_workout_name") or "")

    if kind == "race":
        return _fmt_km(distance) if distance else "Race"

    if day.get("type") == "run_walk":
        minutes = day.get("duration_min")
        return f"{minutes} min" if minutes else _fmt_km(distance)

    if distance <= 0:
        # A zero-distance session is cross-training or mobility, not a run.
        text = (day.get("description") or day.get("notes") or "").lower()
        if "swim" in text or "bike" in text or "cycl" in text:
            return "Swim / bike"
        if "walk" in text:
            return "Easy walk"
        return "Cross-train"

    km = _fmt_km(distance)

    if kind == "quality":
        shape = _rep_shape(structure)
        return f"{km} · {shape}" if shape else km

    if kind == "long" and not named:
        flavour = _long_flavour(name, structure)
        return f"{km} {flavour}" if flavour else km

    if kind == "easy" and not named and _has_strides(day):
        return f"{km} + strides"

    return km


def _card(day: Dict[str, Any]) -> DayCard:
    workout_type = str(day.get("type") or "rest")
    kind = _KIND_BY_TYPE.get(workout_type, "easy")
    if kind == "rest":
        return REST_CARD
    # Race day keeps its shouted generic label: the cover already names the
    # race, and "RACE DAY" reads across the page in a way "Half Marathon Race
    # Day" wrapped onto two lines does not.
    name = "" if kind == "race" else _session_name(day)
    return DayCard(
        kind=kind,
        headline=_headline(day, kind, named=bool(name)),
        label=name
        or _LABEL_BY_TYPE.get(workout_type, workout_type.replace("_", " ").title()),
        strength=bool(day.get("strength_session")),
    )


def _week_cards(week: Dict[str, Any]) -> Tuple[DayCard, ...]:
    """Place each workout on its weekday; unfilled days become rest cards."""
    slots: List[DayCard] = [REST_CARD] * 7
    for index, day in enumerate(week.get("daily_workouts") or [], start=1):
        position = int(day.get("day") or index)
        if 1 <= position <= 7:
            slots[position - 1] = _card(day)
    return tuple(slots)


# --- Phase grouping -------------------------------------------------------


def _phase_label(week: Dict[str, Any]) -> str:
    return str(week.get("phase") or "base").lower()


def _has_race(week: Dict[str, Any]) -> bool:
    return any(
        (day.get("type") or "") == "race" for day in week.get("daily_workouts") or []
    )


def _week_row(week: Dict[str, Any]) -> WeekRow:
    if _has_race(week):
        tag = "(RACE)"
    elif week.get("is_recovery"):
        tag = "DELOAD"
    else:
        tag = ""
    return WeekRow(number=int(week.get("week") or 0), cards=_week_cards(week), tag=tag)


def _build_phases(plan_data: Sequence[Dict[str, Any]]) -> Tuple[PhaseBlock, ...]:
    groups: List[List[Dict[str, Any]]] = []
    for week in plan_data:
        if groups and _phase_label(groups[-1][-1]) == _phase_label(week):
            groups[-1].append(week)
        else:
            groups.append([week])

    blocks: List[PhaseBlock] = []
    for index, group in enumerate(groups, start=1):
        phase = _phase_label(group[0])
        title, default_description = _PHASE_META.get(
            phase, (phase.replace("_", " ").title(), "")
        )
        description = str(group[0].get("phase_description") or default_description)
        first, last = group[0].get("week"), group[-1].get("week")
        span = f"Week {first}" if first == last else f"Weeks {first}–{last}"
        subtitle = f"{span} · {description}" if description else span
        blocks.append(
            PhaseBlock(
                eyebrow=f"PHASE {index}",
                title=title,
                subtitle=subtitle,
                weeks=tuple(_week_row(week) for week in group),
            )
        )
    return tuple(blocks)


# --- Cover ----------------------------------------------------------------


def _race_name(dto: PlanExportDTO) -> str:
    # Backyard first: it rides on the trail flag, but its target_distance_km is
    # a clamped projection — printing that would put "163 km Trail" on the
    # cover of a 48-loop plan.
    if dto.is_backyard and dto.backyard_target_loops:
        return f"{dto.backyard_target_loops}-Loop Backyard"
    if dto.is_trail or dto.target_distance_km == TRAIL_SENTINEL_KM:
        if dto.is_trail and dto.target_distance_km != TRAIL_SENTINEL_KM:
            return f"{dto.target_distance_km:g} km Trail"
        return "Trail Race"
    return _RACE_NAMES.get(dto.target_distance_km, f"{dto.target_distance_km:g} km")


def _peak_km(plan_data: Sequence[Dict[str, Any]]) -> float:
    return max((float(week.get("total_km") or 0) for week in plan_data), default=0.0)


def _run_days(plan_data: Sequence[Dict[str, Any]]) -> int:
    counts = [
        sum(
            1
            for day in week.get("daily_workouts") or []
            if float(day.get("distance") or 0) > 0
        )
        for week in plan_data
    ]
    return max(counts, default=0)


def _description(dto: PlanExportDTO, plan_data: Sequence[Dict[str, Any]]) -> str:
    race = _race_name(dto)
    peak = _peak_km(plan_data)
    return (
        f"A {dto.weeks_duration}-week build from {dto.current_weekly_km:g} km a week "
        f"to a {peak:g} km peak, aimed at your {race}. Every week is written "
        f"around one long run and the quality session it supports — and the plan "
        f"re-paces itself as your runs come in."
    )


def _stat_chips(
    dto: PlanExportDTO, plan_data: Sequence[Dict[str, Any]]
) -> Tuple[Chip, ...]:
    chips = [
        Chip(f"GOAL: {_race_name(dto).upper()}", "quality"),
        Chip(f"{dto.weeks_duration} WEEKS", "long"),
        Chip(f"PEAK {_peak_km(plan_data):g} KM/WK", "easy"),
    ]
    run_days = _run_days(plan_data)
    if run_days:
        chips.append(Chip(f"{run_days} RUNS/WEEK", "recovery"))
    return tuple(chips)


def _legend_chips(phases: Iterable[PhaseBlock]) -> Tuple[Chip, ...]:
    used = {
        card.kind
        for phase in phases
        for week in phase.weeks
        for card in week.cards
        if card.kind != "rest"
    }
    if any(
        card.strength for phase in phases for week in phase.weeks for card in week.cards
    ):
        used.add("strength")
    return tuple(
        Chip(_LEGEND_TEXT[kind], kind) for kind in _LEGEND_ORDER if kind in used
    )


# --- Entry point ----------------------------------------------------------


def build_sheet(
    dto: PlanExportDTO,
    plan_data: Sequence[Dict[str, Any]],
    sections: Optional[Sequence[DetailSection]] = None,
) -> Sheet:
    """Translate a plan into the layout the renderer paints."""
    phases = _build_phases(plan_data)
    race = _race_name(dto)
    cover = Cover(
        eyebrow="TRAINING PLAN",
        title_lines=(race, f"{dto.weeks_duration}-Week Plan"),
        description=_description(dto, plan_data),
        stats=_stat_chips(dto, plan_data),
        legend=_legend_chips(phases),
    )
    footer = f"{race} · {dto.weeks_duration}-WEEK PLAN · PEAK {_peak_km(plan_data):g} KM".upper()
    return Sheet(
        cover=cover,
        phases=phases,
        sections=tuple(sections or ()),
        footer=footer,
    )
