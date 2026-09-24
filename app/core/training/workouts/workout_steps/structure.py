"""Group a flat step list into the blocks a runner actually executes.

The canonical step model is flat: a work step and its recovery each carry a
``repeat`` count, and nothing says how consecutive steps relate. Every surface
that shows the session — the watch export, the day card, the drill-down page,
the PDF — has to answer the same question: *which steps repeat together, and in
what order?* When each surface answered it separately, they disagreed, and the
watch was the one that got it wrong: a threshold over-under (``6 × over``,
``6 × under``) went up as six overs *then* six unders, and ``5 × 1 km`` with
four recoveries went up as five reps with five recoveries.

:func:`group_steps` is the single answer. Rules, in order:

* A repeated unit starts at a step with ``repeat`` N > 1 and takes the
  following *work* steps that share N — that is what makes an over-under or an
  alternating marathon-pace long run alternate.
* The unit then takes recovery steps (``recovery``/``walk``/``rest``) sharing
  N, and ends after them. Ending there keeps back-to-back sets (``4 × 400`` +
  jog, then ``4 × 200`` + jog) as two sets rather than one interleaved one.
* A recovery with N - 1 repeats belongs *between* the reps: the block is
  flagged ``skip_last_recovery`` so the last rep runs straight into what
  follows, exactly as prescribed.
* Strides with no recovery of their own get the walk/jog-back their note
  prescribes (flagged ``implied``), so the watch doesn't string six sprints
  together.

Pure — no I/O.
"""

from __future__ import annotations

from typing import Any

RECOVERY_KINDS = frozenset({"recovery", "walk", "rest"})
_BOOKEND_KINDS = frozenset({"warmup", "cooldown"})

# Walk/jog-back between strides when the builder left it implicit (the step
# note says "full recovery" but no step carries it).
_STRIDE_RECOVERY_S = 60


def _repeat(step: dict[str, Any]) -> int:
    return int(step.get("repeat") or 1)


def _implied_stride_recovery() -> dict[str, Any]:
    return {
        "kind": "recovery",
        "label": "Walk/jog back",
        "distance_m": None,
        "duration_s": _STRIDE_RECOVERY_S,
        "repeat": 1,
        "pace_zone": None,
        "pace_str": None,
        "effort": "walk/jog",
        "note": None,
        "implied": True,
    }


def group_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group ``steps`` into executable blocks.

    Returns:
        A list of blocks ``{"repeat": int, "steps": [...],
        "skip_last_recovery": bool}``. ``repeat`` is 1 for a plain step. The
        steps inside a repeated block are the originals (never copied or
        mutated), except an implied stride recovery, which is new and carries
        ``implied: True``.
    """
    blocks: list[dict[str, Any]] = []
    i, n = 0, len(steps)
    while i < n:
        step = steps[i]
        reps = _repeat(step)
        if reps <= 1 or step.get("kind") in _BOOKEND_KINDS:
            blocks.append({"repeat": 1, "steps": [step], "skip_last_recovery": False})
            i += 1
            continue

        unit = [step]
        j = i + 1
        # Work steps sharing the count alternate with the first one.
        while (
            j < n
            and _repeat(steps[j]) == reps
            and steps[j].get("kind") not in RECOVERY_KINDS | _BOOKEND_KINDS
        ):
            unit.append(steps[j])
            j += 1
        # Then the recoveries that close each rep.
        has_recovery = False
        while (
            j < n
            and _repeat(steps[j]) == reps
            and steps[j].get("kind") in RECOVERY_KINDS
        ):
            unit.append(steps[j])
            has_recovery = True
            j += 1

        skip_last = False
        if (
            not has_recovery
            and j < n
            and steps[j].get("kind") in RECOVERY_KINDS
            and _repeat(steps[j]) == reps - 1
        ):
            unit.append(steps[j])
            skip_last = True
            j += 1
        elif not has_recovery and all(s.get("kind") == "strides" for s in unit):
            unit.append(_implied_stride_recovery())
            skip_last = True

        blocks.append({"repeat": reps, "steps": unit, "skip_last_recovery": skip_last})
        i = j
    return blocks


def is_recovery(step: dict[str, Any]) -> bool:
    """Whether a step is a pause between efforts rather than the work."""
    return step.get("kind") in RECOVERY_KINDS
