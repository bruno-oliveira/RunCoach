"""VDOT calculator using Jack Daniels' running formula.

Calculates training pace zones from a recent race performance.
Reference: Daniels' Running Formula (3rd ed.)
"""

import math
from typing import Dict, Optional, Tuple

STANDARD_RACE_DISTANCES = {
    "5K": 5.0,
    "10K": 10.0,
    "trail": 30.0,
    "half_marathon": 21.0975,
    "marathon": 42.195,
}

# Fastest realistic pace for runs >= 2 km.  The 3 km world record is ~2:23/km;
# anything faster than 2:30/km over 2+ km is almost certainly a GPS glitch or
# auto-pause artifact.
MIN_REALISTIC_PACE_MIN_KM = 2.5


def _vo2_at_velocity(v: float) -> float:
    """Oxygen cost at velocity v (m/min)."""
    return -4.60 + 0.182258 * v + 0.000104 * v ** 2


def _pct_vo2max_at_time(t: float) -> float:
    """Fraction of VO2max sustainable for t minutes."""
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)


def _velocity_at_pct_vdot(vdot: float, pct: float) -> float:
    """Velocity in m/min at a given fraction of VDOT.

    Solves: 0.000104*v^2 + 0.182258*v - (4.60 + vdot*pct) = 0
    """
    target = vdot * pct
    a = 0.000104
    b = 0.182258
    c = -(4.60 + target)
    discriminant = b ** 2 - 4 * a * c
    if discriminant < 0:
        return 0.0
    return (-b + math.sqrt(discriminant)) / (2 * a)


def _pace_from_velocity(v: float) -> float:
    """Convert m/min velocity to min/km pace."""
    if v <= 0:
        return 99.0
    return 1000.0 / v


def _format_pace(pace_min_km: float) -> str:
    """Format decimal min/km as MM:SS/km string."""
    from app.utils import format_pace
    return format_pace(pace_min_km)


class VDOTCalculator:
    """Calculate VDOT and training pace zones from a race result."""

    # %VO2max for each training zone (midpoints of Daniels' ranges)
    ZONE_PCT = {
        "E_slow": 0.65,   # Easy run - conversational (recovery end)
        "E_fast": 0.75,   # Easy run - brisk end of easy range
        "M": 0.79,        # Marathon pace
        "T": 0.86,        # Threshold / tempo pace
        "I": 0.98,        # Interval pace (VO2max work)
        "R": 1.05,        # Repetition pace (speed / economy work)
    }

    @staticmethod
    def calculate_vdot(distance_km: float, time_seconds: int) -> Optional[float]:
        """Calculate VDOT from a race result.

        Args:
            distance_km: Race distance in km (e.g. 5.0, 10.0, 21.1, 42.2)
            time_seconds: Finish time in seconds

        Returns:
            VDOT value (rounded to 1 dp), or None if inputs are invalid
            or the pace is unrealistically fast (GPS glitch / auto-pause artifact).
        """
        if distance_km <= 0 or time_seconds <= 0:
            return None

        # Reject unrealistic pace — almost certainly bad data
        pace_min_km = (time_seconds / 60.0) / distance_km
        if pace_min_km < MIN_REALISTIC_PACE_MIN_KM:
            return None

        distance_m = distance_km * 1000.0
        time_min = time_seconds / 60.0

        velocity = distance_m / time_min  # m/min
        vo2 = _vo2_at_velocity(velocity)
        pct = _pct_vo2max_at_time(time_min)

        if pct <= 0:
            return None

        vdot = vo2 / pct
        # Clamp to realistic range (25 = very beginner, 85 = world-class)
        return round(max(25.0, min(85.0, vdot)), 1)

    @staticmethod
    def get_pace_zones(vdot: float) -> Dict[str, Dict]:
        """Return training pace zones for a given VDOT.

        Args:
            vdot: VDOT value

        Returns:
            Dict with zone names mapping to pace info
        """
        zones = {}
        for zone, pct in VDOTCalculator.ZONE_PCT.items():
            v = _velocity_at_pct_vdot(vdot, pct)
            pace = _pace_from_velocity(v)
            zones[zone] = {
                "pace_min_km": round(pace, 2),
                "pace_str": _format_pace(pace),
            }

        return {
            "E": {
                "pace_min_km_slow": zones["E_slow"]["pace_min_km"],
                "pace_min_km_fast": zones["E_fast"]["pace_min_km"],
                "pace_str": f"{zones['E_slow']['pace_str']}–{zones['E_fast']['pace_str']}",
                "description": "Easy / recovery",
            },
            "M": {
                "pace_min_km": zones["M"]["pace_min_km"],
                "pace_str": zones["M"]["pace_str"],
                "description": "Marathon pace",
            },
            "T": {
                "pace_min_km": zones["T"]["pace_min_km"],
                "pace_str": zones["T"]["pace_str"],
                "description": "Threshold / tempo",
            },
            "I": {
                "pace_min_km": zones["I"]["pace_min_km"],
                "pace_str": zones["I"]["pace_str"],
                "description": "Interval / VO2max",
            },
            "R": {
                "pace_min_km": zones["R"]["pace_min_km"],
                "pace_str": zones["R"]["pace_str"],
                "description": "Repetition / speed",
            },
        }

    @staticmethod
    def format_pace(pace_min_km: float) -> str:
        """Public helper — format a decimal pace as MM:SS/km."""
        return _format_pace(pace_min_km)

    @staticmethod
    def parse_time_to_seconds(time_str: str) -> Optional[int]:
        """Parse HH:MM:SS or MM:SS string to total seconds.

        Args:
            time_str: Time string like "1:45:30" or "24:15"

        Returns:
            Total seconds, or None if unparseable
        """
        from app.utils import parse_race_time_to_seconds
        return parse_race_time_to_seconds(time_str)

    @staticmethod
    def inject_paces_into_description(description: str, zones: Dict, workout_type: str) -> str:
        """Enrich a workout description with specific VDOT-based paces.

        Replaces generic zone references with specific pace values.
        """
        if not zones:
            return description

        replacements = {
            # Interval cues
            "5K pace": f"{zones['I']['pace_str']} (I-pace)",
            "5k pace": f"{zones['I']['pace_str']} (I-pace)",
            "VO2 max pace": f"{zones['I']['pace_str']} (I-pace)",
            "VO2max pace": f"{zones['I']['pace_str']} (I-pace)",
            # Tempo cues
            "threshold pace": f"{zones['T']['pace_str']} (T-pace)",
            "tempo pace": f"{zones['T']['pace_str']} (T-pace)",
            "marathon goal pace": f"{zones['M']['pace_str']} (M-pace)",
            "marathon pace": f"{zones['M']['pace_str']} (M-pace)",
            "10K pace": f"{zones['T']['pace_str']} (T-pace)",
            "10k pace": f"{zones['T']['pace_str']} (T-pace)",
        }

        enriched = description
        for generic, specific in replacements.items():
            enriched = enriched.replace(generic, specific)

        return enriched

    @staticmethod
    def validate_race_distance(distance_km: float) -> bool:
        """Check if distance is valid for prediction."""
        return distance_km in STANDARD_RACE_DISTANCES.values()

    @staticmethod
    def format_duration(seconds: int) -> str:
        """Format seconds as HH:MM:SS or MM:SS."""
        if seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}:{secs:02d}"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def predict_time_for_distance(vdot: float, distance_km: float) -> Optional[int]:
        """Predict race time for a given VDOT and distance.

        Uses binary search to solve: vo2(d/t) / pct_vo2max(t) = VDOT
        For a fixed distance, increasing time → lower velocity → lower VDOT,
        so the function is monotonically decreasing in time.

        Args:
            vdot: Current fitness level (25-85)
            distance_km: Target race distance

        Returns:
            Predicted time in seconds, or None if invalid
        """
        if vdot < 25 or vdot > 85:
            return None
        if distance_km <= 0:
            return None

        distance_m = distance_km * 1000.0

        # Search bounds in minutes: 1 min to 600 min (10 hours)
        lo, hi = 1.0, 600.0

        for _ in range(100):
            mid = (lo + hi) / 2.0
            velocity = distance_m / mid
            vo2 = _vo2_at_velocity(velocity)
            pct = _pct_vo2max_at_time(mid)
            if pct <= 0:
                lo = mid
                continue
            calc_vdot = vo2 / pct
            if abs(calc_vdot - vdot) < 0.01:
                break
            if calc_vdot > vdot:
                # Too fast — need more time
                lo = mid
            else:
                # Too slow — need less time
                hi = mid

        return int(round(mid * 60))

    @staticmethod
    def get_confidence_range(vdot: float, distance_km: float) -> Dict[str, int]:
        """Get optimistic and pessimistic time estimates (±1 VO2max)."""
        fast_vdot = min(85.0, vdot + 1.0)
        slow_vdot = max(25.0, vdot - 1.0)

        fast_time = VDOTCalculator.predict_time_for_distance(fast_vdot, distance_km)
        slow_time = VDOTCalculator.predict_time_for_distance(slow_vdot, distance_km)

        base_time = VDOTCalculator.predict_time_for_distance(vdot, distance_km)

        return {
            "fast": fast_time or base_time,
            "slow": slow_time or base_time,
            "base": base_time,
        }

    @staticmethod
    def predict_times(vdot: float) -> Dict[str, Dict]:
        """Get predicted times for all standard race distances.

        Returns:
            Dict with distance keys mapping to time info
        """
        predictions = {}
        for name, distance in STANDARD_RACE_DISTANCES.items():
            seconds = VDOTCalculator.predict_time_for_distance(vdot, distance)
            if seconds:
                predictions[name] = {
                    "seconds": seconds,
                    "formatted": VDOTCalculator.format_duration(seconds),
                    "distance_km": distance,
                }
        return predictions
