"""The phrase matcher, and the proof that its two implementations agree.

``phrase_cases.json`` is the contract. The Python matcher translates emails,
pushes, the PDF and watch workouts; ``static/js/i18n.js`` carries a port of it
for the page. A sentence that came out differently in the two would read one
way in the app and another in the inbox, so both are run over the same cases —
the JavaScript one through ``node`` where there is one.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.i18n import PhraseBook

HERE = Path(__file__).resolve().parent
CASES = json.loads((HERE / "phrase_cases.json").read_text(encoding="utf-8"))
I18N_JS = HERE.parents[1] / "app" / "web" / "static" / "js" / "i18n.js"

_NODE_RUNNER = """
global.window = {};
const [script, cases] = process.argv.slice(-2);
require(script);
const fixture = JSON.parse(require('fs').readFileSync(cases, 'utf8'));
const matcher = window.RC_I18N._matcher;
const book = matcher.build(fixture.entries);
process.stdout.write(JSON.stringify(fixture.cases.map(c => matcher.lookup(book, c[0]))));
"""


@pytest.fixture(scope="module")
def book() -> PhraseBook:
    return PhraseBook(CASES["entries"])


@pytest.mark.parametrize(("text", "expected"), CASES["cases"])
def test_lookup(book: PhraseBook, text: str, expected: str | None):
    assert book.lookup(text) == expected


def test_translate_returns_the_text_when_nothing_matches(book: PhraseBook):
    assert book.translate("Unknown thing") == "Unknown thing"
    assert book.translate("Rest day") == "Dia de descanso"


def test_the_specific_pattern_wins_whatever_the_order():
    entries = {"{a} run": "corrida {a}", "Easy {a}": "{a} fácil", "Easy run": "x"}
    assert PhraseBook(entries).lookup("Easy run") == "x"
    general_first = {"{a} of {b}": "{a} de {b}", "Week {a:n} of {b:n}": "S{a}/{b}"}
    assert PhraseBook(general_first).lookup("Week 1 of 9") == "S1/9"


def test_a_number_placeholder_refuses_words():
    assert PhraseBook({"Week {n:n}": "Semana {n}"}).lookup("Week two") is None


def test_javascript_matcher_agrees_with_python():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    result = subprocess.run(
        [node, "-e", _NODE_RUNNER, str(I18N_JS), str(HERE / "phrase_cases.json")],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    got = json.loads(result.stdout)
    expected = [case[1] for case in CASES["cases"]]
    assert got == expected
