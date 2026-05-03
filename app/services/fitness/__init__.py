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
        from app.services.fitness.fitness_service import FitnessService
        return FitnessService
    if name == "PerformanceService":
        from app.services.fitness.performance_service import PerformanceService
        return PerformanceService
    if name == "GapAnalysisService":
        from app.services.fitness.gap_analysis_service import GapAnalysisService
        return GapAnalysisService
    if name == "RacePredictorService":
        from app.services.fitness.race_predictor_service import RacePredictorService
        return RacePredictorService
    if name == "RacePacingService":
        from app.services.fitness.race_pacing_service import RacePacingService
        return RacePacingService
    if name == "ReadinessService":
        from app.services.fitness.readiness_service import ReadinessService
        return ReadinessService
    if name == "PersonalRecordsService":
        from app.services.fitness.personal_records_service import PersonalRecordsService
        return PersonalRecordsService
    if name == "TrainingLoadService":
        from app.services.fitness.training_load_service import TrainingLoadService
        return TrainingLoadService
    if name == "AdherenceService":
        from app.services.fitness.adherence_service import AdherenceService
        return AdherenceService
    if name == "HRZoneService":
        from app.services.fitness.hr_zone_service import HRZoneService
        return HRZoneService
    if name == "FeedbackService":
        from app.services.fitness.feedback_service import FeedbackService
        return FeedbackService
    if name == "InsightsService":
        from app.services.fitness.insights_service import InsightsService
        return InsightsService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
