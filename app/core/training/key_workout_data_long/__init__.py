"""Marathon, trail, and backyard key workout definitions.

See key_workout_data.py for the full field documentation. Split into road,
trail, and backyard families; ``WORKOUTS_LONG`` is the combined list callers
import. Backyard sessions are catalogued but never enter the rotation — see
``_BACKYARD_ONLY_IDS`` in key_workout_library.selection.
"""

from typing import Dict, List

from app.core.training.key_workout_data_long.backyard import BACKYARD_LONG
from app.core.training.key_workout_data_long.road import ROAD_LONG
from app.core.training.key_workout_data_long.trail import TRAIL_LONG

WORKOUTS_LONG: List[Dict] = ROAD_LONG + TRAIL_LONG + BACKYARD_LONG
