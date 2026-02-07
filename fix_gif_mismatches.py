#!/usr/bin/env python3
"""
Fix incorrect GIF URLs in strength_exercises.json
"""
import json

# Load exercises
with open('strength_exercises.json', 'r') as f:
    exercises = json.load(f)

# Corrections for mismatched GIFs
corrections = {
    # Already fixed
    "Hanging Leg Raise": "https://fitnessprogramer.com/wp-content/uploads/2021/08/Hanging-Leg-Raises.gif",
    "Freehand Jump Squat": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Jump-Squat.gif",
    "Push Up to Side Plank": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Push-Up-to-Side-Plank.gif",
    "Body-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Plank-to-Push-up.gif",
    
    # New corrections from detailed review
    "3/4 Sit-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Sit-ups.gif",
    "Sit-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Sit-ups.gif",
    "Janda Sit-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Sit-ups.gif",
    "Frog Sit-Ups": "https://fitnessprogramer.com/wp-content/uploads/2022/12/Frog-Sit-up.gif",
    "Oblique Crunches": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Oblique-Crunch.gif",
    "Oblique Crunches - On The Floor": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Oblique-Crunch.gif",
    "Cocoons": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Cocoons.gif",
    "Bottoms Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Leg-Raise.gif",
    "Gorilla Chin/Crunch": "https://fitnessprogramer.com/wp-content/uploads/2021/08/Hanging-Leg-Raises.gif",
    
    # Additional corrections from user feedback - using verified working URLs
    "All Fours Quad Stretch": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Kneeling-Quad-Stretch.gif",
    "Lower Back Curl": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Superman-exercise.gif",
    "Dumbbell Step Ups": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Step-up.gif",
    "Body-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/plank.gif",
    "Butt-Ups": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Pike-Push-up.gif",
    "Stomach Vacuum": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Stomach-Vacuum.gif",
    "Lying Prone Quadriceps": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Quad-Stretch.gif",
    "90/90 Hamstring": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Hamstring-Stretch.gif",
}

# Apply corrections
fixed_count = 0
for exercise in exercises:
    if exercise["name"] in corrections:
        old_url = exercise["gif_url"]
        new_url = corrections[exercise["name"]]
        exercise["gif_url"] = new_url
        fixed_count += 1
        print(f"✓ Fixed: {exercise['name']}")
        print(f"  Old: {old_url.split('/')[-1]}")
        print(f"  New: {new_url.split('/')[-1]}")
        print()

# Save updated file
with open('strength_exercises.json', 'w') as f:
    json.dump(exercises, f, indent=2)

print("="*50)
print(f"Fixed {fixed_count} GIF mismatches")
print("="*50)
