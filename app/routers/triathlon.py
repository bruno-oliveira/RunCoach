"""Triathlon training plan endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_optional_user
from app.models.triathlon_plan import TriathlonPlan
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["triathlon"])


# ---------------------------------------------------------------------------
# Delete plan
# ---------------------------------------------------------------------------


@router.delete("/api/triathlon/plan/{plan_id}")
async def delete_triathlon_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    anonymous_user_id: Optional[str] = Cookie(None),
):
    plan = db.query(TriathlonPlan).filter(TriathlonPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    owner_ok = (
        plan.user_id is None
        or (current_user and plan.user_id == current_user.id)
        or (anonymous_user_id and plan.user_id == anonymous_user_id)
    )
    if not owner_ok:
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(plan)
    db.commit()
    return {"message": "Triathlon plan deleted"}
