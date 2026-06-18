"""Fitness & performance analysis services."""

import importlib

__all__ = [
    "PerformanceService",
    "GapAnalysisService",
    "RacePredictorService",
    "RacePacingService",
    "ReadinessService",
    "PersonalRecordsService",
    "TrainingLoadService",
    "AdherenceService",
    "HRZoneService",
    "FeedbackService",
    "InsightsService",
]

# Public name → (submodule, attribute). Imports stay lazy so importing this
# package doesn't pull in every service (and avoids import cycles).
_LAZY_EXPORTS = {
    "PerformanceService": ("performance_service", "PerformanceService"),
    "GapAnalysisService": ("gap_analysis_service", "GapAnalysisService"),
    "RacePredictorService": ("race_predictor_service", "RacePredictorService"),
    "RacePacingService": ("race_pacing_service", "RacePacingService"),
    "ReadinessService": ("readiness_service", "ReadinessService"),
    "PersonalRecordsService": ("personal_records_service", "PersonalRecordsService"),
    "TrainingLoadService": ("training_load_service", "TrainingLoadService"),
    "AdherenceService": ("adherence_service", "AdherenceService"),
    "HRZoneService": ("hr_zone_service", "HRZoneService"),
    "FeedbackService": ("feedback_service", "FeedbackService"),
    "InsightsService": ("insights_service", "InsightsService"),
}


def __getattr__(name: str):
    try:
        module_name, attr = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = importlib.import_module(f"{__name__}.{module_name}")
    return getattr(module, attr)
