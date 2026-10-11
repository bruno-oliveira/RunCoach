"""Translation of text the app writes in English into the runner's language.

Two halves: :mod:`locale` says *which* language a request is in, and
:mod:`phrasebook` turns an English sentence into its translation. The browser
runs the same matcher (``static/js/i18n.js``) over the same catalogue, so a
sentence reads the same on the page, in an email and on the watch.
"""

from app.core.i18n.locale import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    normalize_language,
    request_language,
    reset_request_language,
    set_request_language,
    stated_request_language,
)
from app.core.i18n.phrasebook import PhraseBook

__all__ = [
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "PhraseBook",
    "normalize_language",
    "request_language",
    "reset_request_language",
    "set_request_language",
    "stated_request_language",
]
