import json
from typing import List, Dict, Any

def clean_up_meals(input_file: str = "app/data/meals.json", output_file: str = "app/data/meals.json"):
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    print(f"Total recipes before cleanup: {len(data)}")
    
    # Remove duplicates, keeping first occurrence
    seen_names = set()
    cleaned_data = []
    
    for recipe in data:
        name = recipe.get('name', '')
        if name not in seen_names:
            seen_names.add(name)
            cleaned_data.append(recipe)
        else:
            print(f"  Removed duplicate: {name}")
    
    print(f"Recipes after removing duplicates: {len(cleaned_data)}")
    
    # Add quick_meals tag to qualifying recipes
    quick_meals_count = 0
    for recipe in cleaned_data:
        prep_time = recipe.get('prep_time', 0)
        cook_time = recipe.get('cook_time', 0)
        total_time = prep_time + cook_time
        
        # Check if meal qualifies (less than 30 min)
        if 0 < total_time < 30:
            dietary_tags = recipe.get('dietary_tags', [])
            
            # Add quick_meals tag
            if 'quick_meals' not in dietary_tags:
                dietary_tags.append('quick_meals')
                recipe['dietary_tags'] = dietary_tags
                quick_meals_count += 1
    
    print(f"Added 'quick_meals' tag to {quick_meals_count} recipes")
    
    # Statistics
    print("\n" + "="*50)
    print("MEAL DATABASE STATISTICS")
    print("="*50)
    print(f"Total unique recipes: {len(cleaned_data)}")
    print(f"Quick meals (< 30 min): {sum(1 for r in cleaned_data if 'quick_meals' in r.get('dietary_tags', []))}")
    
    print("\nBy meal type:")
    for meal_type in ['breakfast', 'lunch', 'dinner', 'snack', 'post_workout']:
        count = sum(1 for r in cleaned_data if r.get('meal_type') == meal_type)
        quick_count = sum(1 for r in cleaned_data 
                         if r.get('meal_type') == meal_type and 'quick_meals' in r.get('dietary_tags', []))
        print(f"  {meal_type}: {count} total, {quick_count} quick")
    
    print("\nBy dietary tags (top 10):")
    tag_counts = {}
    for recipe in cleaned_data:
        for tag in recipe.get('dietary_tags', []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    for tag, count in sorted_tags[:10]:
        print(f"  {tag}: {count}")
    
    # Write cleaned data
    with open(output_file, 'w') as f:
        json.dump(cleaned_data, f, indent=2)
    
    print(f"\nCleaned data written to {output_file}")
    
    return cleaned_data

if __name__ == "__main__":
    clean_up_meals()