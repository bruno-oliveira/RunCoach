"""Spike: push a structured workout to Intervals.icu (send-to-watch tester).

Runs the send-to-watch path end to end WITHOUT the app's OAuth, using an
Intervals.icu personal API key (Settings page, bottom). Use it to confirm the
converter output and that pace targets survive the push to Garmin.

Auth: Intervals.icu API key with HTTP basic auth as ``API_KEY:<key>``.

Setup:
    export INTERVALS_API_KEY=xxxxxxxx           # personal API key
    export INTERVALS_ATHLETE_ID=i12345          # your athlete id (i-prefixed)

Usage:
    # Print the generated workout text only (no network):
    python scripts/send_to_watch_spike.py --dry-run

    # Push a built-in sample interval workout to your calendar (today):
    python scripts/send_to_watch_spike.py --apply

    # Push a real plan day pulled from the local DB:
    python scripts/send_to_watch_spike.py --plan <PLAN_ID> --week 3 --day 3 --apply

Once it appears on your Intervals.icu calendar, check it lands on the watch.
Requirements for pace targets to reach Garmin:
  * Garmin linked + "Upload planned workouts" enabled in Intervals.icu.
  * A Run **threshold pace** set in Intervals.icu (Settings -> sport settings).
    Without it, Intervals silently drops per-step pace targets from the Garmin
    export and the watch shows "No target".
This script deletes any existing event with the same external_id before
recreating it, because updating a planned workout in place does not re-trigger
the Garmin export.
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.training.workout_steps.intervals_export import build_intervals_workout

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

INTERVALS_API_BASE = "https://intervals.icu/api/v1"

# A representative quality session used when no --plan is given.
_SAMPLE_DAY = {
    "type": "interval",
    "key_workout_name": "5K VO2max 1000s",
    "distance": 9.0,
    "steps": [
        {"kind": "warmup", "distance_m": 2000, "pace_zone": "E", "pace_str": "6:00/km"},
        {
            "kind": "run",
            "label": "5 × 1 km",
            "distance_m": 1000,
            "pace_zone": "I",
            "pace_str": "4:00/km",
            "repeat": 5,
        },
        {"kind": "recovery", "duration_s": 90, "repeat": 4},
        {
            "kind": "cooldown",
            "distance_m": 1500,
            "pace_zone": "E",
            "pace_str": "6:00/km",
        },
    ],
}


def _load_day_from_db(plan_id: str, week: int, day: int) -> dict:
    """Fetch one plan_data day dict from the local database."""
    from app.contexts.plan.repositories import SQLAlchemyPlanRepository
    from app.dependencies import SessionLocal

    db = SessionLocal()
    try:
        plan = SQLAlchemyPlanRepository(db).get_by_id(plan_id)
        if not plan:
            sys.exit(f"Plan {plan_id} not found in local DB")
        week_data = next(
            (w for w in (plan.plan_data or []) if w.get("week") == week), None
        )
        if week_data is None:
            sys.exit(f"Week {week} not found in plan {plan_id}")
        day_data = next(
            (d for d in week_data.get("daily_workouts", []) if d.get("day") == day),
            None,
        )
        if day_data is None:
            sys.exit(f"Day {day} not found in week {week}")
        return day_data
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", help="Plan id to pull the workout from (local DB)")
    parser.add_argument("--week", type=int, default=1)
    parser.add_argument("--day", type=int, default=3)
    parser.add_argument("--date", help="start_date_local (YYYY-MM-DD); default today")
    parser.add_argument(
        "--apply", action="store_true", help="Actually POST to Intervals.icu"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the generated workout text (default if --apply absent)",
    )
    args = parser.parse_args()

    day_data = (
        _load_day_from_db(args.plan, args.week, args.day) if args.plan else _SAMPLE_DAY
    )

    try:
        workout = build_intervals_workout(day_data)
    except ValueError as exc:
        sys.exit(f"Cannot build workout: {exc}")

    start_date = args.date or date.today().isoformat()
    event = {
        "category": "WORKOUT",
        "type": "Run",
        "start_date_local": f"{start_date}T00:00:00",
        "name": workout["name"],
        "description": workout["description"],
        "moving_time": workout["moving_time"],
        "external_id": f"runcoach-spike-{args.plan or 'sample'}-{args.week}-{args.day}",
    }

    print("=" * 60)
    print(f"Name: {event['name']}   (~{round(workout['moving_time'] / 60)} min)")
    print(f"start_date_local: {event['start_date_local']}")
    print("-" * 60)
    print(event["description"])
    print("=" * 60)

    if not args.apply or args.dry_run:
        print("Dry run — not sent. Re-run with --apply to push to Intervals.icu.")
        return

    api_key = os.environ.get("INTERVALS_API_KEY")
    athlete_id = os.environ.get("INTERVALS_ATHLETE_ID", "0")
    if not api_key:
        sys.exit(
            "Set INTERVALS_API_KEY to --apply "
            "(INTERVALS_ATHLETE_ID is optional; defaults to 0 = the key owner)."
        )

    base = f"{INTERVALS_API_BASE}/athlete/{athlete_id}/events"
    with httpx.Client(timeout=30.0, auth=httpx.BasicAuth("API_KEY", api_key)) as client:
        # Delete any existing event with this external_id first. Updating a
        # planned workout in place does NOT re-trigger the Garmin export, so a
        # clean delete + recreate is required to (re)send pace targets to Garmin.
        existing = client.get(base, params={"oldest": start_date, "newest": start_date})
        if existing.status_code < 400:
            for ev in existing.json():
                if ev.get("external_id") == event["external_id"]:
                    client.delete(f"{base}/{ev['id']}")
                    print(f"Deleted existing event {ev['id']} to force re-export.")

        resp = client.post(f"{base}/bulk", params={"upsert": "true"}, json=[event])

    print(f"HTTP {resp.status_code}")
    if resp.status_code >= 400:
        print(resp.text)
        sys.exit(1)
    created = resp.json()
    event_id = created[0].get("id") if isinstance(created, list) and created else None
    print(f"✓ Pushed. event_id={event_id}")
    print("Check your Intervals.icu calendar, then your watch after the next sync.")
    print(
        "If pace shows 'No target' on the watch: set a Run threshold pace in "
        "Intervals.icu (Settings -> sport settings), then re-run this script."
    )


if __name__ == "__main__":
    main()
