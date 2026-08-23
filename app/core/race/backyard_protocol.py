"""Race-day protocol for a backyard ultra.

A backyard is not a long race, it is the *same short race* run again every
hour, so almost nothing in the road/trail protocol transfers. There is no
negative split to plan, no aid-station ETA to hit, no finish line to ration
effort toward — the two things that actually decide the result are:

* **the corral routine.** The gap between crossing the line and the next
  whistle is the only recovery in the sport. A runner who drifts through it,
  or who has to think about what comes next, loses three or four minutes an
  hour — and unlike pace, that time never comes back. So the turnaround is
  written out as a rehearsed sequence with a clock against it, the same way a
  pit stop is.
* **the fuelling schedule.** Eating "when hungry" fails here, because hunger
  disappears somewhere around hour eight and the race keeps going. Intake is
  therefore prescribed per hour and *steps down* as the race goes on: the
  gut's capacity falls, chewing gets hard in the dark, and the runner who
  still plans on gels at hour twenty will not be eating at all.

Both are derived from the runner's own profile — the turnaround minutes come
from their goal, so a 36-loop runner gets a longer, more deliberate routine
than a first-timer — and everything is pure arithmetic on the profile.

The three-, two- and one-minute whistles are near-universal in the format, so
the back half of the routine is anchored to them rather than to elapsed time:
they are the only cues the runner will actually hear at 3am.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.training.backyard_profile import BackyardProfile

# Whistles before each start. Universal enough across race directors to plan
# against; the runner is *in* the corral at the two-minute whistle, not
# walking toward it.
_WHISTLE_MINUTES = (3, 2, 1)

# The turnaround's fixed tail: standing up, moving, and being in the corral
# takes about this long no matter how much rest the runner has banked, so it
# is reserved off the top and only the remainder is available for the work.
_CORRAL_TAIL_MINUTES = 3.0

# Fractions of the *usable* turnaround (everything before the tail) at which
# each task should be done. Drinking comes first because it is the one thing
# a runner reliably skips, and feet come before kit because a hotspot found
# at hour six is a blister avoided at hour twelve.
_ROUTINE_FRACTIONS = (
    (0.00, "Cross the line and keep walking for 30 seconds"),
    (0.10, "Drink before anything else"),
    (0.25, "Sit down, and eat"),
    (0.50, "Feet and legs"),
    (0.75, "Restock for the next loop"),
)


def _fmt_min(minutes: float) -> str:
    """Render a minute offset the way a runner reads a stopwatch."""
    total_s = int(round(minutes * 60))
    m, s = divmod(total_s, 60)
    return f"{m}:{s:02d}"


def corral_routine(profile: BackyardProfile) -> List[Dict[str, str]]:
    """The turnaround, rehearsed as a sequence with a clock against it.

    Offsets are measured from crossing the line and scale with the runner's
    own turnaround budget, so the routine stays executable whether they have
    eight minutes or fourteen. The last two entries are anchored to the
    whistles instead, because by then the clock the runner is obeying is the
    race's, not their own.
    """
    usable = max(1.0, profile.turnaround_minutes - _CORRAL_TAIL_MINUTES)

    steps: List[Dict[str, str]] = [
        {
            "when": f"+{_fmt_min(usable * 0.00)}",
            "action": _ROUTINE_FRACTIONS[0][1],
            "why": (
                "Stopping dead stiffens you up and the clock is already running. "
                "Walk it in, then work."
            ),
        },
        {
            "when": f"+{_fmt_min(usable * 0.10)}",
            "action": _ROUTINE_FRACTIONS[1][1],
            "why": (
                "Fluid is the one thing everyone skips when they're rushing, and "
                "it's the one you can't catch up on later."
            ),
        },
        {
            "when": f"+{_fmt_min(usable * 0.25)}",
            "action": _ROUTINE_FRACTIONS[2][1],
            "why": (
                "Off the feet is worth more than any stretch. Eat here, every "
                "loop, whether or not you want to — see the hourly plan."
            ),
        },
        {
            "when": f"+{_fmt_min(usable * 0.50)}",
            "action": _ROUTINE_FRACTIONS[3][1],
            "why": (
                "Check for hotspots by hand, not by feel. A blister found now is "
                "tape; found in three hours it's the reason you stop."
            ),
        },
        {
            "when": f"+{_fmt_min(usable * 0.75)}",
            "action": _ROUTINE_FRACTIONS[4][1],
            "why": (
                "Bottles filled, pockets loaded, layers and headlamp sorted for "
                "the conditions of the *next* hour, not this one."
            ),
        },
    ]

    steps.append(
        {
            "when": f"{_WHISTLE_MINUTES[0]} min whistle",
            "action": "On your feet and moving",
            "why": (
                "Standing up is the hardest part of the hour. Do it on the "
                "whistle, not when you feel ready — you won't feel ready."
            ),
        }
    )
    steps.append(
        {
            "when": f"{_WHISTLE_MINUTES[1]} min whistle",
            "action": "In the corral",
            "why": (
                "Not walking toward it — in it. Missing the start is the only "
                "way out of this race that has nothing to do with your legs."
            ),
        }
    )
    steps.append(
        {
            "when": f"{_WHISTLE_MINUTES[2]} min whistle",
            "action": "Stand still and breathe",
            "why": "Nothing left to do. The next hour starts the same as the last.",
        }
    )
    return steps


# Hour bands the gut actually moves through, independent of the runner's goal.
# Intake steps down and shifts from chewed to sipped: capacity falls, chewing
# gets hard after dark, and salt loss compounds. Bands are truncated at the
# runner's target, so a 10-loop goal never reads advice about hour thirty.
_FUEL_BANDS: List[Dict[str, Any]] = [
    {
        "until": 4,
        "carbs": "60–80 g/h",
        "focus": "Feeling good is not a reason to skip a meal",
        "fuel": (
            "Real, solid food while your stomach still wants it — sandwich, rice "
            "ball, banana, boiled potato. Bank the calories you'll be too "
            "nauseous to take later."
        ),
        "fluid": "500–700 ml/h",
        "sodium": "300–500 mg/h",
    },
    {
        "until": 10,
        "carbs": "50–70 g/h",
        "focus": "Start alternating sweet and savoury",
        "fuel": (
            "Rotate flavours deliberately — the first thing to fail is your "
            "appetite for whatever you've had five times. Soup or broth enters "
            "here."
        ),
        "fluid": "500 ml/h",
        "sodium": "400–600 mg/h",
    },
    {
        "until": 17,
        "carbs": "40–60 g/h",
        "focus": "Into the dark — warm and soft, not chewy",
        "fuel": (
            "Warm liquid calories: broth, soup, sweet tea, flat cola. Chewing is "
            "genuinely hard now and cold food gets refused. First caffeine here, "
            "not earlier."
        ),
        "fluid": "400–500 ml/h",
        "sodium": "500–700 mg/h",
    },
    {
        "until": 26,
        "carbs": "40 g/h minimum",
        "focus": "Through the night — something every single loop",
        "fuel": (
            "Small and constant beats large and occasional. Anything that stays "
            "down counts. If nothing appeals, drink your calories and keep "
            "moving — the low point passes."
        ),
        "fluid": "400 ml/h",
        "sodium": "500–700 mg/h",
    },
    {
        "until": 99,
        "carbs": "Whatever stays down",
        "focus": "Second day — the plan is now damage control",
        "fuel": (
            "Forget the targets and eat the thing you can face, every loop. "
            "Caffeine on a schedule with real gaps, or it stops working when "
            "you need it most."
        ),
        "fluid": "Sip every loop",
        "sodium": "Keep taking it",
    },
]


def hourly_fuelling_schedule(profile: BackyardProfile) -> List[Dict[str, str]]:
    """Per-hour intake, banded and stepping down as the race goes on.

    Bands are truncated at the runner's goal so the plan never describes an
    hour they are not training for, and the final band is labelled open-ended
    ("Loop 18+") because a backyard has no scheduled last hour.
    """
    rows: List[Dict[str, str]] = []
    start = 1
    target = profile.target_loops
    for band in _FUEL_BANDS:
        if start > target:
            break
        end = min(int(band["until"]), target)
        label = f"Loop {start}" if start == end else f"Loops {start}–{end}"
        if end == target:
            # A backyard has no scheduled final hour; if the runner is still
            # out there past their goal the last band keeps applying.
            label = f"Loop {start}+" if start == end else f"Loops {start}+"
        rows.append(
            {
                "loops": label,
                "hours": f"h{start}–{end}" if start != end else f"h{start}",
                "carbs": str(band["carbs"]),
                "fluid": str(band["fluid"]),
                "sodium": str(band["sodium"]),
                "focus": str(band["focus"]),
                "fuel": str(band["fuel"]),
            }
        )
        start = end + 1
    return rows


def _nutrition_timing(profile: BackyardProfile) -> List[Dict[str, str]]:
    """The standing rules, as opposed to the per-hour targets."""
    items = [
        {
            "icon": "🍽️",
            "when": "3 hrs before",
            "what": (
                "Normal tested breakfast. Do not carb-load beyond it — you will "
                "eat more during this race than before it."
            ),
        },
        {
            "icon": "⏱️",
            "when": "Every turnaround",
            "what": (
                "Eat and drink something on every single loop, appetite or not. "
                "The hour you skip is the hour that ends you, three hours later."
            ),
        },
        {
            "icon": "🧂",
            "when": "Every 1–2 loops",
            "what": (
                "Electrolytes on a clock. Hourly restarts hide how much you're "
                "sweating, and cramp in the corral is unrecoverable."
            ),
        },
    ]
    if profile.runs_in_darkness:
        items.append(
            {
                "icon": "☕",
                "when": "From dusk, then every 3–4 loops",
                "what": (
                    "Caffeine held back until dark so it still works when it "
                    "matters. 100–200 mg at a time, with real gaps between."
                ),
            }
        )
    if profile.crosses_full_night:
        items.append(
            {
                "icon": "🍲",
                "when": "Small hours",
                "what": (
                    "Hot, savoury, salty — broth, noodles, soup. Sweet food gets "
                    "refused around 3am and that is when people quietly stop "
                    "eating."
                ),
            }
        )
    if profile.crosses_two_nights:
        items.append(
            {
                "icon": "😴",
                "when": "Second night",
                "what": (
                    "Micro-sleeps of 5–10 min in the turnaround are a fuelling "
                    "decision too — a runner who can't stay awake can't eat."
                ),
            }
        )
    items.append(
        {
            "icon": "🥔",
            "when": "When you stop",
            "what": "Protein and salt before sleep, however little you feel like it.",
        }
    )
    return items


def _morning_timeline(profile: BackyardProfile) -> List[Dict[str, str]]:
    """Race morning, which for a backyard is mostly about the table.

    The camp gets built before the gun and never again: after loop one there
    are only ever ten minutes, and they are spoken for.
    """
    return [
        {
            "time": "3 hrs before",
            "activity": "Wake; normal tested breakfast — this is not a fuel-load",
        },
        {
            "time": "2 hrs before",
            "activity": (
                "Arrive and build your camp: chair facing the corral, table at "
                "arm height, food and kit laid out in the order you'll use it"
            ),
        },
        {
            "time": "90 min before",
            "activity": (
                "Walk the first 500 m of the loop and the route from your chair "
                "to the corral — time both"
            ),
        },
        {
            "time": "60 min before",
            "activity": (
                "Brief your crew on the routine and the whistles; agree who "
                "hands you what, and who says nothing"
            ),
        },
        {
            "time": "30 min before",
            "activity": (
                "Headlamp, spare batteries and night layers staged now, not at "
                "dusk when you'll be tired"
            ),
        },
        {
            "time": "10 min before",
            "activity": (
                "In the corral. Plan to finish loop one feeling like you barely "
                "ran — that is the correct feeling"
            ),
        },
    ]


def _week_before_extras(profile: BackyardProfile) -> List[str]:
    extras = [
        "Rehearse the turnaround at home against a timer until it needs no thinking",
        "Pack the camp by hour, not by category: a bag per block of loops",
        "Bring a chair you can get out of easily — low camping chairs cost minutes",
        "Prepare more savoury food than you think you want, and freeze soup portions",
        "Confirm the loop distance, the corral rules, and where the whistles come from",
    ]
    if profile.runs_in_darkness:
        extras += [
            "Two headlamps plus spare batteries — assume one fails at the worst hour",
            "Stage warm layers for the night before the race starts, not during it",
        ]
    if profile.crosses_full_night:
        extras += [
            "Brief crew on what to do if you get incoherent — and agree the abort call",
            "Plan a hot-food source that still works at 3am",
            "Three or more pairs of shoes and socks; rotating them buys you hours",
        ]
    if profile.crosses_two_nights:
        extras += [
            "Plan micro-sleeps: 5–10 min in the chair is normal and works",
            "Arrange crew shifts so somebody is always awake and sharp",
        ]
    return extras


def _pacing_strategy(profile: BackyardProfile) -> str:
    budget = round(profile.loop_budget_minutes)
    turn = round(profile.turnaround_minutes)
    strategy = (
        f"There is no finish line to ration effort toward — only the next hour. "
        f"Run every loop in about {budget} min and bank the other ~{turn} min as "
        f"rest. That number is the whole strategy: running the loop five minutes "
        f"faster does not earn you a loop, it earns you five more minutes in a "
        f"chair, paid for with legs you will want later. Running it five minutes "
        f"slower takes those minutes from the only recovery you get."
    )
    if profile.crosses_full_night:
        strategy += (
            " Expect the worst hours somewhere between 2am and dawn — they are "
            "not a signal to stop, they are the part of the race everyone has. "
            "Keep eating, change one small thing, and get to daylight."
        )
    if profile.crosses_two_nights:
        strategy += (
            " Past the first night the race becomes a sleep-management problem "
            "as much as a running one. Protect the routine above everything: "
            "when judgement goes, the routine is what keeps you in."
        )
    return strategy


def _mental_checkpoints(profile: BackyardProfile) -> List[Dict[str, str]]:
    """Anchors by loop, which is the only unit the runner is counting."""
    target = profile.target_loops
    anchors = [
        (1, "Too easy. Good — that's the pace that's still there at hour twenty."),
        (
            max(2, round(target * 0.25)),
            "The routine should be automatic by now. If it isn't, fix it here.",
        ),
        (
            max(3, round(target * 0.5)),
            "Halfway to your goal. Check the boring things: feet, salt, mood.",
        ),
        (
            max(4, round(target * 0.75)),
            "The hard part. You are not deciding whether to finish — only "
            "whether to start the next one.",
        ),
        (
            target,
            "Your goal loop. Anything past this is a bonus you've already "
            "earned, so decide it fresh, not now.",
        ),
    ]
    seen: set[int] = set()
    out: List[Dict[str, str]] = []
    for loop, message in anchors:
        if loop in seen or loop > target:
            continue
        seen.add(loop)
        out.append({"distance": f"Loop {loop}", "message": message})
    return out


def build_backyard_protocol(
    profile: BackyardProfile,
    week_before_base: List[str],
) -> Dict[str, Any]:
    """Assemble the full race-day protocol for a backyard goal.

    ``week_before_base`` is the universal checklist the caller already owns,
    so this module doesn't duplicate it.
    """
    return {
        "distance_name": f"{profile.target_loops}-Loop Backyard Ultra",
        "predicted_finish_time": f"{profile.target_hours} h",
        "week_before_checklist": list(week_before_base) + _week_before_extras(profile),
        "race_morning_timeline": _morning_timeline(profile),
        "pacing_strategy": _pacing_strategy(profile),
        # Deliberately empty: every loop is the same distance at the same pace,
        # so a split table would be the same row printed twenty-four times.
        "pacing_splits": [],
        "nutrition_timing": _nutrition_timing(profile),
        "mental_checkpoints": _mental_checkpoints(profile),
        "corral_routine": corral_routine(profile),
        "hourly_fuelling": hourly_fuelling_schedule(profile),
        "loop_budget_min": round(profile.loop_budget_minutes),
        "turnaround_min": round(profile.turnaround_minutes),
        "is_trail": False,
        "is_backyard": True,
    }


def backyard_protocol_or_none(
    profile: Optional[BackyardProfile],
    week_before_base: List[str],
) -> Optional[Dict[str, Any]]:
    """Convenience wrapper for callers holding an optional profile."""
    if profile is None:
        return None
    return build_backyard_protocol(profile, week_before_base)
