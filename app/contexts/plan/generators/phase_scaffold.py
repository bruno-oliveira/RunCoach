"""Shared scaffolding for the phase-based plan generators.

The fitness and performance generators each compute a per-phase week count
(``phase_durations``) and then attach plan-type-specific metadata to it. The
metadata itself differs by plan type (different quality dosing and copy), but
the assembly shape is identical — this helper captures that shape in one place.
"""

from typing import Any, Dict


def build_phases_rich(
    phase_durations: Dict[str, int],
    phase_metadata: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Merge per-phase week counts with plan-type metadata.

    Args:
        phase_durations: Mapping of phase name -> number of weeks.
        phase_metadata: Mapping of phase name -> metadata (e.g. quality_percent,
            description) for this plan type.

    Returns:
        Mapping of phase name -> {"weeks": <count>, **metadata}.
    """
    return {
        phase: {"weeks": phase_durations[phase], **phase_metadata[phase]}
        for phase in phase_durations
    }
