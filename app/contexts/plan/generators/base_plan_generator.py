"""Shared base for the VDOT/pace-based plan generators.

``PerformancePlanGenerator`` and ``FitnessPlanGenerator`` assemble a training
week the same way: schedule a long run plus quality slots, fill the remaining
days with well-spaced easy runs, pad with rest days, then overlay curated key
workouts and coaching notes. This base collects that shared machinery so the
two generators differ only in their distinct phase, mileage, and
quality-priority logic.

It also centralizes the two structural guards that keep build/peak quality
honest:

* ``_enforce_quality_caps`` bounds a formulaic quality session against the long
  run and the distance-scaled physiological caps (shared with the road
  generator and the adaptation engine via ``enforce_week_caps``), then resyncs
  segments and prose.
* ``_overlay_key_workout`` installs a named library session bounded to a
  long-run-relative ceiling, so a fixed prescription (e.g. 8x1000m) can never
  balloon past the week's long run on a low-mileage plan — the same
  ``MAX_KEY_WORKOUT_VS_LONG_RUN`` guard the road generator applies.
"""

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.workout_builder_base import (
    generate_easy_run,
    reconcile_workout_after_cap,
)
from app.core.training.key_workout_library import (
    overlay_key_workout as _overlay_key_workout_shared,
)
from app.core.training.quality_caps import enforce_week_caps
from app.core.training.tuning import MAX_KEY_WORKOUT_VS_LONG_RUN


class BasePlanGenerator:
    """Common weekly-assembly helpers for the pace/VDOT plan generators."""

    # Subclasses map their own workout-type names onto the key-workout library
    # types used for the curated overlay. Types absent from the map stay
    # formulaic (no overlay).
    LIBRARY_TYPE_MAP: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Easy-run scheduling
    # ------------------------------------------------------------------

    @staticmethod
    def _spacing_score(day: int, scheduled_days: set) -> int:
        """Prefer days with rest on both sides (avoids back-to-back runs)."""
        return (1 if (day - 1) not in scheduled_days else 0) + (
            1 if (day + 1) not in scheduled_days else 0
        )

    @staticmethod
    def _would_create_three_consecutive(day: int, scheduled: set) -> bool:
        """True if adding ``day`` would create three consecutive run days."""
        test = scheduled | {day}
        for d in range(1, 6):
            if d in test and (d + 1) in test and (d + 2) in test:
                return True
        return False

    def _fill_easy_runs(
        self,
        daily_workouts: List[Dict[str, Any]],
        zones: Dict,
        runs_per_week: int,
        remaining_km: float,
    ) -> None:
        """Place the remaining easy runs on well-spaced open weekdays (in place).

        Each easy run gets an even share of ``remaining_km`` (floored to a
        meaningful minimum relative to the long run) and is placed to avoid
        three consecutive run days when possible.
        """
        scheduled_days = {w["day"] for w in daily_workouts}
        # Prefer the well-spaced odd days, but fall back to any open day so the
        # requested run frequency can still be met when a fixed session (e.g. a
        # day-3 time trial) consumes one of the odd slots. Without the even-day
        # fallback a 6-run week could only ever place easy runs on days
        # {1,5,7} once day 3 was taken, capping the week a run short of target.
        available_days = [d for d in range(1, 8) if d not in scheduled_days]
        available_days.sort(
            key=lambda d: self._spacing_score(d, scheduled_days), reverse=True
        )

        easy_runs_needed = runs_per_week - len(daily_workouts)
        if easy_runs_needed <= 0 or remaining_km <= 0:
            return

        easy_run_km = remaining_km / easy_runs_needed
        long_runs = [w for w in daily_workouts if w["type"] == "long"]
        long_dist = long_runs[0]["distance"] if long_runs else 0
        min_easy_km = max(3.0, long_dist * 0.20) if long_dist > 0 else 3.0
        easy_run_km = max(easy_run_km, min_easy_km)

        for _ in range(easy_runs_needed):
            safe_days = [
                d
                for d in available_days
                if not self._would_create_three_consecutive(d, scheduled_days)
            ]
            if not safe_days:
                safe_days = available_days
            if not safe_days:
                break
            chosen = safe_days[0]
            workout = generate_easy_run(zones, easy_run_km)
            workout["day"] = chosen
            daily_workouts.append(workout)
            scheduled_days.add(chosen)
            available_days.remove(chosen)

    @staticmethod
    def _fill_rest_days(daily_workouts: List[Dict[str, Any]]) -> None:
        """Pad unscheduled days with rest and sort the week by day (in place)."""
        scheduled_days = {w["day"] for w in daily_workouts}
        for d in range(1, 8):
            if d not in scheduled_days:
                daily_workouts.append(
                    {
                        "day": d,
                        "type": "rest",
                        "distance": 0,
                        "description": "Rest day",
                        "intensity": "rest",
                    }
                )
        daily_workouts.sort(key=lambda x: x["day"])

    # ------------------------------------------------------------------
    # Quality structural guards
    # ------------------------------------------------------------------

    @staticmethod
    def _long_run_distance(daily_workouts: List[Dict[str, Any]]) -> float:
        """The week's long-run distance (km), or 0 when none is scheduled."""
        for w in daily_workouts:
            if w.get("type") == "long":
                return w.get("distance", 0) or 0.0
        return 0.0

    @staticmethod
    def _enforce_quality_caps(
        daily_workouts: List[Dict[str, Any]],
        target_distance: float,
        phase: str,
    ) -> None:
        """Cap formulaic quality vs the long run, then resync segments/prose.

        Key-workout overlays are skipped by ``enforce_week_caps`` (their
        distance is the prescription); the overlay's own long-run ceiling
        bounds those. This pass bounds the pre-overlay formulaic sessions so a
        single tempo/VO2max day can't approach or exceed the long run.
        """
        enforce_week_caps(daily_workouts, target_distance, phase)
        for w in daily_workouts:
            reconcile_workout_after_cap(w)

    def _overlay_key_workout(
        self,
        workout: Dict[str, Any],
        phase: str,
        target_distance: float,
        week_in_phase: int,
        vdot_zones: Optional[Dict],
        max_distance: Optional[float] = None,
    ) -> None:
        """Install a curated key workout for a quality session.

        ``max_distance`` is the long-run-relative ceiling (km) the resulting
        session may occupy. A fixed library prescription whose rebuilt steps
        would exceed it is trimmed (reps dropped) so quality work never reaches
        the long run — the guard the road generator applies but the pace/VDOT
        generators previously omitted.
        """
        library_type = self.LIBRARY_TYPE_MAP.get(workout["type"])
        if not library_type:
            return
        # Clamp the formulaic distance feeding the overlay to the ceiling first.
        # The overlay sizes its prose/steps from this value and, when some reps
        # are duration-based (not priced), floors the displayed distance back to
        # it — so a pre-overlay session above the ceiling (e.g. an uncapped
        # VO2max ladder on a low-mileage week) would otherwise survive past the
        # long run even after the step trim.
        if (
            max_distance
            and max_distance > 0
            and workout.get("distance", 0) > max_distance
        ):
            workout["distance"] = round(max_distance, 1)
        _overlay_key_workout_shared(
            workout,
            library_type,
            phase,
            target_distance=target_distance,
            week_in_phase=week_in_phase,
            pace_zones=vdot_zones,
            max_distance=max_distance,
        )

    def _key_workout_ceiling(
        self, daily_workouts: List[Dict[str, Any]]
    ) -> Optional[float]:
        """Long-run-relative ceiling (km) for a key workout, or None.

        Returns ``None`` when the week has no positive long run so the overlay
        keeps its full prescribed length rather than being trimmed against a
        zero ceiling.
        """
        long_dist = self._long_run_distance(daily_workouts)
        if long_dist <= 0:
            return None
        return long_dist * MAX_KEY_WORKOUT_VS_LONG_RUN
