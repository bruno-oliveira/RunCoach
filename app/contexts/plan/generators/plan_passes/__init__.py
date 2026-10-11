"""Plan-level passes: what happens to a week once the weekly builder is done.

``weekly_plan_builder`` assembles one week in isolation. These passes are the
ones that need to see more than that week — the load the plan has delivered so
far, the weeks either side, or the race the whole thing ends on. In the order
``TrainingPlanGenerator.generate_plan`` runs them:

- ``ramp_cap`` — per week, as it is built: hold it to the 10 % ramp over the
  delivered high-water mark, and hand a trail week back what a clamp released.
- ``smoothing`` — over the finished plan: re-anchor deloads and the taper to
  the load actually delivered, then sweep away token cards.
- ``race_week`` — last: install the race and size what precedes it. Nothing
  rescales a week after this.

``cards`` holds the vocabulary they share.
"""

from app.contexts.plan.generators.plan_passes.cards import (
    refresh_duration_hints,
    week_total_km,
)
from app.contexts.plan.generators.plan_passes.race_week import (
    install_backyard_race_day,
    install_race_day,
)
from app.contexts.plan.generators.plan_passes.ramp_cap import (
    enforce_weekly_ramp_cap,
    refill_trail_week,
)
from app.contexts.plan.generators.plan_passes.smoothing import (
    smooth_recovery_dips,
    smooth_taper,
    sweep_trivial_sessions,
)

__all__ = [
    "enforce_weekly_ramp_cap",
    "install_backyard_race_day",
    "install_race_day",
    "refill_trail_week",
    "refresh_duration_hints",
    "smooth_recovery_dips",
    "smooth_taper",
    "sweep_trivial_sessions",
    "week_total_km",
]
