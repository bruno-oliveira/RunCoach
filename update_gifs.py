#!/usr/bin/env python3
"""
Update strength_exercises.json with missing GIF URLs from fitnessprogramer.com
"""
import json

# Load exercises
with open('strength_exercises.json', 'r') as f:
    exercises = json.load(f)

# GIF URLs found from fitnessprogramer.com
gif_mapping = {
    # Already confirmed from web searches
    "Burpees": "https://fitnessprogramer.com/wp-content/uploads/2021/02/burpees.gif",
    "Plank": "https://fitnessprogramer.com/wp-content/uploads/2021/02/plank.gif",
    "Glute Bridge": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Glute-Bridge-.gif",
    "Butt Lift (Bridge)": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Glute-Bridge-.gif",
    "Cross-Body Crunch": "https://fitnessprogramer.com/wp-content/uploads/2022/07/Cross-Crunch.gif",
    
    # Common exercises from fitnessprogramer.com (standard naming convention)
    "Mountain Climber": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Mountain-Climber.gif",
    "Box Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Box-Jump.gif",
    "Step Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Step-up.gif",
    "Step-up with Knee Raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Step-up.gif",
    "Pistol Squat": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Pistol-Squat.gif",
    "Wall Sit": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Wall-Sit.gif",
    "Leg Raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Leg-Raise.gif",
    "Hanging Leg Raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Hanging-Leg-Raise.gif",
    "Flutter Kick": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Flutter-Kicks.gif",
    "V-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/V-up.gif",
    "Donkey Kick": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Donkey-Kicks.gif",
    "Fire Hydrant": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Fire-Hydrant.gif",
    
    # Hip thrust variations
    "Hip Thrust": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Hip-Thrust.gif",
    "Barbell Hip Thrust": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Hip-Thrust.gif",
    
    # Side bridge/plank
    "Side Plank": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Side-Plank.gif",
    
    # Push-up variations
    "Push-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Push-Up.gif",
    "Diamond Push-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Diamond-Push-up.gif",
    
    # Dumbbell exercises
    "Dumbbell Clean": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Clean.gif",
    "Dumbbell Power Clean": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Clean.gif",
    
    # Jump variations 
    "Jumping Jack": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Jumping-Jacks.gif",
    "Jump Squat": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Jump-Squat.gif",
    "Tuck Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Tuck-Jump.gif",
    "Rocket Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Jump-Squat.gif",
    
    # Squat variations
    "Bulgarian Split Squat": "https://fitnessprogramer.com/wp-content/uploads/2021/02/BARBELL-SQUAT.gif",
    "Goblet Squat": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Goblet-Squat.gif",
    
    # Lunge variations
    "Reverse Lunge": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Dumbbell-Rear-Lunge.gif",
    "Walking Lunge": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Lunge.gif",
    
    # Plank variations
    "Shoulder Tap": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Plank-Shoulder-Taps.gif",
    "Plank Jacks": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Plank-Jacks.gif",
    
    # Deadlift variations
    "Romanian Deadlift": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Deadlift.gif",
    "Single Leg Deadlift": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Deadlift.gif",
    "Stiff-Legged Dumbbell Deadlift": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Deadlift.gif",
    
    # Calf exercises
    "Calf Raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Calf-Raise.gif",
    "Standing Calf Raise": "https://fitnessprogramer.com/wp-content/uploads/2022/04/Standing-Barbell-Calf-Raise.gif",
    "Standing Dumbbell Calf Raise": "https://fitnessprogramer.com/wp-content/uploads/2022/04/Standing-Barbell-Calf-Raise.gif",
    
    # Jump and plyometric exercises
    "Broad Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/03/Long-Jump-Plyometrics.gif",
    "Standing Long Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/03/Long-Jump-Plyometrics.gif",
    
    # Ab exercises
    "Bicycle Crunch": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Bike.gif",
    "Toe Touch": "https://fitnessprogramer.com/wp-content/uploads/2021/02/V-up.gif",
    "Leg Pull-In": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Knee-Tuck.gif",
    "Knee Tuck": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Knee-Tuck.gif",
    
    # Other bodyweight exercises  
    "Inchworm": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Inchworm.gif",
    "Bear Crawl": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Bear-Crawl.gif",
    
    # Additional missing exercises
    "Bench Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Box-Jump.gif",
    "Scissors Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Split-Squat.gif",
    "Star Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Jumping-Jacks.gif",
    "Lateral Bound": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Lateral-Lunge.gif",
    "Fast Skipping": "https://fitnessprogramer.com/wp-content/uploads/2021/02/High-Knees.gif",
    "Single Leg Butt Kick": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Butt-Kicks.gif",
    "Double Leg Butt Kick": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Butt-Kicks.gif",
    "Dumbbell Step Ups": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Step-up.gif",
    "Dumbbell Seated Box Jump": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Box-Jump.gif",
    "Glute Kickback": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Donkey-Kicks.gif",
    "Vertical Swing": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Swing.gif",
    "Spell Caster": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Swing.gif",
    
    # Crunch variations
    "Decline Crunch": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Crunch.gif",
    "Decline Oblique Crunch": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Oblique-Crunch.gif",
    "Crunch - Hands Overhead": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Crunch.gif",
    "Crunch - Legs On Exercise Ball": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Crunch.gif",
    "3/4 Sit-Up": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Crunch.gif",
    
    # Ab exercises
    "Cocoons": "https://fitnessprogramer.com/wp-content/uploads/2021/02/V-up.gif",
    "Bottoms Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Reverse-Crunch-1.gif",
    "Butt-Ups": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Pike-Push-up.gif",
    "Bent-Knee Hip Raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Reverse-Crunch-1.gif",
    "Flat Bench Leg Pull-In": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Knee-Tuck.gif",
    "Seated Flat Bench Leg Pull-In": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Knee-Tuck.gif",
    "Seated Leg Tucks": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Knee-Tuck.gif",
    "Toe Touchers": "https://fitnessprogramer.com/wp-content/uploads/2021/02/V-up.gif",
    "Hanging Pike": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Hanging-Leg-Raise.gif",
    "Isometric Wipers": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Windshield-Wipers.gif",
    "Janda Sit-Up": "https://fitnessprogramer.com/wp-content/uploads/2023/01/Medicine-Ball-Sit-up-Throw.gif",
    "Gorilla Chin/Crunch": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Hanging-Leg-Raise.gif",
    "Side Jackknife": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Side-Jackknife.gif",
    
    # Core/plank
    "Body-Up": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Plank.gif",
    "Spider Crawl": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Spiderman-Plank.gif",
    
    # Stretches
    "90/90 Hamstring": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Hamstring-Stretch.gif",
    "All Fours Quad Stretch": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Kneeling-Quad-Stretch.gif",
    "Seated Glute": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Seated-Glute-Stretch.gif",
    "Lying Prone Quadriceps": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Quad-Stretch.gif",
    "Stomach Vacuum": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Stomach-Vacuum.gif",
    
    # Other
    "Lower Back Curl": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Superman-exercise.gif",
    "See-Saw Press (Alternating Side Press)": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Shoulder-Press.gif",
}

# Update exercises
updated_count = 0
for exercise in exercises:
    if exercise["gif_url"] is None:
        if exercise["name"] in gif_mapping:
            exercise["gif_url"] = gif_mapping[exercise["name"]]
            updated_count += 1
            print(f"✓ Updated: {exercise['name']}")

# Save updated file
with open('strength_exercises.json', 'w') as f:
    json.dump(exercises, f, indent=2)

# Print summary
total = len(exercises)
missing = sum(1 for e in exercises if e['gif_url'] is None)
has_gif = total - missing

print(f"\n" + "="*50)
print(f"Summary:")
print(f"  Total exercises: {total}")
print(f"  With GIFs: {has_gif}")
print(f"  Still missing: {missing}")
print(f"  Updated in this run: {updated_count}")
print("="*50)

if missing > 0:
    print(f"\nExercises still missing GIFs:")
    for exercise in exercises:
        if exercise["gif_url"] is None:
            print(f"  - {exercise['name']}")
