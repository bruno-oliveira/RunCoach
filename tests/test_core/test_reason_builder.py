"""Tests for the headline-reason builder used by plan adjustments.

These tests exercise the branching inside ``build_headline_reason`` plus
the ``compute_net_delta_km`` helper. Pure — no DB, no fixtures.
"""

from app.contexts.plan.adaptation.reason_builder import (
    build_headline_reason,
    compute_net_delta_km,
)


def _base_signals(**overrides):
    """Minimal signals dict that produces a valid headline."""
    signals = {
        "volume_ratio": 1.0,
        "completion_rate": 0.9,
        "avg_effort": 6.0,
        "effort_trend": "stable",
        "overreach_detected": False,
        "current_phase": "build",
        "phase_weights": {"volume": 0.4, "effort": 0.3, "completion": 0.3},
    }
    signals.update(overrides)
    return signals


def _build(**overrides):
    kwargs = {
        "signals": _base_signals(),
        "vdot_result": None,
        "net_delta_km": 0.0,
        "multiplier": 1.0,
        "in_progress": False,
        "current_week": 4,
        "has_adjustable_weeks": True,
    }
    kwargs.update(overrides)
    if "signals" in overrides and isinstance(overrides["signals"], dict):
        # Allow tests to pass a partial override for signals.
        merged = _base_signals()
        merged.update(overrides["signals"])
        kwargs["signals"] = merged
    return build_headline_reason(**kwargs)


# --- compute_net_delta_km --------------------------------------------------


def test_net_delta_empty_snapshots_returns_zero():
    assert compute_net_delta_km({}, {}) == 0.0


def test_net_delta_only_before_returns_negative_sum():
    before = {"a": {"distance_km": 5.0}, "b": {"distance_km": 3.0}}
    assert compute_net_delta_km(before, {}) == -8.0


def test_net_delta_only_after_returns_positive_sum():
    after = {"a": {"distance_km": 5.0}, "b": {"distance_km": 3.0}}
    assert compute_net_delta_km({}, after) == 8.0


def test_net_delta_rounds_to_one_decimal():
    before = {"a": {"distance_km": 1.234}}
    after = {"a": {"distance_km": 2.567}}
    assert compute_net_delta_km(before, after) == 1.3


def test_net_delta_handles_disjoint_ids():
    before = {"a": {"distance_km": 5.0}}
    after = {"b": {"distance_km": 7.0}}
    assert compute_net_delta_km(before, after) == 2.0


# --- verb selection from net_delta_km --------------------------------------


def test_net_delta_positive_uses_increased_verb():
    headline = _build(net_delta_km=0.5)
    assert "Remaining workouts increased" in headline


def test_net_delta_negative_uses_reduced_verb():
    headline = _build(net_delta_km=-0.5)
    assert "Remaining workouts reduced" in headline


def test_net_delta_zero_uses_kept_verb():
    headline = _build(net_delta_km=0.0)
    assert "Remaining workouts kept" in headline


def test_net_delta_within_threshold_uses_kept_verb():
    # Threshold is ±0.05 — 0.03 should still read as "kept".
    headline = _build(net_delta_km=0.03)
    assert "Remaining workouts kept" in headline


# --- untested signal branches ----------------------------------------------


def test_overreach_detected_appends_clamp_phrase():
    headline = _build(signals={"overreach_detected": True})
    assert "Overreach detected — forced reduction to protect recovery." in headline


def test_overreach_false_omits_clamp_phrase():
    headline = _build(signals={"overreach_detected": False})
    assert "Overreach detected" not in headline


def test_vdot_declining_appends_capping_phrase():
    headline = _build(signals={"vdot_trend": "declining"})
    assert "VDOT declining — capping volume to prevent overtraining." in headline


def test_vdot_stable_omits_capping_phrase():
    headline = _build(signals={"vdot_trend": "stable"})
    assert "VDOT declining" not in headline


def test_tsb_form_appends_form_and_tsb():
    headline = _build(signals={"tsb_form": "fresh", "tsb": 12.5})
    assert "Form: fresh (TSB 12.5)." in headline


def test_tsb_form_none_omits_form_phrase():
    headline = _build()
    assert "Form:" not in headline


def test_vdot_result_appends_recalibration_arrow():
    vdot_result = {"old_vdot": 45, "new_vdot": 47, "direction": "up"}
    headline = _build(vdot_result=vdot_result)
    assert "VDOT recalibrated: 45 → 47 (up)." in headline


def test_vdot_result_none_omits_recalibration_phrase():
    headline = _build(vdot_result=None)
    assert "VDOT recalibrated" not in headline


def test_hr_zone_adherence_appends_percentage_and_trend():
    headline = _build(signals={"hr_zone_adherence": 0.83, "hr_zone_trend": "improving"})
    assert "HR zone adherence: 83% (trend: improving)." in headline


def test_hr_zone_adherence_missing_trend_uses_unknown():
    headline = _build(signals={"hr_zone_adherence": 0.5})
    assert "HR zone adherence: 50% (trend: unknown)." in headline


def test_hr_zone_adherence_none_omits_phrase():
    headline = _build()
    assert "HR zone adherence" not in headline


def test_warning_ratio_positive_appends_feedback_warnings():
    headline = _build(signals={"warning_ratio": 0.25})
    assert "Feedback warnings: 25% of runs." in headline


def test_warning_ratio_zero_omits_feedback_warnings():
    headline = _build(signals={"warning_ratio": 0.0})
    assert "Feedback warnings" not in headline


def test_warning_ratio_none_omits_feedback_warnings():
    headline = _build()
    assert "Feedback warnings" not in headline


def test_mountain_simulation_score_appends_score_and_factor():
    headline = _build(
        signals={
            "mountain_simulation_score": 72,
            "mountain_simulation_factor": 0.95,
        }
    )
    assert "Mountain simulation score: 72/100 (factor x0.95)." in headline


def test_mountain_simulation_score_default_factor_when_missing():
    headline = _build(signals={"mountain_simulation_score": 40})
    assert "Mountain simulation score: 40/100 (factor x1.0)." in headline


def test_mountain_simulation_score_none_omits_phrase():
    headline = _build()
    assert "Mountain simulation score" not in headline


def test_avg_effort_none_omits_effort_phrase():
    headline = _build(signals={"avg_effort": None})
    assert "Avg effort" not in headline


def test_avg_effort_present_appends_effort_and_trend():
    headline = _build(signals={"avg_effort": 7.4, "effort_trend": "rising"})
    assert "Avg effort: 7.4/10 (trend: rising)." in headline


# --- in-progress prefix ----------------------------------------------------


def test_in_progress_with_adjustable_weeks_inserts_current_week_prefix():
    headline = _build(in_progress=True, current_week=3, has_adjustable_weeks=True)
    assert headline.startswith(
        "Current week 3 left in place — adjustments apply from week 4."
    )


def test_in_progress_but_no_adjustable_weeks_omits_prefix():
    headline = _build(in_progress=True, current_week=3, has_adjustable_weeks=False)
    assert "Current week 3 left in place" not in headline


def test_not_in_progress_omits_prefix():
    headline = _build(in_progress=False, current_week=3, has_adjustable_weeks=True)
    assert "Current week 3 left in place" not in headline


# --- phase weights (always present) ---------------------------------------


def test_phase_and_weights_always_appear():
    headline = _build(
        signals={
            "current_phase": "peak",
            "phase_weights": {"volume": 0.5, "effort": 0.3, "completion": 0.2},
        }
    )
    assert "Phase: peak (weights: V=50% E=30% C=20%)." in headline


def test_phase_defaults_when_missing():
    signals = _base_signals()
    signals.pop("current_phase")
    signals.pop("phase_weights")
    headline = build_headline_reason(
        signals=signals,
        vdot_result=None,
        net_delta_km=0.0,
        multiplier=1.0,
        in_progress=False,
        current_week=1,
        has_adjustable_weeks=True,
    )
    assert "Phase: build (weights: V=0% E=0% C=0%)." in headline


# --- volume / completion summary line --------------------------------------


def test_volume_and_completion_appear_with_rounding():
    headline = _build(
        signals={"volume_ratio": 1.234, "completion_rate": 0.876},
    )
    assert "Volume ratio: 1.23, completion: 88%." in headline


def test_headline_starts_with_remaining_workouts_when_no_prefix():
    headline = _build(multiplier=0.95, net_delta_km=-2.0)
    assert headline.startswith("Remaining workouts reduced (x0.95).")
