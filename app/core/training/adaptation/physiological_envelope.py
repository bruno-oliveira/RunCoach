"""Physiological volume envelope for race training plans.

What a runner can sensibly do at a given race distance and training frequency,
held in one place so the generator and its tests calibrate against the same
numbers instead of each carrying their own.

**Scope.** These are bands for *recreational* runners — the product's stated
scope ("suitable for recreational runners who want to finish strong", see
``mileage_progression.get_ideal_peak``). They are not elite prescriptions.

**Provenance.** Peak-week bands and long-run distances are compiled from
published coaching guidance and from real plan breakdowns:

* ``trainingplan.dev`` and ``puretriathlon`` peak-week ranges by goal race;
* Runna's own guidance that a half-marathon long run builds to ~75-80 % of race
  distance, and reviewer breakdowns of a 4-run marathon plan peaking with a
  ~32 km long run and ~55-75 km weeks for a mid-pack runner;
* the structure of a 4-run week: the *4-day ceiling is structural, not a
  fitness limit* — past ~45-50 mi (72-80 km) the advice is to add a training
  day rather than stretch individual runs, because the binding constraint is
  the per-run cap (~12-13 mi / 19-21 km), which drives impact injury more than
  weekly total does;
* Runna's model that "increasing your allowed run days or raising your ability
  level unlocks higher mileage bounds".

They are guidance, not peer-reviewed consensus: treat a breach as a prompt to
look, and an in-band value as no proof of safety.

**Purity.** This module is data and arithmetic only — no I/O, no ORM, no
imports from ``contexts``/``infrastructure`` — so ``pyright`` type-checks it
(see ``pyrightconfig.json``) and both the generator and the test suite can
import it.
"""

from typing import Dict, Tuple

# --- The reference bands ----------------------------------------------------

# Peak *weekly volume* band, km, for a 4-run plan (`FREQUENCY_VOLUME_FACTORS`
# scales it away from that reference frequency).
#
# The ultra entries matter as much as the road ones: without them
# ``_interpolate`` clamped every race beyond the marathon to the marathon's own
# band, so a 100 km plan was judged against a 42.2 km plan's ceiling and the
# audit could not see ultra over-prescription at all. They continue the road
# gradient rather than jumping, and stay under
# ``trail_profile.trail_max_weekly_mileage`` (the soft upper bound the app
# itself warns on), so an in-band plan is also one the app is willing to serve.
PEAK_WEEK_KM: Dict[float, Tuple[float, float]] = {
    5.0: (24.0, 48.0),
    10.0: (40.0, 64.0),
    21.1: (48.0, 80.0),
    42.2: (55.0, 80.0),
    50.0: (62.0, 95.0),
    80.0: (72.0, 110.0),
    100.0: (78.0, 118.0),
    163.0: (88.0, 145.0),
}

# Peak *single long run* band, km. The upper bound is what a well-adapted
# recreational runner reaches; the app's own tiered contract lives in
# ``tuning.ROAD_LONG_RUN_CAPS`` and ``training_constants._TRAIL_HARD_CEILINGS``,
# and is authoritative for what a plan may prescribe when the two disagree — as
# they did for ultras, where this table stopped at the marathon's 32 km while
# the engine was already clamped to 38/42. The ultra entries below are set at or
# above those ceilings so the reference and the contract agree.
PEAK_LONG_RUN_KM: Dict[float, Tuple[float, float]] = {
    5.0: (8.0, 12.0),
    10.0: (12.0, 17.0),
    21.1: (16.0, 19.0),
    42.2: (30.0, 32.0),
    50.0: (32.0, 38.0),
    80.0: (34.0, 42.0),
    100.0: (35.0, 42.0),
    163.0: (38.0, 46.0),
}

# Long run as a share of its own week. Guidance clusters on 25-35 %; the floor
# relaxes at very low weekly totals (where a single long run is necessarily a
# big slice).
LONG_RUN_SHARE_LO = 0.20

# Frequency scaling around the 4-run reference point: a 4-day week is the
# reference (factor 1.0), 5-6 days genuinely unlocks more volume, and 2-3 days
# carries less because the same volume has to fit into fewer, capped runs.
FREQUENCY_VOLUME_FACTORS: Dict[int, float] = {
    2: 0.72,
    3: 0.88,
    4: 1.0,
    5: 1.15,
    6: 1.30,
}

# A single easy run is capped around 12-13 mi (19-21 km) even for well-adapted
# runners: per-run distance drives bone-stress and tendon injury faster than
# weekly volume does.
PER_RUN_EASY_CAP_KM = 21.0

# Below this a run is not a training dose at all. The walk/run sessions of a
# genuine couch-to-5K plan are the one legitimate exception.
MIN_VIABLE_RUN_KM = 2.0


def peak_week_band(distance_km: float, max_runs: int) -> Tuple[float, float]:
    """Peak-week volume band for a race distance at a training frequency.

    Falls back to linear interpolation between the nearest known distances and
    to the reference factor for an unknown frequency, so a new race distance or
    run count produces a usable band rather than a ``KeyError``.
    """
    lo, hi = _interpolate(PEAK_WEEK_KM, distance_km)
    factor = FREQUENCY_VOLUME_FACTORS.get(max_runs, 1.0)
    return (lo * factor, hi * factor)


def peak_long_run_band(distance_km: float) -> Tuple[float, float]:
    """Peak single-long-run band for a race distance."""
    return _interpolate(PEAK_LONG_RUN_KM, distance_km)


def long_run_share_ceiling(max_runs: int) -> float:
    """Ceiling on a long run's share of its own week for a training frequency.

    This is a *frequency-aware* ceiling, not the published 25-35 % band. That
    band assumes enough runs to spread a week across; a 2-run week has nowhere
    else for the volume to live, and a plan that honoured 35 % there would have
    to drop the volume entirely rather than put it in the long run. So the
    ceiling sits at the point where the week stops being a week and becomes one
    session plus filler: 0.65 at 2 runs, 0.55 above.

    The 2-run value sits above the 0.60 it used to be because the single
    quality partner on such a week is physiologically capped (Daniels work
    shares, per-distance caps): holding 0.60 strictly held the *pair* to ~83 %
    of the weekly target on every build/peak week — a permanent shortfall no
    amount of layout work could close. At 0.65 the long run plus its capped
    partner can reach the target while the week still reads as one anchor run
    plus one supporting session.

    The retired ``LONG_RUN_SHARE_HI = 0.35`` constant used to sit next to this
    and claim the published band was enforced here. It never was — nothing read
    it — so the module advertised a stricter bound than it applied.
    """
    if max_runs <= 2:
        return 0.65
    return 0.55


def in_peak_week_band(distance_km: float, max_runs: int, peak_km: float) -> bool:
    """Whether ``peak_km`` sits inside the band (inclusive, 0.05 km slack)."""
    lo, hi = peak_week_band(distance_km, max_runs)
    return lo - 0.05 <= peak_km <= hi + 0.05


def _interpolate(
    table: Dict[float, Tuple[float, float]], key: float
) -> Tuple[float, float]:
    """Nearest-band lookup with linear interpolation between known distances."""
    if key in table:
        return table[key]
    keys = sorted(table)
    if key <= keys[0]:
        return table[keys[0]]
    if key >= keys[-1]:
        return table[keys[-1]]
    lower = max(k for k in keys if k < key)
    upper = min(k for k in keys if k > key)
    weight = (key - lower) / (upper - lower)
    lo_a, hi_a = table[lower]
    lo_b, hi_b = table[upper]
    return (lo_a + (lo_b - lo_a) * weight, hi_a + (hi_b - hi_a) * weight)
