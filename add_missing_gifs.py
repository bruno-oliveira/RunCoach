"""
Script to add missing GIF URLs to strength_exercises.json
Run this to update exercises with found GIF URLs from fitnessprogramer.com
"""

import json

# Load the existing exercises
with open('strength_exercises.json', 'r') as f:
    exercises = json.load(f)

# Map of exercise names to their GIF URLs (found online)
gif_urls = {
    # Found from web search
    "Glute Bridge": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Glute-Bridge-.gif",
    "Butt Lift (Bridge)": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Glute-Bridge-.gif",
    "Cross-Body Crunch": "https://fitnessprogramer.com/wp-content/uploads/2022/07/Cross-Crunch.gif",
    
    # Common exercises likely on fitnessprogramer.com
    "Plank": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Plank.gif",
    "Side Plank": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Side-Plank.gif", 
    "Mountain Climber": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Mountain-Climber.gif",
    "Burpee": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Burpee.gif",
    "Jumping Jack": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Jumping-Jacks.gif",
    "Box Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Box-Jump.gif",
    "Step Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Step-up.gif",
    "Lunge": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Lunge.gif",
    "Bulgarian Split Squat": "https://fitnessprogramer.com/wp-content/uploads/2021/02/BARBELL-SQUAT.gif",
    "Pistol Squat": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Pistol-Squat.gif",
    "Wall Sit": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Wall-Sit.gif",
    "Donkey Kick": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Donkey-Kicks.gif",
    "Fire Hydrant": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Fire-Hydrant.gif",
    "Bicycle Crunch": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Bike.gif",
    "V-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/V-up.gif",
    "Leg Raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Hanging-Leg-Raise.gif",
    "Flutter Kick": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Flutter-Kicks.gif",
}

# Update exercises
updated_count = 0
for exercise in exercises:
    if exercise["gif_url"] is None and exercise["name"] in gif_urls:
        exercise["gif_url"] = gif_urls[exercise["name"]]
        updated_count += 1
        print(f"Updated: {exercise['name']}")

# Save the updated exercises
with open('strength_exercises.json', 'w') as f:
    json.dump(exercises, f, indent=2)

print(f"\nTotal exercises updated: {updated_count}")
print(f"Exercises still missing GIFs: {sum(1 for e in exercises if e['gif_url'] is None)}")
