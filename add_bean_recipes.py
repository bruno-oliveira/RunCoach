#!/usr/bin/env python3
"""
Bean-Based Protein Recipe Addition Script for RunCoach App

This script adds nutritious, protein-rich bean-based recipes to expand the database
with affordable, sustainable, and performance-enhancing meal options.
"""

import json
import os
from typing import Dict, List, Any

class BeanRecipeAdder:
    def __init__(self):
        self.data_dir = "/Users/boliveira/Documents/RunCoach/app/data"
        self.meal_files = {
            "breakfast": "meals_breakfast.json",
            "lunch": "meals_lunch.json", 
            "dinner": "meals_dinner.json",
            "snack": "meals_snack.json",
            "post_workout": "meals_post_workout.json"
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
        print(f"Added {len([r for r in recipes if 'bean' in r.get('name', '').lower() or 'black' in r.get('name', '').lower() or 'chickpea' in r.get('name', '').lower()])} bean recipes to {meal_type}")
    
    def get_bean_recipes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Define new bean-based recipes by meal type"""
        return {
            "breakfast": [
                {
                    "name": "Black Bean Breakfast Scramble",
                    "meal_type": "breakfast",
                    "description": "Hearty scramble with black beans, eggs, and vegetables for sustained morning energy",
                    "instructions": "Heat 1 tsp olive oil in a non-stick skillet over medium heat. Add 1/2 cup diced onion and 1/2 cup bell pepper, cook for 3-4 minutes until softened. Add 1 cup canned black beans (rinsed and drained) and heat through. In a bowl, whisk 3 large eggs with 2 tbsp milk. Pour eggs into skillet with vegetables and beans. Gently scramble until eggs are cooked to your liking. Season with salt, pepper, and 1/4 tsp cumin. Serve with 2 tbsp shredded cheese and fresh cilantro.",
                    "prep_time": 8,
                    "cook_time": 10,
                    "calories": 380,
                    "protein": 24,
                    "fiber": 12,
                    "carbs": 28,
                    "fat": 18,
                    "ingredients": [
                        "3 large eggs",
                        "1 cup black beans",
                        "1/2 cup diced onion",
                        "1/2 cup bell pepper",
                        "2 tbsp milk",
                        "2 tbsp shredded cheese",
                        "1 tsp olive oil",
                        "1/4 tsp cumin",
                        "salt and pepper",
                        "fresh cilantro"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "gluten_free",
                        "meal_prep"
                    ]
                },
                {
                    "name": "Chickpea Flour Pancakes",
                    "meal_type": "breakfast",
                    "description": "High-protein savory pancakes made from chickpea flour, perfect for athletes",
                    "instructions": "In a bowl, whisk together 1 cup chickpea flour, 1/2 tsp baking powder, 1/4 tsp salt, and 1/4 tsp turmeric. Gradually add 1 cup water while whisking to create a smooth batter. Let rest for 5 minutes. Heat a non-stick skillet over medium heat and lightly grease with oil. Pour 1/4 cup batter for each pancake, cook for 2-3 minutes per side until golden brown. Serve with avocado slices and hot sauce.",
                    "prep_time": 10,
                    "cook_time": 15,
                    "calories": 320,
                    "protein": 18,
                    "fiber": 8,
                    "carbs": 42,
                    "fat": 10,
                    "ingredients": [
                        "1 cup chickpea flour",
                        "1 cup water",
                        "1/2 tsp baking powder",
                        "1/4 tsp salt",
                        "1/4 tsp turmeric",
                        "1 tsp oil",
                        "1/2 avocado",
                        "hot sauce"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "vegetarian",
                        "gluten_free",
                        "vegan_option"
                    ]
                }
            ],
            "lunch": [
                {
                    "name": "Three Bean Power Salad",
                    "meal_type": "lunch",
                    "description": "Protein-packed salad with three types of beans and fresh vegetables",
                    "instructions": "In a large bowl, combine 1 cup canned kidney beans (rinsed), 1 cup canned black beans (rinsed), and 1 cup canned chickpeas (rinsed). Add 2 cups chopped romaine lettuce, 1 cup cherry tomatoes (halved), 1/2 cup diced red onion, and 1/2 cup diced cucumber. In a small bowl, whisk together 3 tbsp olive oil, 2 tbsp red wine vinegar, 1 tsp Dijon mustard, and salt/pepper. Pour dressing over salad and toss well. Top with 1/4 cup pumpkin seeds.",
                    "prep_time": 15,
                    "cook_time": 0,
                    "calories": 420,
                    "protein": 22,
                    "fiber": 18,
                    "carbs": 48,
                    "fat": 16,
                    "ingredients": [
                        "1 cup kidney beans",
                        "1 cup black beans", 
                        "1 cup chickpeas",
                        "2 cups romaine lettuce",
                        "1 cup cherry tomatoes",
                        "1/2 cup red onion",
                        "1/2 cup cucumber",
                        "3 tbsp olive oil",
                        "2 tbsp red wine vinegar",
                        "1 tsp Dijon mustard",
                        "1/4 cup pumpkin seeds"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "vegan",
                        "meal_prep",
                        "no_cook"
                    ]
                },
                {
                    "name": "Spicy Black Bean Buddha Bowl",
                    "meal_type": "lunch",
                    "description": "Flavorful bowl with spicy black beans, brown rice, and roasted vegetables",
                    "instructions": "Cook 1/2 cup brown rice according to package directions. In a skillet, heat 1 tsp olive oil and sauté 1 cup canned black beans with 1/2 tsp cumin, 1/4 tsp chili powder, and a pinch of cayenne for 3-4 minutes. Arrange rice in a bowl and top with seasoned black beans, 1 cup roasted sweet potato cubes, 1/2 cup steamed broccoli, and 1/4 avocado sliced. Drizzle with 2 tbsp lime juice and 1 tsp olive oil.",
                    "prep_time": 10,
                    "cook_time": 25,
                    "calories": 460,
                    "protein": 20,
                    "fiber": 16,
                    "carbs": 68,
                    "fat": 14,
                    "ingredients": [
                        "1/2 cup brown rice",
                        "1 cup black beans",
                        "1 cup sweet potato",
                        "1/2 cup broccoli",
                        "1/4 avocado",
                        "1 tsp olive oil",
                        "1/2 tsp cumin",
                        "1/4 tsp chili powder",
                        "2 tbsp lime juice",
                        "pinch cayenne"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "vegan",
                        "meal_prep"
                    ]
                },
                {
                    "name": "White Bean and Tuna Salad",
                    "meal_type": "lunch",
                    "description": "Protein-rich combination of white beans and tuna with Mediterranean flavors",
                    "instructions": "In a bowl, flake 5 oz canned tuna in water. Add 1 cup canned cannellini beans (rinsed), 1/4 cup diced red onion, 1/4 cup chopped celery, and 2 tbsp chopped parsley. In a small bowl, mix 3 tbsp Greek yogurt, 1 tbsp lemon juice, 1 tsp Dijon mustard, salt and pepper. Pour dressing over tuna and bean mixture, toss gently. Serve over mixed greens or whole grain bread.",
                    "prep_time": 12,
                    "cook_time": 0,
                    "calories": 380,
                    "protein": 36,
                    "fiber": 10,
                    "carbs": 28,
                    "fat": 12,
                    "ingredients": [
                        "5 oz tuna in water",
                        "1 cup cannellini beans",
                        "1/4 cup red onion",
                        "1/4 cup celery",
                        "2 tbsp parsley",
                        "3 tbsp Greek yogurt",
                        "1 tbsp lemon juice",
                        "1 tsp Dijon mustard",
                        "mixed greens"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "gluten_free",
                        "no_cook",
                        "meal_prep"
                    ]
                }
            ],
            "dinner": [
                {
                    "name": "Red Bean and Turkey Chili",
                    "meal_type": "dinner",
                    "description": "Hearty chili with lean turkey and kidney beans, perfect for muscle recovery",
                    "instructions": "Heat 1 tsp olive oil in a large pot over medium-high heat. Add 1 lb ground turkey and cook until browned, breaking it apart. Add 1 chopped onion, 2 minced garlic cloves, and cook for 3 minutes. Add 2 tbsp chili powder, 1 tsp cumin, and 1/2 tsp oregano. Stir in 1 cup canned kidney beans, 1 cup canned black beans, 1 cup canned diced tomatoes, and 2 cups beef broth. Simmer for 20-30 minutes. Season with salt and pepper.",
                    "prep_time": 10,
                    "cook_time": 35,
                    "calories": 420,
                    "protein": 38,
                    "fiber": 14,
                    "carbs": 32,
                    "fat": 16,
                    "ingredients": [
                        "1 lb ground turkey",
                        "1 cup kidney beans",
                        "1 cup black beans",
                        "1 cup diced tomatoes",
                        "1 onion",
                        "2 cloves garlic",
                        "2 cups beef broth",
                        "2 tbsp chili powder",
                        "1 tsp cumin",
                        "1 tsp olive oil"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "meal_prep",
                        "freezer_friendly"
                    ]
                },
                {
                    "name": "Lentil and Black Bean Curry",
                    "meal_type": "dinner",
                    "description": "Fragrant curry with lentils and black beans, served over brown rice",
                    "instructions": "Heat 1 tbsp coconut oil in a large saucepan over medium heat. Add 1 chopped onion and cook until soft. Add 2 minced garlic cloves and 1 tbsp grated ginger, cook for 1 minute. Add 1 tbsp curry powder and 1/2 tsp turmeric, stir for 30 seconds. Add 1 cup brown lentils (rinsed), 1 cup canned black beans, 1 can coconut milk, and 2 cups vegetable broth. Bring to a simmer, cover and cook for 25-30 minutes until lentils are tender. Serve over brown rice.",
                    "prep_time": 12,
                    "cook_time": 35,
                    "calories": 480,
                    "protein": 22,
                    "fiber": 18,
                    "carbs": 58,
                    "fat": 16,
                    "ingredients": [
                        "1 cup brown lentils",
                        "1 cup black beans",
                        "1 can coconut milk",
                        "2 cups vegetable broth",
                        "1 onion",
                        "2 cloves garlic",
                        "1 tbsp ginger",
                        "1 tbsp curry powder",
                        "1/2 tsp turmeric",
                        "1 tbsp coconut oil"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "vegan",
                        "meal_prep"
                    ]
                },
                {
                    "name": "White Bean and Chicken Stew",
                    "meal_type": "dinner",
                    "description": "Comforting stew with chicken breast, white beans, and vegetables",
                    "instructions": "Cut 1 lb chicken breast into 1-inch cubes. Heat 1 tsp olive oil in a large pot over medium-high heat. Brown chicken pieces for 3-4 minutes, then remove. Add 1 chopped onion, 2 carrots (diced), and 2 celery stalks (diced). Cook for 5 minutes. Add 2 minced garlic cloves and cook 1 minute. Return chicken to pot, add 1 cup cannellini beans, 4 cups chicken broth, 1 tsp thyme, and 1 bay leaf. Simmer for 20 minutes. Season with salt and pepper.",
                    "prep_time": 15,
                    "cook_time": 30,
                    "calories": 440,
                    "protein": 42,
                    "fiber": 12,
                    "carbs": 28,
                    "fat": 18,
                    "ingredients": [
                        "1 lb chicken breast",
                        "1 cup cannellini beans",
                        "4 cups chicken broth",
                        "1 onion",
                        "2 carrots",
                        "2 celery stalks",
                        "2 cloves garlic",
                        "1 tsp thyme",
                        "1 bay leaf",
                        "1 tsp olive oil"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "gluten_free",
                        "meal_prep"
                    ]
                }
            ],
            "snack": [
                {
                    "name": "Spicy Roasted Chickpeas",
                    "meal_type": "snack",
                    "description": "Crunchy, spicy roasted chickpeas for a satisfying high-protein snack",
                    "instructions": "Preheat oven to 400°F (200°C). Drain and rinse 1 can chickpeas, pat very dry with paper towels. Toss with 1 tsp olive oil, 1/2 tsp paprika, 1/4 tsp cayenne, 1/4 tsp garlic powder, and salt. Spread on baking sheet in single layer. Roast for 20-30 minutes until crispy, shaking halfway. Let cool completely before serving.",
                    "prep_time": 5,
                    "cook_time": 25,
                    "calories": 180,
                    "protein": 8,
                    "fiber": 6,
                    "carbs": 24,
                    "fat": 6,
                    "ingredients": [
                        "1 can chickpeas",
                        "1 tsp olive oil",
                        "1/2 tsp paprika",
                        "1/4 tsp cayenne",
                        "1/4 tsp garlic powder",
                        "salt"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "vegan",
                        "gluten_free",
                        "portable"
                    ]
                },
                {
                    "name": "White Bean Hummus",
                    "meal_type": "snack",
                    "description": "Creamy white bean hummus with herbs, perfect with vegetables or crackers",
                    "instructions": "In a food processor, combine 1 can cannellini beans (rinsed and drained), 2 tbsp tahini, 2 tbsp lemon juice, 1 minced garlic clove, 2 tbsp olive oil, 1 tsp fresh rosemary, salt and pepper. Process until smooth and creamy, scraping down sides as needed. Add 1-2 tbsp water if needed for consistency. Serve with vegetable sticks or whole grain crackers.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 160,
                    "protein": 7,
                    "fiber": 5,
                    "carbs": 18,
                    "fat": 8,
                    "ingredients": [
                        "1 can cannellini beans",
                        "2 tbsp tahini",
                        "2 tbsp lemon juice",
                        "1 garlic clove",
                        "2 tbsp olive oil",
                        "1 tsp rosemary",
                        "vegetable sticks",
                        "whole grain crackers"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "vegan",
                        "no_cook",
                        "meal_prep"
                    ]
                },
                {
                    "name": "Edamame and Bean Mix",
                    "meal_type": "snack",
                    "description": "Protein-packed mix of edamame and various beans with a savory seasoning",
                    "instructions": "In a bowl, combine 1/2 cup shelled edamame (thawed), 1/4 cup canned black beans (rinsed), 1/4 cup canned kidney beans (rinsed), and 1/4 cup canned chickpeas (rinsed). Add 1 tsp soy sauce, 1 tsp rice vinegar, 1/2 tsp sesame oil, and a pinch of red pepper flakes. Toss well to combine. Sprinkle with 1 tsp sesame seeds before serving.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 200,
                    "protein": 12,
                    "fiber": 8,
                    "carbs": 28,
                    "fat": 6,
                    "ingredients": [
                        "1/2 cup edamame",
                        "1/4 cup black beans",
                        "1/4 cup kidney beans",
                        "1/4 cup chickpeas",
                        "1 tsp soy sauce",
                        "1 tsp rice vinegar",
                        "1/2 tsp sesame oil",
                        "1 tsp sesame seeds",
                        "red pepper flakes"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "vegan",
                        "no_cook",
                        "portable"
                    ]
                }
            ],
            "post_workout": [
                {
                    "name": "Chocolate Bean Recovery Smoothie",
                    "meal_type": "post_workout",
                    "description": "Creamy chocolate smoothie with white beans for added protein and fiber",
                    "instructions": "In a blender, combine 1/2 cup canned cannellini beans (rinsed), 1 banana, 1 scoop chocolate protein powder, 1 tbsp almond butter, 1 cup almond milk, and 1 tsp honey. Blend until completely smooth. Add ice if desired and blend again. Pour into glass and enjoy immediately for optimal recovery.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 380,
                    "protein": 28,
                    "fiber": 10,
                    "carbs": 42,
                    "fat": 12,
                    "ingredients": [
                        "1/2 cup cannellini beans",
                        "1 banana",
                        "1 scoop chocolate protein powder",
                        "1 tbsp almond butter",
                        "1 cup almond milk",
                        "1 tsp honey",
                        "ice"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "recovery",
                        "no_cook"
                    ]
                },
                {
                    "name": "Black Bean Protein Bowl",
                    "meal_type": "post_workout",
                    "description": "Quick recovery bowl with black beans, quinoa, and protein-rich toppings",
                    "instructions": "In a microwave-safe bowl, combine 1 cup cooked quinoa and 1 cup canned black beans (rinsed). Microwave for 1-2 minutes until heated through. Top with 1/4 cup Greek yogurt, 2 tbsp salsa, and 1 tbsp shredded cheese. Add 1/4 avocado sliced and sprinkle with hot sauce to taste. Mix well before eating.",
                    "prep_time": 5,
                    "cook_time": 2,
                    "calories": 420,
                    "protein": 26,
                    "fiber": 14,
                    "carbs": 48,
                    "fat": 14,
                    "ingredients": [
                        "1 cup cooked quinoa",
                        "1 cup black beans",
                        "1/4 cup Greek yogurt",
                        "2 tbsp salsa",
                        "1 tbsp shredded cheese",
                        "1/4 avocado",
                        "hot sauce"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "recovery",
                        "quick",
                        "meal_prep"
                    ]
                }
            ]
        }
    
    def add_bean_recipes(self):
        """Add all bean-based recipes to the appropriate meal files"""
        bean_recipes = self.get_bean_recipes()
        
        for meal_type, new_recipes in bean_recipes.items():
            if meal_type in self.meal_files:
                # Load existing recipes
                existing_recipes = self.load_recipes(meal_type)
                
                # Add new bean recipes
                existing_recipes.extend(new_recipes)
                
                # Save updated recipes
                self.save_recipes(meal_type, existing_recipes)
                
                print(f"✓ Added {len(new_recipes)} bean recipes to {meal_type}")
        
        print("\n🌱 All bean-based recipes have been added successfully!")
        print("\nProtein benefits of beans:")
        print("• Black beans: 7.6g protein per 1/2 cup")
        print("• Chickpeas: 7.3g protein per 1/2 cup") 
        print("• Kidney beans: 7.7g protein per 1/2 cup")
        print("• White beans: 8.7g protein per 1/2 cup")
        print("• Lentils: 9g protein per 1/2 cup")

if __name__ == "__main__":
    adder = BeanRecipeAdder()
    adder.add_bean_recipes()