"""Architecture guardrails for bounded-context dependency direction.

Enforces the dependency rule from CLAUDE.md: a bounded context must not depend
on a sibling context at module load time. Cross-context collaboration is allowed
via the application layer (``app/application/``), or via deferred (local /
``TYPE_CHECKING``) imports — so this checks only *module-level* (eager) import
edges, which are the ones that couple the contexts' import graphs.
"""

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTEXTS = REPO_ROOT / "app" / "contexts"


def _context_names() -> list[str]:
    return [
        p.name for p in CONTEXTS.iterdir() if p.is_dir() and not p.name.startswith("_")
    ]


def _module_level_import_targets(path: pathlib.Path):
    """Yield modules imported at the top level of a file (not nested in
    functions or ``if TYPE_CHECKING:`` blocks)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in tree.body:  # top-level statements only
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def test_no_module_level_sibling_context_imports():
    """No bounded context imports a sibling context eagerly at module scope."""
    names = _context_names()
    violations: list[str] = []
    for context_dir in CONTEXTS.iterdir():
        if not context_dir.is_dir() or context_dir.name.startswith("_"):
            continue
        forbidden = tuple(f"app.contexts.{n}" for n in names if n != context_dir.name)
        for path in context_dir.rglob("*.py"):
            for target in _module_level_import_targets(path):
                if target.startswith(forbidden):
                    violations.append(f"{path.relative_to(REPO_ROOT)}: {target}")

    assert not violations, (
        "Bounded contexts must not import sibling contexts at module level "
        "(use app/application/ or a deferred/TYPE_CHECKING import):\n  "
        + "\n  ".join(sorted(violations))
    )
