#!/usr/bin/env python3
"""Set up a throwaway database copy for browser-based UI verification.

Verifying a UI change usually needs a signed-in user with a live plan. The
tempting shortcut is to edit ``runcoach.db`` directly — don't. That file holds
real dev data, there is no seed file and no WAL backup beside it, and an
``UPDATE`` without a preceding ``SELECT`` is unrecoverable. It has cost a
developer their local Intervals connection once already.

This script gives you the same setup without touching the original:

    python3 scripts/verify_ui.py

It copies the database, migrates the copy to head, adds a throwaway user and a
plan that started a week ago (so "this week" is populated and the plan isn't
complete), mints a session token, and prints what you need. Then:

    # start the server against the copy
    python3 scripts/dev_verify.py       # or preview_start({name: "runcoach-verify"})

    # in the browser console, on the server's origin:
    document.cookie = "access_token=<TOKEN>; path=/; SameSite=Lax"

The source database is only ever opened for reading, via a file copy. ``--check``
prints its hash so you can prove it didn't change across a session.

Existing rows in the copy are never modified: the throwaway user and plan are
new rows with fixed, recognisable ids, dropped and rebuilt on each run.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = PROJECT_ROOT / "runcoach.db"
VERIFY_DIR = PROJECT_ROOT / ".verify"
VERIFY_DB = VERIFY_DIR / "runcoach.db"

# Fixed ids so repeated runs replace their own rows instead of accumulating, and
# so anything they leave behind is obviously not real data.
USER_ID = "verify-user"
USER_EMAIL = "verify@localhost"
PLAN_ID = "verify-plan"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def guard_target(target: Path) -> None:
    """Refuse to operate on the real database, however we got pointed at it."""
    if not SOURCE_DB.exists():
        return
    if target.resolve() == SOURCE_DB.resolve():
        sys.exit(
            f"refusing to write to the real database at {SOURCE_DB}.\n"
            "This script only ever writes to a copy."
        )


def copy_database(target: Path) -> None:
    guard_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not SOURCE_DB.exists():
        print(f"note: {SOURCE_DB} does not exist — starting from an empty copy")
        target.unlink(missing_ok=True)
        return
    # copy2 preserves mtime, and read-only access to the source is the point.
    shutil.copy2(SOURCE_DB, target)
    for suffix in ("-wal", "-shm"):
        sidecar = SOURCE_DB.with_name(SOURCE_DB.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, target.with_name(target.name + suffix))
    print(f"copied {SOURCE_DB.name} -> {target}")


def migrate(target: Path) -> None:
    """Bring the copy to head, in-process so alembic.ini's URL can't interfere."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{target}")
    command.upgrade(cfg, "head")
    print("migrated the copy to head")


def _template_plan(conn: sqlite3.Connection) -> dict | None:
    """A real plan to clone, so the page renders against realistic plan_data."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "select * from training_plans "
        "where plan_data is not null and id != ? "
        "order by created_at desc limit 1",
        (PLAN_ID,),
    ).fetchone()
    return dict(row) if row else None


def seed(target: Path, weeks_in: int) -> str:
    """Add the throwaway user and plan; return a session token for them."""
    guard_target(target)
    conn = sqlite3.connect(target)

    template = _template_plan(conn)
    if template is None:
        sys.exit(
            "no plan with plan_data found to clone. Generate one through the UI "
            "first, or point this script at a database that has one."
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # last_activity must be recent or _resolve_user rejects the session as timed
    # out and every page 403s — the least obvious part of this setup.
    conn.execute("delete from training_plans where id = ?", (PLAN_ID,))
    conn.execute("delete from users where id = ?", (USER_ID,))
    # created_at / plans_generated are NOT NULL as far as ``UserResponse`` is
    # concerned even though the columns allow null — leaving them unset makes
    # every /api/auth/me and settings save 500 on validation, which looks like a
    # bug in whatever you're verifying rather than in this fixture.
    conn.execute(
        "insert into users (id, email, name, last_activity, created_at, "
        "plans_generated) values (?, ?, ?, ?, ?, ?)",
        (
            USER_ID,
            USER_EMAIL,
            "Verify User",
            now.isoformat(sep=" "),
            now.isoformat(sep=" "),
            1,
        ),
    )

    plan = dict(template)
    plan["id"] = PLAN_ID
    plan["user_id"] = USER_ID
    plan["created_at"] = now.isoformat(sep=" ")
    plan["start_date"] = (
        datetime.combine(date.today(), datetime.min.time())
        - timedelta(days=7 * weeks_in)
    ).isoformat(sep=" ")
    plan["share_token"] = None
    for column in ("watch_synced_at", "watch_event_hashes", "watch_sync_error"):
        if column in plan:
            plan[column] = None
    if "watch_sync_enabled" in plan:
        plan["watch_sync_enabled"] = 0

    columns = ",".join(plan)
    placeholders = ",".join("?" * len(plan))
    conn.execute(
        f"insert into training_plans ({columns}) values ({placeholders})",
        list(plan.values()),
    )
    conn.commit()
    conn.close()

    # Signed with the same SECRET_KEY the server reads from .env, so the cookie
    # is accepted by a server started from this project root.
    os.environ["DATABASE_URL"] = f"sqlite:///{target}"
    from app.contexts.auth.auth_service import AuthService

    return AuthService().create_access_token({"sub": USER_ID})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="print the real database's hash and exit (proves it is unchanged)",
    )
    parser.add_argument(
        "--weeks-in",
        type=int,
        default=1,
        help="how many weeks into the plan today should be (default 1)",
    )
    parser.add_argument("--port", type=int, default=8011, help="dev server port")
    args = parser.parse_args()

    if args.check:
        print(
            f"{SOURCE_DB.name}: {sha256(SOURCE_DB) if SOURCE_DB.exists() else 'absent'}"
        )
        return

    before = sha256(SOURCE_DB) if SOURCE_DB.exists() else None
    copy_database(VERIFY_DB)
    migrate(VERIFY_DB)
    token = seed(VERIFY_DB, args.weeks_in)
    after = sha256(SOURCE_DB) if SOURCE_DB.exists() else None
    if before != after:
        sys.exit("BUG: the real database changed. Investigate before continuing.")

    print()
    print(f"real database unchanged (sha256 {(before or 'n/a')[:16]}…)")
    print(f"DATABASE_URL   sqlite:///{VERIFY_DB}")
    print(f"user           {USER_EMAIL} ({USER_ID})")
    print(f"plan url       http://localhost:{args.port}/plan/{PLAN_ID}")
    print()
    print("start the server:  python3 scripts/dev_verify.py")
    print("then in the browser console, on that origin:")
    print(f'  document.cookie = "access_token={token}; path=/; SameSite=Lax"')


if __name__ == "__main__":
    main()
