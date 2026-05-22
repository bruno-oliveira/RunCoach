"""FIT workout file generation for Garmin devices with pace targets.

Uses the fit-tool library to generate FIT binary files that are fully
compatible with Garmin watches and Garmin Connect.

Each km becomes a workout step with a pace alert range. The watch will
beep if you go outside the pace band for that km, giving real-time
pacing feedback during your race.

Import Instructions:
- Garmin Connect Web: Training > Workouts > Import > Select .fit file
- Garmin Connect Mobile: Training & Planning > Workouts > Import
- USB Transfer: Copy to GARMIN/NewFiles/ on device (some devices support this)

Note: Workout files must be imported through Garmin Connect or supported devices.
Not all Garmin devices support direct workout file imports.
"""

import os
import tempfile
import time
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

PACE_TOLERANCE_SEC = 15

SPEED_SCALE = 1000
DISTANCE_SCALE = 10


def _pace_min_km_to_speed_ms(pace_min_km: float) -> float:
    """Convert pace in min/km to speed in m/s."""
    if pace_min_km <= 0:
        return 0.0
    return 1000.0 / (pace_min_km * 60.0)


def _format_pace(sec_per_km: float) -> str:
    """Format seconds/km back to M:SS string."""
    return f"{int(sec_per_km // 60)}:{int(sec_per_km % 60):02d}"


class FITService:
    """Generate Garmin-compatible FIT workout files with per-km pace targets."""

    @staticmethod
    def generate_race_workout(
        segments: list[dict[str, Any]],
        target_time_seconds: int,
        target_time_str: str,
        race_name: str = "RunCoach Race Plan",
        tolerance_sec: int = PACE_TOLERANCE_SEC,
    ) -> bytes:
        """Create a FIT workout file with distance-based pace targets per km.

        Args:
            segments: List of segment dicts with start_km, end_km, target_pace_min_km, grade_pct.
            target_time_seconds: Total target time in seconds.
            target_time_str: Human-readable target time string (e.g., "1:30:00").
            race_name: Name of the race/plan.
            tolerance_sec: Seconds either side of target pace that triggers an alert.

        Returns:
            Raw FIT file bytes ready for download/import.
        """
        builder = FitFileBuilder()

        file_id = FileIdMessage()
        file_id.type = FileType.WORKOUT
        file_id.manufacturer = Manufacturer.GARMIN
        file_id.time_created = int(time.time() * 1000)
        builder.add(file_id)

        workout = WorkoutMessage()
        workout.sport = Sport.RUNNING
        workout.sub_sport = SubSport.GENERIC
        workout.num_valid_steps = len(segments)
        workout.workout_name = race_name[:16]
        builder.add(workout)

        for idx, seg in enumerate(segments):
            pace = seg["target_pace_min_km"]
            target_sec = pace * 60.0
            slow_sec = target_sec + tolerance_sec
            fast_sec = max(1.0, target_sec - tolerance_sec)

            slow_ms = _pace_min_km_to_speed_ms(slow_sec / 60.0)
            fast_ms = _pace_min_km_to_speed_ms(fast_sec / 60.0)

            km_label = f"KM {seg['start_km']:.0f}-{seg['end_km']:.0f}"
            if seg.get("grade_pct", 0) > 0.5:
                km_label += " (uphill)"
            elif seg.get("grade_pct", 0) < -0.5:
                km_label += " (downhill)"

            step = WorkoutStepMessage()
            step.message_index = idx
            step.workout_step_name = km_label
            step.intensity = Intensity.ACTIVE
            step.duration_type = WorkoutStepDuration.DISTANCE
            step.duration_distance = 1000.0 / DISTANCE_SCALE
            step.target_type = WorkoutStepTarget.SPEED
            step.custom_target_speed_low = slow_ms * SPEED_SCALE
            step.custom_target_speed_high = fast_ms * SPEED_SCALE
            builder.add(step)

        fit_file = builder.build()

        with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            fit_file.to_file(tmp_path)
            with open(tmp_path, "rb") as f:
                fit_bytes = f.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        return fit_bytes
