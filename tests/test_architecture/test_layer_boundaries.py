"""Architecture guardrails for the layer dependency direction.

``test_context_boundaries`` keeps sibling *contexts* apart. This keeps the
*layers* apart — the rest of the rule in CLAUDE.md, which used to hold by
convention only::

    web -> application -> contexts -> core / domain

and had drifted the way conventions do: the post-sync orchestration lived in
``infrastructure`` and imported two contexts, a plan-context module rendered
Jinja templates, and ``core`` reached SQLAlchemy through a grab-bag
``app/utils.py``.

Like the context guard, the layer rules check *module-level* imports: those
are the edges that couple the import graphs. ``core`` is held to more — it is
checked at every depth, because "pure" is a property of the code, not of when
it happens to be imported.

``KNOWN_EXCEPTIONS`` is a ratchet. It lists the edges still to be removed, and
a stale entry fails the build, so it can only shrink.
"""

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "app"

WEB_FRAMEWORK = ("fastapi", "starlette")

# Layer directory -> import prefixes it must not reach at module scope.
FORBIDDEN_AT_MODULE_SCOPE: dict[str, tuple[str, ...]] = {
    "domain": (
        "app.contexts",
        "app.application",
        "app.infrastructure",
        "app.web",
        "app.dependencies",
        "app.models",
        "app.schemas",
        "sqlalchemy",
        *WEB_FRAMEWORK,
    ),
    "models": (
        "app.contexts",
        "app.application",
        "app.infrastructure",
        "app.web",
        "app.dependencies",
        "app.schemas",
        *WEB_FRAMEWORK,
    ),
    "schemas": (
        "app.contexts",
        "app.application",
        "app.infrastructure",
        "app.web",
        "app.dependencies",
        *WEB_FRAMEWORK,
    ),
    "contexts": (
        "app.application",
        "app.infrastructure",
        "app.web",
        "app.dependencies",
        *WEB_FRAMEWORK,
    ),
    "infrastructure": (
        "app.contexts",
        "app.application",
        "app.web",
        "app.dependencies",
    ),
    "application": ("app.web", "app.dependencies"),
}

# ``core`` is pure: no I/O, no ORM, no framework, nothing above it — at any
# depth, deferred imports included.
FORBIDDEN_IN_CORE = (
    "app.contexts",
    "app.application",
    "app.infrastructure",
    "app.web",
    "app.dependencies",
    "app.models",
    "app.schemas",
    "sqlalchemy",
    *WEB_FRAMEWORK,
)

# Settings are read everywhere and import nothing from the app, so the config
# module is a leaf any layer may depend on.
ALLOWED_EVERYWHERE = ("app.infrastructure.config",)

# (file, imported prefix) -> why it is still here. Remove the entry with the edge.
KNOWN_EXCEPTIONS: dict[tuple[str, str], str] = {
    (
        "app/infrastructure/integrations/intervals_service.py",
        "app.contexts",
    ): (
        "IntervalsService is both the HTTP client and the run importer; the "
        "importer half (which enriches and scores each run) belongs in "
        "app/application once the two are split."
    ),
    (
        "app/contexts/plan/plan_template_context.py",
        "fastapi",
    ): "Takes the Request only to put it in the template context.",
    (
        "app/contexts/runner/enrichment/run_creation_service.py",
        "fastapi",
    ): (
        "Raises HTTPException for an ownership failure; should raise from the "
        "RunCoachException hierarchy and let the global handler map it."
    ),
}

# The only modules that may sit at the root of ``app/``. Anything else has no
# layer, which is how ``utils.py`` came to be imported by all of them.
ROOT_MODULES = {"__init__.py", "main.py", "exceptions.py"}


def _imports(path: pathlib.Path, *, module_scope_only: bool):
    """Yield the modules a file imports.

    With ``module_scope_only`` only top-level statements count, so imports
    inside functions and under ``if TYPE_CHECKING:`` are skipped.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = tree.body if module_scope_only else ast.walk(tree)
    for node in nodes:
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def _matches(target: str, prefix: str) -> bool:
    return target == prefix or target.startswith(prefix + ".")


def _violations(
    layer: str, forbidden: tuple[str, ...], *, module_scope_only: bool
) -> set[tuple[str, str]]:
    """``(file, forbidden prefix)`` pairs for every offending import in a layer."""
    found: set[tuple[str, str]] = set()
    for path in sorted((APP / layer).rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for target in _imports(path, module_scope_only=module_scope_only):
            if any(_matches(target, ok) for ok in ALLOWED_EVERYWHERE):
                continue
            for prefix in forbidden:
                if _matches(target, prefix):
                    found.add((rel, prefix))
    return found


def _all_violations() -> set[tuple[str, str]]:
    found = _violations("core", FORBIDDEN_IN_CORE, module_scope_only=False)
    for layer, forbidden in FORBIDDEN_AT_MODULE_SCOPE.items():
        found |= _violations(layer, forbidden, module_scope_only=True)
    return found


def test_layers_only_depend_downward():
    """No layer imports a layer above it (or beside it, where the rule says so)."""
    unexpected = sorted(_all_violations() - set(KNOWN_EXCEPTIONS))
    assert not unexpected, (
        "Layer dependency direction violated (web -> application -> contexts "
        "-> core / domain). Move the code to the layer that owns it, or go "
        "through app/application:\n  "
        + "\n  ".join(f"{file}: imports {prefix}" for file, prefix in unexpected)
    )


def test_known_exceptions_are_still_exceptions():
    """The ratchet only closes: an edge that is gone must leave the list."""
    stale = sorted(set(KNOWN_EXCEPTIONS) - _all_violations())
    assert not stale, (
        "These layer exceptions no longer exist — delete them from "
        "KNOWN_EXCEPTIONS so they cannot come back unnoticed:\n  "
        + "\n  ".join(f"{file}: {prefix}" for file, prefix in stale)
    )


def test_every_module_belongs_to_a_layer():
    """Nothing new at the root of ``app/``: a module there has no layer."""
    loose = {p.name for p in APP.glob("*.py")} - ROOT_MODULES
    assert not loose, (
        "Modules at the root of app/ belong to no layer, so every layer ends "
        f"up importing them. Put these in the package that owns them: {sorted(loose)}"
    )
