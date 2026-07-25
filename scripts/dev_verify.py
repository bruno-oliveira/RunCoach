#!/usr/bin/env python3
"""Dev server bound to the throwaway verification database, never ./runcoach.db.

Run ``python3 scripts/verify_ui.py`` first — it makes the copy, migrates it, and
prints the session cookie to paste into the browser.

``DATABASE_URL`` is set as an environment variable, so it beats the value in
``.env``, and ``app/migrations/__init__.py`` hands the resulting engine URL to
Alembic — so the startup migrations land on the copy too.

Paths come from ``__file__`` rather than the working directory, so this works
regardless of where it is invoked from.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERIFY_DB = PROJECT_ROOT / ".verify" / "runcoach.db"


def main() -> None:
    if not VERIFY_DB.exists():
        sys.exit(
            f"no verification database at {VERIFY_DB}\n"
            "run: python3 scripts/verify_ui.py"
        )

    os.chdir(PROJECT_ROOT)
    # Run as `scripts/dev_verify.py`, sys.path[0] is scripts/ — so `app` is not
    # importable until the project root is on the path.
    sys.path.insert(0, str(PROJECT_ROOT))
    os.environ["DATABASE_URL"] = f"sqlite:///{VERIFY_DB}"
    port = int(os.environ.get("PORT", "8011"))
    print(f"serving on :{port} against {os.environ['DATABASE_URL']}", flush=True)

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
