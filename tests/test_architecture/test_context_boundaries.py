"""Architecture guardrail for the plan context's dependency direction.

Enforces the dependency rule from CLAUDE.md: the ``plan`` bounded context must
not depend on a sibling context (runner / nutrition / auth) at module load time.
Cross-context collaboration is allowed via the application layer
(``app/application/``) or via deferred (local / ``TYPE_CHECKING``) imports — so
this checks only *module-level* (eager) import edges, which are the ones that
couple the contexts' import graphs.

Scope note: this guards the ``plan`` context specifically (cleaned up in the
maintainability refactor). The ``runner`` context still has module-level edges
into ``plan``/``nutrition``/``auth`` — decoupling it is tracked as separate work.
"""

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAN_DIR = REPO_ROOT / "app" / "contexts" / "plan"
FORBIDDEN_PREFIXES = (
    "app.contexts.runner",
    "app.contexts.nutrition",
    "app.contexts.auth",
)


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


def test_plan_context_has_no_module_level_sibling_imports():
    violations: list[str] = []
    for path in PLAN_DIR.rglob("*.py"):
        for target in _module_level_import_targets(path):
            if target.startswith(FORBIDDEN_PREFIXES):
                violations.append(f"{path.relative_to(REPO_ROOT)}: {target}")

    assert not violations, (
        "The plan context must not import sibling contexts at module level "
        "(use app/application/ or a deferred/TYPE_CHECKING import):\n  "
        + "\n  ".join(sorted(violations))
    )
