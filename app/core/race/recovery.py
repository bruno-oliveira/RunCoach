"""What to do after race day — the step the plan used to stop short of.

A finished plan showed stats and a "start your next plan" button, which is an
invitation to go straight from a marathon into week 1 of something else. The
guidance here is the conventional coaching rule, kept deliberately simple:

* **Easy running only for about one day per mile raced** (Jack Foster's rule,
  still the default most coaches quote): ~3 days after a 5K, ~13 after a half,
  ~26 after a marathon. Capped at four weeks — beyond that it's a rest block,
  not a recovery rule.
* **Start the next block from ~70% of peak volume**, not from the peak: the
  post-race weeks are lighter, and a new plan that opens at race-block volume
  skips the rebuild the body actually needs.

Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_KM_PER_MILE = 1.609
_MIN_EASY_DAYS = 3
_MAX_EASY_DAYS = 28
_NEXT_BLOCK_FRACTION = 0.7


@dataclass(frozen=True)
class RecoveryGuidance:
    easy_days: int
    next_base_km: Optional[int]
    line: str


def recovery_guidance(
    race_km: Optional[float], peak_week_km: Optional[float]
) -> Optional[RecoveryGuidance]:
    if not race_km or race_km <= 0:
        return None
    easy_days = int(
        max(_MIN_EASY_DAYS, min(_MAX_EASY_DAYS, round(race_km / _KM_PER_MILE)))
    )
    next_base = (
        int(round(peak_week_km * _NEXT_BLOCK_FRACTION))
        if peak_week_km and peak_week_km > 0
        else None
    )
    line = (
        f"Keep it easy for about {easy_days} days — roughly one day per mile "
        "raced — before any hard session."
    )
    if next_base:
        line += f" Start your next plan from around {next_base} km a week."
    return RecoveryGuidance(easy_days=easy_days, next_base_km=next_base, line=line)
