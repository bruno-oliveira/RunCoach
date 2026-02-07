"""Router for Strava analytics functionality."""

import io
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, Query, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, get_current_user, get_optional_user
from app.models import User, StravaAnalytics, StravaActivity
from app.services.strava_csv_parser import StravaCSVParser
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])
analytics_page_router = APIRouter(tags=["analytics-page"])
templates = Jinja2Templates(directory="app/templates")


@analytics_page_router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    current_user = Depends(get_optional_user),
) -> HTMLResponse:
    """Analytics page."""
    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id,
        },
    )


@analytics_router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_strava_data(
    name: str = Query(..., description="Name for this analytics upload"),
    file: UploadFile = UploadFile(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload and parse Strava activities.csv file.

    The CSV file will be parsed, activities extracted, and analytics generated.
    All data will be stored in the database for future reference.
    """
    try:
        if not file.filename or not file.filename.endswith(".csv"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be a CSV file",
            )

        content = await file.read()
        try:
            csv_content = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                csv_content = content.decode("latin-1")
            except UnicodeDecodeError:
                try:
                    csv_content = content.decode("cp1252")
                except Exception:
                    csv_content = content.decode("utf-8", errors="ignore")

        parsed_data = StravaCSVParser.parse_csv(csv_content)

        analytics_id = str(uuid.uuid4())
        user_id = current_user.id if current_user else None

        strava_analytics = StravaAnalytics(
            id=analytics_id,
            user_id=user_id,
            name=name,
            total_activities=parsed_data["total_activities"],
            summary_data=parsed_data["summary"],
        )

        db.add(strava_analytics)

        for activity_data in parsed_data["activities"]:
            activity = StravaActivity(
                id=str(uuid.uuid4()),
                analytics_id=analytics_id,
                activity_id=activity_data.get("activity_id"),
                date=None if not activity_data["date"] else __import__("datetime").datetime.fromisoformat(activity_data["date"]),
                activity_type=activity_data.get("activity_type"),
                distance_km=activity_data.get("distance_km"),
                moving_time_seconds=activity_data.get("moving_time_seconds"),
                elapsed_time_seconds=activity_data.get("elapsed_time_seconds"),
                avg_speed=activity_data.get("avg_speed"),
                max_speed=activity_data.get("max_speed"),
                avg_heart_rate=activity_data.get("avg_heart_rate"),
                max_heart_rate=activity_data.get("max_heart_rate"),
                elevation_gain_meters=activity_data.get("elevation_gain_meters"),
                calories=activity_data.get("calories"),
                raw_data=activity_data,
            )
            db.add(activity)

        db.commit()
        db.refresh(strava_analytics)

        logger.info(f"Strava analytics uploaded{' for user ' + current_user.id if current_user else ' anonymously'}: {name}")

        return {
            "id": strava_analytics.id,
            "name": strava_analytics.name,
            "upload_date": strava_analytics.upload_date.isoformat(),
            "total_activities": strava_analytics.total_activities,
            "summary": strava_analytics.summary_data,
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error uploading Strava data: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process upload",
        )


@analytics_router.get("")
async def list_analytics_uploads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all analytics uploads for the current user."""
    try:
        uploads = (
            db.query(StravaAnalytics)
            .filter(StravaAnalytics.user_id == current_user.id)
            .order_by(StravaAnalytics.upload_date.desc())
            .all()
        )

        return {
            "uploads": [
                {
                    "id": upload.id,
                    "name": upload.name,
                    "upload_date": upload.upload_date.isoformat(),
                    "total_activities": upload.total_activities,
                    "summary": upload.summary_data,
                }
                for upload in uploads
            ]
        }
    except Exception as e:
        logger.error(f"Error listing analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics",
        )


@analytics_router.get("/{analytics_id}")
async def get_analytics(
    analytics_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed analytics for a specific upload including all charts."""
    try:
        analytics = (
            db.query(StravaAnalytics)
            .filter(
                StravaAnalytics.id == analytics_id,
                StravaAnalytics.user_id == current_user.id,
            )
            .first()
        )

        if not analytics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analytics not found",
            )

        activities = []
        for activity in analytics.activities:
            act_dict = {
                "activity_id": activity.activity_id,
                "date": activity.date.isoformat() if activity.date else None,
                "activity_type": activity.activity_type,
                "distance_km": activity.distance_km,
                "moving_time_seconds": activity.moving_time_seconds,
                "elapsed_time_seconds": activity.elapsed_time_seconds,
                "avg_speed": activity.avg_speed,
                "max_speed": activity.max_speed,
                "avg_heart_rate": activity.avg_heart_rate,
                "max_heart_rate": activity.max_heart_rate,
                "elevation_gain_meters": activity.elevation_gain_meters,
                "calories": activity.calories,
            }
            activities.append(act_dict)

        analytics_data = AnalyticsService.generate_analytics(activities)

        return {
            "id": analytics.id,
            "name": analytics.name,
            "upload_date": analytics.upload_date.isoformat(),
            "total_activities": analytics.total_activities,
            "summary": analytics.summary_data,
            "analytics": analytics_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics",
        )


@analytics_router.delete("/{analytics_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analytics(
    analytics_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an analytics upload and all associated data."""
    try:
        analytics = (
            db.query(StravaAnalytics)
            .filter(
                StravaAnalytics.id == analytics_id,
                StravaAnalytics.user_id == current_user.id,
            )
            .first()
        )

        if not analytics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analytics not found",
            )

        db.delete(analytics)
        db.commit()

        logger.info(f"Analytics {analytics_id} deleted for user {current_user.id}")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete analytics",
        )


@analytics_router.post("/compare")
async def compare_analytics(
    analytics_ids: List[str] = Query(..., description="IDs of analytics uploads to compare"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compare multiple analytics uploads side-by-side.

    Generates comparison charts and summary statistics.
    """
    try:
        if len(analytics_ids) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least 2 analytics uploads required for comparison",
            )

        if len(analytics_ids) > 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 5 analytics can be compared at once",
            )

        uploads = (
            db.query(StravaAnalytics)
            .filter(
                StravaAnalytics.id.in_(analytics_ids),
                StravaAnalytics.user_id == current_user.id,
            )
            .all()
        )

        if len(uploads) != len(analytics_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more analytics uploads not found",
            )

        analytics_list = []
        names = []

        for upload in uploads:
            activities = []
            for activity in upload.activities:
                act_dict = {
                    "activity_id": activity.activity_id,
                    "date": activity.date.isoformat() if activity.date else None,
                    "activity_type": activity.activity_type,
                    "distance_km": activity.distance_km,
                    "moving_time_seconds": activity.moving_time_seconds,
                    "elapsed_time_seconds": activity.elapsed_time_seconds,
                    "avg_speed": activity.avg_speed,
                    "max_speed": activity.max_speed,
                    "avg_heart_rate": activity.avg_heart_rate,
                    "max_heart_rate": activity.max_heart_rate,
                    "elevation_gain_meters": activity.elevation_gain_meters,
                    "calories": activity.calories,
                }
                activities.append(act_dict)

            analytics = AnalyticsService.generate_analytics(activities)
            analytics_list.append(analytics)
            names.append(upload.name)

        comparison = AnalyticsService.compare_analytics(analytics_list, names)

        return {
            "analytics_ids": analytics_ids,
            "comparison": comparison,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compare analytics",
        )