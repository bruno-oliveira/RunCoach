"""Per-frequency composer registry.

Each run count (2–6) gets a dedicated class that controls workout
selection, volume distribution, and adaptation constraints.
"""

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
