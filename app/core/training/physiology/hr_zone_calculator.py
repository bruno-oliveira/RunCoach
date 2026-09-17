"""Heart rate zone calculator.

Pure training-zone math — no database or ORM dependencies.
Computes a 5-zone HR model from max heart rate and provides
zone classification and workout-level zone prescriptions.
"""

from typing import Optional

# Minimum recorded max HR to trust (lower likely a sensor error)
MIN_RELIABLE_MAX_HR = 140

# Maximum recorded max HR to trust (higher is almost certainly an optical
# sensor spike / cadence lock, not a human heart)
MAX_RELIABLE_MAX_HR = 225

# A top reading more than this many BPM above the *second-highest* run max
# is treated as an uncorroborated spike and discarded in favour of the
# corroborated value (optical sensors routinely glitch 15-30 BPM high).
MAX_HR_SPIKE_TOLERANCE_BPM = 8

# Conservative universal default when no age or run data is available
DEFAULT_MAX_HR = 190

# Plausible resting-HR band. Below ~30 is almost certainly noise; above ~100 is
# not a true resting value (likely an easy-run average mislabelled as resting).
MIN_RELIABLE_RESTING_HR = 30
MAX_RELIABLE_RESTING_HR = 100

# Lactate-threshold HR is plausible only as a fraction of max within this band.
# Below ~70% it's not a threshold (more like easy-run HR mislabelled); above
# ~95% it's a VO2max/peak reading, not a sustainable threshold. The same band
# clamps a measured-or-derived LTHR before it anchors the zones, so a noisy
# estimate can never place the threshold somewhere physiologically impossible.
MIN_LTHR_FRACTION_OF_MAX = 0.70
MAX_LTHR_FRACTION_OF_MAX = 0.92

# When no LTHR is measured we derive one from max HR at this fraction. 88% of max
# is the population-average lactate threshold for runners, and it makes the
# LTHR-anchored model fall back to (essentially) the historical %max bands so a
# data-less runner sees no regression.
DEFAULT_LTHR_FRACTION_OF_MAX = 0.88

# No zone may be narrower than this after the bands are built. A safety net: the
# %LTHR partition is monotonic by construction, but capping the top band at max
# HR (or an extreme clamped anchor) could otherwise leave a sliver of a zone.
MIN_ZONE_WIDTH_BPM = 3

# Version of the zone model below. Bump when ZONE_DEFINITIONS changes -- or when
# the zone *math* changes (e.g. %max HR -> Heart Rate Reserve -> %LTHR anchoring,
# or attaching the data-calibrated pace each zone maps to) -- so plans carrying
# zones from an older model are recomputed on next view. v8: the LTHR estimate
# switched from a circular tempo-run HR median to a non-circular pace<->HR-at-
# threshold derivation, moving the anchor for runners without a manual/synced
# threshold.
HR_ZONES_VERSION = 8


# -- Zone definitions (percentage of max HR) ----------------------------------

# Running-specific 5-zone model. The Zone 3/4 boundary is the runner's lactate
# threshold (LTHR), so each band is expressed as a fraction *of LTHR* (Friel's
# running-zone method) -- the most reliable anchor for runners, whose zones
# track threshold far better than a flat %max HR. The top of Zone 5 is capped at
# max HR.
#
# `lthr_min` / `lthr_max` are the band edges as fractions of LTHR; `lthr_max`
# is None for the top zone, which is capped at max HR. The `pct_min` / `pct_max`
# (% of max HR) are kept as a reference vocabulary: they are the SAME bands the
# pace-zone table annotates (zone_calculator.py via TRAINING_ZONE_HR_PERCENTAGES)
# so "Zone 3 - Tempo" means one thing everywhere -- the personal HR-zones panel,
# each workout's BPM badge, and the adaptation engine's zone-adherence signal.
#
# The %LTHR fractions are chosen so that when LTHR sits at the population-average
# 88% of max, the BPM bands reproduce the previous %max model (Z1 60-70%, Z2
# 70-80%, Z3 80-88%, Z4 88-95%, Z5 95-100%). A *measured* LTHR then slides every
# band onto the runner's real physiology while keeping each band a sane width --
# fixing the prior model, where Karvonen (from an unreliable resting-HR estimate)
# compounded with a separate LTHR re-anchor and collapsed Zones 1-3 to 1-2 BPM.
#
# Why these zone numbers: easy runs prescribed below ~68% of LTHR are below most
# runners' slowest sustainable running HR, and a correctly run VO2max session
# averages ~Zone 4 once recoveries are included -- Zone 5 is a classification
# band no whole run can average, never a session target.
ZONE_DEFINITIONS = [
    {
        "zone": 1,
        "name": "Recovery",
        "pct_min": 0.60,
        "pct_max": 0.70,
        "lthr_min": 0.682,
        "lthr_max": 0.795,
        "description": "Very light effort. Active recovery, warm-up, cool-down.",
    },
    {
        "zone": 2,
        "name": "Aerobic",
        "pct_min": 0.70,
        "pct_max": 0.80,
        "lthr_min": 0.795,
        "lthr_max": 0.909,
        "description": "Conversational pace. Builds aerobic base and endurance.",
    },
    {
        "zone": 3,
        "name": "Tempo",
        "pct_min": 0.80,
        "pct_max": 0.88,
        "lthr_min": 0.909,
        "lthr_max": 1.000,
        "description": "Comfortably hard. Threshold effort - improves lactate clearance and stamina.",
    },
    {
        "zone": 4,
        "name": "VO2max",
        "pct_min": 0.88,
        "pct_max": 0.95,
        "lthr_min": 1.000,
        "lthr_max": 1.079,
        "description": "Hard effort. 3-5 minute intervals that develop peak oxygen uptake.",
    },
    {
        "zone": 5,
        "name": "Speed",
        "pct_min": 0.95,
        "pct_max": 1.00,
        "lthr_min": 1.079,
        "lthr_max": None,
        "description": "Near-maximum effort. Short fast reps - only touched briefly within a session.",
    },
]

# HR percentage bands used by the pace-anchored training-zone display
# (see `zone_calculator.py`). Derived from ZONE_DEFINITIONS so the two
# vocabularies can never diverge again.
_ZONE_SLUGS = [
    "zone_1_recovery",
    "zone_2_aerobic",
    "zone_3_tempo",
    "zone_4_vo2max",
    "zone_5_race",
]
TRAINING_ZONE_HR_PERCENTAGES: dict[str, tuple[float, float]] = {
    slug: (defn["pct_min"], defn["pct_max"])
    for slug, defn in zip(_ZONE_SLUGS, ZONE_DEFINITIONS)
}


# Maps workout_type -> target HR zone number (1-5).
#
# Targets are what the *average* HR of a well-executed session should land
# on (that is what the adaptation engine compares against), not the peak of
# the hardest rep. Hence interval/VO2max sessions target zone 4 - including
# their recovery jogs, a correctly run VO2max session averages ~88-93% of
# max - and zone 5 is reserved as a classification band, not a session
# target a whole run could ever average.
WORKOUT_ZONE_MAP: dict[str, int] = {
    "easy": 2,
    "recovery": 1,
    "long": 2,
    "tempo": 3,
    "cruise_interval": 3,
    "race_pace": 3,
    "fartlek": 3,
    "interval": 4,
    "hill": 4,
    "vo2max": 4,
    "vo2max_ladder": 4,
    "time_trial": 4,
    "rest": 1,
}


def _resting_hr_is_usable(max_hr: int, resting_hr: object) -> bool:
    """True when ``resting_hr`` is a plausible value below ``max_hr``."""
    if not isinstance(resting_hr, (int, float)):
        return False
    return (
        MIN_RELIABLE_RESTING_HR <= resting_hr <= MAX_RELIABLE_RESTING_HR
        and resting_hr < max_hr
    )


def _lthr_is_usable(max_hr: int, lthr: object) -> bool:
    """True when ``lthr`` is a plausible threshold HR for this ``max_hr``."""
    if not isinstance(lthr, (int, float)):
        return False
    return (
        MIN_LTHR_FRACTION_OF_MAX * max_hr <= lthr <= MAX_LTHR_FRACTION_OF_MAX * max_hr
    )


def resolve_lthr_anchor(max_hr: int, lthr: Optional[int]) -> int:
    """Return the LTHR the zones will anchor on.

    Uses the supplied ``lthr`` when it is a plausible fraction of max HR;
    otherwise (missing, or out of the ``[MIN..MAX]_LTHR_FRACTION_OF_MAX`` band, so
    likely a mislabelled easy run or a VO2max peak) derives one from max HR at
    the population-average fraction. This keeps a noisy measurement from placing
    the threshold somewhere physiologically impossible.
    """
    if lthr is not None and _lthr_is_usable(max_hr, lthr):
        return int(lthr)
    return round(DEFAULT_LTHR_FRACTION_OF_MAX * max_hr)


def _enforce_min_widths(zones: list[dict], ceiling: int) -> list[dict]:
    """Guarantee a strictly-ascending partition with no band thinner than
    ``MIN_ZONE_WIDTH_BPM``.

    Walks top-down so capping the final band at max HR can never leave a sliver:
    a too-thin zone has its lower edge pushed down, and the zone below it follows.
    A no-op for healthy anchors, where the %LTHR bands are already wide.
    """
    zones[-1]["max_bpm"] = ceiling
    for i in range(len(zones) - 1, -1, -1):
        zone = zones[i]
        if zone["max_bpm"] - zone["min_bpm"] < MIN_ZONE_WIDTH_BPM:
            zone["min_bpm"] = zone["max_bpm"] - MIN_ZONE_WIDTH_BPM
        if i > 0:
            zones[i - 1]["max_bpm"] = zone["min_bpm"]
    return zones


class HRZoneCalculator:
    """Compute and classify heart rate training zones."""

    @staticmethod
    def calculate_zones(
        max_hr: int,
        resting_hr: Optional[int] = None,
        lthr: Optional[int] = None,
    ) -> list[dict]:
        """Return the 5-zone model with absolute BPM ranges.

        Zones are anchored on the runner's lactate-threshold HR: each band is a
        fraction of LTHR (Friel's running-zone method), with the Zone 3/4 edge
        sitting exactly on LTHR and the top of Zone 5 capped at max HR. When no
        LTHR is supplied one is derived from max HR (population-average 88%), so
        a data-less runner gets bands equivalent to the historical %max model.

        Args:
            max_hr: Maximum heart rate in BPM.
            resting_hr: Optional resting heart rate. When supplied and plausible
                it raises the Zone 1 floor (a runner's recovery band should not
                dip below their resting HR); it no longer drives the band math.
            lthr: Optional lactate-threshold HR (measured or supplied). Anchors
                the whole partition; ignored (the 88%-of-max default is used) if
                it falls outside a plausible fraction of max HR.

        Returns:
            List of zone dicts, each with zone, name, min_bpm, max_bpm,
            pct_min, pct_max, and description.
        """
        anchor = resolve_lthr_anchor(max_hr, lthr)
        zones = []
        for defn in ZONE_DEFINITIONS:
            min_bpm = round(anchor * defn["lthr_min"])
            if defn["lthr_max"] is None:
                max_bpm = max_hr
            else:
                max_bpm = min(round(anchor * defn["lthr_max"]), max_hr)
            zones.append(
                {
                    "zone": defn["zone"],
                    "name": defn["name"],
                    "min_bpm": min_bpm,
                    "max_bpm": max_bpm,
                    "pct_min": defn["pct_min"],
                    "pct_max": defn["pct_max"],
                    "description": defn["description"],
                }
            )

        # Resting HR (when genuinely known) only lifts the recovery floor.
        if _resting_hr_is_usable(max_hr, resting_hr):
            floor = int(resting_hr)  # type: ignore[arg-type]
            if floor > zones[0]["min_bpm"] and floor < zones[0]["max_bpm"]:
                zones[0]["min_bpm"] = floor

        return _enforce_min_widths(zones, max_hr)

    @staticmethod
    def classify_hr(hr_bpm: int, zones: list[dict]) -> int:
        """Classify a heart rate reading into a zone number (1–5).

        Args:
            hr_bpm: Heart rate in BPM.
            zones:  Zone list from ``calculate_zones``.

        Returns:
            Zone number (1-5). Values below Zone 1 return 1;
            values above Zone 5 return 5.
        """
        for zone in reversed(zones):
            if hr_bpm >= zone["min_bpm"]:
                return zone["zone"]
        return 1

    @staticmethod
    def get_workout_zone(workout_type: str) -> int:
        """Return the target HR zone number for a workout type.

        Args:
            workout_type: One of easy, recovery, long, tempo, interval, hill, rest.

        Returns:
            Target zone number (1-5).
        """
        return WORKOUT_ZONE_MAP.get(workout_type, 2)

    @staticmethod
    def zone_label(zone_number: int, zones: list[dict]) -> str:
        """Human-readable label for a zone, e.g. 'Zone 2 (Aerobic): 120-140 bpm'.

        Args:
            zone_number: Zone number (1-5).
            zones:       Zone list from ``calculate_zones``.

        Returns:
            Formatted string.
        """
        for z in zones:
            if z["zone"] == zone_number:
                return (
                    f"Zone {z['zone']} ({z['name']}): {z['min_bpm']}-{z['max_bpm']} bpm"
                )
        return f"Zone {zone_number}"

    @staticmethod
    def estimate_max_hr_age_based(age: int) -> int:
        """Age-based max HR estimation (Tanaka formula: 208 - 0.7 * age)."""
        return round(208 - 0.7 * age)
