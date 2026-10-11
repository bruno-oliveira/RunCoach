"""The phrase catalogue on disk, and the translator built from it.

``app/data/i18n/<lang>/*.json`` is one catalogue read by two programs: the
browser fetches the files (they are mounted under ``/static/i18n``) and this
module loads them for text that never reaches a browser — an email, a push, the
PDF, a workout name on the watch. One set of files is what keeps "Easy run"
from being *Corrida leve* on the page and something else in the inbox.

Files group into bundles so a page only downloads what it shows:

- ``core`` — every page: interface text and plan content.
- ``recipes`` — the recipe catalogue, which is large and only read on the
  recipe pages and the nutrition tab.
- ``outbound`` — emails, pushes and the PDF; never sent to the browser.
"""

import hashlib
import json
import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from app.core.i18n import (
    DEFAULT_LANGUAGE,
    PhraseBook,
    normalize_language,
    request_language,
)

logger = logging.getLogger(__name__)

CATALOGUE_DIR = Path(__file__).resolve().parents[2] / "data" / "i18n"

# File stem -> bundle. A file not named here belongs to ``core``.
_BUNDLE_OF = {"recipes": "recipes", "outbound": "outbound", "pdf": "outbound"}
BROWSER_BUNDLES = ("core", "recipes")


def catalogue_files(language: str) -> dict[str, list[Path]]:
    """The catalogue files for ``language``, grouped by bundle."""
    bundles: dict[str, list[Path]] = {}
    for path in sorted((CATALOGUE_DIR / language).glob("*.json")):
        bundles.setdefault(_BUNDLE_OF.get(path.stem, "core"), []).append(path)
    return bundles


@lru_cache(maxsize=None)
def phrasebook(language: str) -> PhraseBook | None:
    """Every phrase known for ``language``, or ``None`` for English.

    The server translates rarely and never per keystroke, so it loads all the
    bundles into one book rather than tracking which text needs which.
    """
    if language == DEFAULT_LANGUAGE:
        return None
    entries: dict[str, str] = {}
    for paths in catalogue_files(language).values():
        for path in paths:
            entries.update(json.loads(path.read_text(encoding="utf-8")))
    if not entries:
        logger.warning("No phrase catalogue found for language %r", language)
        return None
    return PhraseBook(entries)


def translate(text: str | None, language: str | None = None) -> str:
    """Translate English ``text`` for ``language`` (default: this request's).

    Returns the text unchanged for English, for an unknown language, and for
    anything the catalogue does not know.
    """
    if not text:
        return text or ""
    code = normalize_language(language) if language else request_language()
    book = phrasebook(code or DEFAULT_LANGUAGE)
    return text if book is None else book.translate(text)


def localizer(language: str | None) -> Callable[[str], str]:
    """A ``str -> str`` translator pinned to one runner's stored language.

    For work done with no request around it — the daily sweep, a webhook —
    where each runner's ``users.language`` has to be passed along explicitly.
    Pure builders in ``app/core`` take one of these rather than a language,
    which keeps the catalogue (and its file I/O) out of the pure layer.
    """
    code = normalize_language(language) or DEFAULT_LANGUAGE
    book = phrasebook(code)
    if book is None:
        return _unchanged
    return book.translate


def _unchanged(text: str) -> str:
    return text


@lru_cache(maxsize=1)
def browser_manifest() -> dict[str, dict[str, list[str]]]:
    """``{lang: {bundle: [url, …]}}`` for the page to fetch, content-hashed."""
    manifest: dict[str, dict[str, list[str]]] = {}
    if not CATALOGUE_DIR.exists():
        return manifest
    for language_dir in sorted(p for p in CATALOGUE_DIR.iterdir() if p.is_dir()):
        bundles = catalogue_files(language_dir.name)
        manifest[language_dir.name] = {
            bundle: [
                f"/static/i18n/{language_dir.name}/{path.name}"
                f"?h={hashlib.md5(path.read_bytes()).hexdigest()[:8]}"
                for path in bundles.get(bundle, [])
            ]
            for bundle in BROWSER_BUNDLES
        }
    return manifest
