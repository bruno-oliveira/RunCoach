"""FIT workout file generation for Garmin devices with pace targets.

Uses the official Garmin FIT Python SDK to encode FIT binary files
that are fully compatible with Garmin watches and Garmin Connect.

FIT Protocol Scale Factors:
- Speed: m/s * 1000 (stored as mm/s in custom_target_value_low/high)
- Distance: m * 100 (stored as cm in duration_value)

Import Instructions:
- Garmin Connect Web: Training > Workouts > Import > Select .fit file
- Garmin Connect Mobile: Training & Planning > Workouts > Import
- USB Transfer: Copy to GARMIN/NewFiles/ on device (some devices support this)

Note: Workout files must be imported through Garmin Connect or supported devices.
Not all Garmin devices support direct workout file imports.
"""

import datetime
from typing import Any

from garmin_fit_sdk import Encoder, Profile
from garmin_fit_sdk.util import convert_datetime_to_timestamp

SPEED_SCALE = 1000
DISTANCE_SCALE = 100


def _pace_min_km_to_speed_ms(pace_min_km: float) -> float:
    """Convert pace in min/km to speed in m/s."""
    if pace_min_km <= 0:
        return 0.0
    return 1000.0 / (pace_min_km * 60.0)


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

        Args:
            segments: List of segment dicts with start_km, end_km, target_pace_min_km, grade_pct.
            target_time_seconds: Total target time in seconds.
            target_time_str: Human-readable target time string (e.g., "1:30:00").
            race_name: Name of the race/plan.

        Returns:
            Raw FIT file bytes ready for download/import.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        time_created = convert_datetime_to_timestamp(now)

        encoder = Encoder()

        encoder.write_mesg({
            "mesg_num": Profile["mesg_num"]["FILE_ID"],
            "type": "workout",
            "manufacturer": "development",
            "product": 0,
            "time_created": time_created,
            "serial_number": 0x12345678,
        })

        workout_name = f"{race_name} - {target_time_str}"
        workout_description = f"Paced race plan for {target_time_str} target time"

        encoder.write_mesg({
            "mesg_num": Profile["mesg_num"]["WORKOUT"],
            "message_index": 0,
            "sport": "running",
            "sub_sport": "generic",
            "num_valid_steps": len(segments),
            "wkt_name": workout_name,
            "wkt_description": workout_description,
        })

        for idx, seg in enumerate(segments):
            seg_distance_m = (seg["end_km"] - seg["start_km"]) * 1000.0
            pace = seg["target_pace_min_km"]

            speed_low_ms = _pace_min_km_to_speed_ms(pace + (5.0 / 60.0))
            speed_high_ms = _pace_min_km_to_speed_ms(max(0.1, pace - (5.0 / 60.0)))

            km_label = f"KM {seg['start_km']:.0f}-{seg['end_km']:.0f}"
            if seg.get("grade_pct", 0) > 0.5:
                km_label += " (uphill)"
            elif seg.get("grade_pct", 0) < -0.5:
                km_label += " (downhill)"

            encoder.write_mesg({
                "mesg_num": Profile["mesg_num"]["WORKOUT_STEP"],
                "message_index": idx,
                "wkt_step_name": km_label,
                "duration_type": "distance",
                "duration_value": int(seg_distance_m * DISTANCE_SCALE),
                "target_type": "speed",
                "custom_target_value_low": max(500, int(speed_low_ms * SPEED_SCALE)),
                "custom_target_value_high": max(500, int(speed_high_ms * SPEED_SCALE)),
                "intensity": "active",
            })

        return bytes(encoder.close())
