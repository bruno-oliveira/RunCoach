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
    quality_block_fraction,
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
HR_ZONES = HRZoneCalculator.calculate_zones(190)  # Z1 114-133 ... Z5 180-190


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
        assert hr_to_tier(120, HR_ZONES) == RECOVERY  # Z1 (114-133)
        assert hr_to_tier(140, HR_ZONES) == EASY  # Z2 (133-152)
        assert hr_to_tier(155, HR_ZONES) == MODERATE  # Z3 lower half
        assert hr_to_tier(163, HR_ZONES) == TEMPO  # Z3 upper half
        assert hr_to_tier(172, HR_ZONES) == INTERVAL  # Z4 (167-180)
        assert hr_to_tier(185, HR_ZONES) == INTERVAL  # Z5 (180-190)

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


class TestQualityBlockFraction:
    """The embedded-quality-block detector that rescues diluted tempo/interval
    sessions whose easy warm-up + cool-down drag the whole-run average down."""

    def _splits(self, paces):
        return [{"pace_min_km": p} for p in paces]

    def test_tempo_block_detected(self):
        # 2 km easy + 4 km @ T + 2 km easy: average reads easy, but the block
        # is clearly threshold.
        splits = self._splits([6.0, 6.0, 4.5, 4.5, 4.5, 4.5, 6.0, 6.0])
        fraction, tier = quality_block_fraction(splits, PACE_ZONES)
        assert tier == TEMPO
        assert fraction == 0.5

    def test_interval_block_detected(self):
        # Easy warm-up/cool-down with reps at I pace -> interval block.
        splits = self._splits([6.0, 6.0, 4.0, 6.0, 4.0, 6.0, 4.0, 6.0, 6.0])
        fraction, tier = quality_block_fraction(splits, PACE_ZONES)
        assert tier == INTERVAL

    def test_true_easy_run_no_block(self):
        # Nothing at/under marathon pace -> no quality block.
        splits = self._splits([6.0, 5.9, 6.1, 6.0, 5.95, 6.0, 6.05, 6.0])
        fraction, tier = quality_block_fraction(splits, PACE_ZONES)
        assert fraction is None and tier is None

    def test_single_quick_km_is_not_a_block(self):
        # One quickish km doesn't make a session a quality day.
        splits = self._splits([6.0, 6.0, 4.9, 6.0, 6.0, 6.0, 6.0, 6.0])
        fraction, tier = quality_block_fraction(splits, PACE_ZONES)
        assert fraction is None and tier is None

    def test_missing_inputs(self):
        assert quality_block_fraction(None, PACE_ZONES) == (None, None)
        assert quality_block_fraction([{"pace_min_km": 4.5}] * 4, None) == (None, None)
        # No marathon pace -> can't define the easy/quality boundary.
        assert quality_block_fraction([{"pace_min_km": 4.5}] * 4, {"E": {}}) == (
            None,
            None,
        )


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

    def test_embedded_tempo_block_rescues_easy_average(self):
        # Average pace+HR read easy (diluted by warm-up/cool-down), but the
        # splits expose a sustained threshold block -> classify as tempo, and
        # confident enough to displace the unreliable raw "easy" tag.
        wt, conf = combine(EASY, EASY, splits_cv=0.05, splits_quality=(0.5, TEMPO))
        assert wt == "tempo"
        assert conf >= 0.5

    def test_embedded_interval_block_rescues_easy_average(self):
        wt, _ = combine(EASY, None, splits_quality=(0.4, INTERVAL))
        assert wt == "interval"

    def test_rescue_only_lifts_never_demotes(self):
        # A genuine interval read is never pulled DOWN by a weaker block tier.
        wt, _ = combine(INTERVAL, INTERVAL, splits_quality=(0.5, TEMPO))
        assert wt == "interval"

    def test_rescue_ignored_when_no_block(self):
        # No block detected -> easy stays easy.
        assert combine(EASY, EASY, splits_quality=(None, None))[0] == "easy"

    def test_rescue_suppressed_on_hilly(self):
        # Hilly pace is unreliable; the rescue must not fire there.
        wt, _ = combine(EASY, EASY, hilly=True, splits_quality=(0.5, TEMPO))
        assert wt == "easy"

    def test_rescue_below_fraction_threshold_ignored(self):
        # A block tier present but too small a share -> not a quality day.
        assert combine(EASY, EASY, splits_quality=(0.1, TEMPO))[0] == "easy"

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
            resolve_effective_workout_type("recovery", "tempo", is_imported=False)
            == "recovery"
        )

    def test_manual_blank_falls_back_to_inferred(self):
        assert (
            resolve_effective_workout_type(None, "tempo", is_imported=False) == "tempo"
        )

    def test_meaningful_tag_wins(self):
        for tag in ("race", "long", "interval"):
            assert (
                resolve_effective_workout_type(
                    tag, "easy", is_imported=True, confidence=0.9
                )
                == tag
            )

    def test_easy_default_defers_to_confident_inference(self):
        assert (
            resolve_effective_workout_type(
                "easy", "tempo", is_imported=True, confidence=0.8
            )
            == "tempo"
        )

    def test_low_confidence_keeps_raw_tag(self):
        assert (
            resolve_effective_workout_type(
                "easy", "tempo", is_imported=True, confidence=0.3
            )
            == "easy"
        )

    def test_no_inference_keeps_raw_tag(self):
        assert resolve_effective_workout_type("easy", None, is_imported=True) == "easy"
