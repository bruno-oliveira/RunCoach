#!/usr/bin/env python3
"""
Additional Stew Recipe Addition Script

This script adds 15 more one-pot stew recipes (8 lunch, 7 dinner).
"""

import json
import os
from typing import Dict, List, Any

class AdditionalStewRecipeAdder:
    def __init__(self):
        self.data_dir = "/Users/boliveira/Documents/RunCoach/app/data"
        self.meal_files = {
            "lunch": "meals_lunch.json",
            "dinner": "meals_dinner.json"
        }
        
    def load_recipes(self, meal_type: str) -> List[Dict[str, Any]]:
        """Load existing recipes for a given meal type"""
        file_path = os.path.join(self.data_dir, self.meal_files[meal_type])
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def save_recipes(self, meal_type: str, recipes: List[Dict[str, Any]]):
        """Save recipes to file"""
        file_path = os.path.join(self.data_dir, self.meal_files[meal_type])
        with open(file_path, 'w') as f:
            json.dump(recipes, f, indent=2)
    
    def get_additional_stew_recipes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Define additional one-pot stew recipes"""
        return {
            "lunch": [
                {
                    "name": "Hearty Beef and Pumpkin Stew",
                    "meal_type": "lunch",
                    "description": "Warming stew with beef chunks and pumpkin for a cozy meal",
                    "instructions": "Cut 8oz beef chuck into cubes. Brown in pot with 1 tbsp oil. Add 1 onion, 2 cloves garlic. Cook 3 min. Add 2 cups beef broth, 2 cups pumpkin cubes, 2 potatoes, 1 tsp thyme, cinnamon. Simmer 50 min. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 55,
                    "calories": 460,
                    "protein": 32,
                    "fiber": 8,
                    "carbs": 32,
                    "fat": 22,
                    "ingredients": [
                        "8oz beef chuck",
                        "2 cups beef broth",
                        "2 cups pumpkin",
                        "2 potatoes",
                        "1 onion",
                        "thyme, cinnamon"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Quick Beef and Carrot Stew",
                    "meal_type": "lunch",
                    "description": "Simplified beef stew for faster preparation",
                    "instructions": "Cut 6oz beef into small cubes. Brown quickly. Add 1 onion, 3 carrots diced, 2 cups beef broth, 1 cup frozen peas, 1 tsp thyme. Simmer 25 min. Serve over rice.",
                    "prep_time": 10,
                    "cook_time": 30,
                    "calories": 400,
                    "protein": 30,
                    "fiber": 6,
                    "carbs": 24,
                    "fat": 18,
                    "ingredients": [
                        "6oz beef",
                        "2 cups beef broth",
                        "3 carrots",
                        "1 cup peas",
                        "1 onion",
                        "1 tsp thyme"
                    ],
                    "dietary_tags": ["high_protein", "quick", "one_pot"]
                },
                {
                    "name": "Split Pea and Ham Stew",
                    "meal_type": "lunch",
                    "description": "Classic split pea soup-style stew with ham",
                    "instructions": "Rinse 1 cup split peas. Add to pot with 4 cups broth, 1 diced onion, 2 carrots, 2 celery stalks, 6oz ham hock. Simmer 45 min. Remove ham, dice, return. Add 2 cups water, simmer 15 more. Serve over rice.",
                    "prep_time": 10,
                    "cook_time": 65,
                    "calories": 440,
                    "protein": 28,
                    "fiber": 18,
                    "carbs": 44,
                    "fat": 14,
                    "ingredients": [
                        "1 cup split peas",
                        "4 cups broth",
                        "6oz ham hock",
                        "1 onion",
                        "2 carrots",
                        "2 celery stalks"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "one_pot", "meal_prep"]
                },
                {
                    "name": "Creamy Potato and Bacon Stew",
                    "meal_type": "lunch",
                    "description": "Hearty stew with potatoes and crispy bacon",
                    "instructions": "Cook 3 strips bacon, crumble. Brown 1 onion in fat. Add 4 cups chicken broth, 3 potatoes diced, 2 carrots, 1 cup cream, bacon. Simmer 30 min. Season with salt, pepper. Serve over rice.",
                    "prep_time": 12,
                    "cook_time": 35,
                    "calories": 480,
                    "protein": 20,
                    "fiber": 6,
                    "carbs": 42,
                    "fat": 28,
                    "ingredients": [
                        "3 strips bacon",
                        "4 cups chicken broth",
                        "3 potatoes",
                        "2 carrots",
                        "1 cup cream"
                    ],
                    "dietary_tags": ["one_pot", "quick", "meal_prep"]
                },
                {
                    "name": "Green Lentil and Vegetable Stew",
                    "meal_type": "lunch",
                    "description": "Nutritious green lentil stew with mixed vegetables",
                    "instructions": "Add 1 cup green lentils, 4 cups vegetable broth, diced zucchini, green beans, green pepper, onion to pot. Add 1 tsp cumin, garlic. Simmer 40 min. Serve over rice.",
                    "prep_time": 10,
                    "cook_time": 45,
                    "calories": 340,
                    "protein": 20,
                    "fiber": 16,
                    "carbs": 54,
                    "fat": 6,
                    "ingredients": [
                        "1 cup green lentils",
                        "4 cups vegetable broth",
                        "zucchini",
                        "green beans",
                        "green pepper",
                        "onion",
                        "cumin, garlic"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "vegetarian", "vegan", "one_pot"]
                },
                {
                    "name": "Sausage and Potato Stew",
                    "meal_type": "lunch",
                    "description": "Filling stew with sliced sausage and potatoes",
                    "instructions": "Slice 6oz kielbasa, brown in pot. Add 1 onion, 3 potatoes, 2 celery stalks, 4 cups chicken broth, baby spinach. Simmer 30 min. Serve over rice.",
                    "prep_time": 10,
                    "cook_time": 35,
                    "calories": 520,
                    "protein": 28,
                    "fiber": 8,
                    "carbs": 44,
                    "fat": 26,
                    "ingredients": [
                        "6oz kielbasa",
                        "4 cups chicken broth",
                        "3 potatoes",
                        "1 onion",
                        "2 celery stalks",
                        "baby spinach"
                    ],
                    "dietary_tags": ["high_protein", "quick", "one_pot"]
                },
                {
                    "name": "Turkey and Rice Stew",
                    "meal_type": "lunch",
                    "description": "Light turkey stew with vegetables and rice",
                    "instructions": "Cut 6oz turkey breast into pieces, brown. Add 1 onion, 2 carrots, celery, 3 cups chicken broth, 1/2 cup wild rice. Simmer 40 min. Serve over rice.",
                    "prep_time": 12,
                    "cook_time": 45,
                    "calories": 380,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 32,
                    "fat": 10,
                    "ingredients": [
                        "6oz turkey breast",
                        "3 cups chicken broth",
                        "1/2 cup wild rice",
                        "1 onion",
                        "2 carrots",
                        "celery"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "quick"]
                },
                {
                    "name": "Cabbage and Beef Stew",
                    "meal_type": "lunch",
                    "description": "Hearty Eastern European-style stew with cabbage",
                    "instructions": "Brown 6oz beef cubes in pot. Add 1 onion, 4 cups beef broth, 4 cups shredded cabbage, 2 tbsp tomato paste, 1 tsp caraway. Simmer 40 min. Serve over rice.",
                    "prep_time": 12,
                    "cook_time": 45,
                    "calories": 420,
                    "protein": 32,
                    "fiber": 10,
                    "carbs": 28,
                    "fat": 20,
                    "ingredients": [
                        "6oz beef",
                        "4 cups beef broth",
                        "4 cups cabbage",
                        "1 onion",
                        "2 tbsp tomato paste",
                        "1 tsp caraway"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                }
            ],
            "dinner": [
                {
                    "name": "Red Wine Beef Stew",
                    "meal_type": "dinner",
                    "description": "Classic French-style beef stew with red wine",
                    "instructions": "Cut 10oz beef chuck into cubes. Brown with 1 tbsp oil. Remove. Add 1 onion, 2 carrots, 2 celery. Cook 5 min. Return beef. Add 2 cups red wine, 2 cups beef broth, 2 tbsp tomato paste, thyme, bay leaves. Simmer 75 min. Add 2 potatoes quarters, simmer 25 more. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 100,
                    "calories": 600,
                    "protein": 40,
                    "fiber": 8,
                    "carbs": 32,
                    "fat": 32,
                    "ingredients": [
                        "10oz beef chuck",
                        "2 cups red wine",
                        "2 cups beef broth",
                        "2 tbsp tomato paste",
                        "2 potatoes",
                        "onion, carrots, celery",
                        "thyme, bay leaves"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Ale-Style Beef Stew",
                    "meal_type": "dinner",
                    "description": "British-style beef stew with ale and herbs",
                    "instructions": "Cut 8oz beef chuck. Brown in pot. Remove. Add 1 onion, leek. Cook 5 min. Return beef. Add 1 brown ale, 2 cups beef broth, 1 tbsp Worcestershire, thyme, rosemary. Simmer 1 hour. Add potatoes, carrots. Simmer 30 more. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 95,
                    "calories": 560,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 28,
                    "fat": 28,
                    "ingredients": [
                        "8oz beef chuck",
                        "1 brown ale",
                        "2 cups beef broth",
                        "1 tbsp Worcestershire",
                        "leek, onions",
                        "potatoes, carrots",
                        "thyme, rosemary"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Slow-Cooked Lamb Stew",
                    "meal_type": "dinner",
                    "description": "Tender slow-cooked lamb with vegetables",
                    "instructions": "Cut 8oz lamb shoulder into cubes. Brown with 1 tbsp oil. Add 1 onion, garlic. Cook 3 min. Add 3 cups lamb broth, 1 cup red wine, rosemary, thyme, bay leaves. Simmer 90 min. Add carrots, potatoes. Simmer 25 more. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 120,
                    "calories": 520,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 26,
                    "fat": 28,
                    "ingredients": [
                        "8oz lamb shoulder",
                        "3 cups lamb broth",
                        "1 cup red wine",
                        "onion, garlic",
                        "rosemary, thyme",
                        "carrots, potatoes",
                        "bay leaves"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Provençal Vegetable Stew",
                    "meal_type": "dinner",
                    "description": "French vegetable stew with white beans",
                    "instructions": "Heat 1 tbsp oil in pot. Add 1 onion, 2 zucchini, 2 yellow squash, 2 bell peppers. Cook 10 min. Add 2 cups cannellini beans, 4 cups vegetable broth, 1 cup tomatoes, 2 sprigs thyme, rosemary. Simmer 30 min. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 45,
                    "calories": 360,
                    "protein": 20,
                    "fiber": 16,
                    "carbs": 52,
                    "fat": 12,
                    "ingredients": [
                        "2 cups cannellini beans",
                        "4 cups vegetable broth",
                        "2 zucchini",
                        "2 yellow squash",
                        "2 bell peppers",
                        "1 cup tomatoes",
                        "thyme, rosemary"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "vegetarian", "vegan", "one_pot"]
                },
                {
                    "name": "Mexican Beef Stew",
                    "meal_type": "dinner",
                    "description": "Spicy Mexican-style stew with beef and chilies",
                    "instructions": "Cut 8oz beef chuck. Brown with 1 tsp cumin, chili powder. Add 1 onion, 3 garlic cloves, 4 cups beef broth, 2 ancho chilies, 1 tbsp tomato paste. Simmer 1 hour. Add potatoes, carrots. Simmer 25 more. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 90,
                    "calories": 500,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 32,
                    "fat": 24,
                    "ingredients": [
                        "8oz beef chuck",
                        "4 cups beef broth",
                        "2 ancho chilies",
                        "potatoes, carrots",
                        "1 tbsp tomato paste",
                        "1 tsp cumin, chili powder"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Beef and Mushroom Stew",
                    "meal_type": "dinner",
                    "description": "Earthy stew with beef, mushrooms, and herbs",
                    "instructions": "Cut 8oz beef chuck. Brown with 1 onion, 10oz mushrooms. Add 2 cups beef broth, 1/2 cup red wine, 2 tbsp tomato paste, thyme, rosemary. Simmer 50 min. Add 2 potatoes. Simmer 25 more. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 80,
                    "calories": 520,
                    "protein": 40,
                    "fiber": 8,
                    "carbs": 28,
                    "fat": 28,
                    "ingredients": [
                        "8oz beef chuck",
                        "10oz mushrooms",
                        "2 cups beef broth",
                        "1/2 cup red wine",
                        "2 tbsp tomato paste",
                        "2 potatoes",
                        "thyme, rosemary"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Paprika Beef Stew",
                    "meal_type": "dinner",
                    "description": "Rich beef stew with paprika and sour cream",
                    "instructions": "Cut 8oz beef chuck. Brown with 1 onion, 2 tbsp sweet paprika. Add 3 cups beef broth, 2 tbsp tomato paste, 1 tsp caraway. Simmer 60 min. Add 2 potatoes. Simmer 25 more. Stir in 1/2 cup sour cream. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 85,
                    "calories": 540,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 32,
                    "fat": 30,
                    "ingredients": [
                        "8oz beef chuck",
                        "3 cups beef broth",
                        "2 tbsp sweet paprika",
                        "2 tbsp tomato paste",
                        "2 potatoes",
                        "1 tsp caraway",
                        "1/2 cup sour cream"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                }
            ]
        }
    
    def add_additional_stew_recipes(self):
        """Add additional stew recipes to meal files"""
        stew_recipes = self.get_additional_stew_recipes()
        
        for meal_type, new_recipes in stew_recipes.items():
            if meal_type in self.meal_files:
                existing_recipes = self.load_recipes(meal_type)
                existing_recipes.extend(new_recipes)
                self.save_recipes(meal_type, existing_recipes)
                print(f"✓ Added {len(new_recipes)} {meal_type} stew recipes")
        
        total = sum(len(recipes) for recipes in stew_recipes.values())
        print(f"\n🍖 All {total} additional one-pot stew recipes added successfully!")

if __name__ == "__main__":
    adder = AdditionalStewRecipeAdder()
    adder.add_additional_stew_recipes()