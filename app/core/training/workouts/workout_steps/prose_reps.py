"""Keep a card's prose on the rep counts its steps deliver.

Key-workout prose is rendered from the card's *distance*. The steps are then
trimmed by ceilings the distance knows nothing about — the long run, the weekly
intensity share — and a dropped rep changed the steps while the sentence above
them kept promising the original count: "2 x 1.6km" over a single 1.6 km rep.

The steps are what the runner executes and what the watch receives, so they are
the authority. Wherever steps are final (the overlay, the post-pass clamps, and
the page render that re-derives the prose from the distance) the prose is
re-counted against them.

Pure — no I/O.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.core.training.workouts.workout_steps.structure import RECOVERY_KINDS

# "2 x 1.6km", "3 × 400m", "6 × 3 min", "4 × 20-second strides" — and the
# authored ranges, "8-10 x 60 seconds".
_REP_CITE = re.compile(
    r"(?<![\d.])(?P<count>(?P<fewest>\d+)(?:\s*[-–]\s*(?P<most>\d+))?)"
    r"(?=\s*[×x]\s*(?P<amount>\d+(?:\.\d+)?)[\s-]*"
    r"(?P<unit>km|min|sec|m|s)(?:ute|ond)?s?\b)",
    re.IGNORECASE,
)

# What one cited unit is worth in the step field that carries it.
_UNIT_FIELDS = {
    "km": ("distance_m", 1000.0),
    "m": ("distance_m", 1.0),
    "min": ("duration_s", 60.0),
    "sec": ("duration_s", 1.0),
    "s": ("duration_s", 1.0),
}

# "1.6km" is cited for a 1609 m mile; anything further apart is another set.
_AMOUNT_TOLERANCE = 0.02

_WARMUP_CITE = re.compile(r"Warm up (\d+(?:\.\d+)?)\s*km", re.IGNORECASE)

# Prose cites a warm-up to one decimal of a km; the step carries metres.
_WARMUP_TOLERANCE_KM = 0.051

_NON_WORK_KINDS = RECOVERY_KINDS | {"warmup", "cooldown"}

_PROSE_FIELDS = ("description", "structure")


def _cited_amount(match: re.Match[str]) -> tuple[str, float]:
    field, scale = _UNIT_FIELDS[match.group("unit").lower()]
    return field, float(match.group("amount")) * scale


def _cites(match: re.Match[str], reps: Optional[int]) -> bool:
    """Whether the cited count — or count range — covers ``reps``."""
    if reps is None:
        return False
    fewest = int(match.group("fewest"))
    return fewest <= reps <= int(match.group("most") or fewest)


def _is_amount(step: dict[str, Any], amount: tuple[str, float]) -> bool:
    field, value = amount
    actual = step.get(field)
    return bool(actual) and abs(actual - value) <= value * _AMOUNT_TOLERANCE


def _find_set(
    work: list[dict[str, Any]], cursor: int, amount: tuple[str, float]
) -> Optional[int]:
    """Index of the work set citing ``amount``: the next one, else an earlier.

    Sets are read in the order the prose cites them, so a ladder that returns
    to a distance ("400s, 800s, 400s") resolves each mention to its own set; a
    sentence that names the same set twice falls back to the one already read.
    """
    order = list(range(cursor, len(work))) + list(range(cursor))
    return next((i for i in order if _is_amount(work[i], amount)), None)


def _set_reps(work: list[dict[str, Any]], start: int, amount: tuple[str, float]) -> int:
    """Reps in the set at ``start``, counting reps a builder wrote out singly."""
    reps = 0
    for step in work[start:]:
        if not _is_amount(step, amount):
            break
        reps += int(step.get("repeat") or 1)
    return reps


def _cited_reps(
    text: str, steps: list[dict[str, Any]]
) -> list[tuple[re.Match[str], Optional[int]]]:
    """Each ``N x <amount>`` in ``text`` with the reps its set delivers.

    The reps are None when no set of that size exists among the steps.
    """
    work = [s for s in steps if s.get("kind") not in _NON_WORK_KINDS]
    cursor = 0
    cited: list[tuple[re.Match[str], Optional[int]]] = []
    for match in _REP_CITE.finditer(text):
        amount = _cited_amount(match)
        start = _find_set(work, cursor, amount)
        if start is None:
            cited.append((match, None))
            continue
        cursor = start + 1
        cited.append((match, _set_reps(work, start, amount)))
    return cited


def recount_reps(text: str, steps: list[dict[str, Any]]) -> str:
    """Rewrite each ``N x <amount>`` in ``text`` to the reps its set delivers.

    A citation with no set of that size among the steps is left as written —
    the prose is only ever corrected against a step it demonstrably describes —
    and so is an authored range ("8-10 x") the delivered reps fall inside.
    """
    parts: list[str] = []
    copied = 0
    for match, reps in _cited_reps(text, steps):
        if reps is None or _cites(match, reps):
            continue
        parts += [text[copied : match.start("count")], str(reps)]
        copied = match.end("count")
    return "".join(parts) + text[copied:]


def sync_prose_to_steps(workout: dict[str, Any]) -> None:
    """Make a card's description and structure cite the reps in its steps."""
    steps = workout.get("steps")
    if not steps:
        return
    for field in _PROSE_FIELDS:
        text = workout.get(field)
        if isinstance(text, str):
            workout[field] = recount_reps(text, steps)


def _miscites_reps(text: str, steps: list[dict[str, Any]]) -> bool:
    return any(not _cites(match, reps) for match, reps in _cited_reps(text, steps))


def _miscites_warmup(text: str, steps: list[dict[str, Any]]) -> bool:
    cited = _WARMUP_CITE.search(text)
    warmup_m = next(
        (s.get("distance_m") for s in steps if s.get("kind") == "warmup"), None
    )
    if not cited or not warmup_m:
        return False
    return abs(float(cited.group(1)) - warmup_m / 1000.0) > _WARMUP_TOLERANCE_KM


def prose_contradicts_steps(workout: dict[str, Any]) -> bool:
    """Whether the card's prose cites a rep set or warm-up its steps lack.

    Only what can be checked is checked: a text citing neither is never a
    contradiction, and neither is a card with no steps to contradict.
    """
    steps = workout.get("steps")
    if not steps:
        return False
    texts = [workout.get(field) for field in _PROSE_FIELDS]
    return any(
        _miscites_reps(text, steps) or _miscites_warmup(text, steps)
        for text in texts
        if isinstance(text, str)
    )
