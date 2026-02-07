"""Strength training workout generator service."""

import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from sqlalchemy import text

from app.dependencies import engine


class StrengthWorkoutGenerator:
    """Generates daily strength training workouts for runners."""
    
    # Warmup exercises (dynamic stretching)
    WARMUP_FOCUSES = ["stretching", "mobility"]
    
    # Main workout focuses and their primary muscles
    WORKOUT_FOCUSES = {
        "lower_body": ["quadriceps", "hamstrings", "glutes", "calves"],
        "upper_body": ["abdominals", "obliques", "chest", "back"],
        "core": ["abdominals", "obliques", "lower back"],
        "full_body": ["quadriceps", "hamstrings", "glutes", "abdominals"],
    }
    
    # Cooldown exercises (static stretching)
    COOLDOWN_FOCUSES = ["stretching"]
    
    def __init__(self):
        self.exercises = []
        self._load_exercises()
    
    def _load_exercises(self):
        """Load all exercises from database."""
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        """
                        SELECT id, name, exercise_id, category, primary_muscles,
                               secondary_muscles, equipment, level, is_bodyweight,
                               is_dumbbell, gif_url, images
                        FROM strength_exercises
                        WHERE is_running_related = 1
                        """
                    )
                )
                
                for row in result:
                    self.exercises.append({
                        "id": row[0],
                        "name": row[1],
                        "exercise_id": row[2],
                        "category": row[3],
                        "primary_muscles": json.loads(row[4]) if row[4] else [],
                        "secondary_muscles": json.loads(row[5]) if row[5] else [],
                        "equipment": row[6],
                        "level": row[7],
                        "is_bodyweight": bool(row[8]),
                        "is_dumbbell": bool(row[9]),
                        "gif_url": row[10],
                        "images": json.loads(row[11]) if row[11] else [],
                    })
                
                # print(f"Loaded {len(self.exercises)} running-related exercises")
                
        except Exception as e:
            print(f"Error loading exercises: {e}")
            self.exercises = []
    
    def _filter_exercises(self, category: str = None, 
                        muscles: List[str] = None,
                        equipment: str = None) -> List[Dict]:
        """Filter exercises based on criteria."""
        filtered = self.exercises
        
        if category:
            filtered = [ex for ex in filtered if ex["category"] == category]
        
        if muscles:
            filtered = [
                ex for ex in filtered 
                if any(muscle in ex["primary_muscles"] for muscle in muscles)
                or any(muscle in ex["secondary_muscles"] for muscle in muscles)
            ]
        
        if equipment == "bodyweight":
            filtered = [ex for ex in filtered if ex["is_bodyweight"]]
        elif equipment == "dumbbell":
            filtered = [ex for ex in filtered if ex["is_dumbbell"]]
        
        return filtered
    
    def _generate_warmup(self, duration_minutes: int = 5) -> List[Dict]:
        """Generate warmup exercises."""
        warmup_exercises = self._filter_exercises(
            category="stretching"
        )

        # Each stretching exercise requires BOTH sides (left/right)
        # 1 set = 30 seconds per side × 2 sides = 1 minute
        # 2 sets = 2 minutes per exercise
        # For 5 min warmup, need ~2-3 exercises
        time_per_exercise = 2.0  # minutes (accounts for both sides + transitions)
        num_exercises = max(2, min(int(duration_minutes / time_per_exercise), len(warmup_exercises)))

        # Select warmup exercises
        selected = random.sample(
            warmup_exercises,
            min(len(warmup_exercises), num_exercises)
        ) if warmup_exercises else []

        warmup = []
        for exercise in selected:
            warmup.append({
                "exercise_id": exercise["id"],
                "name": exercise["name"],
                "sets": 1,  # 1 set (both sides)
                "reps": "30 sec/side",  # Make it clear it's per side
                "type": "warmup"
            })

        return warmup
    
    def _generate_main_workout(self, focus: str = "full_body",
                             difficulty: str = "beginner",
                             duration_minutes: int = 25,
                             forced_count: int = None) -> List[Dict]:
        """Generate main workout exercises."""
        # Get target muscles based on focus
        target_muscles = self.WORKOUT_FOCUSES.get(focus, self.WORKOUT_FOCUSES["full_body"])
        
        # Filter exercises
        main_exercises = self._filter_exercises(
            category="strength",
            muscles=target_muscles
        )
        
        # Determine sets and reps based on difficulty
        # time_per_set includes work time + rest time between sets
        sets_reps = {
            "beginner": {"sets": 2, "reps": "10-12", "time_per_set": 1.5, "rest_seconds": 60},  # 1.5 min per set (work + rest)
            "intermediate": {"sets": 3, "reps": "12-15", "time_per_set": 1.5, "rest_seconds": 60},
            "advanced": {"sets": 4, "reps": "15-20", "time_per_set": 2.0, "rest_seconds": 90}  # 2 min per set for advanced
        }

        sets_reps_data = sets_reps.get(difficulty, sets_reps["beginner"])
        time_per_exercise = sets_reps_data["sets"] * sets_reps_data["time_per_set"]
        
        # Calculate number of exercises that fit in duration
        if forced_count is not None:
            num_exercises = max(3, min(forced_count, len(main_exercises)))
        else:
            num_exercises = max(3, min(int(duration_minutes / time_per_exercise), len(main_exercises)))
        
        # Randomly select exercises
        selected = random.sample(
            main_exercises,
            min(len(main_exercises), num_exercises)
        ) if main_exercises else []
        
        workout = []
        for exercise in selected:
            workout.append({
                "exercise_id": exercise["id"],
                "name": exercise["name"],
                "sets": sets_reps_data["sets"],
                "reps": sets_reps_data["reps"],
                "rest_seconds": sets_reps_data["rest_seconds"],
                "type": "main"
            })
        
        return workout
    
    def _generate_cooldown(self, duration_minutes: int = 5) -> List[Dict]:
        """Generate cooldown exercises."""
        cooldown_exercises = self._filter_exercises(
            category="stretching"
        )

        # Each stretching exercise requires BOTH sides (left/right)
        # 1 set = 30 seconds per side × 2 sides = 1 minute
        # 2 sets = 2 minutes per exercise
        # For 5 min cooldown, need ~2-3 exercises
        time_per_exercise = 2.0  # minutes (accounts for both sides + transitions)
        num_exercises = max(2, min(int(duration_minutes / time_per_exercise), len(cooldown_exercises)))

        # Select cooldown exercises
        selected = random.sample(
            cooldown_exercises,
            min(len(cooldown_exercises), num_exercises)
        ) if cooldown_exercises else []

        cooldown = []
        for exercise in selected:
            cooldown.append({
                "exercise_id": exercise["id"],
                "name": exercise["name"],
                "sets": 1,  # 1 set (both sides)
                "reps": "30 sec/side",  # Make it clear it's per side
                "type": "cooldown"
            })

        return cooldown
    
    def generate_workout(self, date: str = None,
                        focus: str = "full_body",
                        difficulty: str = "beginner",
                        total_duration: int = 35) -> Dict[str, Any]:
        """Generate a complete strength training workout."""
        import math
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # Clamp target total to 30-40 minutes
        target_total = max(30, min(40, total_duration))
        
        # Define time constants
        sets_time = {
            "beginner": 1.5,    # 1.5 min per set (includes rest)
            "intermediate": 1.5,
            "advanced": 2.0
        }
        time_per_set = sets_time.get(difficulty, 1.5)
        sets_per_exercise = {"beginner": 2, "intermediate": 3, "advanced": 4}.get(difficulty, 2)
        time_per_main_exercise = sets_per_exercise * time_per_set
        
        # Generate warmup and cooldown first to compute their actual durations
        # Warmup: ~5 min (2-3 exercises @ 2 min each - includes both sides)
        warmup = self._generate_warmup(5)
        warmup_duration = len(warmup) * 2.0  # 2 min per exercise (both sides + transition)

        # Cooldown: ~5 min (2-3 exercises @ 2 min each - includes both sides)
        cooldown = self._generate_cooldown(5)
        cooldown_duration = len(cooldown) * 2.0  # 2 min per exercise (both sides + transition)
        
        # Calculate main exercise count to hit target total
        # desired_by_target: exercises needed to reach target
        desired_by_target = math.ceil((target_total - warmup_duration - cooldown_duration) / time_per_main_exercise)
        
        # max_by_40: max exercises without exceeding 40 min
        max_by_40 = math.floor((40 - warmup_duration - cooldown_duration) / time_per_main_exercise)
        
        # Ensure at least 3 exercises, but don't exceed max_by_40
        num_main = max(3, min(desired_by_target, max_by_40))
        
        # Generate main workout with explicit count
        main = self._generate_main_workout(focus, difficulty, 0, forced_count=num_main)
        
        # Calculate actual durations based on generated exercises
        main_duration = len(main) * time_per_main_exercise
        
        # Compute final durations (rounded consistently)
        warmup_duration_final = round(warmup_duration)
        main_duration_final = round(main_duration)
        cooldown_duration_final = round(cooldown_duration)
        total_duration_final = warmup_duration_final + main_duration_final + cooldown_duration_final
        
        # Create workout data
        workout_data = {
            "date": date,
            "title": f"{focus.replace('_', ' ').title()} Strength Training",
            "description": f"A {difficulty} level {focus} workout for runners.",
            "warmup_exercises": json.dumps(warmup),
            "main_exercises": json.dumps(main),
            "cooldown_exercises": json.dumps(cooldown),
            "warmup_duration": warmup_duration_final,
            "main_duration": main_duration_final,
            "cooldown_duration": cooldown_duration_final,
            "total_duration": total_duration_final,
            "primary_focus": focus,
            "difficulty": difficulty
        }
        
        return workout_data
    
    def save_workout(self, workout_data: Dict[str, Any]) -> bool:
        """Save workout to database."""
        try:
            import uuid
            
            with engine.connect() as conn:
                # Check if workout already exists for this date
                existing = conn.execute(
                    text(
                        """
                        SELECT id FROM daily_strength_workouts
                        WHERE date = :date
                        """
                    ),
                    {"date": workout_data["date"]}
                ).fetchone()
                
                if existing:
                    print(f"Workout already exists for {workout_data['date']}. Skipping.")
                    return False
                
                # Insert new workout
                conn.execute(
                    text(
                        """
                        INSERT INTO daily_strength_workouts (
                            id, date, title, description, warmup_exercises,
                            main_exercises, cooldown_exercises, warmup_duration,
                            main_duration, cooldown_duration, total_duration,
                            primary_focus, difficulty
                        ) VALUES (
                            :id, :date, :title, :description, :warmup_exercises,
                            :main_exercises, :cooldown_exercises, :warmup_duration,
                            :main_duration, :cooldown_duration, :total_duration,
                            :primary_focus, :difficulty
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        **workout_data
                    }
                )
                
                conn.commit()
                print(f"Successfully saved workout for {workout_data['date']}")
                return True
                
        except Exception as e:
            print(f"Error saving workout: {e}")
            return False
    
    def generate_workouts_for_week(self, start_date: str = None,
                                  difficulty: str = "beginner") -> int:
        """Generate workouts for a week."""
        if start_date is None:
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        # Rotation of workout focuses
        focuses = ["lower_body", "upper_body", "core", "full_body", 
                   "lower_body", "upper_body", "rest"]
        
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        saved_count = 0
        
        for i, focus in enumerate(focuses):
            date = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            
            if focus == "rest":
                continue
            
            workout_data = self.generate_workout(
                date=date,
                focus=focus,
                difficulty=difficulty
            )
            
            if self.save_workout(workout_data):
                saved_count += 1
        
        return saved_count


def main():
    """Test the workout generator."""
    generator = StrengthWorkoutGenerator()
    
    # Generate a workout for today
    print("\n" + "="*80)
    print("GENERATING WORKOUT FOR TODAY")
    print("="*80)
    
    workout = generator.generate_workout(
        difficulty="beginner",
        focus="lower_body"
    )
    
    print(f"\nWorkout: {workout['title']}")
    print(f"Date: {workout['date']}")
    print(f"Total Duration: {workout['total_duration']} minutes")
    print(f"\nWarmup ({workout['warmup_duration']} min):")
    
    warmup = json.loads(workout['warmup_exercises'])
    for ex in warmup:
        print(f"  - {ex['name']}: {ex['sets']} set(s) of {ex['reps']}")
    
    print(f"\nMain Workout ({workout['main_duration']} min):")
    main = json.loads(workout['main_exercises'])
    for ex in main:
        print(f"  - {ex['name']}: {ex['sets']} set(s) of {ex['reps']}")
    
    print(f"\nCooldown ({workout['cooldown_duration']} min):")
    cooldown = json.loads(workout['cooldown_exercises'])
    for ex in cooldown:
        print(f"  - {ex['name']}: {ex['sets']} set(s) of {ex['reps']}")
    
    # Generate workouts for a week
    print("\n" + "="*80)
    print("GENERATING WORKOUTS FOR A WEEK")
    print("="*80)
    
    saved = generator.generate_workouts_for_week(
        start_date=datetime.now().strftime("%Y-%m-%d"),
        difficulty="beginner"
    )
    print(f"\nSaved {saved} workouts for the week")


if __name__ == "__main__":
    main()
