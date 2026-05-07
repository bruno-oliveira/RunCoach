"""Polarized training ratio validation.

Validates and adjusts the 80/20 polarized training distribution.
"""

from typing import Dict, Optional


def validate_polarized_ratio(distribution: Dict[str, int], phase: str,
                             target_distance: float,
                             trail_profile=None) -> Dict[str, int]:
    """Validate 80/20 polarized training ratio and adjust if needed.

    Trail gets slightly easier targets (85/15 build, 80/20 peak) because
    terrain naturally provides intensity through elevation. Flat-trail plans
    keep the road target since they aren't getting hill-driven intensity.
    """
    is_trail = trail_profile is not None or target_distance == 30.0
    if trail_profile is not None and trail_profile.elevation_class == "flat":
        # Flat trail: no terrain-driven intensity → use the road polarized target.
        is_trail = False
    hard_targets = {
        'base': 0.10,
        'build': 0.15 if is_trail else 0.20,
        'peak': 0.20 if is_trail else 0.25,
        'taper': 0.10,
    }

    hard_count = distribution.get('interval', 0) + distribution.get('tempo', 0) + distribution.get('hill', 0)
    total_runs = hard_count + distribution.get('easy', 0) + distribution.get('long', 0)

    if total_runs == 0:
        return distribution

    hard_pct = hard_count / total_runs
    target = hard_targets.get(phase, 0.20)

    # If hard% exceeds target by >5%, reduce quality by 1.
    # Never reduce below 1 quality in build/peak — with 3-4 total runs the
    # count-based ratio overstates intensity.
    if hard_pct > target + 0.05 and hard_count > 0:
        if phase == 'base' and hard_count <= 1:
            pass
        elif phase in ('build', 'peak') and hard_count <= 1:
            pass
        else:
            for key in ('interval', 'tempo', 'hill'):
                if distribution.get(key, 0) > 0:
                    distribution[key] -= 1
                    distribution['easy'] = distribution.get('easy', 0) + 1
                    break
    # If under by >10% in build/peak, increase by 1.
    elif (phase in ('build', 'peak') and hard_pct < target - 0.10
          and distribution.get('easy', 0) > 0 and total_runs >= 3):
        distribution['easy'] -= 1
        distribution['interval'] = distribution.get('interval', 0) + 1

    return distribution
