"""External integration services (Intervals.icu, FIT)."""

__all__ = [
    "FitService",
]


def __getattr__(name: str):
    if name == "FitService":
        from app.infrastructure.integrations.fit_service import FitService

        return FitService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
