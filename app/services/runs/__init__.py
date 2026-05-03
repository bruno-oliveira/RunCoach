"""Run logging & enrichment services."""

__all__ = [
    "RunEnrichmentService",
    "CompletionStats",
    "WeekPulseGenerator",
]


def __getattr__(name: str):
    if name == "RunEnrichmentService":
        from app.services.runs.run_enrichment_service import RunEnrichmentService
        return RunEnrichmentService
    if name == "CompletionStats":
        from app.services.runs.completion_stats import CompletionStats
        return CompletionStats
    if name == "WeekPulseGenerator":
        from app.services.runs.week_pulse_generator import WeekPulseGenerator
        return WeekPulseGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
