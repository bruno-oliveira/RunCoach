"""Plan lifecycle & operation services.

``PlanService`` is re-exported lazily so importing the package does not pull in
the generators. Two other names used to be here, and both were dead and broken:
``PlanLifecycleService`` named a class that ``plan_lifecycle_service`` does not
define (that module is a set of functions), and ``PlanAdjustments`` named a class
that ``plan_adjustments`` does not define either (also functions). Nothing
imported either alias, so the only thing they could do was raise ``ImportError``
for whoever tried next. Removed rather than corrected — a second name for an
abstraction nobody uses is a name waiting to disagree with the first.
"""

__all__ = [
    "PlanService",
]


def __getattr__(name: str):
    if name == "PlanService":
        from app.contexts.plan.plan_service import PlanService

        return PlanService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
