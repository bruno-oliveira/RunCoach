"""Nothing the app can say is missing from the Portuguese phrase catalogue.

Text reaches a runner from four places — a template, a script, the training
engine, the recipe data — and only the first had a guard
(``test_i18n_keys``, for markup that carries a ``data-i18n`` key). The rest
shipped in English whenever nobody remembered: a toast, a chart label, a
workout description assembled in ``core/training``. The phrase layer
(``app/core/i18n``, ``static/js/i18n.js``) translates all of it by its English
text, which only works while the catalogue keeps up — so this asks, of each
source, whether any sentence would be left as it is.

A failure lists the untranslated text. Add it to a file under
``app/data/i18n/pt/`` (use ``{name}`` / ``{name:n}`` for the parts that vary),
or, if it is not copy a runner reads, to the allow-list beside the scan that
found it.
"""

import ast
import html
import json
import re
from pathlib import Path

import pytest

from app.core.i18n import PhraseBook
from app.infrastructure.i18n import CATALOGUE_DIR, phrasebook

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "app" / "web"
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)(:n|!)?\}")
# Units, brands and tokens that read the same in both languages.
SAME_IN_BOTH = re.compile(
    r"\b(km|min|bpm|kcal|cal|sec|wk|hrs?|mi|ml|mg|kg|vs|VDOT|RunCoach|"
    r"Intervals\.icu|Garmin|COROS|Wahoo|Suunto|Zwift|Google|PDF|GPX|FIT|"
    r"GARMIN|NewFiles|Polar|Apple)\b"
)


@pytest.fixture(scope="module")
def book() -> PhraseBook:
    found = phrasebook("pt")
    assert found is not None, "no Portuguese catalogue under app/data/i18n/pt"
    return found


def _is_copy(text: str) -> bool:
    """Whether ``text`` has words in it once the invariant tokens are gone."""
    bare = SAME_IN_BOTH.sub(" ", PLACEHOLDER.sub(" ", text))
    return bool(re.search(r"[A-Za-z]{3}", bare))


def _missing(book: PhraseBook, texts) -> list[str]:
    out: dict[str, None] = {}
    for text in texts:
        for gap in book.gaps(text):
            if _is_copy(gap):
                out.setdefault(gap)
    return list(out)


# --- the catalogue itself ---------------------------------------------------


def _catalogue_files() -> list[Path]:
    return sorted((CATALOGUE_DIR / "pt").glob("*.json"))


def test_catalogue_is_well_formed():
    assert _catalogue_files(), "no catalogue files found"
    for path in _catalogue_files():
        entries = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(entries, dict) and entries, path.name
        for source, target in entries.items():
            assert isinstance(target, str) and target.strip(), (path.name, source)


def test_a_translation_only_uses_placeholders_its_source_has():
    # "{a} km" -> "{b} km" would print the literal "{b}" on the page.
    broken = []
    for path in _catalogue_files():
        for source, target in json.loads(path.read_text(encoding="utf-8")).items():
            known = {m.group(1) for m in PLACEHOLDER.finditer(source)}
            used = {m.group(1) for m in PLACEHOLDER.finditer(target)}
            if not used <= known:
                broken.append((path.name, source))
    assert not broken, broken


def test_no_sentence_is_translated_two_ways():
    # The browser merges the files; which translation won would depend on the
    # order they arrived in.
    seen: dict[str, tuple[str, str]] = {}
    clashes = []
    for path in _catalogue_files():
        for source, target in json.loads(path.read_text(encoding="utf-8")).items():
            first = seen.setdefault(source, (path.name, target))
            if first[1] != target:
                clashes.append((source, first[0], path.name))
    assert not clashes, clashes


# --- recipes ----------------------------------------------------------------

_RECIPE_FIELDS = (
    "name",
    "description",
    "ingredients",
    "steps",
    "tip",
    "storage",
    "serving_size",
)


def test_every_recipe_is_translated(book: PhraseBook):
    texts = []
    for path in sorted((ROOT / "app" / "data").glob("meals_*.json")):
        for recipe in json.loads(path.read_text(encoding="utf-8")):
            for field in _RECIPE_FIELDS:
                value = recipe.get(field)
                values = value if isinstance(value, list) else [value]
                texts.extend(v for v in values if isinstance(v, str))
    assert len(texts) > 2000, "the recipe scan found almost nothing"
    assert not _missing(book, texts)


# --- generated plan content -------------------------------------------------

# Identifier-valued fields: keys the templates turn into labels themselves.
_PLAN_KEYS_NOT_COPY = re.compile(
    r"(_id|type|kind|intensity|code|status|pace_zone|role|tier|class|"
    r"start_time|phase|focus|level|date|key)$"
)


def _plan_texts(node, key: str = ""):
    if isinstance(node, dict):
        for name, value in node.items():
            yield from _plan_texts(value, name)
    elif isinstance(node, list):
        for value in node:
            yield from _plan_texts(value, key)
    elif isinstance(node, str) and not _PLAN_KEYS_NOT_COPY.search(key):
        yield node


def _sample_custom_plans():
    from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
    from app.core.training.custom_plan import (
        CustomPlanSpec,
        StrengthChoice,
        eligible_options,
        slot_grid,
    )

    for runs, template in ((4, "climb_descent"), (5, "auto")):
        for offset in (0, 3):
            menus = {
                phase: {
                    slot: tuple(
                        o.id
                        for o in eligible_options(phase, slot, target_distance=21.1)
                        if slot.value == "long" or o.id.startswith("ftm_")
                    )[offset : offset + 3]
                    or tuple(
                        o.id
                        for o in eligible_options(phase, slot, target_distance=21.1)
                    )[:3]
                    for slot in slots
                }
                for phase, slots in slot_grid(runs).items()
            }
            spec = CustomPlanSpec(menus=menus, strength=StrengthChoice(2, template))
            yield TrainingPlanGenerator().generate_plan(
                40, 21.1, 14, max_runs_per_week=runs, vdot=48, custom_spec=spec
            )


def _sample_plans():
    from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
    from app.core.training.profiles.backyard_profile import classify_backyard
    from app.core.training.profiles.trail_profile import classify_trail

    generator = TrainingPlanGenerator
    yield generator().generate_plan(0, 5.0, 8, max_runs_per_week=3)
    yield generator().generate_plan(25, 10.0, 12, max_runs_per_week=4, vdot=45)
    yield generator().generate_plan(40, 21.1, 14, max_runs_per_week=5, vdot=50)
    yield generator().generate_plan(
        50, 42.2, 18, max_runs_per_week=5, vdot=48, goal_pace_min_km=5.0
    )
    yield generator().generate_plan(
        60,
        50.0,
        16,
        max_runs_per_week=5,
        terrain="flat",
        trail_profile=classify_trail(50.0, 2500.0),
        intensive_weekend_enabled=True,
    )
    # A custom plan: every long-run shape and Flat to Mountain session, and
    # both strength templates, reach the scan.
    yield from _sample_custom_plans()
    backyard = classify_backyard(24)
    yield generator().generate_plan(
        70,
        backyard.as_trail_profile().distance_km,
        16,
        max_runs_per_week=5,
        backyard_profile=backyard,
    )


def test_generated_plans_are_translated(book: PhraseBook):
    texts = [text for plan in _sample_plans() for text in _plan_texts(plan)]
    assert len(texts) > 1000, "the plan scan found almost nothing"
    assert not _missing(book, texts)


# --- templates --------------------------------------------------------------

_TAG = re.compile(r"<(/?)([a-zA-Z0-9]+)((?:[^<>\"']|\"[^\"]*\"|'[^']*')*)>", re.S)
_VOID = {"br", "img", "input", "meta", "link", "hr", "source", "path", "circle"}
_VOID |= {"rect", "line", "polyline", "polygon", "use", "stop"}
_ATTRIBUTE_GUARD = {
    "title": "data-i18n-title",
    "placeholder": "data-i18n-placeholder",
    "aria-label": "data-i18n-aria",
    "alt": "data-i18n-alt",
}
_TRANSLATABLE_ATTRIBUTE = re.compile(
    r"""\b(title|placeholder|aria-label|alt)=(["'])(.*?)\2""", re.S
)
# The admin console is for the developer and stays in English.
_TEMPLATES_NOT_TRANSLATED = {"admin.html"}
# Template text the scan cannot judge. "{{ level }} Plan" is translated through
# "{level!} Plan", which only matches a level the catalogue knows. The rest are
# pieces a template assembles — a plural "s", a clause behind an {% if %} — into
# a sentence the catalogue holds whole ("{a:n} sessions", "1 session").
_TEMPLATE_TEXT_ALLOWED = {
    "{a} Plan",
    "<!DOCTYPE html>",
    "{a} session{b}",
    "{a} warning{b}",
    "{a} adaptation{b}",
    "{a} day{b}",
    "{a} workout{b} changed across {c} week{d}",
    "Strength Training ({a} session{b})",
    ", starting in the evening so the later loops run in the dark",
}


def _blank(match: re.Match) -> str:
    return "\n" * match.group(0).count("\n")


def _template_texts(source: str):
    """Text nodes and translatable attributes outside ``data-i18n`` elements.

    Jinja expressions become ``{a}``-style placeholders, and each branch of a
    ``{% if %}`` is taken as its own piece of text.
    """
    source = re.sub(r"<(script|style)\b.*?</\1>", _blank, source, flags=re.S)
    source = re.sub(r"\{#.*?#\}|<!--.*?-->", _blank, source, flags=re.S)
    position, stack = 0, []
    for tag in _TAG.finditer(source):
        keyed = any(stack)
        if not keyed:
            yield source[position : tag.start()]
        closing, name, attributes = tag.group(1), tag.group(2).lower(), tag.group(3)
        if not closing:
            if not keyed:
                for match in _TRANSLATABLE_ATTRIBUTE.finditer(attributes):
                    if _ATTRIBUTE_GUARD[match.group(1)] not in attributes:
                        yield match.group(3)
            if name not in _VOID and not attributes.rstrip().endswith("/"):
                stack.append(
                    bool(re.search(r"data-i18n(-html|-skip)?(=|\b)", attributes))
                )
        elif stack:
            stack.pop()
        position = tag.end()


def _as_shapes(raw: str):
    letters = "abcdefghijklmnopqrstuvwxyz"
    for branch in re.split(r"\{%.*?%\}", raw, flags=re.S):
        names = iter(letters)
        shaped = re.sub(
            r"\{\{.*?\}\}", lambda _: "{%s}" % next(names, "z"), branch, flags=re.S
        )
        shaped = " ".join(html.unescape(shaped).split())
        if shaped:
            yield shaped


def _sample(shape: str) -> str:
    """A concrete sentence for a shape: every placeholder becomes ``7``."""
    return re.sub(r"\{[a-z]\}", "7", shape)


def test_template_copy_is_translated(book: PhraseBook):
    missing: dict[str, str] = {}
    scanned = 0
    for path in sorted((WEB / "templates").rglob("*.html")):
        if path.name in _TEMPLATES_NOT_TRANSLATED:
            continue
        for raw in _template_texts(path.read_text(encoding="utf-8")):
            for shape in _as_shapes(raw):
                scanned += 1
                if shape in _TEMPLATE_TEXT_ALLOWED or not _is_copy(shape):
                    continue
                for gap in _missing(book, [_sample(shape)]):
                    missing.setdefault(gap, str(path.relative_to(WEB)))
    assert scanned > 500, "the template scan found almost nothing"
    assert not missing, missing


# --- scripts ----------------------------------------------------------------

_LITERAL = re.compile(r"""(?P<q>['"`])(?P<s>(?:\\.|(?!(?P=q)).)*)(?P=q)""")
_ENTITIES = {
    "&mdash;": "—",
    "&ndash;": "–",
    "&hellip;": "…",
    "&rarr;": "→",
    "&larr;": "←",
    "&middot;": "·",
    "&amp;": "&",
    "&rsquo;": "’",
    "&ldquo;": "“",
    "&rdquo;": "”",
    "&nbsp;": " ",
    "&times;": "×",
    "&darr;": "↓",
}
# String literals that look like sentences to the scan and are not copy:
# keyboard keys, error names, font stacks, browser API names, header names.
_SCRIPT_TEXT_NOT_COPY = {
    "AbortError",
    "Escape",
    "Tab",
    "ArrowRight",
    "ArrowLeft",
    "Home",
    "End",
    "Authorization",
    "Bearer",
    "Notification",
    "PushManager",
    "MacIntel",
    "Building…",
    "Type: {a} ·",
    '"Bricolage Grotesque", Georgia, serif',
    '"DM Sans", sans-serif',
    '"JetBrains Mono", monospace',
    "Change-plan modal not available — falling back.",
    "Change-plan UI unavailable.",
    "Unknown action:",
    "— check logs)",
    # Two halves of one tooltip, joined around a number the scan cannot see
    # past; the catalogue holds the sentence ("Adjusted from {a} km — …").
    "Adjusted from",
    "km — open the latest changes panel for the reason",
}


def _unescape(text: str) -> str:
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    text = text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    text = text.replace("\\'", "'").replace('\\"', '"').replace("\\n", " ")
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    return text


def _reads_as_copy(text: str) -> bool:
    """A heuristic for "a person would read this", as opposed to code."""
    text = text.strip()
    if not re.search(r"[A-Za-z]{3}", text):
        return False
    if text.startswith("<") or re.search(r"\b(class|type|id|data-[a-z-]+)=", text):
        return False  # an opening tag split across lines
    if re.search(r"^(https?:|/|\.|#|data-|aria-|M\d|rgba?\(|var\(|\d+px)", text):
        return False
    if re.search(r"[;{}]\s*$|^\s*(function|return|var|const|let|if)\b|=>", text):
        return False
    words = re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}", text)
    if re.fullmatch(r"[\w\-.#:/\[\]=>*()@%,+!?&|;{}$\s'\"]+", text) and not words:
        return bool(re.fullmatch(r"[A-Z][a-z]{2,}( [a-z]+)*", text))
    if re.fullmatch(r"[a-z0-9\-_ .#>\[\]=:,()*+~\"'{}|^$]+", text):
        return bool(re.search(r"[a-z]{3,} [a-z]{3,} [a-z]{2,}", text))
    return True


def _script_texts(source: str):
    """The text each source line can put on screen.

    Literals joined by ``+`` become one sentence with ``{a}`` where code sits
    between them, ``${…}`` becomes a placeholder, and markup is reduced to
    its text nodes and translatable attributes.
    """
    letters = "abcdefghijklmnopqrstuvwxyz"
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")) or "console." in stripped:
            continue
        line = re.sub(r"\s//\s.*$", "", line)
        names = iter(letters)
        pieces: list[str] = []
        sentences: list[str] = []
        end = None
        for literal in _LITERAL.finditer(line):
            text = re.sub(
                r"\$\{[^}]*\}",
                lambda _: "{%s}" % next(names, "z"),
                _unescape(literal.group("s")),
            )
            gap = line[end : literal.start()] if end is not None else ""
            if end is not None and re.fullmatch(r"\s*\+\s*[^'\"`;]*?\+\s*", gap):
                pieces += ["{%s}" % next(names, "z"), text]
            elif end is not None and re.fullmatch(r"\s*\+\s*", gap):
                pieces.append(text)
            else:
                if pieces:
                    sentences.append("".join(pieces))
                pieces = [text]
            end = literal.end()
        if pieces:
            sentences.append("".join(pieces))
        for sentence in sentences:
            yield from re.split(r"<[^>]*>", sentence)
            yield from re.findall(
                r"""(?:title|placeholder|aria-label|alt)=\\?["']([^"'\\]+)""",
                sentence,
            )


def _script_sources():
    for path in sorted((WEB / "static" / "js").rglob("*.js")):
        # i18n.js is the catalogue; sw.js runs outside any page and cannot
        # read the language (its offline page stays in English).
        if path.name not in {"i18n.js", "sw.js"}:
            yield path, path.read_text(encoding="utf-8")
    for path in sorted((WEB / "templates").rglob("*.html")):
        if path.name in _TEMPLATES_NOT_TRANSLATED:
            continue
        blocks = re.findall(
            r"<script\b[^>]*>(.*?)</script>", path.read_text(encoding="utf-8"), re.S
        )
        yield path, "\n".join(blocks)


def test_script_copy_is_translated(book: PhraseBook):
    missing: dict[str, str] = {}
    scanned = 0
    for path, source in _script_sources():
        for raw in _script_texts(source):
            text = " ".join(raw.split())
            if not _reads_as_copy(text) or text in _SCRIPT_TEXT_NOT_COPY:
                continue
            scanned += 1
            for gap in _missing(book, [_sample(text)]):
                if gap not in _SCRIPT_TEXT_NOT_COPY:
                    missing.setdefault(gap, str(path.relative_to(WEB)))
    assert scanned > 300, "the script scan found almost nothing"
    assert not missing, missing


def test_the_scans_parse_python_they_exercise():
    # Guards the guard: a helper that silently yields nothing would pass.
    assert list(_as_shapes("Week {{ n }} of {{ total }}")) == ["Week {a} of {b}"]
    assert list(_script_texts("x = 'Sync failed: ' + message;"))[0] == "Sync failed: "
    assert ast.literal_eval(repr(_sample("{a} km"))) == "7 km"
