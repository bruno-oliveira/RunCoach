"""Tests for the plan-generation error taxonomy.

The diagnostic exceptions exist so callers and ops can tell *why* plan
generation failed — frequency-infeasible vs distance-infeasible vs invalid
config — instead of one generic message. These tests pin the contract:
each subclass carries its measured numbers, both in the exception fields
and in the rendered message, and ``diagnostics()`` exposes them for logs.
"""

import pytest

from app.exceptions import (
    DistanceInfeasibleError,
    FrequencyBudgetInfeasibleError,
    InvalidPlanConfigurationError,
    PlanGenerationError,
    PlanGenerationException,
)


class TestHierarchy:
    def test_subclasses_extend_plan_generation_exception(self):
        """The taxonomy plugs into the existing router/handler catch chain."""
        for cls in (
            FrequencyBudgetInfeasibleError,
            DistanceInfeasibleError,
            InvalidPlanConfigurationError,
        ):
            assert issubclass(cls, PlanGenerationError)
            assert issubclass(cls, PlanGenerationException)


class TestFrequencyBudgetInfeasibleError:
    def test_message_carries_measured_numbers(self):
        err = FrequencyBudgetInfeasibleError(
            runs_per_week=3, target_weekly_km=80.0, max_reachable_weekly_km=45.5
        )
        assert "80.0" in str(err)
        assert "3" in str(err)
        assert "45.5" in str(err)

    def test_fields_exposed(self):
        err = FrequencyBudgetInfeasibleError(
            runs_per_week=2, target_weekly_km=60.0, max_reachable_weekly_km=30.0
        )
        assert err.runs_per_week == 2
        assert err.target_weekly_km == 60.0
        assert err.max_reachable_weekly_km == 30.0

    def test_diagnostics_includes_all_fields(self):
        err = FrequencyBudgetInfeasibleError(
            runs_per_week=4, target_weekly_km=70.0, max_reachable_weekly_km=55.0
        )
        assert err.diagnostics() == {
            "runs_per_week": 4,
            "target_weekly_km": 70.0,
            "max_reachable_weekly_km": 55.0,
        }

    def test_user_message_is_runner_friendly_without_numbers(self):
        err = FrequencyBudgetInfeasibleError(3, 80.0, 45.5)
        assert err.user_message
        assert "80.0" not in err.user_message


class TestDistanceInfeasibleError:
    def test_message_carries_measured_numbers(self):
        err = DistanceInfeasibleError(
            requested_distance_km=42.2, max_reachable_long_run_km=30.0
        )
        assert "42.2" in str(err)
        assert "30.0" in str(err)

    def test_fields_exposed(self):
        err = DistanceInfeasibleError(21.1, 18.0)
        assert err.requested_distance_km == 21.1
        assert err.max_reachable_long_run_km == 18.0

    def test_diagnostics_includes_all_fields(self):
        err = DistanceInfeasibleError(42.2, 30.0)
        assert err.diagnostics() == {
            "requested_distance_km": 42.2,
            "max_reachable_long_run_km": 30.0,
        }

    def test_user_message_is_runner_friendly_without_numbers(self):
        err = DistanceInfeasibleError(42.2, 30.0)
        assert err.user_message
        assert "42.2" not in err.user_message


class TestInvalidPlanConfigurationError:
    def test_message_names_parameter_and_value(self):
        err = InvalidPlanConfigurationError(
            "max_runs_per_week", 9, "supported range is 2-6"
        )
        assert "max_runs_per_week" in str(err)
        assert "9" in str(err)
        assert "supported range is 2-6" in str(err)

    def test_fields_exposed(self):
        err = InvalidPlanConfigurationError("weeks", 0, "must be positive")
        assert err.parameter == "weeks"
        assert err.value == 0
        assert err.reason == "must be positive"

    def test_diagnostics_includes_all_fields(self):
        err = InvalidPlanConfigurationError("weeks", -1, "must be positive")
        assert err.diagnostics() == {
            "parameter": "weeks",
            "value": -1,
            "reason": "must be positive",
        }

    def test_user_message_is_runner_friendly(self):
        err = InvalidPlanConfigurationError("weeks", -1, "must be positive")
        assert err.user_message


class TestDiagnosticBaseDefaults:
    def test_base_diagnostics_is_empty(self):
        """The base carries no fields — subclasses own their measurements."""
        assert PlanGenerationError("boom").diagnostics() == {}

    def test_base_defaults_user_message_to_message(self):
        err = PlanGenerationError("boom")
        assert err.user_message == "boom"


@pytest.mark.parametrize(
    "exc",
    [
        FrequencyBudgetInfeasibleError(3, 80.0, 45.5),
        DistanceInfeasibleError(42.2, 30.0),
        InvalidPlanConfigurationError("weeks", -1, "must be positive"),
    ],
    ids=["frequency", "distance", "config"],
)
def test_all_are_catchable_as_plan_generation_error(exc):
    """One except clause can cover the whole taxonomy."""
    with pytest.raises(PlanGenerationError):
        raise exc
