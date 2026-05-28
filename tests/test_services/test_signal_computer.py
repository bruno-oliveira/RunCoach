"""Unit tests for pure helpers in app.contexts.plan.adaptation.signal_computer.

Covers the math-only helpers that drive plan-adjustment decisions:
``_redistribute_weight`` and ``_apply_clamps``. These functions don't touch
the DB and are easy to unit-test directly, which lets us refactor the
adaptation module with more confidence.
"""

import pytest

from app.contexts.plan.adaptation import signal_computer as sc
from app.contexts.plan.adaptation.tuning import (
    HR_OVERREACH_ADHERENCE,
    HR_OVERREACH_CLAMP,
    HR_OVERREACH_DEVIATION,
    OVERREACH_EFFORT_THRESHOLD,
    OVERREACH_VOLUME_EFFORT_CLAMP,
    OVERREACH_VOLUME_RATIO,
    RACE_EFFORT_CLAMP,
    RACE_EFFORT_COUNT_THRESHOLD,
    TSB_FRESH,
    TSB_LOADED,
    TSB_OVERREACHED,
    TSB_OVERREACHED_CLAMP,
    TSB_PRIMED,
    VDOT_DECLINE_CLAMP,
)

# ----------------------------------------------------------------------------
# _redistribute_weight
# ----------------------------------------------------------------------------


def test_redistribute_weight_zeroes_dropped_and_preserves_total():
    weights = {"a": 0.4, "b": 0.4, "c": 0.2}
    sc._redistribute_weight(weights, "a")
    assert weights["a"] == 0.0
    # Total weight is conserved.
    assert weights["b"] + weights["c"] == pytest.approx(1.0)


def test_redistribute_weight_proportional_split():
    # Drop a 0.5 weight onto siblings of 0.3 and 0.2. scale = 1 + 0.5/0.5 = 2.
    weights = {"a": 0.5, "b": 0.3, "c": 0.2}
    sc._redistribute_weight(weights, "a")
    assert weights["a"] == 0.0
    assert weights["b"] == pytest.approx(0.6)
    assert weights["c"] == pytest.approx(0.4)
    # Ratio between b and c is preserved.
    assert weights["b"] / weights["c"] == pytest.approx(0.3 / 0.2)


def test_redistribute_weight_noop_when_dropped_already_zero():
    weights = {"a": 0.0, "b": 0.5, "c": 0.5}
    sc._redistribute_weight(weights, "a")
    assert weights == {"a": 0.0, "b": 0.5, "c": 0.5}


def test_redistribute_weight_sequential_inflates_compounding():
    """Sequential drops compound, matching the documented legacy behavior."""
    weights = {"a": 0.4, "b": 0.4, "c": 0.2}
    sc._redistribute_weight(weights, "a")
    # After first redistribute, b and c carry all the weight.
    first_c = weights["c"]
    sc._redistribute_weight(weights, "b")
    # b is now zero; c carries everything (compounded onto its inflated value).
    assert weights["b"] == 0.0
    assert weights["c"] > first_c


# ----------------------------------------------------------------------------
# _apply_clamps — overreach detection
# ----------------------------------------------------------------------------


def _baseline_clamp_args(**overrides):
    """Build clamp inputs that trip nothing by default."""
    defaults = {
        "raw_multiplier": 1.10,
        "volume_ratio": 1.0,
        "avg_effort": 5.0,
        "hr_extras": {"hr_zone_adherence": 1.0, "avg_abs_deviation": 0.0},
        "recent_race_effort_count": 0,
        "vdot_trend": "stable",
        "training_load": None,
        "current_phase": "build",
    }
    defaults.update(overrides)
    return defaults


def test_apply_clamps_returns_unchanged_when_no_triggers_fire():
    out, overreach, tsb_info = sc._apply_clamps(**_baseline_clamp_args())
    assert out == pytest.approx(1.10)
    assert overreach is False
    assert tsb_info["tsb"] is None
    assert tsb_info["tsb_form"] is None
    assert tsb_info["peak_primed"] is False


def test_apply_clamps_high_volume_and_effort_trips_overreach():
    args = _baseline_clamp_args(
        volume_ratio=OVERREACH_VOLUME_RATIO + 0.1,
        avg_effort=OVERREACH_EFFORT_THRESHOLD + 0.5,
    )
    out, overreach, _ = sc._apply_clamps(**args)
    assert overreach is True
    assert out <= OVERREACH_VOLUME_EFFORT_CLAMP


def test_apply_clamps_low_hr_adherence_trips_overreach():
    args = _baseline_clamp_args(
        hr_extras={
            "hr_zone_adherence": HR_OVERREACH_ADHERENCE - 0.05,
            "avg_abs_deviation": HR_OVERREACH_DEVIATION + 0.5,
        },
    )
    out, overreach, _ = sc._apply_clamps(**args)
    assert overreach is True
    assert out <= HR_OVERREACH_CLAMP


def test_apply_clamps_repeated_race_efforts_trip_overreach():
    args = _baseline_clamp_args(
        recent_race_effort_count=RACE_EFFORT_COUNT_THRESHOLD,
    )
    out, overreach, _ = sc._apply_clamps(**args)
    assert overreach is True
    assert out <= RACE_EFFORT_CLAMP


def test_apply_clamps_declining_vdot_caps_multiplier_without_overreach_flag():
    args = _baseline_clamp_args(vdot_trend="declining")
    out, overreach, _ = sc._apply_clamps(**args)
    # vdot-decline clamp is a cap, not an overreach signal.
    assert out <= VDOT_DECLINE_CLAMP
    assert overreach is False


def test_apply_clamps_uses_minimum_when_multiple_triggers_fire():
    args = _baseline_clamp_args(
        volume_ratio=OVERREACH_VOLUME_RATIO + 0.1,
        avg_effort=OVERREACH_EFFORT_THRESHOLD + 0.5,
        recent_race_effort_count=RACE_EFFORT_COUNT_THRESHOLD,
    )
    out, _, _ = sc._apply_clamps(**args)
    # Result is bounded by the strictest active clamp.
    assert out <= min(OVERREACH_VOLUME_EFFORT_CLAMP, RACE_EFFORT_CLAMP)


# ----------------------------------------------------------------------------
# _apply_clamps — TSB form classification
# ----------------------------------------------------------------------------


def _training_load(tsb: float):
    return {"available": True, "current": {"tsb": tsb, "ctl": 60.0, "atl": 50.0}}


def test_apply_clamps_overreached_tsb_clamps_and_labels():
    args = _baseline_clamp_args(training_load=_training_load(TSB_OVERREACHED - 1.0))
    out, _, tsb_info = sc._apply_clamps(**args)
    assert tsb_info["tsb_form"] == "overreached"
    assert out <= TSB_OVERREACHED_CLAMP


def test_apply_clamps_primed_only_in_peak_phase():
    args = _baseline_clamp_args(
        training_load=_training_load(TSB_PRIMED + 1.0),
        current_phase="peak",
    )
    _, _, tsb_info = sc._apply_clamps(**args)
    assert tsb_info["tsb_form"] == "primed"
    assert tsb_info["peak_primed"] is True


def test_apply_clamps_primed_tsb_outside_peak_is_fresh():
    args = _baseline_clamp_args(
        training_load=_training_load(TSB_PRIMED + 1.0),
        current_phase="build",
    )
    _, _, tsb_info = sc._apply_clamps(**args)
    assert tsb_info["tsb_form"] == "fresh"
    assert tsb_info["peak_primed"] is False


def test_apply_clamps_loaded_tsb_label():
    args = _baseline_clamp_args(training_load=_training_load(TSB_LOADED - 1.0))
    _, _, tsb_info = sc._apply_clamps(**args)
    assert tsb_info["tsb_form"] == "loaded"


def test_apply_clamps_neutral_tsb_label():
    # A value between LOADED and FRESH.
    midpoint = (TSB_LOADED + TSB_FRESH) / 2
    args = _baseline_clamp_args(training_load=_training_load(midpoint))
    _, _, tsb_info = sc._apply_clamps(**args)
    assert tsb_info["tsb_form"] == "neutral"


def test_apply_clamps_ignores_training_load_when_unavailable():
    args = _baseline_clamp_args(
        training_load={"available": False, "current": {"tsb": -100.0}},
    )
    _, _, tsb_info = sc._apply_clamps(**args)
    assert tsb_info["tsb"] is None
    assert tsb_info["tsb_form"] is None
