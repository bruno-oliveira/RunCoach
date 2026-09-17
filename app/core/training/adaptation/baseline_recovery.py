"""Recover true baselines from corrupted adaptation state.

A workout is "corrupted" when its `baseline_distance_km` was frozen to an
already-adjusted `distance_km` (e.g. legacy plans backfilled after an old
adjustment had inflated the distance). The lingering `(Adjusted: xN.NN)`
note encodes the multiplier that was applied, so the true original distance
is recoverable as `distance / multiplier`.

Pure module: no I/O, no ORM. Operates on plain numbers and the note string.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Matches the adaptation/recalibration annotations appended to workout notes,
# e.g. " (Adjusted: x1.15)". Shared with the adaptation sub-package.
ANNOTATION_RE = re.compile(r"\s*\((Adapted|Recalibrated|Adjusted):[^)]*\)")

# Only the "Adjusted: xN.NN" form carries a recoverable numeric multiplier.
_ADJUSTED_MULT_RE = re.compile(r"\(Adjusted:\s*x([0-9]+(?:\.[0-9]+)?)\)")

# Baseline and distance are considered "equal" within ORM rounding (1 dp).
_EQUAL_TOL = 0.05


def strip_annotations(notes: Optional[str]) -> Optional[str]:
    """Remove any adaptation annotations from a note, returning None if empty."""
    if not notes:
        return notes
    clean = ANNOTATION_RE.sub("", notes).strip()
    return clean or None


def parse_adjustment_multiplier(notes: Optional[str]) -> Optional[float]:
    """Extract the multiplier from an `(Adjusted: xN.NN)` note.

    Returns the product when several annotations are stacked (the adjuster
    strips before re-adding, so this normally finds at most one). Returns
    None when no parseable multiplier is present.
    """
    if not notes:
        return None
    matches = _ADJUSTED_MULT_RE.findall(notes)
    if not matches:
        return None
    product = 1.0
    for raw in matches:
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 0:
            product *= value
    return product if product > 0 else None


def recover_baseline(
    distance: Optional[float],
    baseline: Optional[float],
    notes: Optional[str],
) -> Tuple[Optional[float], Optional[float], bool]:
    """Recover the true baseline/distance for a corrupted workout.

    Corruption signature: the note carries an `(Adjusted:)` multiplier *and*
    the stored baseline equals the (already-adjusted) distance. In that case
    the stored baseline is not a real baseline — back-compute the original
    from the multiplier.

    Returns `(true_baseline, true_distance, recovered)`. When the signature
    does not match (or no multiplier parses), inputs are returned unchanged
    with `recovered=False`.
    """
    if distance is None or distance <= 0 or baseline is None:
        return baseline, distance, False

    # A genuine adaptation diverges baseline from distance — leave it alone.
    if abs(baseline - distance) > _EQUAL_TOL:
        return baseline, distance, False

    multiplier = parse_adjustment_multiplier(notes)
    if multiplier is None or multiplier == 1.0:
        return baseline, distance, False

    true_value = round(distance / multiplier, 1)
    return true_value, true_value, True
