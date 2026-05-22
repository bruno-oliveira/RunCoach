"""VDOT calculator using Jack Daniels' running formula.

Calculates training pace zones from a recent race performance.
Reference: Daniels' Running Formula (3rd ed.)
"""

import math
from typing import Dict, Optional

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

# Runs above this elevation gain per km are considered hilly/trail and should
# not feed into a flat-ground VDOT estimate -- Daniels' formula assumes flat
# terrain, so a hilly effort produces an artificially low VDOT.
TRAIL_ELEVATION_M_PER_KM = 20.0


def _vo2_at_velocity(v: float) -> float:
    """Oxygen cost at velocity v (m/min)."""
    return -4.60 + 0.182258 * v + 0.000104 * v**2


def _pct_vo2max_at_time(t: float) -> float:
    """Fraction of VO2max sustainable for t minutes."""
    return (
        0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)
    )


def _velocity_at_pct_vdot(vdot: float, pct: float) -> float:
    """Velocity in m/min at a given fraction of VDOT.

    Solves: 0.000104*v^2 + 0.182258*v - (4.60 + vdot*pct) = 0
    """
    target = vdot * pct
    a = 0.000104
    b = 0.182258
    c = -(4.60 + target)
    discriminant = b**2 - 4 * a * c
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
        "E_slow": 0.65,  # Easy run - conversational (recovery end)
        "E_fast": 0.75,  # Easy run - brisk end of easy range
        "M": 0.79,  # Marathon pace
        "T": 0.86,  # Threshold / tempo pace
        "I": 0.98,  # Interval pace (VO2max work)
        "R": 1.05,  # Repetition pace (speed / economy work)
    }

    # Easy sub-zones: Recovery / Easy / Long Run
    E_SUB_ZONES = {
        "recovery": (0.59, 0.65),  # very easy, active recovery
        "easy": (0.65, 0.72),  # standard easy run
        "long_run": (0.72, 0.76),  # upper easy, long run pace
    }

    @staticmethod
    def calculate_vdot(
        distance_km: float,
        time_seconds: int,
        elevation_gain_m: Optional[float] = None,
    ) -> Optional[float]:
        """Calculate VDOT from a race result.

        Args:
            distance_km: Race distance in km (e.g. 5.0, 10.0, 21.1, 42.2)
            time_seconds: Finish time in seconds
            elevation_gain_m: Total elevation gain in meters. If the run
                averages more than TRAIL_ELEVATION_M_PER_KM of climb per km,
                returns None -- VDOT assumes flat ground and a hilly run
                would otherwise pollute the user's flat-ground fitness estimate.

        Returns:
            VDOT value (rounded to 1 dp), or None if inputs are invalid,
            the pace is unrealistically fast (GPS glitch / auto-pause artifact),
            or the run is too hilly to be a meaningful flat-ground VDOT.
        """
        if distance_km <= 0 or time_seconds <= 0:
            return None

        # Reject unrealistic pace — almost certainly bad data
        pace_min_km = (time_seconds / 60.0) / distance_km
        if pace_min_km < MIN_REALISTIC_PACE_MIN_KM:
            return None

        if (
            elevation_gain_m is not None
            and elevation_gain_m / distance_km > TRAIL_ELEVATION_M_PER_KM
        ):
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
    def get_pace_zones(vdot: float, target_distance_km: float = 0.0) -> Dict[str, Dict]:
        """Return training pace zones for a given VDOT.

        Args:
            vdot: VDOT value
            target_distance_km: Optional target race distance for a
                dedicated "race" zone (ignored for 5K/10K which are
                always included).

        Returns:
            Dict with zone names mapping to pace info
        """
        from app.core.training.race_predictor import predict_time_for_distance

        zones = {}
        for zone, pct in VDOTCalculator.ZONE_PCT.items():
            v = _velocity_at_pct_vdot(vdot, pct)
            pace = _pace_from_velocity(v)
            zones[zone] = {
                "pace_min_km": round(pace, 2),
                "pace_str": _format_pace(pace),
            }

        # Compute easy sub-zone paces
        easy_subs = {}
        for sub_name, (lo_pct, hi_pct) in VDOTCalculator.E_SUB_ZONES.items():
            v_slow = _velocity_at_pct_vdot(vdot, lo_pct)
            v_fast = _velocity_at_pct_vdot(vdot, hi_pct)
            p_slow = _pace_from_velocity(v_slow)
            p_fast = _pace_from_velocity(v_fast)
            easy_subs[sub_name] = {
                "pace_min_km_slow": round(p_slow, 2),
                "pace_min_km_fast": round(p_fast, 2),
                "pace_str": f"{_format_pace(p_slow)}–{_format_pace(p_fast)}",
            }

        # Race-specific pace zones computed from predicted race times
        race_paces: Dict[str, Dict] = {}
        for dist_km, label in [(5.0, "5K"), (10.0, "10K")]:
            race_seconds = predict_time_for_distance(vdot, dist_km)
            if race_seconds:
                race_pace = (race_seconds / 60.0) / dist_km
                race_paces[label] = {
                    "pace_min_km": round(race_pace, 2),
                    "pace_str": _format_pace(race_pace),
                    "description": f"{label} race pace",
                }

        if target_distance_km > 0 and target_distance_km not in (5.0, 10.0):
            race_seconds = predict_time_for_distance(vdot, target_distance_km)
            if race_seconds:
                race_pace = (race_seconds / 60.0) / target_distance_km
                race_paces["race"] = {
                    "pace_min_km": round(race_pace, 2),
                    "pace_str": _format_pace(race_pace),
                    "description": f"{target_distance_km}K race pace",
                }

        return {
            "E": {
                "pace_min_km_slow": zones["E_slow"]["pace_min_km"],
                "pace_min_km_fast": zones["E_fast"]["pace_min_km"],
                "pace_str": f"{zones['E_slow']['pace_str']}–{zones['E_fast']['pace_str']}",
                "description": "Easy / recovery",
                "sub_zones": {
                    "recovery": {
                        **easy_subs["recovery"],
                        "description": "Recovery run — very easy, conversational",
                    },
                    "easy": {
                        **easy_subs["easy"],
                        "description": "Standard easy run",
                    },
                    "long_run": {
                        **easy_subs["long_run"],
                        "description": "Long run pace — upper easy range",
                    },
                },
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
            **race_paces,
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
    def inject_paces_into_description(
        description: str, zones: Dict, workout_type: str
    ) -> str:
        """Enrich a workout description with specific VDOT-based paces.

        Replaces generic zone references with specific pace values.
        """
        if not zones:
            return description

        ten_k = zones.get("10K", zones["T"])
        replacements = {
            # Interval cues
            "5K pace": f"{zones['I']['pace_str']} (I-pace)",
            "5k pace": f"{zones['I']['pace_str']} (I-pace)",
            "VO2 max pace": f"{zones['I']['pace_str']} (I-pace)",
            "VO2max pace": f"{zones['I']['pace_str']} (I-pace)",
            # Race-specific cues
            "10K pace": f"{ten_k['pace_str']} (10K pace)",
            "10k pace": f"{ten_k['pace_str']} (10K pace)",
            # Tempo cues
            "threshold pace": f"{zones['T']['pace_str']} (T-pace)",
            "tempo pace": f"{zones['T']['pace_str']} (T-pace)",
            "marathon goal pace": f"{zones['M']['pace_str']} (M-pace)",
            "marathon pace": f"{zones['M']['pace_str']} (M-pace)",
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

    # -- Race prediction (delegates to race_predictor module) ---------------

    @staticmethod
    def predict_time_for_distance(
        vdot: float,
        distance_km: float,
        elevation_gain_m: Optional[float] = None,
        trail_runs_count: Optional[int] = None,
        endurance_factor: Optional[float] = None,
    ) -> Optional[int]:
        from app.core.training.race_predictor import predict_time_for_distance

        return predict_time_for_distance(
            vdot, distance_km, elevation_gain_m, trail_runs_count, endurance_factor
        )

    @staticmethod
    def get_confidence_range(
        vdot: float,
        distance_km: float,
        target_distance: float = 0.0,
        elevation_gain_m: Optional[float] = None,
        trail_runs_count: Optional[int] = None,
        endurance_factor: Optional[float] = None,
    ) -> Dict[str, int]:
        from app.core.training.race_predictor import get_confidence_range

        return get_confidence_range(
            vdot,
            distance_km,
            target_distance,
            elevation_gain_m,
            trail_runs_count,
            endurance_factor,
        )

    @staticmethod
    def predict_times(
        vdot: float,
        trail_runs_count: Optional[int] = None,
        elevation_map: Optional[Dict[str, float]] = None,
        endurance_factor: Optional[float] = None,
    ) -> Dict[str, Dict]:
        from app.core.training.race_predictor import predict_times

        return predict_times(vdot, trail_runs_count, elevation_map, endurance_factor)
