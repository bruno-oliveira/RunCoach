"""Pre-encoded triathlon training plans for Sprint, Olympic, and Half Ironman distances.

Data sourced from:
  IRONMAN/13-training-plan-sprint.md
  IRONMAN/12-training-plan-olympic.md
  IRONMAN/10-training-plan-70-3.md
"""

from app.core.generators.triathlon_plan_data import (
    HALF_IRONMAN_PLAN,
    OLYMPIC_PLAN,
    SPRINT_PLAN,
)


class TriathlonPlanGenerator:
    """Returns pre-defined week-by-week triathlon training plans."""

    DISTANCES = {
        "sprint": {
            "label": "Sprint Triathlon",
            "swim": "750m",
            "bike": "20km",
            "run": "5km",
            "weeks": 8,
        },
        "olympic": {
            "label": "Olympic Triathlon",
            "swim": "1.5km",
            "bike": "40km",
            "run": "10km",
            "weeks": 16,
        },
        "half_ironman": {
            "label": "Half Ironman (70.3)",
            "swim": "1.9km",
            "bike": "90km",
            "run": "21.1km",
            "weeks": 20,
        },
    }

    # Keep class-level aliases for backward compatibility
    _SPRINT_PLAN = SPRINT_PLAN
    _OLYMPIC_PLAN = OLYMPIC_PLAN
    _HALF_IRONMAN_PLAN = HALF_IRONMAN_PLAN

    def generate_plan(self, distance: str) -> list[dict]:
        """Return the pre-defined weekly plan for the given distance.

        Args:
            distance: One of 'sprint', 'olympic', 'half_ironman'

        Returns:
            List of weekly plan dicts.

        Raises:
            ValueError: If distance is not recognised.
        """
        if distance == "sprint":
            return list(SPRINT_PLAN)
        elif distance == "olympic":
            return list(OLYMPIC_PLAN)
        elif distance == "half_ironman":
            return list(HALF_IRONMAN_PLAN)
        else:
            raise ValueError(
                f"Unknown distance: {distance!r}. "
                "Choose from: sprint, olympic, half_ironman"
            )

    def get_distance_info(self, distance: str) -> dict:
        """Return metadata for a distance."""
        if distance not in self.DISTANCES:
            raise ValueError(f"Unknown distance: {distance!r}")
        return self.DISTANCES[distance]
