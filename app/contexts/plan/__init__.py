"""Plan lifecycle & operation services."""

__all__ = [
    "PlanService",
    "PlanLifecycleService",
    "PlanAdjustments",
]


def __getattr__(name: str):
    if name == "PlanService":
        from app.contexts.plan.plan_service import PlanService
        return PlanService
    if name == "PlanLifecycleService":
        from app.contexts.plan.plan_lifecycle_service import PlanLifecycleService
        return PlanLifecycleService
    if name == "PlanAdjustments":
        from app.contexts.plan.plan_adjustments import PlanAdjustments
        return PlanAdjustments
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
