"""Fitness & performance analysis services."""

__all__ = [
    "FitnessService",
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


def __getattr__(name: str):
    if name == "FitnessService":
        from app.contexts.runner.fitness.fitness_service import FitnessService
        return FitnessService
    if name == "PerformanceService":
        from app.contexts.runner.fitness.performance_service import PerformanceService
        return PerformanceService
    if name == "GapAnalysisService":
        from app.contexts.runner.fitness.gap_analysis_service import GapAnalysisService
        return GapAnalysisService
    if name == "RacePredictorService":
        from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
        return RacePredictorService
    if name == "RacePacingService":
        from app.contexts.runner.fitness.race_pacing_service import RacePacingService
        return RacePacingService
    if name == "ReadinessService":
        from app.contexts.runner.fitness.readiness_service import ReadinessService
        return ReadinessService
    if name == "PersonalRecordsService":
        from app.contexts.runner.fitness.personal_records_service import PersonalRecordsService
        return PersonalRecordsService
    if name == "TrainingLoadService":
        from app.contexts.runner.fitness.training_load_service import TrainingLoadService
        return TrainingLoadService
    if name == "AdherenceService":
        from app.contexts.runner.fitness.adherence_service import AdherenceService
        return AdherenceService
    if name == "HRZoneService":
        from app.contexts.runner.fitness.hr_zone_service import HRZoneService
        return HRZoneService
    if name == "FeedbackService":
        from app.contexts.runner.fitness.feedback_service import FeedbackService
        return FeedbackService
    if name == "InsightsService":
        from app.contexts.runner.fitness.insights_service import InsightsService
        return InsightsService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
