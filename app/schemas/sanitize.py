"""Scrubbing free-text user input at the request boundary."""

import re
from typing import Optional

_TAG_RE = re.compile(r"<[^>]*>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_user_text(value: Optional[str]) -> Optional[str]:
    """Defense-in-depth scrub for free-text user input rendered back to the UI.

    Templates already autoescape on output, so this is belt-and-braces for paths
    that bypass Jinja (raw API consumers, future innerHTML usage). Strips HTML/XML
    tags and non-printable control characters; preserves tab/newline/CR.
    """
    if value is None:
        return None
    cleaned = _TAG_RE.sub("", value)
    cleaned = _CONTROL_RE.sub("", cleaned)
    cleaned = cleaned.strip()
    return cleaned or None
