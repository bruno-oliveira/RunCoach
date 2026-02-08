"""Router for Strava analytics functionality."""

import io
import json
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, Query, status, Cookie
from fastapi.responses import HTMLResponse, Response
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


def _ensure_compatible_analytics_data(analytics_data: dict) -> dict:
    """Ensure analytics data has all expected fields for template rendering."""
    # Add aliases for old field names
    if 'summary' in analytics_data:
        summary = analytics_data['summary']
        if 'total_runs' in summary and 'total_activities' not in summary:
            summary['total_activities'] = summary['total_runs']
        if 'total_distance_km' in summary and 'total_distance' not in summary:
            summary['total_distance'] = summary['total_distance_km']
        if 'avg_distance_per_run_km' in summary and 'avg_distance' not in summary:
            summary['avg_distance'] = summary['avg_distance_per_run_km']
        # Add max_distance if missing
        if 'max_distance' not in summary and 'distance_trends' in analytics_data:
            summary['max_distance'] = analytics_data['distance_trends'].get('max_distance_km', 0)

    # Add weekly volume aggregates if missing
    if 'weekly_volume' in analytics_data:
        wv = analytics_data['weekly_volume']
        if 'yearly_breakdown' in wv and 'avg_weekly_distance' not in wv:
            # Calculate from yearly_breakdown
            yearly_data = wv['yearly_breakdown']
            if yearly_data:
                all_weekly_avgs = [y['weekly_average_km'] for y in yearly_data.values()]
                all_max_weekly = [y['max_weekly_km'] for y in yearly_data.values()]
                wv['avg_weekly_distance'] = sum(all_weekly_avgs) / len(all_weekly_avgs) if all_weekly_avgs else 0
                wv['max_weekly_distance'] = max(all_max_weekly) if all_max_weekly else 0

    return analytics_data


@analytics_page_router.get("/analytics/{analytics_id}", response_class=HTMLResponse)
async def analytics_detail_page(
    request: Request,
    analytics_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_optional_user),
) -> HTMLResponse:
    """Analytics detail page showing charts for a specific upload."""
    try:
        anonymous_user_id = getattr(request.state, 'anonymous_user_id', None)
        user_filter = current_user.id if current_user else anonymous_user_id
        
        analytics = (
            db.query(StravaAnalytics)
            .filter(
                StravaAnalytics.id == analytics_id,
                StravaAnalytics.user_id == user_filter,
            )
            .first()
        )

        if not analytics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analytics not found",
            )

        # Generate analytics if not already present
        analytics_data = analytics.analytics_data
        if not analytics_data:
            activities = []
            for activity in analytics.activities:
                # Calculate pace if we have distance and time
                pace_min_km = None
                if activity.distance_km and activity.distance_km > 0 and activity.moving_time_seconds and activity.moving_time_seconds > 0:
                    pace_min_km = activity.moving_time_seconds / 60.0 / activity.distance_km

                act_dict = {
                    "date": activity.date.isoformat() if activity.date else None,
                    "activity_type": activity.activity_type,
                    "distance_km": activity.distance_km,
                    "avg_heart_rate": activity.avg_heart_rate,
                    "moving_time_seconds": activity.moving_time_seconds,
                    "pace_min_km": pace_min_km,
                }
                activities.append(act_dict)

            analytics_data = AnalyticsService.generate_analytics(activities)
            analytics.analytics_data = json.loads(json.dumps(analytics_data))
            db.commit()

        # Ensure backward compatibility with old data structures
        analytics_data = _ensure_compatible_analytics_data(analytics_data)

        return templates.TemplateResponse(
            "analytics_detail.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "analytics": analytics,
                "analytics_data": analytics_data,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading analytics detail page: {e}", exc_info=True)
        # Provide more specific error information
        error_detail = f"Failed to load analytics detail page: {str(e)}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        )
    finally:
        db.close()


@analytics_router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_strava_data(
    request: Request,
    name: str = Query(..., description="Name for this analytics upload"),
    file: UploadFile = UploadFile(...),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
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
        # Get anonymous_user_id from request state (set by middleware)
        anonymous_user_id = getattr(request.state, 'anonymous_user_id', None)
        effective_user_id = current_user.id if current_user else anonymous_user_id

        strava_analytics = StravaAnalytics(
            id=analytics_id,
            user_id=effective_user_id,
            name=name,
            total_activities=parsed_data["total_activities"],
            summary_data=parsed_data["summary"],
        )

        db.add(strava_analytics)

        activities_for_analytics = []
        for activity_data in parsed_data["activities"]:
            # Store only essential data for memory efficiency
            activity = StravaActivity(
                id=str(uuid.uuid4()),
                analytics_id=analytics_id,
                activity_id=None,  # Not needed for analytics
                date=None if not activity_data["date"] else __import__("datetime").datetime.fromisoformat(activity_data["date"]),
                activity_type=activity_data.get("activity_type"),
                distance_km=activity_data.get("distance_km"),
                moving_time_seconds=activity_data.get("moving_time_seconds"),
                elapsed_time_seconds=None,
                avg_speed=None,
                max_speed=None,
                avg_heart_rate=activity_data.get("avg_heart_rate"),
                max_heart_rate=None,
                elevation_gain_meters=None,
                calories=None,
                raw_data=None,  # Don't store raw data to save memory
            )
            db.add(activity)

            activities_for_analytics.append({
                "date": activity_data.get("date"),
                "activity_type": activity_data.get("activity_type"),
                "distance_km": activity_data.get("distance_km"),
                "avg_heart_rate": activity_data.get("avg_heart_rate"),
                "moving_time_seconds": activity_data.get("moving_time_seconds"),
                "pace_min_km": activity_data.get("pace_min_km"),
            })

        db.commit()
        db.refresh(strava_analytics)

        analytics_data = AnalyticsService.generate_analytics(activities_for_analytics)
        # Ensure analytics data is JSON-serializable by converting to JSON and back
        strava_analytics.analytics_data = json.loads(json.dumps(analytics_data))
        db.commit()
        db.refresh(strava_analytics)

        logger.info(f"Strava analytics uploaded{' for user ' + current_user.id if current_user else ' anonymously'}: {name}")

        # Return response data (middleware handles cookie setting)
        return {
            "id": strava_analytics.id,
            "name": strava_analytics.name,
            "upload_date": strava_analytics.upload_date.isoformat(),
            "total_activities": strava_analytics.total_activities,
            "summary": strava_analytics.summary_data,
        }

    except ValueError as e:
        db.rollback()
        logger.warning(f"Validation error uploading Strava data: {e}")
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
            detail=f"Failed to process upload: {str(e)}",
        )
    finally:
        db.close()


@analytics_router.get("")
async def list_analytics_uploads(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """List all analytics uploads for the current user."""
    try:
        anonymous_user_id = getattr(request.state, 'anonymous_user_id', None)
        
        if current_user:
            uploads = (
                db.query(StravaAnalytics)
                .filter(StravaAnalytics.user_id == current_user.id)
                .order_by(StravaAnalytics.upload_date.desc())
                .all()
            )
        elif anonymous_user_id:
            uploads = (
                db.query(StravaAnalytics)
                .filter(StravaAnalytics.user_id == anonymous_user_id)
                .order_by(StravaAnalytics.upload_date.desc())
                .all()
            )
        else:
            uploads = []

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


@analytics_router.get("/{analytics_id}/activities")
async def get_analytics_activities(
    request: Request,
    analytics_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get all activities for a specific analytics upload."""
    try:
        anonymous_user_id = getattr(request.state, 'anonymous_user_id', None)
        user_filter = current_user.id if current_user else anonymous_user_id
        analytics = (
            db.query(StravaAnalytics)
            .filter(
                StravaAnalytics.id == analytics_id,
                StravaAnalytics.user_id == user_filter,
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
            # Return only essential data for memory efficiency
            act_dict = {
                "id": activity.id,
                "date": activity.date.isoformat() if activity.date else None,
                "activity_type": activity.activity_type,
                "distance_km": activity.distance_km,
                "formatted_distance": f"{activity.distance_km:.2f} km" if activity.distance_km else None,
                "avg_heart_rate": activity.avg_heart_rate,
            }
            activities.append(act_dict)

        activities.sort(key=lambda x: x["date"] or "", reverse=True)

        return {
            "analytics_id": analytics_id,
            "analytics_name": analytics.name,
            "activities": activities,
            "total_activities": len(activities),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analytics activities: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve activities",
        )


@analytics_router.get("/{analytics_id}")
async def get_analytics(
    request: Request,
    analytics_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get detailed analytics for a specific upload including all charts."""
    try:
        anonymous_user_id = getattr(request.state, 'anonymous_user_id', None)
        user_filter = current_user.id if current_user else anonymous_user_id
        analytics = (
            db.query(StravaAnalytics)
            .filter(
                StravaAnalytics.id == analytics_id,
                StravaAnalytics.user_id == user_filter,
            )
            .first()
        )

        if not analytics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analytics not found",
            )

        analytics_data = analytics.analytics_data
        if not analytics_data:
            activities = []
            for activity in analytics.activities:
                # Calculate pace if we have distance and time
                pace_min_km = None
                if activity.distance_km and activity.distance_km > 0 and activity.moving_time_seconds and activity.moving_time_seconds > 0:
                    pace_min_km = activity.moving_time_seconds / 60.0 / activity.distance_km

                # Use only essential data for analytics generation
                act_dict = {
                    "date": activity.date.isoformat() if activity.date else None,
                    "activity_type": activity.activity_type,
                    "distance_km": activity.distance_km,
                    "avg_heart_rate": activity.avg_heart_rate,
                    "moving_time_seconds": activity.moving_time_seconds,
                    "pace_min_km": pace_min_km,
                }
                activities.append(act_dict)

            analytics_data = AnalyticsService.generate_analytics(activities)
            analytics.analytics_data = json.loads(json.dumps(analytics_data))
            db.commit()

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
    request: Request,
    analytics_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Delete an analytics upload and all associated data."""
    try:
        anonymous_user_id = getattr(request.state, 'anonymous_user_id', None)
        user_filter = current_user.id if current_user else anonymous_user_id
        analytics = (
            db.query(StravaAnalytics)
            .filter(
                StravaAnalytics.id == analytics_id,
                StravaAnalytics.user_id == user_filter,
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

        logger.info(f"Analytics {analytics_id} deleted for user {user_filter}")

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
    request: Request,
    analytics_ids: List[str] = Query(..., description="IDs of analytics uploads to compare"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
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

        anonymous_user_id = getattr(request.state, 'anonymous_user_id', None)
        user_filter = current_user.id if current_user else anonymous_user_id
        uploads = (
            db.query(StravaAnalytics)
            .filter(
                StravaAnalytics.id.in_(analytics_ids),
                StravaAnalytics.user_id == user_filter,
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
            if upload.analytics_data:
                analytics_list.append(upload.analytics_data)
                names.append(upload.name)
            else:
                activities = []
                for activity in upload.activities:
                    # Calculate pace if we have distance and time
                    pace_min_km = None
                    if activity.distance_km and activity.distance_km > 0 and activity.moving_time_seconds and activity.moving_time_seconds > 0:
                        pace_min_km = activity.moving_time_seconds / 60.0 / activity.distance_km

                    # Use only essential data for comparison analytics
                    act_dict = {
                        "date": activity.date.isoformat() if activity.date else None,
                        "activity_type": activity.activity_type,
                        "distance_km": activity.distance_km,
                        "avg_heart_rate": activity.avg_heart_rate,
                        "moving_time_seconds": activity.moving_time_seconds,
                        "pace_min_km": pace_min_km,
                    }
                    activities.append(act_dict)

                analytics = AnalyticsService.generate_analytics(activities)
                upload.analytics_data = json.loads(json.dumps(analytics))
                db.commit()
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


class AnalyticsRouterHelpers:
    @staticmethod
    def _format_pace(pace_min_km: float) -> str:
        minutes = int(pace_min_km)
        seconds = int((pace_min_km - minutes) * 60)
        return f"{minutes}:{seconds:02d}"

    @staticmethod
    def _format_duration(seconds: int) -> str:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def _sanitize_analytics_for_json(data):
        """
        Recursively sanitize analytics data to ensure JSON serializability.
        Converts booleans and other non-JSON-serializable types to JSON-safe formats.
        """
        if isinstance(data, dict):
            return {key: AnalyticsRouterHelpers._sanitize_analytics_for_json(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [AnalyticsRouterHelpers._sanitize_analytics_for_json(item) for item in data]
        elif isinstance(data, bool):
            return data  # Booleans are JSON-serializable, but SQLAlchemy may have issues
        elif isinstance(data, (int, float, str, type(None))):
            return data
        else:
            return str(data)