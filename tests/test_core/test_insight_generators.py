"""Branch coverage for the individual insight generator functions."""

from app.contexts.runner.fitness import insight_generators as gen
from app.contexts.runner.profile.runner_profile import RunnerProfile


def _profile(**kw) -> RunnerProfile:
    return RunnerProfile(**kw)


class TestAcwrInsight:
    def test_optimal(self):
        i = gen.acwr_insight(_profile(acwr=1.0, acwr_risk="optimal"))
        assert i.sentiment == "positive" and i.category == "recovery"

    def test_low(self):
        i = gen.acwr_insight(_profile(acwr=0.6, acwr_risk="low"))
        assert i.sentiment == "warning"

    def test_high(self):
        i = gen.acwr_insight(_profile(acwr=1.4, acwr_risk="high"))
        assert i.sentiment == "negative" and i.priority == 1

    def test_very_high(self):
        i = gen.acwr_insight(_profile(acwr=1.7, acwr_risk="very_high"))
        assert i.sentiment == "negative"


class TestVolumeInsight:
    def test_large_swings(self):
        i = gen.volume_insight(_profile(peak_weekly_km=70, avg_weekly_km=40))
        assert i.sentiment == "warning"

    def test_steady(self):
        i = gen.volume_insight(_profile(peak_weekly_km=42, avg_weekly_km=40))
        assert i.sentiment == "neutral"


class TestPolarizationInsight:
    def test_great(self):
        assert gen.polarization_insight(_profile(easy_pct=80)).sentiment == "positive"

    def test_moderate(self):
        assert gen.polarization_insight(_profile(easy_pct=65)).sentiment == "warning"

    def test_too_much_intensity(self):
        assert gen.polarization_insight(_profile(easy_pct=40)).sentiment == "negative"


class TestFitnessInsight:
    def test_improving(self):
        i = gen.fitness_insight(_profile(current_vdot=50, vdot_trend="improving"))
        assert i.sentiment == "positive"

    def test_declining(self):
        i = gen.fitness_insight(_profile(current_vdot=50, vdot_trend="declining"))
        assert i.sentiment == "warning"

    def test_stable(self):
        i = gen.fitness_insight(_profile(current_vdot=50, vdot_trend="stable"))
        assert i.sentiment == "neutral"


class TestConsistencyInsight:
    def test_strong(self):
        assert (
            gen.consistency_insight(_profile(runs_per_week=5)).sentiment == "positive"
        )

    def test_solid(self):
        assert gen.consistency_insight(_profile(runs_per_week=3)).sentiment == "neutral"

    def test_low(self):
        assert gen.consistency_insight(_profile(runs_per_week=2)).sentiment == "warning"


class TestEfficiencyInsight:
    def test_improving(self):
        assert (
            gen.efficiency_insight(_profile(efficiency_trend_pct=5)).sentiment
            == "positive"
        )

    def test_dipped(self):
        assert (
            gen.efficiency_insight(_profile(efficiency_trend_pct=-5)).sentiment
            == "warning"
        )

    def test_steady_when_none(self):
        assert (
            gen.efficiency_insight(_profile(efficiency_trend_pct=None)).sentiment
            == "neutral"
        )


class TestLongRunInsight:
    def test_dominant(self):
        i = gen.long_run_insight(_profile(longest_run_km=25, avg_weekly_km=40))
        assert i.sentiment == "warning"

    def test_balanced(self):
        i = gen.long_run_insight(_profile(longest_run_km=10, avg_weekly_km=40))
        assert i.sentiment == "positive"


class TestVarietyInsight:
    def test_no_data(self):
        assert gen.variety_insight(_profile(workout_type_counts={})).priority == 5

    def test_missing_quality(self):
        counts = {"easy": 8}
        assert gen.variety_insight(_profile(workout_type_counts=counts)).title == (
            "Missing quality sessions"
        )

    def test_heavy_quality(self):
        counts = {"easy": 5, "tempo": 3, "interval": 2}
        assert gen.variety_insight(_profile(workout_type_counts=counts)).sentiment == (
            "warning"
        )

    def test_good_mix(self):
        counts = {"easy": 9, "tempo": 1}
        assert gen.variety_insight(_profile(workout_type_counts=counts)).sentiment == (
            "positive"
        )


class TestRecoveryInsight:
    def test_plenty(self):
        assert gen.recovery_insight(_profile(rest_days_per_week=3)).sentiment == (
            "positive"
        )

    def test_reasonable(self):
        assert gen.recovery_insight(_profile(rest_days_per_week=2)).sentiment == (
            "neutral"
        )

    def test_too_few(self):
        assert gen.recovery_insight(_profile(rest_days_per_week=0.5)).sentiment == (
            "negative"
        )


class TestVolumeTrendInsight:
    def test_increasing(self):
        assert gen.volume_trend_insight(_profile(volume_trend="increasing")).title == (
            "Volume is trending up"
        )

    def test_decreasing(self):
        assert gen.volume_trend_insight(
            _profile(volume_trend="decreasing")
        ).sentiment == ("warning")


class TestRunLengthInsight:
    def test_short(self):
        assert gen.run_length_insight(_profile(avg_run_km=3)).sentiment == "warning"

    def test_long(self):
        assert gen.run_length_insight(_profile(avg_run_km=15)).sentiment == "neutral"

    def test_healthy(self):
        assert gen.run_length_insight(_profile(avg_run_km=8)).sentiment == "positive"


class TestRaceReadinessInsight:
    def test_advanced_improving(self):
        i = gen.race_readiness_insight(
            _profile(current_vdot=58, vdot_trend="improving")
        )
        assert "advanced" in i.title and i.sentiment == "positive"

    def test_intermediate_declining(self):
        i = gen.race_readiness_insight(
            _profile(current_vdot=48, vdot_trend="declining")
        )
        assert "intermediate" in i.title and i.sentiment == "neutral"

    def test_developing_stable(self):
        i = gen.race_readiness_insight(_profile(current_vdot=38, vdot_trend="stable"))
        assert "developing" in i.title

    def test_beginner(self):
        i = gen.race_readiness_insight(_profile(current_vdot=30, vdot_trend="stable"))
        assert "beginner" in i.title
