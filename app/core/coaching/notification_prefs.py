"""Which push notifications a runner wants — keys, defaults, and the lookup.

Granting a browser's push permission is already a deliberate act, so every
category that answers something the runner did (a run landed, the plan moved
because of it) defaults on. The two that arrive unprompted — the morning brief
and the Sunday review — default on too, but each fires at most once a day /
week and only when there is something specific to say.

Stored as a sparse dict on ``User.notification_prefs``: only explicit choices
are written, so adding a category later gives existing runners its default
instead of a silent ``False``.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

AFTER_RUN = "after_run"
PLAN_CHANGES = "plan_changes"
MORNING_BRIEF = "morning_brief"
WEEK_REVIEW = "week_review"
COACHING_NUDGES = "coaching_nudges"

# Ordered for display.
CATEGORIES: Dict[str, Dict[str, Any]] = {
    AFTER_RUN: {
        "label": "After each run",
        "help": "A line on how the run went, minutes after your watch syncs.",
        "default": True,
    },
    PLAN_CHANGES: {
        "label": "Plan changes",
        "help": "When your plan adapts — what moved and why.",
        "default": True,
    },
    MORNING_BRIEF: {
        "label": "Morning brief",
        "help": "Today's session and how recovered your watch says you are.",
        "default": True,
    },
    WEEK_REVIEW: {
        "label": "Week review",
        "help": "Sunday evening: planned vs done, and what changes next week.",
        "default": True,
    },
    COACHING_NUDGES: {
        "label": "Coaching nudges",
        "help": "When training quietly slips or mornings keep being rough.",
        "default": True,
    },
}


def resolve(prefs: Optional[Mapping[str, Any]]) -> Dict[str, bool]:
    """Every category with the runner's choice or its default."""
    stored = prefs or {}
    return {
        key: bool(stored[key]) if key in stored else bool(meta["default"])
        for key, meta in CATEGORIES.items()
    }


def wants(prefs: Optional[Mapping[str, Any]], category: str) -> bool:
    """Whether this runner wants pushes of ``category`` (unknown → no)."""
    if category not in CATEGORIES:
        return False
    return resolve(prefs)[category]


def merge(
    prefs: Optional[Mapping[str, Any]], updates: Mapping[str, Any]
) -> Dict[str, bool]:
    """Apply explicit choices, ignoring keys that aren't categories."""
    merged = {k: bool(v) for k, v in (prefs or {}).items() if k in CATEGORIES}
    for key, value in updates.items():
        if key in CATEGORIES and value is not None:
            merged[key] = bool(value)
    return merged
