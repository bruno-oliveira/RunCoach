"""Backyard Ultra key workout definitions.

See key_workout_data.py for the full field documentation.

These sessions are never picked by the normal rotation — they are listed in
``_BACKYARD_ONLY_IDS`` and installed exclusively by the backyard week
post-pass, which knows the runner's loop length and rest budget and cannot
express either through the rotation's (distance, phase, terrain) interface.
They live in the catalog anyway so that ``get_by_id`` resolves them, which is
what lets stored plans, the key-workout listing, and the adaptation engine all
recognise a backyard session rather than treating it as an unlabelled long run.

Every one of them carries ``fixed_structure``: a simulation's distance is
``loops × loop length``, an integer number of hours on a clock. Adaptation may
not rescale it to 0.9× the way it would a long run — five and a half loops is
not a thing that exists.
"""

from typing import Dict, List

BACKYARD_LONG: List[Dict] = [
    {
        "id": "backyard_loop_simulation",
        "distances": [30.0],
        "phases": ["base", "build", "peak"],
        "type": "long",
        "terrain": ["any"],
        "fixed_structure": True,
        "name": "Loop Simulation",
        "structure": "Hourly loops on the hour, with the full turnaround between",
        "description": (
            "Run the race loop, start the next one on the hour, repeat. Treat "
            "every turnaround as if it were race day: eat, drink, refill, check "
            "your feet, and be back before the whistle."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "A long run teaches you to keep going. A backyard asks you to stop "
            "and start again, over and over, on legs that have gone cold. "
            "Nothing but the format itself trains the restart."
        ),
    },
    {
        "id": "backyard_night_simulation",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["any"],
        "fixed_structure": True,
        "name": "Night Loop Simulation",
        "structure": "Evening-start loop simulation running into full darkness",
        "description": (
            "Start in the evening so the loops run into the dark. Headlamp, "
            "spare batteries, night kit, and the food you'll actually want at "
            "2am — all of it rehearsed while a mistake still only costs you a "
            "training session."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Darkness slows everyone down and the clock does not care. Finding "
            "out on race night how much a headlamp costs you per loop is how "
            "runners get timed out in the small hours."
        ),
    },
    {
        "id": "backyard_dress_rehearsal",
        "distances": [30.0],
        "phases": ["peak"],
        "type": "long",
        "terrain": ["any"],
        "fixed_structure": True,
        "name": "Dress Rehearsal",
        "structure": "The plan's longest loop simulation, run exactly as the race",
        "description": (
            "The full rehearsal: race kit, race shoes, race food, drop bag laid "
            "out the way it will be laid out on the day. Change nothing between "
            "this session and the start line."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "This is the last session that can still teach you something in "
            "time to act on it. Everything it exposes — a chafe point, a gel "
            "you can no longer swallow, a headlamp angle — is a problem you get "
            "to solve before it costs you loops."
        ),
    },
    {
        "id": "backyard_turnaround_drill",
        "distances": [30.0],
        "phases": ["base", "build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "fixed_structure": True,
        "name": "Turnaround Drill",
        "structure": "A few loops on the hour, with the transition timed each lap",
        "description": (
            "A short simulation whose real work happens standing still. Run the "
            "loop to its budget, then execute the full turnaround against a "
            "clock: bottle, food, feet, kit, corral."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Backyard runners are eliminated by the corral, not by the course. "
            "A turnaround that takes four minutes longer than planned is four "
            "minutes of recovery you never get, every hour, forever."
        ),
    },
    {
        "id": "backyard_loop_repeats",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "tempo",
        "terrain": ["any"],
        "fixed_structure": True,
        "name": "Loop-Pace Repeats",
        "structure": "Loop-distance reps at goal loop pace off a standing rest",
        "description": (
            "Repeats over the race loop distance at exactly your goal loop "
            "pace, with a standing rest between them. Same split every rep — a "
            "fast one is a mistake, not a win."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Loop pace is a rest budget, and it only becomes automatic if you "
            "rehearse hitting it from cold. Running it off a standing start is "
            "what makes the pace survive hour fifteen."
        ),
    },
    {
        "id": "backyard_b2b_day2",
        "distances": [30.0],
        "phases": ["build", "peak"],
        "type": "long",
        "terrain": ["any"],
        "fixed_structure": True,
        "name": "Second-Day Loops",
        "structure": "Easy loops at goal pace on legs fatigued from yesterday",
        "description": (
            "Easy running at goal loop pace on legs that already did yesterday's "
            "work. Practise fuelling on the same schedule you'll use in the "
            "race, and pay attention to how the pace feels rather than how fast "
            "it is."
        ),
        "intensity": "medium",
        "target_zone": 2,
        "pace_zone": "E",
        "rationale": (
            "Hour twenty of a backyard feels like the second day of a training "
            "weekend, not like the end of a long run. Starting already tired is "
            "the closest a week of training gets to the back half of the race."
        ),
    },
]
