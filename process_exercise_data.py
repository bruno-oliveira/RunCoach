import json
import urllib.request
from typing import Dict, List, Any
import re

# Running-related muscles and muscle groups
RUNNING_MUSCLES = {
    "quadriceps", "hamstrings", "glutes", "calves",
    "abdominals", "obliques", "hip flexors", "lower back",
    "core", "legs", "quads", "hams"
}

# Valid equipment types for our use case
VALID_EQUIPMENT = {
    "body only", "bodyweight", "dumbbell", "dumbbells"
}

def normalize_muscle_name(muscle: str) -> str:
    """Normalize muscle name for comparison."""
    muscle = muscle.lower().strip()
    # Common aliases
    if muscle in ["abs", "abdominals"]:
        return "abdominals"
    if muscle in ["quads", "quadriceps"]:
        return "quadriceps"
    if muscle in ["hams", "hamstring"]:
        return "hamstrings"
    if muscle in ["glute", "gluteus", "gluteals"]:
        return "glutes"
    if muscle in ["gastrocnemius", "soleus"]:
        return "calves"
    return muscle

def is_running_related(primary_muscles: List[str], secondary_muscles: List[str]) -> bool:
    """Check if exercise targets running-related muscles."""
    all_muscles = primary_muscles + secondary_muscles
    normalized_muscles = {normalize_muscle_name(m) for m in all_muscles}
    
    # Check if any muscle is running-related
    return bool(normalized_muscles & RUNNING_MUSCLES)

def is_valid_equipment(equipment: str) -> bool:
    """Check if equipment is valid for our use case."""
    if not equipment:
        return False
    normalized = equipment.lower().strip()
    
    # Check for exact matches
    if normalized in VALID_EQUIPMENT:
        return True
    
    # Check for dumbbell variations
    if "dumbbell" in normalized:
        return True
    
    # Check for bodyweight variations
    if "body" in normalized and "weight" in normalized:
        return True
    
    return False

def match_exercises_with_gifs(exercises: List[Dict], gifs: List[Dict]) -> List[Dict]:
    """Match exercises from free-exercise-db with GIFs from Exercises_Dataset."""
    
    # Create a mapping from exercise name to GIF URL
    gif_map = {}
    for gif in gifs:
        title = gif.get("title", "").lower().strip()
        # Remove common variations to improve matching
        title_clean = re.sub(r'\s+', ' ', title)
        title_clean = title_clean.replace(" dumbbell", "").replace(" barbell", "")
        gif_map[title_clean] = gif
    
    matched_exercises = []
    
    for exercise in exercises:
        exercise_name = exercise.get("name", "").lower().strip()
        exercise_name_clean = re.sub(r'\s+', ' ', exercise_name)
        exercise_name_clean = exercise_name_clean.replace(" dumbbell", "").replace(" barbell", "")
        
        # Try exact match
        matching_gif = gif_map.get(exercise_name_clean)
        
        # Try fuzzy matching if exact match fails
        if not matching_gif:
            for gif_title, gif_data in gif_map.items():
                if exercise_name_clean in gif_title or gif_title in exercise_name_clean:
                    matching_gif = gif_data
                    break
        
        exercise_with_gif = exercise.copy()
        if matching_gif:
            exercise_with_gif["gif_url"] = matching_gif.get("src")
            exercise_with_gif["target_muscles"] = matching_gif.get("targetMuscle")
        
        matched_exercises.append(exercise_with_gif)
    
    return matched_exercises

def filter_exercises(exercises: List[Dict]) -> List[Dict]:
    """Filter exercises for running-focused bodyweight and dumbbell exercises."""
    
    filtered = []
    
    for exercise in exercises:
        equipment = exercise.get("equipment", "").lower() if exercise.get("equipment") else ""
        primary_muscles = exercise.get("primaryMuscles", [])
        secondary_muscles = exercise.get("secondaryMuscles", [])
        
        # Check equipment
        is_bodyweight = equipment in ["body only", "bodyweight"]
        is_dumbbell = "dumbbell" in equipment
        
        if not (is_bodyweight or is_dumbbell):
            continue
        
        # Check if running-related
        if not is_running_related(primary_muscles, secondary_muscles):
            continue
        
        # Add flags
        exercise["is_running_related"] = True
        exercise["is_bodyweight"] = is_bodyweight
        exercise["is_dumbbell"] = is_dumbbell
        
        filtered.append(exercise)
    
    return filtered

def prepare_for_database(exercises: List[Dict]) -> List[Dict]:
    """Prepare exercises for database insertion."""
    
    prepared = []
    
    for exercise in exercises:
        prepared_exercise = {
            "exercise_id": exercise.get("id"),
            "name": exercise.get("name"),
            "force": exercise.get("force"),
            "level": exercise.get("level"),
            "mechanic": exercise.get("mechanic"),
            "equipment": exercise.get("equipment"),
            "primary_muscles": json.dumps(exercise.get("primaryMuscles", [])),
            "secondary_muscles": json.dumps(exercise.get("secondaryMuscles", [])),
            "instructions": json.dumps(exercise.get("instructions", [])),
            "category": exercise.get("category"),
            "target_muscles": exercise.get("target_muscles"),
            "images": json.dumps(exercise.get("images", [])),
            "gif_url": exercise.get("gif_url"),
            "is_running_related": exercise.get("is_running_related", False),
            "is_bodyweight": exercise.get("is_bodyweight", False),
            "is_dumbbell": exercise.get("is_dumbbell", False),
        }
        prepared.append(prepared_exercise)
    
    return prepared

def main():
    print("Fetching exercise data...")
    
    # Fetch free-exercise-db
    exercises_url = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
    with urllib.request.urlopen(exercises_url) as response:
        exercises_data = json.loads(response.read())
    
    # Fetch GIFs
    gifs_url = "https://raw.githubusercontent.com/azilRababe/Exercises_Dataset/refs/heads/main/data/gifs.json"
    with urllib.request.urlopen(gifs_url) as response:
        gifs_data = json.loads(response.read())
    
    print(f"Fetched {len(exercises_data)} exercises and {len(gifs_data)} GIFs")
    
    # Match exercises with GIFs
    print("\nMatching exercises with GIFs...")
    matched_exercises = match_exercises_with_gifs(exercises_data, gifs_data)
    matched_count = sum(1 for ex in matched_exercises if "gif_url" in ex)
    print(f"Matched {matched_count} exercises with GIFs")
    
    # Filter for running-related bodyweight and dumbbell exercises
    print("\nFiltering exercises...")
    filtered_exercises = filter_exercises(matched_exercises)
    print(f"Found {len(filtered_exercises)} running-related bodyweight/dumbbell exercises")
    
    # Show some examples
    print("\n" + "="*80)
    print("EXAMPLE EXERCISES:")
    print("="*80)
    for i, exercise in enumerate(filtered_exercises[:5]):
        print(f"\n{i+1}. {exercise['name']}")
        print(f"   Equipment: {exercise['equipment']}")
        print(f"   Primary Muscles: {exercise['primaryMuscles']}")
        print(f"   Has GIF: {'Yes' if 'gif_url' in exercise else 'No'}")
        print(f"   Category: {exercise['category']}")
    
    # Prepare for database
    print("\n" + "="*80)
    print("PREPARING FOR DATABASE...")
    print("="*80)
    prepared_exercises = prepare_for_database(filtered_exercises)
    
    # Save to JSON file for database insertion
    output_file = "strength_exercises.json"
    with open(output_file, "w") as f:
        json.dump(prepared_exercises, f, indent=2)
    
    print(f"\nSaved {len(prepared_exercises)} exercises to {output_file}")
    print("\nYou can now import this data into your database.")
    
    # Statistics
    print("\n" + "="*80)
    print("STATISTICS:")
    print("="*80)
    bodyweight_count = sum(1 for ex in filtered_exercises if ex["is_bodyweight"])
    dumbbell_count = sum(1 for ex in filtered_exercises if ex["is_dumbbell"])
    gif_count = sum(1 for ex in filtered_exercises if "gif_url" in ex)
    
    print(f"Bodyweight exercises: {bodyweight_count}")
    print(f"Dumbbell exercises: {dumbbell_count}")
    print(f"Exercises with GIFs: {gif_count}")
    print(f"Total running-related exercises: {len(filtered_exercises)}")

if __name__ == "__main__":
    main()
