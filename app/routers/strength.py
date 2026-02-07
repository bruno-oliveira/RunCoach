"""Strength training endpoints."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.config import settings
from app.dependencies import get_current_user, get_optional_user
from app.models import User
from app.schemas import (
    DailyWorkoutResponse,
    ExerciseSet,
    FavoriteRequest,
    StrengthExerciseResponse,
    UserFavoriteWorkoutResponse,
)
from app.services.strength_workout_generator import StrengthWorkoutGenerator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["strength"])
workout_generator = StrengthWorkoutGenerator()
templates = Jinja2Templates(directory="app/templates")


def db_query(query: str, params: dict = None):
    """Execute a database query and return results."""
    from app.dependencies import engine
    
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        rows = result.fetchall()
        
        # For INSERT/UPDATE/DELETE, commit the transaction
        if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
            conn.commit()
        
        return rows


@router.get("/api/strength/exercises", response_model=List[StrengthExerciseResponse])
async def list_exercises(
    name: Optional[str] = Query(None, description="Search by exercise name"),
    category: Optional[str] = Query(None, description="Filter by category (strength, stretching)"),
    equipment: Optional[str] = Query(None, description="Filter by equipment (bodyweight, dumbbell)"),
    muscle: Optional[str] = Query(None, description="Filter by primary muscle"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    current_user: Optional[User] = Depends(get_optional_user),
) -> List[StrengthExerciseResponse]:
    """List strength training exercises."""
    try:
        query = """
            SELECT id, name, exercise_id, force, level, mechanic, equipment,
                   primary_muscles, secondary_muscles, instructions, category,
                   target_muscles, images, gif_url, is_running_related,
                   is_bodyweight, is_dumbbell
            FROM strength_exercises
            WHERE is_running_related = 1
        """
        params = {}
        
        if name:
            query += " AND name LIKE :name"
            params["name"] = f"%{name}%"
        
        if category:
            query += " AND category = :category"
            params["category"] = category
        
        if equipment == "bodyweight":
            query += " AND is_bodyweight = 1"
        elif equipment == "dumbbell":
            query += " AND is_dumbbell = 1"
        
        if muscle:
            query += " AND (primary_muscles LIKE :muscle OR secondary_muscles LIKE :muscle)"
            params["muscle"] = f"%{muscle}%"
        
        query += " ORDER BY name LIMIT :limit"
        params["limit"] = limit
        
        results = db_query(query, params)
        
        exercises = []
        for row in results:
            exercises.append(StrengthExerciseResponse(
                id=row[0],
                name=row[1],
                exercise_id=row[2],
                force=row[3],
                level=row[4],
                mechanic=row[5],
                equipment=row[6],
                primary_muscles=json.loads(row[7]) if row[7] else [],
                secondary_muscles=json.loads(row[8]) if row[8] else [],
                instructions=json.loads(row[9]) if row[9] else [],
                category=row[10],
                target_muscles=row[11],
                images=json.loads(row[12]) if row[12] else [],
                gif_url=row[13],
                is_running_related=bool(row[14]),
                is_bodyweight=bool(row[15]),
                is_dumbbell=bool(row[16]),
            ))
        
        return exercises
        
    except Exception as e:
        logger.error(f"Error listing exercises: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve exercises")


@router.get("/api/strength/exercises/{exercise_id}", response_model=StrengthExerciseResponse)
async def get_exercise(
    exercise_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
) -> StrengthExerciseResponse:
    """Get a specific exercise by ID."""
    try:
        query = """
            SELECT id, name, exercise_id, force, level, mechanic, equipment,
                   primary_muscles, secondary_muscles, instructions, category,
                   target_muscles, images, gif_url, is_running_related,
                   is_bodyweight, is_dumbbell
            FROM strength_exercises
            WHERE id = :exercise_id
        """
        
        results = db_query(query, {"exercise_id": exercise_id})
        
        if not results:
            raise HTTPException(status_code=404, detail="Exercise not found")
        
        row = results[0]
        return StrengthExerciseResponse(
            id=row[0],
            name=row[1],
            exercise_id=row[2],
            force=row[3],
            level=row[4],
            mechanic=row[5],
            equipment=row[6],
            primary_muscles=json.loads(row[7]) if row[7] else [],
            secondary_muscles=json.loads(row[8]) if row[8] else [],
            instructions=json.loads(row[9]) if row[9] else [],
            category=row[10],
            target_muscles=row[11],
            images=json.loads(row[12]) if row[12] else [],
            gif_url=row[13],
            is_running_related=bool(row[14]),
            is_bodyweight=bool(row[15]),
            is_dumbbell=bool(row[16]),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting exercise: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve exercise")


@router.get("/api/strength/workout/today", response_model=DailyWorkoutResponse)
async def get_today_workout(
    current_user: Optional[User] = Depends(get_optional_user),
) -> DailyWorkoutResponse:
    """Get today's strength training workout."""
    try:
        date = datetime.now().strftime("%Y-%m-%d")
        return await get_workout_by_date(date, current_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting today's workout: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve workout")


@router.get("/api/strength/workout/week", response_model=List[DailyWorkoutResponse])
async def get_week_workouts(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD), defaults to today"),
    current_user: Optional[User] = Depends(get_optional_user),
) -> List[DailyWorkoutResponse]:
    """Get workouts for a week starting from start_date."""
    try:
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        query = """
            SELECT id, date, title, description, warmup_exercises, main_exercises,
                   cooldown_exercises, warmup_duration, main_duration, cooldown_duration,
                   total_duration, primary_focus, secondary_focus, difficulty
            FROM daily_strength_workouts
            WHERE date >= :start_date
            ORDER BY date
            LIMIT 7
        """
        
        results = db_query(query, {"start_date": start_date})
        
        workouts = []
        for row in results:
            warmup_exercises = enrich_exercises_with_details(json.loads(row[4]) if row[4] else [])
            main_exercises = enrich_exercises_with_details(json.loads(row[5]) if row[5] else [])
            cooldown_exercises = enrich_exercises_with_details(json.loads(row[6]) if row[6] else [])
            
            workouts.append(DailyWorkoutResponse(
                id=row[0],
                date=row[1],
                title=row[2],
                description=row[3],
                warmup_exercises=warmup_exercises,
                main_exercises=main_exercises,
                cooldown_exercises=cooldown_exercises,
                warmup_duration=row[7],
                main_duration=row[8],
                cooldown_duration=row[9],
                total_duration=row[10],
                primary_focus=row[11],
                secondary_focus=row[12],
                difficulty=row[13],
            ))
        
        # Generate missing workouts
        if len(workouts) < 6:  # 6 days, 1 rest day
            logger.info(f"Generating missing workouts for week starting {start_date}...")
            saved = workout_generator.generate_workouts_for_week(
                start_date=start_date,
                difficulty="beginner"
            )
            
            # Query again to get all workouts
            results = db_query(query, {"start_date": start_date})
            
            workouts = []
            for row in results:
                warmup_exercises = enrich_exercises_with_details(json.loads(row[4]) if row[4] else [])
                main_exercises = enrich_exercises_with_details(json.loads(row[5]) if row[5] else [])
                cooldown_exercises = enrich_exercises_with_details(json.loads(row[6]) if row[6] else [])
                
                workouts.append(DailyWorkoutResponse(
                    id=row[0],
                    date=row[1],
                    title=row[2],
                    description=row[3],
                    warmup_exercises=warmup_exercises,
                    main_exercises=main_exercises,
                    cooldown_exercises=cooldown_exercises,
                    warmup_duration=row[7],
                    main_duration=row[8],
                    cooldown_duration=row[9],
                    total_duration=row[10],
                    primary_focus=row[11],
                    secondary_focus=row[12],
                    difficulty=row[13],
                ))
        
        return workouts
        
    except Exception as e:
        logger.error(f"Error getting week workouts: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve workouts")


def enrich_exercises_with_details(exercise_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Enrich exercise list with full exercise details including GIF URLs."""
    enriched = []
    for ex in exercise_list:
        try:
            query = """
                SELECT id, name, exercise_id, force, level, mechanic, equipment,
                       primary_muscles, secondary_muscles, instructions, category,
                       target_muscles, images, gif_url, is_running_related,
                       is_bodyweight, is_dumbbell
                FROM strength_exercises
                WHERE id = :exercise_id
            """
            results = db_query(query, {"exercise_id": ex.get("exercise_id")})
            
            if results:
                row = results[0]
                enriched.append({
                    **ex,
                    "name": row[1],
                    "force": row[3],
                    "level": row[4],
                    "mechanic": row[5],
                    "equipment": row[6],
                    "primary_muscles": json.loads(row[7]) if row[7] else [],
                    "secondary_muscles": json.loads(row[8]) if row[8] else [],
                    "instructions": json.loads(row[9]) if row[9] else [],
                    "category": row[10],
                    "gif_url": row[13],
                    "images": json.loads(row[12]) if row[12] else [],
                })
            else:
                enriched.append(ex)
        except Exception as e:
            logger.error(f"Error enriching exercise {ex.get('exercise_id')}: {e}")
            enriched.append(ex)
    
    return enriched


@router.get("/api/strength/workout/{date}", response_model=DailyWorkoutResponse)
async def get_workout_by_date(
    date: str,
    current_user: Optional[User] = Depends(get_optional_user),
) -> DailyWorkoutResponse:
    """Get a strength training workout by date."""
    try:
        logger.info(f"Fetching workout for date: {date}")
        query = """
            SELECT id, date, title, description, warmup_exercises, main_exercises,
                   cooldown_exercises, warmup_duration, main_duration, cooldown_duration,
                   total_duration, primary_focus, secondary_focus, difficulty
            FROM daily_strength_workouts
            WHERE date = :date
        """
        
        results = db_query(query, {"date": date})
        logger.info(f"Query returned {len(results)} results")
        
        if not results:
            # Generate a new workout if none exists
            logger.info(f"No workout found for {date}, generating new one...")
            workout_data = workout_generator.generate_workout(date=date)
            workout_generator.save_workout(workout_data)
            
            # Query again to get the saved workout
            results = db_query(query, {"date": date})
            
            if not results:
                raise HTTPException(status_code=500, detail="Failed to generate workout")
        
        row = results[0]
        logger.info(f"Workout found: {row[2]}")
        
        # Parse exercises and enrich with full details
        warmup_exercises = enrich_exercises_with_details(json.loads(row[4]) if row[4] else [])
        main_exercises = enrich_exercises_with_details(json.loads(row[5]) if row[5] else [])
        cooldown_exercises = enrich_exercises_with_details(json.loads(row[6]) if row[6] else [])
        
        return DailyWorkoutResponse(
            id=row[0],
            date=row[1],
            title=row[2],
            description=row[3],
            warmup_exercises=warmup_exercises,
            main_exercises=main_exercises,
            cooldown_exercises=cooldown_exercises,
            warmup_duration=row[7],
            main_duration=row[8],
            cooldown_duration=row[9],
            total_duration=row[10],
            primary_focus=row[11],
            secondary_focus=row[12],
            difficulty=row[13],
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workout: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve workout: {str(e)}")


@router.get("/api/strength/favorites", response_model=List[UserFavoriteWorkoutResponse])
async def get_user_favorites(
    current_user: User = Depends(get_current_user),
) -> List[UserFavoriteWorkoutResponse]:
    """Get current user's favorite workouts."""
    try:
        query = """
            SELECT fw.id, fw.user_id, fw.workout_id, fw.notes, fw.created_at,
                   w.id, w.date, w.title, w.description, w.warmup_exercises,
                   w.main_exercises, w.cooldown_exercises, w.warmup_duration,
                   w.main_duration, w.cooldown_duration, w.total_duration,
                   w.primary_focus, w.secondary_focus, w.difficulty
            FROM user_favorite_workouts fw
            LEFT JOIN daily_strength_workouts w ON fw.workout_id = w.id
            WHERE fw.user_id = :user_id
            ORDER BY fw.created_at DESC
        """
        
        results = db_query(query, {"user_id": current_user.id})
        
        favorites = []
        for row in results:
            workout_data = None
            if row[5]:  # If workout exists
                warmup_exercises = enrich_exercises_with_details(json.loads(row[9]) if row[9] else [])
                main_exercises = enrich_exercises_with_details(json.loads(row[10]) if row[10] else [])
                cooldown_exercises = enrich_exercises_with_details(json.loads(row[11]) if row[11] else [])
                
                workout_data = DailyWorkoutResponse(
                    id=row[5],
                    date=row[6],
                    title=row[7],
                    description=row[8],
                    warmup_exercises=warmup_exercises,
                    main_exercises=main_exercises,
                    cooldown_exercises=cooldown_exercises,
                    warmup_duration=row[12],
                    main_duration=row[13],
                    cooldown_duration=row[14],
                    total_duration=row[15],
                    primary_focus=row[16],
                    secondary_focus=row[17],
                    difficulty=row[18],
                )
            
            favorites.append(UserFavoriteWorkoutResponse(
                id=row[0],
                user_id=row[1],
                workout_id=row[2],
                workout=workout_data,
                notes=row[3],
                created_at=row[4],
            ))
        
        return favorites
        
    except Exception as e:
        logger.error(f"Error getting favorites: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve favorites")


@router.post("/api/strength/favorites")
async def add_favorite(
    request: FavoriteRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Add a workout to favorites."""
    try:
        # Check if workout exists
        check_query = """
            SELECT id FROM daily_strength_workouts
            WHERE id = :workout_id
        """
        results = db_query(check_query, {"workout_id": request.workout_id})
        
        if not results:
            raise HTTPException(status_code=404, detail="Workout not found")
        
        # Check if already favorited
        existing_query = """
            SELECT id FROM user_favorite_workouts
            WHERE user_id = :user_id AND workout_id = :workout_id
        """
        existing = db_query(existing_query, {
            "user_id": current_user.id,
            "workout_id": request.workout_id
        })
        
        if existing:
            return {"message": "Workout already in favorites", "id": existing[0][0]}
        
        # Add favorite
        insert_query = """
            INSERT INTO user_favorite_workouts (id, user_id, workout_id, notes)
            VALUES (:id, :user_id, :workout_id, :notes)
        """
        
        import uuid
        db_query(insert_query, {
            "id": str(uuid.uuid4()),
            "user_id": current_user.id,
            "workout_id": request.workout_id,
            "notes": request.notes
        })
        
        return {"message": "Workout added to favorites"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding favorite: {e}")
        raise HTTPException(status_code=500, detail="Failed to add favorite")


@router.delete("/api/strength/favorites/{workout_id}")
async def remove_favorite(
    workout_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Remove a workout from favorites."""
    try:
        query = """
            DELETE FROM user_favorite_workouts
            WHERE user_id = :user_id AND workout_id = :workout_id
        """
        
        db_query(query, {
            "user_id": current_user.id,
            "workout_id": workout_id
        })
        
        return {"message": "Workout removed from favorites"}
        
    except Exception as e:
        logger.error(f"Error removing favorite: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove favorite")


@router.get("/strength-training/{workout_id}", response_class=HTMLResponse)
async def workout_detail(
    request: Request,
    workout_id: str,
    user: Optional[User] = Depends(get_optional_user),
):
    """Workout detail page with shareable URL."""
    try:
        # Query workout by ID
        query = """
            SELECT id, date, title, description, warmup_exercises, main_exercises, 
                   cooldown_exercises, total_duration, primary_focus, difficulty
            FROM daily_strength_workouts
            WHERE id = :workout_id
        """
        
        results = db_query(query, {"workout_id": workout_id})
        
        if not results:
            raise HTTPException(status_code=404, detail="Workout not found")
        
        row = results[0]
        workout = {
            "id": row[0],
            "date": row[1],
            "title": row[2],
            "description": row[3],
            "warmup_exercises": json.loads(row[4]) if row[4] else [],
            "main_exercises": json.loads(row[5]) if row[5] else [],
            "cooldown_exercises": json.loads(row[6]) if row[6] else [],
            "total_duration": row[7],
            "primary_focus": row[8],
            "difficulty": row[9],
        }
        
        # Check if workout is in user's favorites
        is_favorite = False
        favorite_id = None
        if user:
            fav_query = """
                SELECT id FROM user_favorite_workouts
                WHERE user_id = :user_id AND workout_id = :workout_id
            """
            fav_results = db_query(fav_query, {"user_id": user.id, "workout_id": workout_id})
            if fav_results:
                is_favorite = True
                favorite_id = fav_results[0][0]
        
        return templates.TemplateResponse(
            "workout_detail.html",
            {
                "request": request,
                "workout": workout,
                "user": user,
                "is_favorite": is_favorite,
                "favorite_id": favorite_id,
                "google_client_id": settings.google_client_id,
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving workout: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve workout")


@router.get("/strength-training", response_class=HTMLResponse)
async def strength_training_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    """Strength training page."""
    return templates.TemplateResponse(
        "strength_training.html",
        {
            "request": request,
            "user": user,
            "current_page": "strength",
            "google_client_id": settings.google_client_id,
        }
    )
