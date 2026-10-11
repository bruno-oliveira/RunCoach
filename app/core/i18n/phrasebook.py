"""English sentence in, translated sentence out.

Most of what a runner reads is not written in a template: a workout
description is assembled in ``core/training`` with the distances baked in, kept
in the plan's JSON snapshot, and then printed by a page, a PDF, an email and
the watch. Translating at each of those call sites would mean threading a
language through the training science, and it could never reach a plan that was
already saved. So the catalogue is keyed by the English text itself, gettext
style, and is applied where the text is *shown*.

An entry is either an exact sentence or a pattern::

    "Rest day": "Dia de descanso"
    "Week {n:n} of {total:n}": "Semana {n} de {total}"

``{name}`` matches any text and ``{name:n}`` a number; a captured value is
itself looked up, so ``"{level} Plan"`` translates the level too. ``{name!}``
matches only text the catalogue can translate, which is what makes a pattern as
loose as ``"{a!} and {b!}"`` safe: it joins two known phrases and declines
everything else. A phrase that opens a sentence is found under its lower-case
entry, so ``"your legs are heavy"`` is written once; a heading set in capitals
(``"RACE DAY"``) is found under its ordinary spelling and capitalised again.
Failing all of those, case is ignored altogether — the watch titles its
workouts ``"400S Into 200S"`` — and the translation is used as catalogued.
Text that
matches nothing whole is tried in pieces — the parts of an ``a · b`` line, then
its sentences — because generated prose is mostly known sentences in a new
order. Whatever still matches nothing is returned unchanged: an English
sentence is a visible gap, a half-substituted one would be a wrong statement.

``static/js/i18n.js`` implements the same rules; ``tests/test_core/
test_phrasebook.py`` holds the cases both must satisfy.
"""

import re
from collections.abc import Mapping

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)(:n|!)?\}")
_NUMBER = r"[-+−]?[0-9][0-9.,:]*"
# What ``{name}`` may capture: anything that stays inside one sentence and one
# side of an ``a · b`` line. Without the limit a pattern ending in a
# placeholder swallows whatever follows it — the next sentence, the rest of
# the line — and that text is then never translated.
_TEXT = r"(?:(?![.!?…][\"”')]?\s| · ).)+?"
_WHITESPACE = re.compile(r"\s+")
# Decoration carried around a phrase rather than translated with it: a leading
# emoji, bullet or arrow, a trailing colon or chevron.
_LEAD = re.compile(r"^[^\w(\[{\"'“‘«]+")
_TRAIL = re.compile(r"[\s:…→←↑↓›»▾▸*]+$")
_DOT_SEPARATOR = re.compile(r"( · )")
_SENTENCE_END = re.compile(r"([.!?…]+[\"”')]?\s+)")
_FIRST_WORD = re.compile(r"^\w+")


class PhraseBook:
    """A catalogue of ``{english: translation}`` entries and its matcher."""

    def __init__(self, entries: Mapping[str, str]) -> None:
        self._exact: dict[str, str] = {}
        self._exact_any_case: dict[str, str] = {}
        patterns: list[_Pattern] = []
        for source, target in entries.items():
            source = _normalize(source)
            if not _PLACEHOLDER.search(source):
                self._exact[source] = target
                self._exact_any_case.setdefault(source.lower(), target)
                continue
            regex, names, required, literal = _compile(source)
            head = _FIRST_WORD.match(source)
            patterns.append(
                (
                    literal,
                    head.group(0) if head else None,
                    regex,
                    target,
                    names,
                    required,
                )
            )
        # Most literal text first, so the specific pattern wins over the
        # general one whatever order the catalogue files were read in.
        patterns.sort(key=lambda p: -p[0])
        self._anywhere = [p for p in patterns if p[1] is None]
        self._by_head: dict[str, list] = {}
        self._by_head_any_case: dict[str, list] = {}
        for pattern in patterns:
            if pattern[1] is not None:
                self._by_head.setdefault(pattern[1], []).append(pattern)
                self._by_head_any_case.setdefault(pattern[1].lower(), []).append(
                    pattern
                )
        self._any_case: dict[str, re.Pattern[str]] = {}
        self._cache: dict[str, str | None] = {}

    def __len__(self) -> int:
        return (
            len(self._exact)
            + sum(len(v) for v in self._by_head.values())
            + len(self._anywhere)
        )

    def translate(self, text: str) -> str:
        """Translate ``text``, returning it unchanged when nothing matches."""
        found = self.lookup(text)
        return text if found is None else found

    def lookup(self, text: str) -> str | None:
        """Translate ``text``, or ``None`` when no part of it is known."""
        if not text or not text.strip():
            return None
        body = text.strip()
        start = text.index(body)
        key = _normalize(body)
        if key not in self._cache:
            self._cache[key] = self._chunk(key)
        found = self._cache[key]
        if found is None:
            return None
        return text[:start] + found + text[start + len(body) :]

    def gaps(self, text: str) -> list[str]:
        """The pieces of ``text`` this book would leave in English.

        Empty when the text translates whole. Used by the coverage tests,
        which ask of every sentence the app can produce: is anything left?
        """
        return self._gaps(_normalize(text)) if text and text.strip() else []

    def _gaps(self, text: str) -> list[str]:
        if self._unit(text) is not None:
            return []
        for split in (_split_on_dots, _split_sentences):
            parts = split(text)
            if len(parts) > 1:
                return [gap for part, _ in parts for gap in self._gaps(part)]
        return [text]

    def _chunk(self, text: str) -> str | None:
        found = self._unit(text)
        if found is not None:
            return found
        for split in (_split_on_dots, _split_sentences):
            parts = split(text)
            if len(parts) < 2:
                continue
            out, hit = [], False
            for part, separator in parts:
                translated = self._chunk(part)
                hit = hit or translated is not None
                out.append((part if translated is None else translated) + separator)
            if hit:
                return "".join(out)
        return None

    def _unit(self, text: str) -> str | None:
        found = self._cased(text)
        if found is not None:
            return found
        lead = _LEAD.match(text)
        start = lead.end() if lead else 0
        trail = _TRAIL.search(text, start)
        end = trail.start() if trail else len(text)
        if text.startswith("(") and text.endswith(")"):
            start, end = 1, len(text) - 1
        if (start, end) == (0, len(text)) or start >= end:
            return None
        found = self._cased(text[start:end])
        return None if found is None else text[:start] + found + text[end:]

    def _cased(self, text: str) -> str | None:
        """Match ``text`` as written, or as a known phrase in another case."""
        found = self._match(text)
        if found is not None:
            return found
        if text[:1].isupper() and text[1:2].isupper():
            found = self._in_capitals(text)
        elif text[:1].isupper():
            # "Your legs are heavy" is the entry "your legs are heavy" opening
            # a sentence.
            found = self._match(text[0].lower() + text[1:])
            if found is not None:
                found = found[:1].upper() + found[1:]
        return self._match(text, any_case=True) if found is None else found

    def _in_capitals(self, text: str) -> str | None:
        """``"RACE DAY"`` is ``"Race day"`` (or ``"Race Day"``) set in capitals.

        Only for text that is capitals throughout: a lone acronym (VDOT) has
        no ordinary spelling to find, and falls through untouched.
        """
        if text != text.upper() or text == text.lower():
            return None
        lowered = text.lower()
        for spelling in (
            lowered[:1].upper() + lowered[1:],
            " ".join(word[:1].upper() + word[1:] for word in lowered.split(" ")),
            lowered,
        ):
            found = self._match(spelling)
            if found is not None:
                return found.upper()
        return None

    def _match(self, text: str, any_case: bool = False) -> str | None:
        if any_case:
            exact = self._exact_any_case.get(text.lower())
        else:
            exact = self._exact.get(text)
        if exact is not None:
            return exact
        head = _FIRST_WORD.match(text)
        if not head:
            candidates = []
        elif any_case:
            candidates = self._by_head_any_case.get(head.group(0).lower(), [])
        else:
            candidates = self._by_head.get(head.group(0), [])
        for _, _, regex, target, names, required in (*candidates, *self._anywhere):
            if any_case:
                regex = self._ignoring_case(regex)
            match = regex.fullmatch(text)
            if match is None:
                continue
            values: dict[str, str] = {}
            for name in names:
                captured = match.group(name)
                if name not in required:
                    values[name] = self._value(captured)
                    continue
                known = self._unit(captured)
                if known is None:
                    break
                values[name] = known
            else:
                return _PLACEHOLDER.sub(
                    lambda m: values.get(m.group(1), m.group(0)), target
                )
        return None

    def _ignoring_case(self, regex: re.Pattern[str]) -> re.Pattern[str]:
        """The same pattern, case-insensitive — compiled on first need."""
        found = self._any_case.get(regex.pattern)
        if found is None:
            found = re.compile(regex.pattern, regex.flags | re.IGNORECASE)
            self._any_case[regex.pattern] = found
        return found

    def _value(self, captured: str) -> str:
        if re.fullmatch(_NUMBER, captured):
            return captured
        found = self._unit(captured)
        return captured if found is None else found


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


_Pattern = tuple[int, str | None, re.Pattern[str], str, list[str], set[str]]


def _compile(source: str) -> tuple[re.Pattern[str], list[str], set[str], int]:
    """Turn ``"Week {n:n}"`` into a regex, its names, and its literal length.

    Also returns the names marked ``!``: captures that must translate.
    """
    parts, names, literal, position = [], [], 0, 0
    required: set[str] = set()
    for match in _PLACEHOLDER.finditer(source):
        text = source[position : match.start()]
        literal += len(text)
        parts.append(re.escape(text))
        name = match.group(1)
        if name in names:
            parts.append(f"(?P={name})")
        else:
            names.append(name)
            if match.group(2) == "!":
                required.add(name)
            numeric = match.group(2) == ":n"
            parts.append(f"(?P<{name}>{_NUMBER if numeric else _TEXT})")
        position = match.end()
    tail = source[position:]
    literal += len(tail)
    parts.append(re.escape(tail))
    return re.compile("".join(parts), re.DOTALL), names, required, literal


def _split_on_dots(text: str) -> list[tuple[str, str]]:
    return _pairs(_DOT_SEPARATOR.split(text))


def _split_sentences(text: str) -> list[tuple[str, str]]:
    """Split into sentences, each keeping its closing punctuation."""
    out = []
    for part, separator in _pairs(_SENTENCE_END.split(text)):
        closing = separator.rstrip()
        out.append((part + closing, separator[len(closing) :]))
    return out


def _pairs(tokens: list[str]) -> list[tuple[str, str]]:
    """Group ``re.split`` output (text, separator, text, …) into pairs."""
    pairs = []
    for index in range(0, len(tokens), 2):
        separator = tokens[index + 1] if index + 1 < len(tokens) else ""
        if tokens[index] or separator:
            pairs.append((tokens[index], separator))
    return pairs
