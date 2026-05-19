"""Run logging & enrichment services."""

__all__ = [
    "RunEnrichmentService",
    "CompletionStats",
    "WeekPulseGenerator",
]


def __getattr__(name: str):
    if name == "RunEnrichmentService":
        from app.contexts.runner.enrichment.run_enrichment_service import RunEnrichmentService
        return RunEnrichmentService
    if name == "CompletionStats":
        from app.contexts.runner.enrichment.completion_stats import CompletionStats
        return CompletionStats
    if name == "WeekPulseGenerator":
        from app.contexts.runner.enrichment.week_pulse_generator import WeekPulseGenerator
        return WeekPulseGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
