import json
import urllib.request

# Fetch the free-exercise-db JSON
print("=" * 80)
print("FREE EXERCISE DB - First 3 entries:")
print("=" * 80)
exercises_url = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
with urllib.request.urlopen(exercises_url) as response:
    exercises_data = json.loads(response.read())
    for i, exercise in enumerate(exercises_data[:3]):
        print(f"\n--- Exercise {i+1} ---")
        print(json.dumps(exercise, indent=2))

# Fetch the GIFs JSON
print("\n" + "=" * 80)
print("EXERCISES GIFS DATASET - First 3 entries:")
print("=" * 80)
gifs_url = "https://raw.githubusercontent.com/azilRababe/Exercises_Dataset/refs/heads/main/data/gifs.json"
with urllib.request.urlopen(gifs_url) as response:
    gifs_data = json.loads(response.read())
    for i, gif in enumerate(gifs_data[:3]):
        print(f"\n--- GIF {i+1} ---")
        print(json.dumps(gif, indent=2))

print("\n" + "=" * 80)
print(f"Total exercises in free-exercise-db: {len(exercises_data)}")
print(f"Total GIFs in Exercises_Dataset: {len(gifs_data)}")
print("=" * 80)
