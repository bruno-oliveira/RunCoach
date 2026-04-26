"""FIT workout file generation for Garmin devices with pace targets.

Uses raw encoded values to work around a fit_tool bug where sub-field
resolution incorrectly matches the wrong scale factor.

FIT Protocol Scale Factors:
- Speed: m/s * 1000 (stored as mm/s)
- Distance: m * 100 (stored as cm)
- Time: s * 1000 (stored as ms)
"""

import datetime
from typing import Any

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
from fit_tool.profile.profile_type import (
    FileType,
    Intensity,
    Manufacturer,
    Sport,
    SubSport,
    WorkoutStepDuration,
    WorkoutStepTarget,
)

SPEED_SCALE = 1000
DISTANCE_SCALE = 100
TIME_SCALE = 1000


def _pace_min_km_to_speed_raw(pace_min_km: float) -> int:
    """Convert pace in min/km to FIT raw speed value (m/s * 1000)."""
    if pace_min_km <= 0:
        return 0
    seconds_per_km = pace_min_km * 60.0
    speed_ms = 1000.0 / seconds_per_km
    return int(round(speed_ms * SPEED_SCALE))


def _set_raw_duration_distance(step: WorkoutStepMessage, meters: float) -> None:
    """Set duration distance using raw encoded value (meters * 100)."""
    field = step.get_field(2)
    field.set_encoded_value(0, int(meters * DISTANCE_SCALE))


def _set_raw_duration_time(step: WorkoutStepMessage, seconds: float) -> None:
    """Set duration time using raw encoded value (seconds * 1000)."""
    field = step.get_field(2)
    field.set_encoded_value(0, int(seconds * TIME_SCALE))


def _set_raw_target_speed(step: WorkoutStepMessage, field_id: int, speed_ms: float) -> None:
    """Set custom target speed using raw encoded value (m/s * 1000)."""
    field = step.get_field(field_id)
    field.set_encoded_value(0, int(speed_ms * SPEED_SCALE))


class FITService:
    """Generate Garmin-compatible FIT workout files with per-km pace targets."""

    @staticmethod
    def generate_race_workout(
        segments: list[dict[str, Any]],
        target_time_seconds: int,
        target_time_str: str,
        race_name: str = "RunCoach Race Plan",
    ) -> bytes:
        """Create a FIT workout file with distance-based pace targets per km.

        Each segment becomes a workout step with a distance target and
        a speed range (target +/- 5 seconds/km) so the Garmin watch shows
        ahead/behind alerts during the race.

        Structure: Warmup -> Active segments (one per km) -> Cooldown
        """
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)

        file_id = FileIdMessage()
        file_id.type = FileType.WORKOUT
        file_id.manufacturer = Manufacturer.DEVELOPMENT.value
        file_id.product = 0
        file_id.time_created = now_ms
        file_id.serial_number = 0x12345678

        total_steps = len(segments)

        workout = WorkoutMessage()
        workout.workout_name = f"{race_name} - {target_time_str}"
        workout.sport = Sport.RUNNING
        workout.sub_sport = SubSport.GENERIC
        workout.num_valid_steps = total_steps

        steps = []

        for idx, seg in enumerate(segments):
            step = WorkoutStepMessage()

            seg_distance_km = seg["end_km"] - seg["start_km"]
            seg_distance_m = seg_distance_km * 1000.0
            pace = seg["target_pace_min_km"]

            speed_low_raw = _pace_min_km_to_speed_raw(pace + (5.0 / 60.0))
            speed_high_raw = _pace_min_km_to_speed_raw(max(0.1, pace - (5.0 / 60.0)))

            km_label = f"KM {seg['start_km']:.0f}-{seg['end_km']:.0f}"
            if seg.get("grade_pct", 0) > 0.5:
                km_label += " (uphill)"
            elif seg.get("grade_pct", 0) < -0.5:
                km_label += " (downhill)"

            step.message_index = idx
            step.workout_step_name = km_label
            step.intensity = Intensity.ACTIVE
            step.duration_type = WorkoutStepDuration.DISTANCE
            _set_raw_duration_distance(step, seg_distance_m)
            step.target_type = WorkoutStepTarget.SPEED
            step.get_field(5).set_encoded_value(0, max(500, speed_low_raw))
            step.get_field(6).set_encoded_value(0, max(500, speed_high_raw))

            steps.append(step)

        builder = FitFileBuilder(auto_define=True, min_string_size=80)
        builder.add(file_id)
        builder.add(workout)
        for step in steps:
            builder.add(step)

        fit_file = builder.build()
        return fit_file.to_bytes()
