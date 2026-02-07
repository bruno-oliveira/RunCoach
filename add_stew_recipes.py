#!/usr/bin/env python3
"""
One-Pot Stew Recipe Addition Script

This script adds hearty one-pot stew recipes perfect for serving with rice.
Each stew is designed for easy preparation with minimal cleanup.
"""

import json
import os
from typing import Dict, List, Any

class StewRecipeAdder:
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
    
    def get_stew_recipes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Define one-pot stew recipes"""
        return {
            "lunch": [
                {
                    "name": "Beef and Root Vegetable Stew",
                    "meal_type": "lunch",
                    "description": "Classic one-pot beef stew with root vegetables, tender meat and rich flavor",
                    "instructions": "Cut 6oz beef chuck into 1-inch cubes. Heat 1 tbsp oil in large pot, brown beef 5 minutes. Remove beef. Add 1 cup chopped onion, 2 carrots diced, 2 celery stalks diced. Cook 5 min. Return beef, add 2 cups beef broth, 2 cups water, 2 tbsp tomato paste, 1 tsp thyme, 1 bay leaf. Simmer 45 min. Add 2 potatoes. Simmer 30 more. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 90,
                    "calories": 420,
                    "protein": 28,
                    "fiber": 6,
                    "carbs": 24,
                    "fat": 22,
                    "ingredients": [
                        "6oz beef chuck",
                        "1 tbsp oil",
                        "2 cups beef broth",
                        "1 onion",
                        "2 carrots",
                        "2 celery stalks",
                        "2 potatoes",
                        "2 tbsp tomato paste",
                        "1 tsp thyme",
                        "1 bay leaf"
                    ],
                    "dietary_tags": ["high_protein", "meal_prep", "freezer_friendly", "one_pot"]
                },
                {
                    "name": "Lentil Stew with Vegetables",
                    "meal_type": "lunch",
                    "description": "Hearty lentil stew packed with vegetables, perfect for meal prep",
                    "instructions": "Heat 1 tbsp oil in large pot. Add 1 chopped onion, 2 carrots diced, 2 celery stalks diced, 2 cloves garlic. Cook 5 min. Add 1 cup brown lentils, 4 cups vegetable broth, 1 cup diced tomatoes, 1 tsp cumin, 1 tsp smoked paprika. Bring to boil, reduce heat, simmer 40 min until lentils are tender. Season with salt, pepper. Serve over rice.",
                    "prep_time": 12,
                    "cook_time": 45,
                    "calories": 360,
                    "protein": 22,
                    "fiber": 18,
                    "carbs": 52,
                    "fat": 8,
                    "ingredients": [
                        "1 cup brown lentils",
                        "4 cups vegetable broth",
                        "1 onion",
                        "2 carrots",
                        "2 celery stalks",
                        "2 cloves garlic",
                        "1 cup tomatoes",
                        "1 tsp cumin",
                        "1 tsp smoked paprika"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "vegetarian", "vegan", "one_pot", "meal_prep"]
                },
                {
                    "name": "Chicken and Vegetable Stew",
                    "meal_type": "lunch",
                    "description": "Comforting chicken stew with vegetables, great for leftovers",
                    "instructions": "Cut 6oz chicken breast into pieces. Heat 1 tbsp oil in pot, brown chicken 3 min. Add 1 chopped onion, 3 carrots diced, 2 celery stalks, 1 parsnip diced. Cook 5 min. Add 4 cups chicken broth, 1/2 cup frozen peas, 1 tsp thyme, 1 bay leaf. Simmer 30 min until chicken is cooked. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 40,
                    "calories": 380,
                    "protein": 32,
                    "fiber": 8,
                    "carbs": 28,
                    "fat": 14,
                    "ingredients": [
                        "6oz chicken breast",
                        "4 cups chicken broth",
                        "1 onion",
                        "3 carrots",
                        "2 celery stalks",
                        "1 parsnip",
                        "1/2 cup frozen peas",
                        "1 tsp thyme",
                        "1 bay leaf"
                    ],
                    "dietary_tags": ["high_protein", "meal_prep", "one_pot"]
                },
                {
                    "name": "Three Bean Stew with Vegetables",
                    "meal_type": "lunch",
                    "description": "Protein-packed vegetarian stew with three types of beans",
                    "instructions": "Heat 1 tbsp oil in large pot. Add 1 chopped onion, 1 bell pepper diced, 2 cloves garlic. Cook 5 min. Add 1 cup each black beans, kidney beans, chickpeas. Add 3 cups vegetable broth, 1 cup diced tomatoes, 1 tsp Italian herbs. Simmer 25 min. Add 2 cups chopped spinach, simmer 3 more. Serve over rice.",
                    "prep_time": 10,
                    "cook_time": 35,
                    "calories": 400,
                    "protein": 24,
                    "fiber": 18,
                    "carbs": 56,
                    "fat": 10,
                    "ingredients": [
                        "1 cup black beans",
                        "1 cup kidney beans",
                        "1 cup chickpeas",
                        "3 cups vegetable broth",
                        "1 bell pepper",
                        "1 onion",
                        "1 cup tomatoes",
                        "2 cups spinach"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "vegetarian", "vegan", "one_pot", "meal_prep"]
                },
                {
                    "name": "Beef and Barley Stew",
                    "meal_type": "lunch",
                    "description": "Classic stew with beef and nutritious barley",
                    "instructions": "Cut 6oz beef chuck into cubes. Brown in pot with 1 tbsp oil. Add 1 chopped onion, 2 carrots diced, 2 celery stalks. Cook 5 min. Add 4 cups beef broth, 1/2 cup pearl barley, 2 tbsp tomato paste, 1 tsp thyme. Simmer 45 min until barley is tender. Season with salt, pepper. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 55,
                    "calories": 440,
                    "protein": 30,
                    "fiber": 8,
                    "carbs": 36,
                    "fat": 18,
                    "ingredients": [
                        "6oz beef chuck",
                        "4 cups beef broth",
                        "1/2 cup pearl barley",
                        "1 onion",
                        "2 carrots",
                        "2 celery stalks",
                        "2 tbsp tomato paste",
                        "1 tsp thyme"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep", "freezer_friendly"]
                },
                {
                    "name": "Pork and Apple Stew",
                    "meal_type": "lunch",
                    "description": "Sweet and savory stew with pork and apples",
                    "instructions": "Cut 6oz pork shoulder into cubes. Brown with 1 tbsp oil. Add 1 onion chopped, 2 apples peeled and diced, 2 carrots. Cook 5 min. Add 3 cups broth, 2 tbsp honey, 1 tsp cinnamon, 1/2 tsp nutmeg. Simmer 40 min. Serve with rice.",
                    "prep_time": 15,
                    "cook_time": 45,
                    "calories": 400,
                    "protein": 28,
                    "fiber": 6,
                    "carbs": 32,
                    "fat": 16,
                    "ingredients": [
                        "6oz pork shoulder",
                        "3 cups broth",
                        "2 apples",
                        "1 onion",
                        "2 carrots",
                        "2 tbsp honey",
                        "1 tsp cinnamon",
                        "1/2 tsp nutmeg"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Vegetable Chickpea Stew",
                    "meal_type": "lunch",
                    "description": "Rich vegetarian stew with chickpeas and mixed vegetables",
                    "instructions": "Heat 1 tbsp oil in pot. Add 1 onion, 2 carrots, 2 celery stalks, 1 parsnip. Cook 5 min. Add 2 cups chickpeas, 4 cups vegetable broth, 1 cup tomatoes, 2 cups mixed vegetables (peas, corn). Add 1 tsp each cumin, coriander. Simmer 30 min. Serve over rice.",
                    "prep_time": 12,
                    "cook_time": 35,
                    "calories": 380,
                    "protein": 18,
                    "fiber": 14,
                    "carbs": 62,
                    "fat": 8,
                    "ingredients": [
                        "2 cups chickpeas",
                        "4 cups vegetable broth",
                        "1 onion",
                        "2 carrots",
                        "2 celery stalks",
                        "1 parsnip",
                        "1 cup tomatoes",
                        "2 cups mixed vegetables",
                        "1 tsp cumin",
                        "1 tsp coriander"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "vegetarian", "vegan", "one_pot"]
                },
                {
                    "name": "Turkey Vegetable Stew",
                    "meal_type": "lunch",
                    "description": "Light and healthy turkey stew with vegetables",
                    "instructions": "Cut 6oz turkey breast into pieces. Brown with onions, garlic. Add 4 cups broth, 2 carrots, 2 celery stalks, 1 parsnip, 2 potatoes diced. Simmer 30 min. Add 1 cup peas. Simmer 5 more. Serve over rice.",
                    "prep_time": 12,
                    "cook_time": 35,
                    "calories": 360,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 28,
                    "fat": 10,
                    "ingredients": [
                        "6oz turkey breast",
                        "4 cups broth",
                        "2 carrots",
                        "2 celery stalks",
                        "1 parsnip",
                        "2 potatoes",
                        "1 cup peas"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "quick", "meal_prep"]
                }
            ],
            "dinner": [
                {
                    "name": "Beef Guinness Stew",
                    "meal_type": "dinner",
                    "description": "Classic Irish-style beef stew with Guinness for depth of flavor",
                    "instructions": "Cut 8oz beef chuck into cubes. Coat in flour, brown in 1 tbsp oil. Remove. Add 1 onion, 2 carrots, 2 celery stalks. Cook 5 min. Return beef. Add 1 cup Guinness beer, 2 cups beef broth, 2 tbsp tomato paste, 1 tsp thyme, 1 bay leaf. Simmer 1 hour. Add 2 potatoes quarters, simmer 30 more. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 90,
                    "calories": 520,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 28,
                    "fat": 28,
                    "ingredients": [
                        "8oz beef chuck",
                        "1 cup Guinness",
                        "2 cups beef broth",
                        "2 tbsp tomato paste",
                        "1 onion",
                        "2 carrots",
                        "2 celery stalks",
                        "2 potatoes",
                        "1 tsp thyme",
                        "flour"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep", "freezer_friendly"]
                },
                {
                    "name": "Lamb and Root Vegetable Stew",
                    "meal_type": "dinner",
                    "description": "Rich lamb stew with hearty root vegetables",
                    "instructions": "Cut 6oz lamb shoulder into cubes. Brown in 1 tbsp oil. Add 1 onion, 3 parsnips, 3 carrots, 2 rutabagas. Cook 5 min. Add 2 cups lamb broth, 1 cup red wine, 1 tbsp rosemary, thyme. Simmer 1 hour. Vegetables should be tender. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 65,
                    "calories": 480,
                    "protein": 32,
                    "fiber": 8,
                    "carbs": 26,
                    "fat": 28,
                    "ingredients": [
                        "6oz lamb shoulder",
                        "2 cups lamb broth",
                        "1 cup red wine",
                        "3 parsnips",
                        "3 carrots",
                        "2 rutabagas",
                        "1 onion",
                        "1 tbsp rosemary"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Seafood Stew",
                    "meal_type": "dinner",
                    "description": "Light and flavorful seafood stew with tomatoes and herbs",
                    "instructions": "Heat 1 tbsp olive oil in pot. Add 1 onion, 2 garlic cloves. Cook 2 min. Add 1 cup white wine, 2 cups fish broth, 1 cup diced tomatoes, 8oz cod, 8oz shrimp, 1/2 cup clams, 1 tbsp parsley, 1 tsp thyme. Simmer 15 min until seafood is cooked. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 20,
                    "calories": 420,
                    "protein": 44,
                    "fiber": 4,
                    "carbs": 18,
                    "fat": 14,
                    "ingredients": [
                        "8oz cod",
                        "8oz shrimp",
                        "1/2 cup clams",
                        "1 cup white wine",
                        "2 cups fish broth",
                        "1 cup tomatoes",
                        "onion, garlic",
                        "parsley, thyme"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "quick"]
                },
                {
                    "name": "Portuguese Beef Stew",
                    "meal_type": "dinner",
                    "description": "Traditional Portuguese stew with beef and chorizo",
                    "instructions": "Cut 8oz beef chuck, 4oz chorizo into cubes. Brown together in oil. Add 1 onion, 3 garlic cloves, 2 peppers. Cook 5 min. Add 3 cups beef broth, 1 cup diced tomatoes, 1/2 tsp paprika, 1 bay leaf. Simmer 45 min. Add 2 potatoes. Simmer 25 more. Serve with rice.",
                    "prep_time": 15,
                    "cook_time": 80,
                    "calories": 560,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 30,
                    "fat": 32,
                    "ingredients": [
                        "8oz beef chuck",
                        "4oz chorizo",
                        "3 cups beef broth",
                        "1 cup tomatoes",
                        "2 potatoes",
                        "1 onion",
                        "3 garlic cloves",
                        "2 peppers",
                        "1/2 tsp paprika"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Mushroom and Lentil Stew",
                    "meal_type": "dinner",
                    "description": "Earthy vegetarian stew with mushrooms and lentils",
                    "instructions": "Heat 1 tbsp oil in pot. Add 1 onion, 8oz mushrooms sliced. Cook 7 min until browned. Add garlic, 1 cup brown lentils, 4 cups vegetable broth, 1 cup tomatoes, 1 tsp each thyme and rosemary. Simmer 40 min. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 50,
                    "calories": 340,
                    "protein": 22,
                    "fiber": 16,
                    "carbs": 44,
                    "fat": 10,
                    "ingredients": [
                        "8oz mushrooms",
                        "1 cup brown lentils",
                        "4 cups vegetable broth",
                        "1 cup tomatoes",
                        "1 onion",
                        "thyme, rosemary"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "vegetarian", "vegan", "one_pot"]
                },
                {
                    "name": "Hungarian Beef Stew",
                    "meal_type": "dinner",
                    "description": "Spicy Hungarian beef stew with paprika and vegetables",
                    "instructions": "Cut 8oz beef chuck into cubes. Brown in oil. Add 1 onion, 2 garlic cloves, 2 tbsp Hungarian paprika. Cook 2 min. Add 2 cups beef broth, 1 cup diced tomatoes, 2 bell peppers, 2 potatoes, 1 tsp caraway seeds. Simmer 1 hour. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 65,
                    "calories": 500,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 36,
                    "fat": 24,
                    "ingredients": [
                        "8oz beef chuck",
                        "2 cups beef broth",
                        "2 tbsp Hungarian paprika",
                        "2 bell peppers",
                        "2 potatoes",
                        "1 cup tomatoes",
                        "1 tsp caraway seeds"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Moroccan Lamb Stew",
                    "meal_type": "dinner",
                    "description": "Fragrant Moroccan stew with lamb, chickpeas, and spices",
                    "instructions": "Cut 6oz lamb into cubes. Brown in oil. Add 1 onion, 2 tsp cumin, 2 tsp turmeric, 1 tsp cinnamon. Cook 2 min. Add 2 cups lamb broth, 1 cup chickpeas, 2 carrots, 2 tbsp raisins, 1 apricot. Simmer 45 min. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 50,
                    "calories": 480,
                    "protein": 32,
                    "fiber": 8,
                    "carbs": 36,
                    "fat": 24,
                    "ingredients": [
                        "6oz lamb",
                        "2 cups lamb broth",
                        "1 cup chickpeas",
                        "2 carrots",
                        "2 tbsp raisins",
                        "1 apricot",
                        "2 tsp cumin",
                        "2 tsp turmeric",
                        "1 tsp cinnamon"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Mediterranean Beef Stew",
                    "meal_type": "dinner",
                    "description": "Light Mediterranean-style beef stew with olives and herbs",
                    "instructions": "Cut 8oz beef chuck into cubes. Brown with 1 onion diced. Add 2 cups beef broth, 1/2 cup red wine, 1 cup diced tomatoes, 1/2 cup kalamata olives, 2 sprigs rosemary, 1 bay leaf. Simmer 50 min. Add 2 zucchini, 1 yellow squash. Simmer 15 more. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 70,
                    "calories": 480,
                    "protein": 36,
                    "fiber": 6,
                    "carbs": 18,
                    "fat": 26,
                    "ingredients": [
                        "8oz beef chuck",
                        "2 cups beef broth",
                        "1/2 cup red wine",
                        "1 cup tomatoes",
                        "1/2 cup olives",
                        "2 zucchini",
                        "1 yellow squash",
                        "rosemary, bay leaf"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Spicy Chorizo and Bean Stew",
                    "meal_type": "dinner",
                    "description": "Bold stew with chorizo, white beans, and vegetables",
                    "instructions": "Brown 4oz chorizo in pot. Remove, drain most fat. Add 1 onion, 2 red peppers diced, 2 garlic cloves. Cook 5 min. Return chorizo. Add 2 cups white beans, 3 cups chicken broth, 1 cup tomatoes, 1 tsp paprika. Simmer 35 min. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 45,
                    "calories": 480,
                    "protein": 28,
                    "fiber": 12,
                    "carbs": 48,
                    "fat": 20,
                    "ingredients": [
                        "4oz chorizo",
                        "2 cups white beans",
                        "3 cups chicken broth",
                        "2 red peppers",
                        "1 cup tomatoes",
                        "1 tsp paprika"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "quick"]
                },
                {
                    "name": "Cajun Beef Stew",
                    "meal_type": "dinner",
                    "description": "Spicy Cajun-style beef stew with okra and tomatoes",
                    "instructions": "Cut 8oz beef chuck into cubes. Brown with 1 tbsp Cajun seasoning. Remove. Add 1 onion, 1 green pepper diced, 3 celery stalks. Cook 5 min. Return beef. Add 3 cups beef broth, 1 cup tomatoes, 1 cup okra, 2 bay leaves. Simmer 45 min. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 55,
                    "calories": 480,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 24,
                    "fat": 24,
                    "ingredients": [
                        "8oz beef chuck",
                        "3 cups beef broth",
                        "1 cup tomatoes",
                        "1 cup okra",
                        "1 onion",
                        "1 green pepper",
                        "3 celery stalks",
                        "1 tbsp Cajun seasoning"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Coconut Beef Stew",
                    "meal_type": "dinner",
                    "description": "Creamy coconut milk beef stew with Asian spices",
                    "instructions": "Cut 8oz beef chuck into cubes. Brown with 1 lemongrass stalk, 2 ginger slices. Add 4 cups beef broth, 1 cup coconut milk, 1 tbsp fish sauce, 2 tbsp soy sauce, 2 potatoes, 2 carrots. Simmer 1 hour. Serve over rice.",
                    "prep_time": 20,
                    "cook_time": 65,
                    "calories": 520,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 32,
                    "fat": 30,
                    "ingredients": [
                        "8oz beef chuck",
                        "4 cups beef broth",
                        "1 cup coconut milk",
                        "1 tbsp fish sauce",
                        "2 tbsp soy sauce",
                        "2 potatoes",
                        "2 carrots",
                        "lemongrass, ginger"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "meal_prep"]
                },
                {
                    "name": "Sausage and Vegetable Stew",
                    "meal_type": "dinner",
                    "description": "Hearty stew with sausage and seasonal vegetables",
                    "instructions": "Brown 6oz Italian sausage. Remove. Add 1 onion, 3 carrots, 3 celery stalks, 2 potatoes diced. Cook 5 min. Return sausage. Add 3 cups chicken broth, 1/2 cup white wine, 1 tsp thyme, bay leaf. Simmer 40 min. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 50,
                    "calories": 520,
                    "protein": 32,
                    "fiber": 8,
                    "carbs": 28,
                    "fat": 32,
                    "ingredients": [
                        "6oz Italian sausage",
                        "3 cups chicken broth",
                        "1/2 cup white wine",
                        "3 carrots",
                        "3 celery stalks",
                        "2 potatoes",
                        "1 onion",
                        "thyme, bay leaf"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "quick", "meal_prep"]
                },
                {
                    "name": "Chicken and White Bean Stew",
                    "meal_type": "dinner",
                    "description": "Family-friendly stew with chicken and cannellini beans",
                    "instructions": "Cut 8oz chicken breast into pieces. Brown with onion, garlic. Add 4 cups chicken broth, 2 cups cannellini beans, 2 carrots, 2 celery stalks, 1 cup frozen peas, 1 tsp thyme, 2 sprigs rosemary. Simmer 30 min. Serve over rice.",
                    "prep_time": 15,
                    "cook_time": 35,
                    "calories": 480,
                    "protein": 40,
                    "fiber": 14,
                    "carbs": 36,
                    "fat": 16,
                    "ingredients": [
                        "8oz chicken breast",
                        "2 cups cannellini beans",
                        "4 cups chicken broth",
                        "2 carrots",
                        "2 celery stalks",
                        "1 cup frozen peas",
                        "thyme, rosemary"
                    ],
                    "dietary_tags": ["high_protein", "one_pot", "quick", "family_friendly"]
                }
            ]
        }
    
    def add_stew_recipes(self):
        """Add all stew recipes to the appropriate meal files"""
        stew_recipes = self.get_stew_recipes()
        
        for meal_type, new_recipes in stew_recipes.items():
            if meal_type in self.meal_files:
                existing_recipes = self.load_recipes(meal_type)
                existing_recipes.extend(new_recipes)
                self.save_recipes(meal_type, existing_recipes)
                print(f"✓ Added {len(new_recipes)} {meal_type} stew recipes")
        
        total = sum(len(recipes) for recipes in stew_recipes.values())
        print(f"\n🍖 All {total} one-pot stew recipes have been added successfully!")
        print("\nAll stews are designed to be:")
        print("• Made in a single pot for easy cleanup")
        print("• Served with rice for complete meals")
        print("• Perfect for meal prep and freezing")

if __name__ == "__main__":
    adder = StewRecipeAdder()
    adder.add_stew_recipes()