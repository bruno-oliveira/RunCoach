"""Unit tests for the pure run-type inference math."""

from app.core.training.hr_zone_calculator import HRZoneCalculator
from app.core.training.workout_inference import (
    EASY,
    INTERVAL,
    MODERATE,
    RECOVERY,
    TEMPO,
    combine,
    hr_to_tier,
    pace_to_tier,
    resolve_effective_workout_type,
    splits_variability,
)

# Synthetic VDOT pace zones with clean boundaries (I < T < M < E_fast < E_slow).
PACE_ZONES = {
    "I": {"pace_min_km": 4.0},
    "T": {"pace_min_km": 4.5},
    "M": {"pace_min_km": 5.0},
    "E": {"pace_min_km_slow": 6.0, "pace_min_km_fast": 5.5},
}
HR_ZONES = HRZoneCalculator.calculate_zones(190)  # Z1 95-114 ... Z5 171-190


class TestPaceToTier:
    def test_bands(self):
        assert pace_to_tier(3.8, PACE_ZONES) == INTERVAL  # <= I
        assert pace_to_tier(4.3, PACE_ZONES) == TEMPO  # <= T
        assert pace_to_tier(4.8, PACE_ZONES) == MODERATE  # <= M
        assert pace_to_tier(5.8, PACE_ZONES) == EASY  # <= E_slow
        assert pace_to_tier(6.5, PACE_ZONES) == RECOVERY  # slower than easy

    def test_missing_inputs(self):
        assert pace_to_tier(None, PACE_ZONES) is None
        assert pace_to_tier(0, PACE_ZONES) is None
        assert pace_to_tier(5.0, None) is None
        assert pace_to_tier(5.0, {}) is None


class TestHrToTier:
    def test_zones(self):
        assert hr_to_tier(100, HR_ZONES) == RECOVERY  # Z1
        assert hr_to_tier(125, HR_ZONES) == EASY  # Z2
        assert hr_to_tier(145, HR_ZONES) == MODERATE  # Z3
        assert hr_to_tier(165, HR_ZONES) == TEMPO  # Z4
        assert hr_to_tier(180, HR_ZONES) == INTERVAL  # Z5

    def test_missing_inputs(self):
        assert hr_to_tier(None, HR_ZONES) is None
        assert hr_to_tier(150, None) is None


class TestSplitsVariability:
    def test_steady_low_cv(self):
        steady = [{"pace_min_km": 4.6 + 0.01 * i} for i in range(8)]
        cv, n = splits_variability(steady)
        assert n == 8
        assert cv < 0.05

    def test_surging_high_cv(self):
        surging = [{"pace_min_km": p} for p in [3.9, 6.2, 3.8, 6.4, 3.9, 6.0]]
        cv, n = splits_variability(surging)
        assert cv > 0.12

    def test_too_few_returns_none(self):
        assert splits_variability([{"pace_min_km": 5.0}]) == (None, 1)
        assert splits_variability(None) == (None, 0)


class TestCombine:
    def test_no_signal_returns_none(self):
        assert combine(None, None) is None

    def test_agreement_high_confidence(self):
        wt, conf = combine(TEMPO, TEMPO)
        assert wt == "tempo"
        assert conf == 0.9

    def test_disagreement_lowers_confidence(self):
        # recovery (pace) vs interval (HR): big gap -> low confidence.
        _, conf = combine(RECOVERY, INTERVAL)
        assert conf <= 0.6

    def test_single_signal_medium_confidence(self):
        wt, conf = combine(None, INTERVAL)
        assert wt == "interval"
        assert conf == 0.6

    def test_hilly_is_conservative(self):
        # Pace looks like a tempo but it's a hilly easy run; don't over-rate.
        wt, conf = combine(TEMPO, EASY, hilly=True)
        assert wt == "easy"
        assert conf == 0.5

    def test_splits_separate_tempo_from_interval(self):
        steady = combine(TEMPO, TEMPO, splits_cv=0.03)
        surging = combine(TEMPO, TEMPO, splits_cv=0.25)
        assert steady[0] == "tempo"
        assert surging[0] == "interval"

    def test_steady_hard_downgrades_interval_to_tempo(self):
        # Both signals say interval, but the splits are flat -> threshold effort.
        wt, _ = combine(INTERVAL, INTERVAL, splits_cv=0.02)
        assert wt == "tempo"

    def test_long_overrides_easy(self):
        assert combine(EASY, EASY, is_long=True)[0] == "long"
        assert combine(RECOVERY, RECOVERY, is_long=True)[0] == "long"

    def test_long_does_not_override_quality(self):
        # A long, hard session stays a quality workout, not "long".
        assert (
            combine(INTERVAL, INTERVAL, is_long=True, splits_cv=0.25)[0] == "interval"
        )

    def test_moderate_needs_hr_to_be_tempo(self):
        # Marathon-pace by pace alone reads as a brisk easy run...
        assert combine(MODERATE, EASY)[0] == "easy"
        # ...but a corroborating HR makes it a quality (tempo) effort.
        assert combine(MODERATE, TEMPO)[0] == "tempo"

    def test_perceived_effort_firms_confidence(self):
        base = combine(TEMPO, TEMPO)[1]
        bumped = combine(TEMPO, TEMPO, perceived_effort=8)[1]
        assert bumped >= base


class TestResolveEffectiveWorkoutType:
    def test_manual_explicit_wins(self):
        assert (
            resolve_effective_workout_type("recovery", "tempo", is_strava=False)
            == "recovery"
        )

    def test_manual_blank_falls_back_to_inferred(self):
        assert resolve_effective_workout_type(None, "tempo", is_strava=False) == "tempo"

    def test_strava_meaningful_tag_wins(self):
        for tag in ("race", "long", "interval"):
            assert (
                resolve_effective_workout_type(
                    tag, "easy", is_strava=True, confidence=0.9
                )
                == tag
            )

    def test_strava_easy_defers_to_confident_inference(self):
        assert (
            resolve_effective_workout_type(
                "easy", "tempo", is_strava=True, confidence=0.8
            )
            == "tempo"
        )

    def test_low_confidence_keeps_raw_tag(self):
        assert (
            resolve_effective_workout_type(
                "easy", "tempo", is_strava=True, confidence=0.3
            )
            == "easy"
        )

    def test_no_inference_keeps_raw_tag(self):
        assert resolve_effective_workout_type("easy", None, is_strava=True) == "easy"
