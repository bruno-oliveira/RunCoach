"""Reference pages that follow the calendar in the plan sheet.

The calendar answers "what am I doing on Thursday". These sections answer the
questions it deliberately leaves off the grid — what the paces mean, what the
named sessions actually are, and how to eat and stay healthy around them — in
the same visual language so the document reads as one piece.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from app.core.training.vdot_calculator import VDOTCalculator
from app.infrastructure.export.plan_export_dto import PlanExportDTO
from app.infrastructure.export.runna.sheet import DetailRow, DetailSection

# --- Static guidance ------------------------------------------------------

_FUELLING: Sequence[tuple[str, str, str]] = (
    (
        "Before a run (30–90 min)",
        "Banana with a spoon of peanut butter, porridge with berries and honey, or "
        "toast with avocado and salt. On race morning keep it low-fibre — a plain "
        "bagel with jam is the safest thing you will ever eat at 6am.",
        "easy",
    ),
    (
        "Within 30 min of finishing",
        "Aim for roughly 3 parts carbohydrate to 1 part protein: chocolate milk, "
        "Greek yoghurt with granola and berries, or a protein smoothie with banana "
        "and spinach. The window matters most after long and quality sessions.",
        "recovery",
    ),
    (
        "Hydration",
        "2.5–3 L of water a day as a base, plus electrolytes on long-run days. "
        "500 ml two hours before, 250 ml half an hour before, then 150–200 ml every "
        "15–20 minutes once a run passes an hour.",
        "easy",
    ),
    (
        "During long runs",
        "Anything over 75 minutes wants 30–60 g of carbohydrate per hour, and you "
        "should practise it on the long runs marked as race simulations rather than "
        "discovering what your stomach tolerates on race day.",
        "long",
    ),
    (
        "Race week",
        "Increase carbohydrate in the last two or three days while volume drops — "
        "you are topping up glycogen, not eating more in total. Keep fibre, alcohol "
        "and anything unfamiliar out of the final 48 hours.",
        "race",
    ),
    (
        "Daily pattern",
        "Build meals around a carbohydrate base, a palm of protein and plenty of "
        "colour: oats or eggs on toast, a grain bowl with chicken or salmon at "
        "lunch, fish or lean meat with rice or potatoes at dinner.",
        "quality",
    ),
)

_HEALTH: Sequence[tuple[str, str, str]] = (
    (
        "Warm up (10–15 min)",
        "Leg swings, walking lunges and high knees, then glute bridges and monster "
        "walks, then walk 2 min, jog 3 min, run 5 min. Add A-skips and butt kicks "
        "before anything with intervals in it.",
        "easy",
    ),
    (
        "Cool down (10–15 min)",
        "Five minutes of easy jogging or walking, then static stretches held 30 "
        "seconds each — hamstrings, quads, calves, hips, IT band. Foam roll 1–2 "
        "minutes per muscle group.",
        "recovery",
    ),
    (
        "Strength, 2–3× per week",
        "Squats 3×12, lunges 3×10 each side, calf raises 3×20. Core: plank 3×45 s, "
        "side plank 3×30 s, dead bugs 3×10. Hips: clamshells and glute bridges "
        "3×15. The dot on a card marks a day with a session attached.",
        "strength",
    ),
    (
        "Stop and reassess if",
        "Pain increases as you run rather than easing off with the warm-up; it is "
        "sharp, stabbing or pin-point; it changes your gait; there is swelling or "
        "warmth in a joint; or it is still there 24 hours after resting.",
        "race",
    ),
    (
        "Recovery",
        "7–9 hours of sleep on a consistent schedule, protein within 30 minutes of "
        "finishing, and genuinely easy cross-training — swimming, cycling, yoga — "
        "on recovery days rather than a secretly hard run.",
        "recovery",
    ),
    (
        "Shoes",
        "Replace every 500–800 km or 6–12 months. Rotating two pairs extends the "
        "life of both. Fit them in the afternoon with a thumb-width of space at the "
        "toe, and watch for uneven wear or a compressed midsole.",
        "quality",
    ),
)

_ZONE_ORDER = (
    (
        "E",
        "Easy",
        "easy",
        "The bulk of the plan. Conversational — if you can't speak in full sentences, slow down.",
    ),
    (
        "M",
        "Marathon",
        "long",
        "Steady, controlled, sustainable for hours. Shows up inside longer runs.",
    ),
    (
        "T",
        "Threshold",
        "quality",
        "Comfortably hard, about an hour's race effort. The engine of tempo work.",
    ),
    (
        "I",
        "Interval",
        "quality",
        "3–5 minute repetitions at hard-but-repeatable effort. Builds VO2max.",
    ),
    (
        "R",
        "Repetition",
        "race",
        "Short, fast, fully recovered. Strides and speed work — never a grind.",
    ),
)


def _pace_rows(vdot: float) -> List[DetailRow]:
    zones = VDOTCalculator.get_pace_zones(vdot)
    rows: List[DetailRow] = []
    for key, name, kind, meaning in _ZONE_ORDER:
        zone = zones.get(key)
        if not zone:
            continue
        rows.append(
            DetailRow(
                lead=f"{name} · {zone.get('pace_str', '')}", body=meaning, kind=kind
            )
        )
    for key, label in (("5K", "5K race pace"), ("10K", "10K race pace")):
        zone = zones.get(key)
        if zone:
            rows.append(
                DetailRow(
                    lead=f"{label} · {zone.get('pace_str', '')}",
                    body="Reference effort for pacing a race or a race-pace segment.",
                    kind="neutral",
                )
            )
    return rows


def _key_session_rows(plan_data: Sequence[Dict[str, Any]]) -> List[DetailRow]:
    rows: List[DetailRow] = []
    seen: set[str] = set()
    for week in plan_data:
        for day in week.get("daily_workouts") or []:
            name = day.get("key_workout_name")
            structure = day.get("structure")
            if not name or not structure:
                continue
            if name in seen:
                continue
            seen.add(name)
            rows.append(
                DetailRow(
                    lead=str(name),
                    body=str(structure),
                    kind="long" if day.get("type") == "long" else "quality",
                )
            )
    return rows


_TARGET_LABELS = (
    ("calories", "Daily calories", "kcal"),
    ("carbs", "Carbohydrate", "g"),
    ("protein", "Protein", "g"),
    ("fat", "Fat", "g"),
    ("fiber", "Fibre", "g"),
)

_HYDRATION_LABELS = (
    ("daily_target", "Daily target"),
    ("pre_run", "Before a run"),
    ("during_run", "During a run"),
    ("post_run", "After a run"),
    ("race_day", "Race day"),
)


def _personal_nutrition_rows(nutrition: Dict[str, Any]) -> List[DetailRow]:
    """Front the personalised numbers when the plan carries a nutrition blueprint."""
    rows: List[DetailRow] = []
    targets = nutrition.get("nutrition_targets") or {}
    numbers = [
        f"{label} {value:g} {unit}"
        for key, label, unit in _TARGET_LABELS
        if isinstance((value := targets.get(key)), (int, float))
    ]
    if numbers:
        rows.append(
            DetailRow(
                lead="Your daily targets",
                body=" · ".join(numbers)
                + ". Calculated from your body mass and this plan's training load.",
                kind="easy",
            )
        )

    hydration = nutrition.get("hydration_guide") or {}
    detail = [
        f"{label}: {hydration[key]}"
        for key, label in _HYDRATION_LABELS
        if hydration.get(key)
    ]
    if detail:
        rows.append(
            DetailRow(
                lead="Your hydration plan",
                body=". ".join(detail) + ".",
                kind="recovery",
            )
        )
    return rows


def _trail_rows(nutrition: Dict[str, Any]) -> List[DetailRow]:
    """Race-day fuelling detail that only exists for trail and ultra plans."""
    rows: List[DetailRow] = []
    in_race = nutrition.get("in_race_fueling") or {}
    if in_race:
        hours = in_race.get("estimated_duration_hours")
        parts = [
            f"Carbohydrate {in_race['carbs_per_hour']}"
            if in_race.get("carbs_per_hour")
            else "",
            f"fluid {in_race['fluid_per_hour_ml']}"
            if in_race.get("fluid_per_hour_ml")
            else "",
            in_race.get("electrolytes", ""),
        ]
        rows.append(
            DetailRow(
                lead=f"In-race fuelling · about {hours:g} hours"
                if isinstance(hours, (int, float))
                else "In-race fuelling",
                body=". ".join(part for part in parts if part),
                kind="race",
            )
        )
        for key, label in (
            ("real_food_strategy", "Real food"),
            ("rehearsal_advice", "Rehearse it"),
        ):
            if in_race.get(key):
                rows.append(DetailRow(lead=label, body=str(in_race[key]), kind="long"))

    phases = {
        phase.get("key"): phase for phase in nutrition.get("trail_fuel_phases") or []
    }
    grouped: Dict[str, List[str]] = {}
    for idea in nutrition.get("trail_fuel_ideas") or []:
        name = idea.get("name")
        if not name:
            continue
        carbs = idea.get("carbs")
        grouped.setdefault(str(idea.get("phase", "during")), []).append(
            f"{name} ({carbs})" if carbs else str(name)
        )
    for key, names in grouped.items():
        phase = phases.get(key, {})
        label = str(phase.get("label") or key.title())
        blurb = str(phase.get("blurb") or "")
        rows.append(
            DetailRow(
                lead=f"Fuel ideas · {label}",
                body=f"{blurb} {'; '.join(names)}.".strip(),
                kind="quality",
            )
        )

    for tip in nutrition.get("trail_tips") or []:
        topic, text = tip.get("topic"), tip.get("text")
        if topic and text:
            rows.append(DetailRow(lead=str(topic), body=str(text), kind="easy"))
    return rows


def build_sections(
    dto: PlanExportDTO, plan_data: Sequence[Dict[str, Any]]
) -> List[DetailSection]:
    sections: List[DetailSection] = []

    if dto.vdot:
        sections.append(
            DetailSection(
                eyebrow="REFERENCE",
                title="Your training paces",
                subtitle=(
                    f"Derived from a VDOT of {dto.vdot:g}. Every pace in the plan "
                    "comes from this table, and it moves as your runs come in."
                ),
                rows=tuple(_pace_rows(dto.vdot)),
                columns=2,
            )
        )

    key_sessions = _key_session_rows(plan_data)
    if key_sessions:
        sections.append(
            DetailSection(
                eyebrow="REFERENCE",
                title="Key sessions",
                subtitle="What the named workouts on the calendar actually ask for.",
                rows=tuple(key_sessions),
                columns=2,
            )
        )

    nutrition = dto.nutrition_plan_data or {}
    fuelling = [
        DetailRow(lead=lead, body=body, kind=kind) for lead, body, kind in _FUELLING
    ]
    fuelling = _personal_nutrition_rows(nutrition) + fuelling
    sections.append(
        DetailSection(
            eyebrow="REFERENCE",
            title="Fuelling",
            subtitle="Eat for the session in front of you, and practise race fuelling before race day.",
            rows=tuple(fuelling),
            columns=2,
        )
    )

    trail = _trail_rows(nutrition)
    if trail:
        sections.append(
            DetailSection(
                eyebrow="REFERENCE",
                title="Trail race fuelling",
                subtitle=(
                    "A long day off-road is an eating contest with a running problem. "
                    "Rehearse all of this on your longest training runs."
                ),
                rows=tuple(trail),
                columns=2,
            )
        )

    sections.append(
        DetailSection(
            eyebrow="REFERENCE",
            title="Staying healthy",
            subtitle="The unglamorous half of the plan — the part that decides whether you reach the start line.",
            rows=tuple(
                DetailRow(lead=lead, body=body, kind=kind)
                for lead, body, kind in _HEALTH
            ),
            columns=2,
        )
    )
    return sections
