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
import re
import tempfile
import time
from typing import Any, Optional

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

from app.core.training.workout_steps.metrics import _parse_pace_str_to_min_per_km

PACE_TOLERANCE_SEC = 15

# fit-tool's WorkoutStepMessage duration_time/duration_distance/custom_target_speed_*
# properties don't apply the FIT-profile sub-field scale themselves (confirmed by
# round-tripping generated files through an independent decoder, fitdecode): the
# raw bytes end up scaled by 1000 regardless of which of these fields is set, while
# the FIT spec's own scale differs per field (distance: 100, time: 1000, speed:
# 1000). These constants are the compensating factors so the bytes written match
# the spec Garmin Connect expects - not tunable knobs, don't change without
# re-verifying against fitdecode.
SPEED_SCALE = 1000
DISTANCE_SCALE = 10
TIME_SCALE = 1000

_KIND_TO_INTENSITY = {
    "warmup": Intensity.WARMUP,
    "run": Intensity.ACTIVE,
    "strides": Intensity.ACTIVE,
    "walk": Intensity.ACTIVE,
    "recovery": Intensity.RECOVERY,
    "cooldown": Intensity.COOLDOWN,
    "rest": Intensity.REST,
}

_HR_BPM_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s*bpm", re.IGNORECASE)


def _pace_min_km_to_speed_ms(pace_min_km: float) -> float:
    """Convert pace in min/km to speed in m/s."""
    if pace_min_km <= 0:
        return 0.0
    return 1000.0 / (pace_min_km * 60.0)


def _format_pace(sec_per_km: float) -> str:
    """Format seconds/km back to M:SS string."""
    return f"{int(sec_per_km // 60)}:{int(sec_per_km % 60):02d}"


def _hr_bpm_band(hr_zone_label: Optional[str]) -> Optional[tuple[int, int]]:
    """Extract a (low, high) bpm band from a label like 'Zone 2: 120-140 bpm'."""
    if not hr_zone_label:
        return None
    match = _HR_BPM_RE.search(hr_zone_label)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _expand_repeated_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand repeat>1 work/recovery step pairs into an alternating sequence.

    Step builders emit one dict per block - e.g. a "run" step with repeat=8
    immediately followed by a "recovery" step with repeat=7 or 8 - but the
    session actually alternates them (run, rest, run, rest, ..., run), not
    8 reps back-to-back followed by 8 rest periods back-to-back.
    """
    expanded: list[dict[str, Any]] = []
    i = 0
    n = len(steps)
    while i < n:
        step = steps[i]
        repeat = step.get("repeat", 1) or 1
        nxt = steps[i + 1] if i + 1 < n else None
        if (
            repeat > 1
            and nxt is not None
            and (nxt.get("repeat", 1) or 1) > 1
            and nxt.get("kind") in ("recovery", "walk")
        ):
            rec_repeat = nxt.get("repeat", 1) or 1
            for rep_idx in range(repeat):
                expanded.append(step)
                if rep_idx < rec_repeat:
                    expanded.append(nxt)
            i += 2
        else:
            expanded.extend([step] * repeat)
            i += 1
    return expanded


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

    @staticmethod
    def generate_daily_workout(
        day: dict[str, Any],
        tolerance_sec: int = PACE_TOLERANCE_SEC,
    ) -> bytes:
        """Create a FIT workout file for a single training-plan day.

        Consumes one day-dict from ``TrainingPlan.plan_data`` (the shape
        produced by ``app/core/training/workout_builders.py``). Workouts with
        a ``steps`` list (tempo/interval/hill/long/easy) become one FIT step
        per entry, each carrying a distance or time duration and, when a
        pace or HR-zone band is resolvable, a target range. Days without
        ``steps`` (recovery) become a single step for the day's distance.

        Args:
            day: One day-dict from plan_data, e.g. ``week["daily_workouts"][i]``.
            tolerance_sec: Seconds either side of target pace that triggers
                an alert, applied to every pace-targeted step.

        Returns:
            Raw FIT file bytes ready for download/import.

        Raises:
            ValueError: The day has neither steps nor a positive distance
                (i.e. it's a rest day) - there's nothing to export.
        """
        raw_steps = day.get("steps") or []
        distance_km = day.get("distance") or 0

        if not raw_steps and distance_km <= 0:
            raise ValueError("Cannot generate a FIT workout for a rest day")

        if raw_steps:
            steps = _expand_repeated_steps(raw_steps)
        else:
            steps = [
                {
                    "kind": "run",
                    "distance_m": int(round(distance_km * 1000)),
                }
            ]

        hr_band = _hr_bpm_band(day.get("hr_zone_label"))

        builder = FitFileBuilder()

        file_id = FileIdMessage()
        file_id.type = FileType.WORKOUT
        file_id.manufacturer = Manufacturer.GARMIN
        file_id.time_created = int(time.time() * 1000)
        builder.add(file_id)

        workout_name = f"{str(day.get('type', 'Run')).title()} {distance_km:.1f}km"
        workout = WorkoutMessage()
        workout.sport = Sport.RUNNING
        workout.sub_sport = SubSport.GENERIC
        workout.num_valid_steps = len(steps)
        workout.workout_name = workout_name[:16]
        builder.add(workout)

        for idx, step in enumerate(steps):
            msg = WorkoutStepMessage()
            msg.message_index = idx
            label = step.get("label")
            if label:
                msg.workout_step_name = str(label)[:16]
            kind = step.get("kind")
            msg.intensity = _KIND_TO_INTENSITY.get(
                kind if isinstance(kind, str) else "", Intensity.ACTIVE
            )

            distance_m = step.get("distance_m")
            duration_s = step.get("duration_s")
            if distance_m:
                msg.duration_type = WorkoutStepDuration.DISTANCE
                msg.duration_distance = distance_m / DISTANCE_SCALE
            elif duration_s:
                msg.duration_type = WorkoutStepDuration.TIME
                msg.duration_time = duration_s * TIME_SCALE
            else:
                msg.duration_type = WorkoutStepDuration.OPEN

            pace_min_km = _parse_pace_str_to_min_per_km(
                step.get("pace_str"), step.get("pace_zone")
            )
            if pace_min_km and pace_min_km > 0:
                target_sec = pace_min_km * 60.0
                slow_sec = target_sec + tolerance_sec
                fast_sec = max(1.0, target_sec - tolerance_sec)
                slow_ms = _pace_min_km_to_speed_ms(slow_sec / 60.0)
                fast_ms = _pace_min_km_to_speed_ms(fast_sec / 60.0)
                msg.target_type = WorkoutStepTarget.SPEED
                msg.custom_target_speed_low = slow_ms * SPEED_SCALE
                msg.custom_target_speed_high = fast_ms * SPEED_SCALE
            elif hr_band:
                msg.target_type = WorkoutStepTarget.HEART_RATE
                msg.custom_target_heart_rate_low = hr_band[0]
                msg.custom_target_heart_rate_high = hr_band[1]
            else:
                msg.target_type = WorkoutStepTarget.OPEN

            builder.add(msg)

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
