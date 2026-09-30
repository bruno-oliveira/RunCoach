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


def _pin(spec: str) -> str | None:
    """The exact version in ``spec``, or None when it is not an exact pin."""
    match = re.search(r"==\s*([^,\s]+)", spec)
    return match.group(1) if match else None


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

    def test_pyproject_requires_python_matches_the_shipped_runtime(self):
        """CI, the Dockerfile and Fly all run 3.12, so that is the floor."""
        data = tomllib.loads(PYPROJECT.read_text())

        assert data["project"]["requires-python"] == ">=3.12"

    @staticmethod
    def _pyproject_specs() -> dict[str, str]:
        data = tomllib.loads(PYPROJECT.read_text())
        specs = list(data["project"]["dependencies"])
        for extra in data["project"].get("optional-dependencies", {}).values():
            specs.extend(extra)
        return {_name(spec).lower(): spec for spec in specs}

    def test_pyproject_pins_the_same_versions_as_requirements(self):
        """A lock is only useful if it describes what actually ships.

        requirements.txt is what CI and the Docker image install with pip, so it
        is authoritative; pyproject must pin the same versions or `uv lock`
        resolves to a set nobody runs — which is exactly how `uv.lock` came to
        hold `fastapi` 0.136.0 while CI installed 0.115.12, and how it ended up
        with no `anthropic` entry at all.
        """
        pyproject = self._pyproject_specs()
        mismatches = []
        for _, spec in _requirement_lines():
            name = _name(spec).lower()
            declared = pyproject.get(name)
            if declared is None:
                mismatches.append(f"{name}: in requirements.txt, not pyproject.toml")
            elif _pin(declared) != _pin(spec):
                mismatches.append(
                    f"{name}: pyproject.toml says {_pin(declared)!r}, "
                    f"requirements.txt says {_pin(spec)!r}"
                )

        assert not mismatches, (
            "requirements.txt is authoritative — mirror it in pyproject.toml: "
            f"{mismatches}"
        )

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
