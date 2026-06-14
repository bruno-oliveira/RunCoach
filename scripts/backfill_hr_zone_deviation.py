"""Backfill hr_zone_deviation for existing runs."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal

from app.core.coaching.hr_feedback import compute_hr_zone_deviation
from app.models import DailyWorkout, RunLog, TrainingPlan


def backfill():
    db = SessionLocal()
    try:
        plans = db.query(TrainingPlan).all()

        for plan in plans:
            if not plan.hr_zones_data:
                continue

            hr_zones = plan.hr_zones_data.get("zones")
            if not hr_zones:
                continue

            runs = (
                db.query(RunLog)
                .filter(
                    RunLog.training_plan_id == plan.id,
                    RunLog.hr_zone_deviation.is_(None),
                    RunLog.avg_heart_rate.isnot(None),
                )
                .all()
            )

            for run in runs:
                workout = None
                if run.daily_workout_id:
                    workout = (
                        db.query(DailyWorkout)
                        .filter(DailyWorkout.id == run.daily_workout_id)
                        .first()
                    )

                deviation = compute_hr_zone_deviation(run, workout, hr_zones)
                if deviation is not None:
                    run.hr_zone_deviation = deviation

            if runs:
                db.commit()
                print(f"Backfilled {len(runs)} runs for plan {plan.id}")

        print("Backfill complete.")
    finally:
        db.close()


if __name__ == "__main__":
    backfill()
