"""Custom exception classes for RunCoach application."""


class RunCoachException(Exception):
    """Base exception for RunCoach application."""

    def __init__(self, message: str, user_message: str = None):
        self.message = message
        self.user_message = user_message or message
        super().__init__(self.message)


class ValidationException(RunCoachException):
    """Exception for validation errors."""

    pass


class UnrealisticGoalException(ValidationException):
    """Exception when training goals are unrealistic."""

    def __init__(self, message: str, suggestion: str = None):
        self.suggestion = suggestion
        super().__init__(message, message)  # Don't duplicate suggestion in user_message


class InsufficientTimeException(UnrealisticGoalException):
    """Exception when training duration is insufficient for target distance."""

    pass


class InadequateBaseException(UnrealisticGoalException):
    """Exception when current fitness level is inadequate for goal."""

    pass


class ZeroMileageUnsupportedException(UnrealisticGoalException):
    """Exception when user has 0 mileage but selects an unsupported distance."""

    pass


class PlanGenerationException(RunCoachException):
    """Exception for errors during plan generation."""

    pass


class DatabaseException(RunCoachException):
    """Exception for database-related errors."""

    pass
