"""Database session and repository dependency factories."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.runner.repositories import SQLAlchemyRunRepository
from app.contexts.runner.wellness.repository import SQLAlchemyReadinessRepository
from app.infrastructure.database import SessionLocal, engine, get_db


def get_plan_repository(db: Session = Depends(get_db)) -> SQLAlchemyPlanRepository:
    """Per-request plan repository bound to the current DB session."""
    return SQLAlchemyPlanRepository(db)


def get_run_repository(db: Session = Depends(get_db)) -> SQLAlchemyRunRepository:
    """Per-request run repository bound to the current DB session."""
    return SQLAlchemyRunRepository(db)


def get_user_repository(db: Session = Depends(get_db)) -> SQLAlchemyUserRepository:
    """Per-request user repository bound to the current DB session."""
    return SQLAlchemyUserRepository(db)


def get_readiness_repository(
    db: Session = Depends(get_db),
) -> SQLAlchemyReadinessRepository:
    """Per-request readiness repository bound to the current DB session."""
    return SQLAlchemyReadinessRepository(db)


__all__ = [
    "engine",
    "SessionLocal",
    "get_db",
    "get_plan_repository",
    "get_run_repository",
    "get_user_repository",
    "get_readiness_repository",
]
