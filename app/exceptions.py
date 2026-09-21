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


class PlanGenerationError(PlanGenerationException):
    """Generation failure that carries the measurements which caused it.

    :class:`PlanGenerationException` says *that* generation failed;
    ``PlanGenerationError`` and its subclasses say *why*, with the numbers
    that prove it — a frequency budget that cannot reach the weekly volume,
    a race distance the long-run ceiling never touches, or a parameter
    outside its supported range. Without them the only signal available to
    callers and ops is a generic message, and "frequency infeasible" is
    indistinguishable from "invalid config".

    The diagnostic ``message`` (with measured values) is for logs and tests;
    ``user_message`` is what the runner sees.
    """

    def diagnostics(self) -> dict[str, object]:
        """Return the measured values that made generation infeasible."""
        return {}


class FrequencyBudgetInfeasibleError(PlanGenerationError):
    """The requested weekly volume exceeds what the run frequency allows.

    The per-frequency composers cap how much volume a week built from
    ``runs_per_week`` runs can carry; when the periodisation model asks for
    more than that cap, generation cannot proceed honestly.
    """

    def __init__(
        self,
        runs_per_week: int,
        target_weekly_km: float,
        max_reachable_weekly_km: float,
        user_message: str | None = None,
    ):
        self.runs_per_week = runs_per_week
        self.target_weekly_km = target_weekly_km
        self.max_reachable_weekly_km = max_reachable_weekly_km
        super().__init__(
            (
                f"Frequency budget infeasible: {target_weekly_km:.1f} km/week "
                f"requested on {runs_per_week} runs/week, but that frequency "
                f"caps the week at {max_reachable_weekly_km:.1f} km."
            ),
            user_message=user_message
            or (
                "That weekly mileage is too ambitious for the number of runs "
                "per week you selected. Try more runs per week or a lower "
                "mileage."
            ),
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "runs_per_week": self.runs_per_week,
            "target_weekly_km": self.target_weekly_km,
            "max_reachable_weekly_km": self.max_reachable_weekly_km,
        }


class DistanceInfeasibleError(PlanGenerationError):
    """The race distance cannot be reached within the training window.

    Even the final-week long run, at its ceiling, falls short of building the
    runner up to the requested distance — the goal needs more weeks (or more
    base mileage) than were requested.
    """

    def __init__(
        self,
        requested_distance_km: float,
        max_reachable_long_run_km: float,
        user_message: str | None = None,
    ):
        self.requested_distance_km = requested_distance_km
        self.max_reachable_long_run_km = max_reachable_long_run_km
        super().__init__(
            (
                f"Distance infeasible: requested {requested_distance_km:.1f} km, "
                f"but the long run caps at {max_reachable_long_run_km:.1f} km "
                "within the requested training window."
            ),
            user_message=user_message
            or (
                "We can't get you race-ready for that distance in the weeks "
                "you selected. Try a longer training window."
            ),
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "requested_distance_km": self.requested_distance_km,
            "max_reachable_long_run_km": self.max_reachable_long_run_km,
        }


class InvalidPlanConfigurationError(PlanGenerationError):
    """A generation parameter is outside its supported range.

    Raised for structural misconfigurations (a frequency with no composer, a
    non-positive week count) as opposed to *infeasible-but-well-formed*
    goals, which get :class:`FrequencyBudgetInfeasibleError` or
    :class:`DistanceInfeasibleError`.
    """

    def __init__(
        self,
        parameter: str,
        value: object,
        reason: str,
        user_message: str | None = None,
    ):
        self.parameter = parameter
        self.value = value
        self.reason = reason
        super().__init__(
            (f"Invalid plan configuration: {parameter}={value!r} — {reason}."),
            user_message=user_message
            or (
                "One of the plan settings isn't supported. Please adjust your "
                "inputs and try again."
            ),
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "parameter": self.parameter,
            "value": self.value,
            "reason": self.reason,
        }


class DatabaseException(RunCoachException):
    """Exception for database-related errors."""

    pass
