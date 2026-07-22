"""Human-facing status decoration for training plans.

Shared by the My Plans list and the logged-in home hero so both surfaces
compute "Week 4 of 12" / "Completed" / "Starts Aug 3" the same way.
"""

from datetime import date, datetime
from typing import Optional

from app.contexts.plan.plan_type_registry import display_label as plan_display_label
from app.core.training.plan_calendar import compute_current_week
from app.core.training.strength_plan import derive_experience_level
from app.models import TrainingPlan


def decorate_plan_status(plan: TrainingPlan, today: date) -> TrainingPlan:
    """Attach display fields (`target_distance_display`, `experience_level`,
    `status_label`) to a plan in place, and return it.

    `status_label` is one of "Completed", "Week {n} of {total}",
    "Starts {Mon} {day}", or None when the plan has no start date.
    """
    plan.target_distance_display = plan_display_label(plan)
    plan.experience_level = derive_experience_level(plan.current_weekly_km or 0)

    if plan.start_date:
        sd = plan.start_date
        start_d = sd.date() if isinstance(sd, datetime) else sd
        current_wk = compute_current_week(start_d, today, pre_start=0)
        if current_wk > plan.weeks_duration:
            plan.status_label = "Completed"
        elif current_wk >= 1:
            plan.status_label = f"Week {current_wk} of {plan.weeks_duration}"
        else:
            plan.status_label = f"Starts {start_d.strftime('%b')} {start_d.day}"
    else:
        plan.status_label = None

    return plan


def current_active_plan(plans: list[TrainingPlan]) -> Optional[TrainingPlan]:
    """Pick the plan to surface as "your current training".

    Prefers the first non-completed plan (the list is newest-first); falls
    back to the most recent plan when every plan is completed. Assumes each
    plan has already been through `decorate_plan_status`.
    """
    for plan in plans:
        if getattr(plan, "status_label", None) != "Completed":
            return plan
    return plans[0] if plans else None
