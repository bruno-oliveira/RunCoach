"""Human-facing status for training plans, as a view model.

Shared by the My Plans list, the logged-in home hero, the /today redirect and the
scheduled push, so every surface computes "Week 4 of 12" / "Completed" / "Starts
Aug 3" the same way.

This is deliberately a *view model* rather than state on the ORM object.
``TrainingPlan`` used to carry ``status_label`` / ``target_distance_display`` /
``experience_level`` as plain attributes written per request by a decorator,
which forced ``TrainingPlan.__allow_unmapped__ = True`` — and under that flag a
future column annotation that forgets its ``Mapped[]`` silently becomes a plain
attribute instead of raising. Building a :class:`PlanStatus` per plan keeps the
ORM class a database object and the display logic a pure function of it, so the
model no longer needs the opt-in at all.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from app.contexts.plan.plan_type_registry import display_label as plan_display_label
from app.core.training.periodization.plan_calendar import (
    compute_current_week,
    plan_has_ended,
)
from app.core.training.periodization.strength_plan import derive_experience_level
from app.models import TrainingPlan

# The one label that means "this plan's training window is over". Read through
# ``PlanStatus.completed`` rather than comparing labels by hand.
_COMPLETED_LABEL = "Completed"


@dataclass(frozen=True)
class PlanStatus:
    """How one plan should be described to the runner looking at it."""

    # "Completed", "Week {n} of {total}", "Starts {Mon} {day}", or None when the
    # plan has no start date.
    label: Optional[str]
    distance_display: str
    experience_level: str

    @property
    def completed(self) -> bool:
        """Whether the plan's training window is over.

        Only the "Completed" label counts. A plan with no start date — or one we
        cannot measure against a ``weeks_duration`` it does not have — is not
        claimed to be finished.
        """
        return self.label == _COMPLETED_LABEL


def plan_status(plan: TrainingPlan, today: date) -> PlanStatus:
    """Describe ``plan`` as of ``today``."""
    distance_display = plan_display_label(plan)
    experience_level = derive_experience_level(plan.current_weekly_km or 0)

    if not plan.start_date:
        return PlanStatus(
            label=None,
            distance_display=distance_display,
            experience_level=experience_level,
        )

    sd = plan.start_date
    start_d = sd.date() if isinstance(sd, datetime) else sd
    # `pre_start=0` makes this a plain `int` (see the overloads on
    # `compute_current_week`): a not-yet-started plan comes back as 0.
    current_wk = compute_current_week(start_d, today, pre_start=0)
    # `weeks_duration` is a nullable column: comparing it directly raised
    # TypeError, which took out the home hero and the My Plans list for a plan
    # with no duration. A plan we cannot measure against its length is not
    # claimed to be finished.
    if plan_has_ended(start_d, plan.weeks_duration, today):
        label: Optional[str] = _COMPLETED_LABEL
    elif current_wk >= 1:
        # A plan with no recorded duration still has a current week, so report
        # that much rather than rendering "Week 3 of None" at the runner.
        label = (
            f"Week {current_wk} of {plan.weeks_duration}"
            if plan.weeks_duration is not None
            else f"Week {current_wk}"
        )
    else:
        label = f"Starts {start_d.strftime('%b')} {start_d.day}"

    return PlanStatus(
        label=label,
        distance_display=distance_display,
        experience_level=experience_level,
    )


def plan_statuses(plans: Iterable[TrainingPlan], today: date) -> dict[str, PlanStatus]:
    """Status for a batch of plans, keyed by plan id.

    A mapping rather than a list so a template can render a plan card with the
    status computed for it (``plan_statuses[plan.id]``) without a parallel
    ordering contract.
    """
    return {plan.id: plan_status(plan, today) for plan in plans}


def current_active_plan(
    plans: list[TrainingPlan], statuses: dict[str, PlanStatus]
) -> Optional[TrainingPlan]:
    """Pick the plan to surface as "your current training".

    Prefers the first non-completed plan (the list is newest-first); falls back
    to the most recent plan when every plan is completed.
    """
    for plan in plans:
        if not statuses[plan.id].completed:
            return plan
    return plans[0] if plans else None


def in_progress_plan(
    plans: Iterable[TrainingPlan], today: date
) -> Optional[TrainingPlan]:
    """The plan the runner is training on today: started, and not yet over.

    Distinct from :func:`current_active_plan`, which picks what to *show*
    (an unstarted or a just-finished plan is still worth a home-page hero). The
    nudge email and the scheduled pushes talk about today's training, so they
    need the plan that has a today: each used to re-derive that separately, and
    they disagreed — one returned nothing when the newest plan had no start date
    even though an older plan was mid-block, the other returned a future plan
    that hadn't begun.

    Args:
        plans: The runner's plans, newest first.
        today: The runner's local date.
    """
    for plan in plans:
        sd = plan.start_date
        start = sd.date() if isinstance(sd, datetime) else sd
        if start is None or start > today:
            continue
        if plan_has_ended(start, plan.weeks_duration, today):
            continue
        return plan
    return None
