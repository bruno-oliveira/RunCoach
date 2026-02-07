I want to add a "Strength training" top nav to our app, that contains sets and reps for the exercises focused on strengthening muscles for running.
Most of our exercises in our app are body weight exercises since those are easy to do anywhere. I have 2 dumbbells at home so let's focus on that too.
The goal is to have a dedicated page with daily workouts in the app that can be favorited by logged in users.
Let's add a sort of warmup and cooldown to each exercise main set, and lets make it all between 30-40 min MAX.
To add images/gifs of the exercises lets use:
1. yuhonas/free-exercise-db - 800+ exercises with images (not GIFs, but images), public domain, Unlicense
2. azilRababe/Exercises_Dataset - Smaller but has GIFs specifically mentioned, MIT license 

JSON structure for https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json:
```json
[
  {
    "name": "3/4 Sit-Up",
    "force": "pull",
    "level": "beginner",
    "mechanic": "compound",
    "equipment": "body only",
    "primaryMuscles": [
      "abdominals"
    ],
    "secondaryMuscles": [],
    "instructions": [
      "Lie down on the floor and secure your feet. Your legs should be bent at the knees.",
      "Place your hands behind or to the side of your head. You will begin with your back on the ground. This will be your starting position.",
      "Flex your hips and spine to raise your torso toward your knees.",
      "At the top of the contraction your torso should be perpendicular to the ground. Reverse the motion, going only ¾ of the way down.",
      "Repeat for the recommended amount of repetitions."
    ],
    "category": "strength",
    "images": [
      "3_4_Sit-Up/0.jpg",
      "3_4_Sit-Up/1.jpg"
    ],
    "id": "3_4_Sit-Up"
  },
  {
    "name": "90/90 Hamstring",
    "force": "push",
    "level": "beginner",
    "mechanic": null,
    "equipment": "body only",
    "primaryMuscles": [
      "hamstrings"
    ],
    "secondaryMuscles": [
      "calves"
    ],
    "instructions": [
      "Lie on your back, with one leg extended straight out.",
      "With the other leg, bend the hip and knee to 90 degrees. You may brace your leg with your hands if necessary. This will be your starting position.",
      "Extend your leg straight into the air, pausing briefly at the top. Return the leg to the starting position.",
      "Repeat for 10-20 repetitions, and then switch to the other leg."
    ],
    "category": "stretching",
    "images": [
      "90_90_Hamstring/0.jpg",
      "90_90_Hamstring/1.jpg"
    ],
    "id": "90_90_Hamstring"
  },....
]
```

GIFS in https://raw.githubusercontent.com/azilRababe/Exercises_Dataset/refs/heads/main/data/gifs.json:
```json
[{"targetMuscle":"full-body","title":"One Arm Medicine Ball Slam","src":"https:\/\/fitnessprogramer.com\/wp-content\/uploads\/2024\/06\/One-Arm-Medicine-Ball-Slam.gif"},{"targetMuscle":"full-body","title":"Navy Seal Burpee","src":"https:\/\/fitnessprogramer.com\/wp-content\/uploads\/2023\/10\/Navy-Seal-Burpee.gif"},{"targetMuscle":"full-body","title":"Dumbbell Walking Lunge","src":"https:\/\/fitnessprogramer.com\/wp-content\/uploads\/2023\/09\/dumbbell-lunges.gif"},...]
```

I think trying to combine these two datasets would be a good idea.

KEY: IF YOU WANT TO READ THE JSON FILES, DO NOT USE THE WEBFETCH TOOL AND WRITE A PYTHON SCRIPT TO PARSE 3 ENTRIES OF EACH JSON FILE.