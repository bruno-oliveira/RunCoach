"""Per-frequency composer registry.

Each run count (2–6) gets a dedicated class that controls workout
selection, volume distribution, and adaptation constraints.
"""

from app.core.training.training_config import MIN_VIABLE_RUN_KM
from app.domain.frequency import FrequencyComposer

from .five_run import FiveRunComposer
from .four_run import FourRunComposer
from .six_run import SixRunComposer
from .three_run import ThreeRunComposer
from .two_run import TwoRunComposer

_COMPOSERS: dict[int, type] = {
    2: TwoRunComposer,
    3: ThreeRunComposer,
    4: FourRunComposer,
    5: FiveRunComposer,
    6: SixRunComposer,
}


def get_composer(frequency: int) -> FrequencyComposer:
    """Return the composer for the given runs-per-week frequency."""
    cls = _COMPOSERS.get(frequency)
    if cls is None:
        raise ValueError(f"No composer for {frequency} runs/week (supported: 2-6)")
    return cls()


# Floor on running days: a real training week still wants a long run, a quality
# session, and an easy run, so frequency is never reduced below this.
MIN_RUNNING_DAYS = 3


def viable_run_frequency(current_km: float, max_runs: int) -> int:
    """Reduce running frequency when the weekly budget can't fill every run.

    Keeps each run at or above :data:`MIN_VIABLE_RUN_KM` where possible, without
    ever dropping below :data:`MIN_RUNNING_DAYS`. Returns ``max_runs`` unchanged
    for any adequately-resourced plan. Here rather than in the generator because
    the custom-plan builder and its validation must resolve the same frequency
    the generator will: a 5-run request it lowers to 4 has a different grid.
    """
    runs = max_runs
    while runs > MIN_RUNNING_DAYS and current_km / runs < MIN_VIABLE_RUN_KM:
        runs -= 1
    return runs
