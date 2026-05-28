"""Threshold-ladder verdicts for training-gap and progress reporting.

Pure: maps a numeric value to a verdict label through an ordered set of
thresholds. Centralizes the ``on_track / close / behind / far_behind`` ladder
that gap analysis repeats per metric.
"""

from typing import Sequence

#: Default labels for a deficit/gap ladder (best → worst).
VERDICT_LABELS: Sequence[str] = ("on_track", "close", "behind", "far_behind")


def verdict_from_thresholds(
    value: float,
    thresholds: Sequence[float],
    labels: Sequence[str] = VERDICT_LABELS,
    *,
    higher_is_better: bool = False,
) -> str:
    """Map ``value`` to a verdict label via an ordered threshold ladder.

    With ``higher_is_better=False`` (default — "lower is better", e.g. a deficit
    percentage or a pace gap), the ladder is upper-inclusive ascending:
    ``value <= thresholds[0]`` → ``labels[0]``, then ``thresholds[1]`` → and so on.

    With ``higher_is_better=True`` (e.g. a completion rate), it is lower-inclusive
    descending: ``value >= thresholds[0]`` → ``labels[0]``, etc.

    Args:
        value: The metric to classify.
        thresholds: Ladder rungs in best→worst order. ``len(labels)`` must equal
            ``len(thresholds) + 1`` — the last label is the fallthrough.
        labels: Verdict labels best→worst.
        higher_is_better: Direction of the comparison (see above).

    Returns:
        The matching label, or ``labels[-1]`` when no rung matches.
    """
    for threshold, label in zip(thresholds, labels):
        matched = value >= threshold if higher_is_better else value <= threshold
        if matched:
            return label
    return labels[-1]
