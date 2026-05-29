"""Marathon and trail key workout definitions.

See key_workout_data.py for the full field documentation. Split into road vs
trail families; ``WORKOUTS_LONG`` is the combined list callers import.
"""

from typing import Dict, List

from app.core.training.key_workout_data_long.road import ROAD_LONG
from app.core.training.key_workout_data_long.trail import TRAIL_LONG

WORKOUTS_LONG: List[Dict] = ROAD_LONG + TRAIL_LONG
