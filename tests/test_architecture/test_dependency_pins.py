"""Repo-contract guardrails for dependency declarations.

CI's premise is that `pip install -r requirements.txt` installs *the exact
versions that ship*. A floating `>=` in that file quietly breaks the premise:
CI resolves the newest match, which is not the version anyone tested, and it can
change under a repo nobody touched.

That is not hypothetical here. `anthropic>=0.40.0` resolved to a 1.x release
whose `Messages.create` no longer takes `temperature`; the adapter passed it,
the SDK raised `TypeError`, and the Coach's Note swallowed the error and fell
back forever — green CI, dead feature.
"""

import pathlib
import re
import tomllib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REQUIREMENTS = REPO_ROOT / "requirements.txt"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Lines that are deliberately not exact pins: pytest-cov's floor is a
# test-tooling lower bound where the CI job itself is what pins ruff.
_ALLOWED_NON_PINS: set[str] = {"pytest-cov"}


def _requirement_lines() -> list[tuple[int, str]]:
    lines = []
    for number, raw in enumerate(REQUIREMENTS.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append((number, line))
    return lines


def _name(spec: str) -> str:
    return re.split(r"[=<>!\[]", spec, maxsplit=1)[0].strip()


class TestRequirementsArePinned:
    def test_every_requirement_is_an_exact_pin(self):
        """`==` only. A `>=` means CI installs something nobody tested."""
        floating = [
            (number, spec)
            for number, spec in _requirement_lines()
            if "==" not in spec and _name(spec) not in _ALLOWED_NON_PINS
        ]

        assert not floating, (
            "requirements.txt must pin with == so CI installs what ships; "
            f"floating: {floating}"
        )

    def test_the_file_actually_declares_dependencies(self):
        """Guards the test above from passing on an empty/renamed file."""
        specs = [spec for _, spec in _requirement_lines()]

        assert len(specs) >= 10
        assert any(spec.startswith("sqlalchemy") for spec in specs)

    def test_anthropic_is_pinned(self):
        """The specific package whose floating constraint caused a silent outage."""
        pinned = [
            spec for _, spec in _requirement_lines() if _name(spec) == "anthropic"
        ]

        assert len(pinned) == 1
        assert "==" in pinned[0], f"anthropic must be pinned: {pinned[0]}"


class TestRequirementsAndPyprojectAgree:
    """CLAUDE.md: a new dependency goes in *both* files."""

    @staticmethod
    def _pyproject_dependency_names() -> set[str]:
        # Parsed as TOML, not with string splitting: `uvicorn[standard]>=0.34.3`
        # contains a `]`, which truncates any naive block extraction (that bug
        # made five correctly-declared packages look missing).
        data = tomllib.loads(PYPROJECT.read_text())
        return {_name(spec).lower() for spec in data["project"]["dependencies"]}

    def test_pyproject_declares_the_runtime_dependencies(self):
        names = self._pyproject_dependency_names()

        assert {"fastapi", "sqlalchemy", "anthropic", "gpxpy"} <= names

    def test_pyproject_requires_python_matches_the_classifiers(self):
        data = tomllib.loads(PYPROJECT.read_text())

        assert data["project"]["requires-python"] == ">=3.11"

    @pytest.mark.parametrize(
        "package",
        ["fastapi", "sqlalchemy", "anthropic", "gpxpy", "httpx", "reportlab"],
    )
    def test_a_declared_dependency_is_in_both_files(self, package):
        in_pyproject = package in self._pyproject_dependency_names()
        in_requirements = any(
            _name(spec).lower() == package for _, spec in _requirement_lines()
        )

        assert in_pyproject and in_requirements, (
            f"{package}: requirements.txt={in_requirements}, "
            f"pyproject.toml={in_pyproject} — declare it in both"
        )
