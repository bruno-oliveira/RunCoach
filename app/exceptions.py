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


class UnverifiedEmailException(RunCoachException):
    """Google sign-in whose unverified email collides with an existing account.

    Linking (or creating a duplicate) on an unverified address would let an
    attacker claim another user's account, so the sign-in is refused.
    """

    def __init__(self, message: str):
        super().__init__(
            message,
            user_message=(
                "This Google account's email address is not verified, and an "
                "account with that address already exists. Verify the address "
                "with Google, or sign in with the account you used originally."
            ),
        )


class PlanGenerationException(RunCoachException):
    """Exception for errors during plan generation."""

    pass


class DatabaseException(RunCoachException):
    """Exception for database-related errors."""

    pass
