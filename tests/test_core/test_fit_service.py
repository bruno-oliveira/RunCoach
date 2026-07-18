"""Tests for FITService.generate_daily_workout (Garmin .fit export)."""

import tempfile

import fitdecode
import pytest

from app.infrastructure.integrations.fit_service import FITService


def _decode_steps(fit_bytes: bytes) -> list[dict]:
    steps = []
    with tempfile.NamedTemporaryFile(suffix=".fit") as tmp:
        tmp.write(fit_bytes)
        tmp.flush()
        with fitdecode.FitReader(tmp.name) as fit:
            for frame in fit:
                if (
                    isinstance(frame, fitdecode.FitDataMessage)
                    and frame.name == "workout_step"
                ):
                    steps.append({f.name: f.value for f in frame.fields})
    return steps


class TestGenerateDailyWorkoutRestDay:
    def test_rest_day_raises(self):
        day = {"day": 1, "type": "rest", "distance": 0}
        with pytest.raises(ValueError):
            FITService.generate_daily_workout(day)

    def test_zero_distance_no_steps_raises(self):
        day = {"day": 1, "type": "recovery", "distance": 0}
        with pytest.raises(ValueError):
            FITService.generate_daily_workout(day)


class TestGenerateDailyWorkoutPlainRun:
    def test_easy_run_single_step(self):
        day = {
            "day": 2,
            "type": "easy",
            "distance": 6.0,
            "hr_zone_target": 2,
            "hr_zone_label": "Zone 2 (Aerobic): 120-140 bpm",
        }
        fit_bytes = FITService.generate_daily_workout(day)

        assert fit_bytes[8:12] == b".FIT"
        steps = _decode_steps(fit_bytes)
        assert len(steps) == 1
        assert steps[0]["duration_type"] == "distance"
        assert steps[0]["duration_distance"] == pytest.approx(6000.0)
        assert steps[0]["target_type"] == "heart_rate"
        assert steps[0]["custom_target_heart_rate_low"] == 120
        assert steps[0]["custom_target_heart_rate_high"] == 140


class TestGenerateDailyWorkoutIntervals:
    def test_interval_steps_alternate_work_and_recovery(self):
        day = {
            "day": 3,
            "type": "interval",
            "distance": 8.0,
            "hr_zone_target": 4,
            "hr_zone_label": "Zone 4 (Threshold): 150-165 bpm",
            "steps": [
                {
                    "kind": "warmup",
                    "label": "Warmup",
                    "distance_m": 1500,
                    "pace_zone": "easy",
                },
                {
                    "kind": "run",
                    "label": "400m repeat",
                    "distance_m": 400,
                    "repeat": 4,
                    "pace_str": "4:30/km",
                },
                {
                    "kind": "recovery",
                    "label": "jog",
                    "duration_s": 90,
                    "repeat": 3,
                },
                {
                    "kind": "cooldown",
                    "label": "Cooldown",
                    "distance_m": 1000,
                    "pace_zone": "easy",
                },
            ],
        }
        fit_bytes = FITService.generate_daily_workout(day)
        steps = _decode_steps(fit_bytes)

        # warmup, (run, recovery) x3, run, cooldown = 9 steps, alternating
        # not two flattened blocks of 4 runs then 3 recoveries.
        assert len(steps) == 9
        kinds = [s["intensity"] for s in steps]
        assert kinds == [
            "warmup",
            "active",
            "recovery",
            "active",
            "recovery",
            "active",
            "recovery",
            "active",
            "cooldown",
        ]

        run_step = steps[1]
        assert run_step["duration_type"] == "distance"
        assert run_step["duration_distance"] == pytest.approx(400.0)
        assert run_step["target_type"] == "speed"
        assert (
            run_step["custom_target_speed_low"] < run_step["custom_target_speed_high"]
        )

        recovery_step = steps[2]
        assert recovery_step["duration_type"] == "time"
        assert recovery_step["duration_time"] == pytest.approx(90.0)
        # No pace on the recovery step, so it falls back to the HR band.
        assert recovery_step["target_type"] == "heart_rate"
        assert recovery_step["custom_target_heart_rate_low"] == 150
        assert recovery_step["custom_target_heart_rate_high"] == 165

    def test_unrecognized_step_kind_defaults_to_active_intensity(self):
        day = {
            "day": 4,
            "type": "interval",
            "distance": 5.0,
            "steps": [{"kind": "unknown_kind", "distance_m": 1000}],
        }
        fit_bytes = FITService.generate_daily_workout(day)
        steps = _decode_steps(fit_bytes)
        assert steps[0]["intensity"] == "active"
