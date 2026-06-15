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

# Version of the zone model below. Bump when ZONE_DEFINITIONS changes -- or when
# the zone *math* changes (e.g. %max HR -> Heart Rate Reserve) -- so plans
# carrying zones from an older model are recomputed on next view.
HR_ZONES_VERSION = 3


# -- Zone definitions (percentage of max HR) ----------------------------------

# Running-specific 5-zone model (% of max HR). These are the SAME bands the
# pace-zone table annotates (zone_calculator.py), so "Zone 3 - Tempo" means
# one thing everywhere: on the personal HR-zones panel, on each workout's
# BPM badge, and in the adaptation engine's zone-adherence signal.
#
# The previous model used generic 50/60/70/80/90% bands. Two bugs followed:
# 1. The plan page showed contradictory numbers - a workout badge said
#    "Zone 2: 60-70% of max" while the zone table said "Aerobic: 70-80%".
# 2. Easy runs prescribed at 60-70% of max are below most runners' slowest
#    sustainable running HR (Daniels puts E pace at 65-79% of max), so the
#    adaptation engine scored correctly-run easy runs as "+1 zone too hard"
#    and applied an unearned volume penalty - while interval days targeted
#    at 90-100% *average* HR (unattainable as a run average) scored -1.
ZONE_DEFINITIONS = [
    {
        "zone": 1,
        "name": "Recovery",
        "pct_min": 0.60,
        "pct_max": 0.70,
        "description": "Very light effort. Active recovery, warm-up, cool-down.",
    },
    {
        "zone": 2,
        "name": "Aerobic",
        "pct_min": 0.70,
        "pct_max": 0.80,
        "description": "Conversational pace. Builds aerobic base and endurance.",
    },
    {
        "zone": 3,
        "name": "Tempo",
        "pct_min": 0.80,
        "pct_max": 0.88,
        "description": "Comfortably hard. Threshold effort - improves lactate clearance and stamina.",
    },
    {
        "zone": 4,
        "name": "VO2max",
        "pct_min": 0.88,
        "pct_max": 0.95,
        "description": "Hard effort. 3-5 minute intervals that develop peak oxygen uptake.",
    },
    {
        "zone": 5,
        "name": "Speed",
        "pct_min": 0.95,
        "pct_max": 1.00,
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


def _zone_bpm(pct: float, max_hr: int, resting_hr: Optional[int]) -> int:
    """Absolute BPM for a zone fraction.

    When a usable resting HR is supplied we use the Heart Rate Reserve
    (Karvonen) method -- ``resting + pct * (max - resting)`` -- which reflects
    metabolic intensity far better than a flat %max HR for runners, whose low
    resting HR otherwise pushes every band several BPM too low. Without a
    resting HR we fall back to the historical %max HR mapping unchanged.
    """
    if resting_hr is not None and _resting_hr_is_usable(max_hr, resting_hr):
        return round(resting_hr + pct * (max_hr - resting_hr))
    return round(max_hr * pct)


class HRZoneCalculator:
    """Compute and classify heart rate training zones."""

    @staticmethod
    def calculate_zones(max_hr: int, resting_hr: Optional[int] = None) -> list[dict]:
        """Return 5-zone model with absolute BPM ranges.

        Args:
            max_hr: Maximum heart rate in BPM.
            resting_hr: Optional resting heart rate. When provided (and
                plausible) zones are computed via Heart Rate Reserve
                (Karvonen); otherwise the %max HR mapping is used.

        Returns:
            List of zone dicts, each with zone, name, min_bpm, max_bpm,
            pct_min, pct_max, and description.
        """
        usable_resting = (
            resting_hr if _resting_hr_is_usable(max_hr, resting_hr) else None
        )
        zones = []
        for defn in ZONE_DEFINITIONS:
            zones.append(
                {
                    "zone": defn["zone"],
                    "name": defn["name"],
                    "min_bpm": _zone_bpm(defn["pct_min"], max_hr, usable_resting),
                    "max_bpm": _zone_bpm(defn["pct_max"], max_hr, usable_resting),
                    "pct_min": defn["pct_min"],
                    "pct_max": defn["pct_max"],
                    "description": defn["description"],
                }
            )
        return zones

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
