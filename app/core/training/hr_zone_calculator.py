"""Heart rate zone calculator.

Pure training-zone math — no database or ORM dependencies.
Computes a 5-zone HR model from max heart rate and provides
zone classification and workout-level zone prescriptions.
"""

# Minimum recorded max HR to trust (lower likely a sensor error)
MIN_RELIABLE_MAX_HR = 140

# Conservative universal default when no age or run data is available
DEFAULT_MAX_HR = 190


# -- Zone definitions (percentage of max HR) ----------------------------------

ZONE_DEFINITIONS = [
    {"zone": 1, "name": "Recovery", "pct_min": 0.50, "pct_max": 0.60,
     "description": "Very light effort. Active recovery, warm-up, cool-down."},
    {"zone": 2, "name": "Aerobic", "pct_min": 0.60, "pct_max": 0.70,
     "description": "Conversational pace. Builds aerobic base and fat-burning efficiency."},
    {"zone": 3, "name": "Tempo", "pct_min": 0.70, "pct_max": 0.80,
     "description": "Comfortably hard. Improves lactate clearance and stamina."},
    {"zone": 4, "name": "Threshold", "pct_min": 0.80, "pct_max": 0.90,
     "description": "Hard effort. Raises lactate threshold and race-day tolerance."},
    {"zone": 5, "name": "VO2max", "pct_min": 0.90, "pct_max": 1.00,
     "description": "Maximum effort. Develops peak oxygen uptake and speed."},
]

# Maps workout_type → target HR zone number (1-5)
WORKOUT_ZONE_MAP: dict[str, int] = {
    "easy": 2,
    "recovery": 1,
    "long": 2,
    "tempo": 3,
    "interval": 5,
    "hill": 5,
    "rest": 1,
}


class HRZoneCalculator:
    """Compute and classify heart rate training zones."""

    @staticmethod
    def calculate_zones(max_hr: int) -> list[dict]:
        """Return 5-zone model with absolute BPM ranges.

        Args:
            max_hr: Maximum heart rate in BPM.

        Returns:
            List of zone dicts, each with zone, name, min_bpm, max_bpm,
            pct_min, pct_max, and description.
        """
        zones = []
        for defn in ZONE_DEFINITIONS:
            zones.append({
                "zone": defn["zone"],
                "name": defn["name"],
                "min_bpm": round(max_hr * defn["pct_min"]),
                "max_bpm": round(max_hr * defn["pct_max"]),
                "pct_min": defn["pct_min"],
                "pct_max": defn["pct_max"],
                "description": defn["description"],
            })
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
                return f"Zone {z['zone']} ({z['name']}): {z['min_bpm']}-{z['max_bpm']} bpm"
        return f"Zone {zone_number}"

    @staticmethod
    def estimate_max_hr_age_based(age: int) -> int:
        """Age-based max HR estimation (Tanaka formula: 208 - 0.7 * age)."""
        return round(208 - 0.7 * age)
