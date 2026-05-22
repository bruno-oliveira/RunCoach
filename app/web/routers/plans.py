"""Plan router aggregator — includes generation, view, list, adjustments, and sharing sub-routers."""

from fastapi import APIRouter

from app.web.routers.plan_adjustments import router as adjustments_router
from app.web.routers.plan_generation import router as generation_router
from app.web.routers.plan_list import router as list_router
from app.web.routers.plan_sharing import router as sharing_router
from app.web.routers.plan_view import router as view_router

router = APIRouter(tags=["plans"])
router.include_router(generation_router)
router.include_router(view_router)
router.include_router(list_router)
router.include_router(adjustments_router)
router.include_router(sharing_router)
