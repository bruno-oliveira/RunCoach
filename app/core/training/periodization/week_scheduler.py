"""Week day scheduling.

Assigns workout types to specific days of the week.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from app.domain.frequency import FrequencyComposer


def schedule_workout_types(
    distribution: Dict[str, int], phase: str, week_number: int, is_recovery_week: bool
) -> List[Optional[str]]:
    """Assign workout types to specific days.

    Recovery is always on Day 2 and does NOT count towards max_runs.
    """
    workout_types: List[Optional[str]] = [None] * 7

    workout_types[1] = "recovery"

    workout_types[5] = "long"
    if distribution.get("long", 0) > 0:
        distribution["long"] -= 1

    if not is_recovery_week:
        quality_count = sum(
            distribution.get(t, 0) for t in ("hill", "interval", "tempo")
        )
        # Space hard days apart. A single quality session sits mid-week
        # (day 4). Two sessions go on days 1 and 4: the recovery day and an
        # easy day separate them, and an easy day always buffers the long
        # run — filling consecutive slots put interval + tempo on
        # back-to-back days. Three (defensive; the distribution caps at
        # two) alternate hard/easy across the week.
        if quality_count >= 3:
            quality_slots = [0, 2, 4]
        elif quality_count == 2:
            quality_slots = [0, 3]
        else:
            quality_slots = [3]
        for day_idx in quality_slots:
            if workout_types[day_idx] is not None:
                continue
            if distribution["hill"] > 0:
                workout_types[day_idx] = "hill"
                distribution["hill"] -= 1
            elif distribution["interval"] > 0:
                workout_types[day_idx] = "interval"
                distribution["interval"] -= 1
            elif distribution["tempo"] > 0:
                workout_types[day_idx] = "tempo"
                distribution["tempo"] -= 1

    # For busy 2-run weeks (1 easy + 1 long), anchor easy on Wed (day_idx 2)
    # so it sits ~3 days from the Saturday long on either side.
    if (
        distribution["easy"] == 1
        and sum(distribution.get(k, 0) for k in ("interval", "tempo", "hill")) == 0
        and workout_types[2] is None
    ):
        workout_types[2] = "easy"
        distribution["easy"] -= 1

    for day_idx in range(7):
        if workout_types[day_idx] is not None:
            continue
        if distribution["easy"] > 0:
            workout_types[day_idx] = "easy"
            distribution["easy"] -= 1

    for day_idx in range(7):
        if workout_types[day_idx] is None:
            workout_types[day_idx] = "rest"
            distribution["rest"] -= 1

    return workout_types


# Day indices for each slot role, chosen to space hard days apart and
# anchor the long run on Saturday (day_idx 5).
_SLOT_DAY_MAP: dict[str, list[int]] = {
    "long": [5],
    "recovery": [1],
    "quality": [0, 3],
    "medium_long": [2, 1, 3, 4],
    "easy": [2, 0, 3, 1, 6, 4],
}

# Sessions that load the legs. Easy days are placed away from these.
_QUALITY = frozenset({"interval", "tempo", "hill"})
_LOADED = _QUALITY | {"long", "medium_long"}


def _longest_streak(running: set[int]) -> int:
    """Longest run of consecutive running days, wrapping Sunday into Monday."""
    if len(running) == 7:
        return 7
    best = 0
    for start in running:
        if (start - 1) % 7 in running:
            continue
        length = 1
        while (start + length) % 7 in running:
            length += 1
        best = max(best, length)
    return best


def _pick_easy_days(schedule: List[Optional[str]], count: int) -> List[int]:
    """Choose ``count`` free days for easy runs, spreading the week.

    A fixed fill order stacks the easy days wherever the order starts — the
    4-run plan ran Mon/Tue/Wed and then rested until Saturday. Greedily, each
    easy run goes on the free day that, in order of priority, leaves the
    shortest streak of consecutive running days, touches the fewest loaded
    sessions, touches the fewest runs at all, and isn't the eve of the long
    run; the preference order in ``_SLOT_DAY_MAP`` breaks what ties remain.
    """
    order = _SLOT_DAY_MAP["easy"]
    chosen: List[int] = []
    for _ in range(count):
        running = {
            d for d in range(7) if schedule[d] not in (None, "recovery", "rest")
        } | set(chosen)
        free = [d for d in order if schedule[d] is None and d not in chosen]
        if not free:
            break

        def cost(day: int) -> tuple[int, int, int, int, int]:
            neighbours = ((day - 1) % 7, (day + 1) % 7)
            loaded = sum(1 for n in neighbours if schedule[n] in _LOADED)
            touching = sum(1 for n in neighbours if n in running)
            eve_of_long = int(schedule[(day + 1) % 7] == "long")
            streak = _longest_streak(running | {day})
            return (streak, loaded, touching, eve_of_long, order.index(day))

        chosen.append(min(free, key=cost))
    return chosen


def schedule_from_composer(
    composer: FrequencyComposer,
    phase: str,
    quality_types: Dict[str, int],
    is_recovery_week: bool,
) -> List[Optional[str]]:
    """Map composer slots to a 7-day schedule.

    The composer's ordered slots define *what* the week contains; this
    function decides *which day* each slot lands on.  Quality slots are
    filled with the concrete quality types (tempo/interval/hill) from the
    distribution, but if it's a recovery week all quality becomes easy.
    """
    from app.domain.frequency import SlotType

    slots = composer.slots(phase)
    schedule: List[Optional[str]] = [None] * 7
    used: set[int] = set()

    def _claim(day_idx: int, label: str) -> bool:
        if day_idx in used or schedule[day_idx] is not None:
            return False
        schedule[day_idx] = label
        used.add(day_idx)
        return True

    # Pass 1: anchor long run on Saturday
    for slot in slots:
        if slot.slot_type == SlotType.LONG:
            _claim(5, "long")

    # Pass 2: anchor recovery on Tuesday (day after Monday quality)
    for slot in slots:
        if slot.slot_type == SlotType.RECOVERY:
            for d in (1, 2):
                if _claim(d, "recovery"):
                    break

    # Pass 3: place quality sessions, spaced apart
    quality_queue: list[str] = []
    if not is_recovery_week:
        for qtype in ("interval", "hill", "tempo"):
            quality_queue.extend([qtype] * quality_types.get(qtype, 0))

    quality_slots_needed = sum(1 for s in slots if s.slot_type == SlotType.QUALITY)
    if is_recovery_week:
        quality_slots_needed = 0

    quality_day_preferences = [0, 3, 2, 4]
    qi = 0
    for d in quality_day_preferences:
        if qi >= quality_slots_needed:
            break
        label = quality_queue[qi] if qi < len(quality_queue) else "easy"
        if _claim(d, label):
            qi += 1

    # Pass 4: place medium-long runs mid-week. Friday was the old first
    # choice, which stacked quality, medium-long and long on Thu/Fri/Sat.
    # With two quality days plus the long run, one loaded pair can't be
    # avoided; the medium-long then follows a quality day rather than
    # preceding one, so the quality session is run on fresh legs.
    for slot in slots:
        if slot.slot_type == SlotType.MEDIUM_LONG:
            free = [d for d in _SLOT_DAY_MAP["medium_long"] if schedule[d] is None]
            if not free:
                continue

            def ml_cost(day: int) -> tuple[int, int, int]:
                neighbours = (schedule[(day - 1) % 7], schedule[(day + 1) % 7])
                loaded = sum(1 for n in neighbours if n in _LOADED)
                precedes_quality = int(schedule[(day + 1) % 7] in _QUALITY)
                order = _SLOT_DAY_MAP["medium_long"].index(day)
                return (loaded, precedes_quality, order)

            _claim(min(free, key=ml_cost), "medium_long")

    # Pass 5: fill remaining with easy runs.
    # frequency is the running-day count; recovery is extra (non-running).
    # Easy fills whatever running slots are left after long/quality/medium_long.
    placed_running = sum(
        1
        for d in range(7)
        if schedule[d] is not None and schedule[d] not in ("recovery",)
    )
    easy_needed = max(0, composer.frequency - placed_running)
    for d in _pick_easy_days(schedule, easy_needed):
        _claim(d, "easy")

    # Pass 6: rest days
    for d in range(7):
        if schedule[d] is None:
            schedule[d] = "rest"

    return schedule
