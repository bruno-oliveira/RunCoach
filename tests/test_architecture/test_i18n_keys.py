"""Every i18n key the markup asks for must exist in the catalogue.

``RC_I18N.t()`` falls back to returning the key itself, so a key missing from
``i18n.js`` doesn't fail loudly — it replaces the English text the server
rendered with the raw key. That shipped once: every "Open full session" link
on the plan read ``workout.open_day``. This scans the templates and scripts for
``data-i18n*`` attributes and checks each key against both locales.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "app" / "web"
CATALOGUE = WEB / "static" / "js" / "i18n.js"

_ATTR = re.compile(
    r"""data-i18n(?:-html|-placeholder|-aria|-title)?=["']([^"'{}+]+)["']"""
)
_KEY = re.compile(r"""^\s*'([a-z0-9_.\-]+)'\s*:""", re.MULTILINE)


def _locale_keys() -> dict[str, set[str]]:
    src = CATALOGUE.read_text(encoding="utf-8")
    en_start, pt_start = src.index("en: {"), src.index("pt: {")
    return {
        "en": set(_KEY.findall(src[en_start:pt_start])),
        "pt": set(_KEY.findall(src[pt_start:])),
    }


def _used_keys() -> dict[str, set[str]]:
    used: dict[str, set[str]] = {}
    files = [*WEB.glob("templates/**/*.html"), *WEB.glob("static/js/**/*.js")]
    for path in files:
        if path == CATALOGUE:
            continue
        for key in _ATTR.findall(path.read_text(encoding="utf-8")):
            used.setdefault(key, set()).add(str(path.relative_to(WEB)))
    return used


def test_scan_finds_keys():
    # Guards the guard: a regex that silently matches nothing would pass.
    assert len(_used_keys()) > 100
    assert all(len(keys) > 100 for keys in _locale_keys().values())


def test_every_used_key_exists_in_each_locale():
    locales = _locale_keys()
    missing = {
        f"{locale}:{key}": sorted(files)
        for key, files in _used_keys().items()
        for locale, keys in locales.items()
        if key not in keys
    }
    assert not missing, f"i18n keys missing from i18n.js: {missing}"


def test_locales_define_the_same_keys():
    locales = _locale_keys()
    assert locales["en"] ^ locales["pt"] == set()
