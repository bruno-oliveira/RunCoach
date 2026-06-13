"""Regression tests for calculate_quality_score.

These lock in the scoring contract that previously had no direct coverage —
in particular that hill reps are scored on effort alone (average pace on a
30 s uphill rep is physically meaningless), while pace-based types keep the
40/60 effort/pace split.
"""

from app.core.training.quality_scorer import (
    EXPECTED_EFFORT,
    calculate_quality_score,
)


class TestHillsAreEffortOnly:
    def test_on_effort_hill_scores_high_despite_meaningless_pace(self):
        # A correctly-executed hill rep: effort in the 7-8 band, but the logged
        # average pace is wildly off the planned pace (because pace on a hill is
        # not a meaningful target). It must still score as "Nailed it".
        lo, hi = EXPECTED_EFFORT["hill"]
        score, label = calculate_quality_score(
            actual_effort=(lo + hi) // 2,
            actual_pace_min_km=3.0,  # absurd vs a 6:00/km planned pace
            workout_type="hill",
            planned_pace_min_km=6.0,
        )
        assert score == 100.0
        assert label == "Nailed it"

    def test_under_effort_hill_flagged_too_easy_regardless_of_pace(self):
        score, label = calculate_quality_score(
            actual_effort=3,  # below the 7-8 hill band
            actual_pace_min_km=6.0,
            workout_type="hill",
            planned_pace_min_km=6.0,
        )
        assert label == "Too easy"
        assert score < 65

    def test_hill_score_is_independent_of_pace(self):
        # Two hills, same on-target effort, very different paces -> same score.
        a = calculate_quality_score(7, 4.0, "hill", planned_pace_min_km=6.0)
        b = calculate_quality_score(7, 8.0, "hill", planned_pace_min_km=6.0)
        assert a == b


class TestPaceTypesKeepPaceComponent:
    def test_tempo_on_target_nails_it(self):
        score, label = calculate_quality_score(
            actual_effort=6,
            actual_pace_min_km=5.0,
            workout_type="tempo",
            planned_pace_min_km=5.0,
        )
        assert score == 100.0
        assert label == "Nailed it"

    def test_tempo_right_effort_wrong_pace_is_penalised(self):
        # Effort is in-band but pace is far off -> the 60% pace component bites,
        # so a tempo (unlike a hill) cannot score 100 on a big pace miss.
        on_pace = calculate_quality_score(6, 5.0, "tempo", planned_pace_min_km=5.0)
        off_pace = calculate_quality_score(6, 7.5, "tempo", planned_pace_min_km=5.0)
        assert off_pace[0] < on_pace[0]
        assert off_pace[0] < 100.0

    def test_missing_pace_falls_back_to_neutral_not_zero(self):
        # No planned/actual pace -> pace component is neutral (half), so a
        # perfect-effort run still lands mid-range, never a false "Too hard".
        score, _ = calculate_quality_score(
            actual_effort=6,
            actual_pace_min_km=None,
            workout_type="tempo",
            planned_pace_min_km=None,
        )
        assert 30.0 <= score <= 100.0
