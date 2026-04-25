"""Sentiment classification for coaching feedback."""


def determine_sentiment(feedback: dict) -> str:
    """Return overall_sentiment based on populated feedback fields."""
    texts = [
        v for k, v in feedback.items()
        if k != "overall_sentiment" and v
    ]
    if not texts:
        return "info"

    combined = " ".join(texts).lower()
    warning_signals = [
        "slower than",
        "faster than planned",
        "too hard",
        "too easy",
        "above target",
        "impairs recovery",
        "pattern detected",
    ]
    positive_signals = [
        "nailed it",
        "right on target",
        "great execution",
        "well paced",
        "target reached",
    ]

    has_warning = any(s in combined for s in warning_signals)
    has_positive = any(s in combined for s in positive_signals)

    if has_warning and not has_positive:
        return "warning"
    if has_positive and not has_warning:
        return "positive"
    return "info"
