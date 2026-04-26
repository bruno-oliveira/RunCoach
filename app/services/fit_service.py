"""FIT workout file generation for Garmin devices with pace targets."""

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


def _pace_min_km_to_speed_ms(pace_min_km: float) -> float:
    """Convert pace in min/km to speed in m/s."""
    if pace_min_km <= 0:
        return 0.0
    seconds_per_km = pace_min_km * 60.0
    return 1000.0 / seconds_per_km


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

        Each segment becomes a workout step with a 1km distance target and
        a speed range (target +/- 5 seconds/km) so the Garmin watch shows
        ahead/behind alerts during the race.
        """
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)

        file_id = FileIdMessage()
        file_id.type = FileType.WORKOUT
        file_id.manufacturer = Manufacturer.DEVELOPMENT.value
        file_id.product = 0
        file_id.time_created = now_ms
        file_id.serial_number = 0x12345678

        workout = WorkoutMessage()
        workout.workout_name = f"{race_name} - {target_time_str}"
        workout.sport = Sport.RUNNING
        workout.sub_sport = SubSport.GENERIC
        workout.num_valid_steps = len(segments)

        steps = []
        for idx, seg in enumerate(segments):
            step = WorkoutStepMessage()

            seg_distance_km = seg["end_km"] - seg["start_km"]
            seg_distance_m = seg_distance_km * 1000.0
            pace = seg["target_pace_min_km"]

            speed_low = _pace_min_km_to_speed_ms(pace + (5.0 / 60.0))
            speed_high = _pace_min_km_to_speed_ms(pace - (5.0 / 60.0))

            km_label = f"KM {seg['start_km']:.0f}-{seg['end_km']:.0f}"
            if seg.get("grade_pct", 0) > 0.5:
                km_label += " (uphill)"
            elif seg.get("grade_pct", 0) < -0.5:
                km_label += " (downhill)"

            step.message_index = idx
            step.workout_step_name = km_label
            step.intensity = Intensity.ACTIVE
            step.duration_type = WorkoutStepDuration.DISTANCE
            step.duration_distance = round(seg_distance_m, 1)
            step.duration_value = round(seg_distance_m, 1)
            step.target_type = WorkoutStepTarget.SPEED
            step.custom_target_speed_low = round(max(0.5, speed_low), 2)
            step.custom_target_speed_high = round(max(0.5, speed_high), 2)
            step.target_value = round(_pace_min_km_to_speed_ms(pace), 2)

            steps.append(step)

        builder = FitFileBuilder(auto_define=True, min_string_size=80)
        builder.add(file_id)
        builder.add(workout)
        for step in steps:
            builder.add(step)

        fit_file = builder.build()
        return fit_file.to_bytes()
