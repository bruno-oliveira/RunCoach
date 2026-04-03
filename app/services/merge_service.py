"""Service for merging anonymous user data to authenticated users."""

import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.models import User, TrainingPlan, RunLog, FavoriteRecipe, TriathlonPlan

logger = logging.getLogger(__name__)


class MergeService:
    """Handle merging anonymous user plans/logs to authenticated users."""

    @staticmethod
    def merge_anonymous_user(
        db: Session,
        anonymous_user_id: Optional[str],
        authenticated_user_id: str
    ) -> dict:
        """
        Merge all data from anonymous user to authenticated user.

        Returns dict with statistics of what was merged.
        """
        if not anonymous_user_id:
            return {"merged": False, "reason": "No anonymous_user_id provided"}

        if anonymous_user_id == authenticated_user_id:
            return {"merged": False, "reason": "Anonymous user ID matches authenticated user ID"}

        anonymous_user = db.query(User).filter(User.id == anonymous_user_id).first()
        if not anonymous_user:
            return {"merged": False, "reason": "Anonymous user not found"}

        if anonymous_user.google_id or anonymous_user.email:
            return {"merged": False, "reason": "Anonymous user already linked to account"}

        stats = {
            "training_plans": 0,
            "run_logs": 0,
            "favorite_recipes": 0,
            "triathlon_plans": 0,
            "merged": True
        }

        try:
            plans = db.query(TrainingPlan).filter(
                TrainingPlan.user_id == anonymous_user_id
            ).all()

            for plan in plans:
                plan.user_id = authenticated_user_id
                stats["training_plans"] += 1

            logs = db.query(RunLog).filter(
                RunLog.user_id == anonymous_user_id
            ).all()

            for log in logs:
                log.user_id = authenticated_user_id
                stats["run_logs"] += 1

            recipes = db.query(FavoriteRecipe).filter(
                FavoriteRecipe.user_id == anonymous_user_id
            ).all()

            for recipe in recipes:
                recipe.user_id = authenticated_user_id
                stats["favorite_recipes"] += 1

            tri_plans = db.query(TriathlonPlan).filter(
                TriathlonPlan.user_id == anonymous_user_id
            ).all()

            for tp in tri_plans:
                tp.user_id = authenticated_user_id
                stats["triathlon_plans"] += 1

            db.delete(anonymous_user)

            db.commit()
            logger.info("Merged anonymous user %s to %s: %s", anonymous_user_id, authenticated_user_id, stats)

        except Exception as e:
            db.rollback()
            logger.error("Error merging anonymous user: %s", e)
            raise

        return stats
