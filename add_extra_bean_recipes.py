#!/usr/bin/env python3
"""
Additional Bean-Based Protein Recipe Addition Script

This script adds 45 new protein-rich bean-based recipes (15 lunch, 15 dinner, 15 snack)
focused on beans, vegetables, and beef combinations.
"""

import json
import os
from typing import Dict, List, Any

class ExtraBeanRecipeAdder:
    def __init__(self):
        self.data_dir = "/Users/boliveira/Documents/RunCoach/app/data"
        self.meal_files = {
            "lunch": "meals_lunch.json",
            "dinner": "meals_dinner.json",
            "snack": "meals_snack.json"
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
    
    def get_extra_bean_recipes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Define new bean-based recipes by meal type"""
        return {
            "lunch": [
                {
                    "name": "Beef and Black Bean Quesadilla",
                    "meal_type": "lunch",
                    "description": "Protein-packed quesadilla with seasoned beef and black beans",
                    "instructions": "Brown 4oz lean ground beef with 1 tsp taco seasoning. Add 1/2 cup black beans. Spread 1 whole wheat tortilla with 2 tbsp cheese, add beef mixture and another tortilla on top. Cook in skillet 3-4 min each side until golden. Cut into wedges and serve.",
                    "prep_time": 8,
                    "cook_time": 12,
                    "calories": 450,
                    "protein": 28,
                    "fiber": 8,
                    "carbs": 32,
                    "fat": 22,
                    "ingredients": [
                        "4oz lean ground beef",
                        "1/2 cup black beans",
                        "2 whole wheat tortillas",
                        "2 tbsp cheese",
                        "1 tsp taco seasoning"
                    ],
                    "dietary_tags": ["high_protein", "meal_prep", "quick"]
                },
                {
                    "name": "Bean and Beef Stuffed Sweet Potato",
                    "meal_type": "lunch",
                    "description": "Loaded sweet potato with spiced ground beef and beans",
                    "instructions": "Microwave 1 large sweet potato 6-7 min. In skillet, brown 4oz ground beef with 1/2 cup diced onion and garlic. Add 1/2 cup black beans, 1/2 tsp cumin, 1/4 tsp chili powder. Split potato, fill with beef mixture. Top with 2 tbsp Greek yogurt.",
                    "prep_time": 5,
                    "cook_time": 15,
                    "calories": 420,
                    "protein": 26,
                    "fiber": 12,
                    "carbs": 38,
                    "fat": 16,
                    "ingredients": [
                        "1 large sweet potato",
                        "4oz ground beef",
                        "1/2 cup black beans",
                        "1/2 cup diced onion",
                        "2 tbsp Greek yogurt",
                        "1/2 tsp cumin"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "Chickpea and Beef Protein Bowl",
                    "meal_type": "lunch",
                    "description": "Balanced bowl with roasted chickpeas, ground beef, and vegetables",
                    "instructions": "Roast 1 cup chickpeas at 400°F for 25 min with 1 tsp olive oil and spices. Brown 4oz ground beef with 1/2 tsp cumin. Arrange 1 cup cooked quinoa, roasted chickpeas, beef, 1 cup mixed greens, 1/4 avocado. Drizzle with 1 tbsp tahini.",
                    "prep_time": 10,
                    "cook_time": 25,
                    "calories": 480,
                    "protein": 32,
                    "fiber": 14,
                    "carbs": 44,
                    "fat": 20,
                    "ingredients": [
                        "1 cup chickpeas",
                        "4oz ground beef",
                        "1 cup quinoa",
                        "1 cup mixed greens",
                        "1/4 avocado",
                        "1 tbsp tahini"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "White Bean and Beef Sloppy Joes",
                    "meal_type": "lunch",
                    "description": "Healthy twist on sloppy joes with white beans and lean beef",
                    "instructions": "Brown 4oz ground beef with 1/2 cup diced onion. Add 1/2 cup mashed cannellini beans, 1/4 cup tomato sauce, 1 tbsp tomato paste, 1 tsp Worcestershire, salt/pepper. Simmer 5 min. Serve on whole grain bun.",
                    "prep_time": 5,
                    "cook_time": 12,
                    "calories": 380,
                    "protein": 26,
                    "fiber": 8,
                    "carbs": 32,
                    "fat": 14,
                    "ingredients": [
                        "4oz ground beef",
                        "1/2 cup cannellini beans",
                        "1/4 cup tomato sauce",
                        "1 tbsp tomato paste",
                        "1 whole grain bun",
                        "1 tbsp Worcestershire"
                    ],
                    "dietary_tags": ["high_protein", "quick", "family_friendly"]
                },
                {
                    "name": "Three Bean and Beef Salad",
                    "meal_type": "lunch",
                    "description": "Fresh salad with beef and three types of beans",
                    "instructions": "Brown 3oz ground beef, let cool. In bowl, combine 1/4 cup each black beans, kidney beans, chickpeas. Add 3 cups mixed greens, 1 cup cherry tomatoes, 1/2 cucumber. Add beef, 2 tbsp Italian dressing. Toss and serve.",
                    "prep_time": 10,
                    "cook_time": 8,
                    "calories": 380,
                    "protein": 26,
                    "fiber": 10,
                    "carbs": 28,
                    "fat": 16,
                    "ingredients": [
                        "3oz ground beef",
                        "1/4 cup black beans",
                        "1/4 cup kidney beans",
                        "1/4 cup chickpeas",
                        "3 cups mixed greens",
                        "2 tbsp Italian dressing"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "no_cook"]
                },
                {
                    "name": "Black Bean and Beef Burrito Bowl",
                    "meal_type": "lunch",
                    "description": "Deconstructed burrito with seasoned beef, black beans, and rice",
                    "instructions": "Cook 1/2 cup brown rice. Brown 4oz beef with 1/2 tsp cumin and garlic powder. In bowl, layer rice, 1/2 cup black beans, seasoned beef, 1/2 cup salsa, 1/4 cup Greek yogurt, 1/4 avocado.",
                    "prep_time": 5,
                    "cook_time": 20,
                    "calories": 460,
                    "protein": 28,
                    "fiber": 14,
                    "carbs": 48,
                    "fat": 16,
                    "ingredients": [
                        "1/2 cup brown rice",
                        "4oz ground beef",
                        "1/2 cup black beans",
                        "1/2 cup salsa",
                        "1/4 cup Greek yogurt",
                        "1/4 avocado"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "Roasted Bean and Beef Wrap",
                    "meal_type": "lunch",
                    "description": "Protein-rich wrap with roasted chickpeas and ground beef",
                    "instructions": "Roast 1/2 cup chickpeas at 400°F for 20 min. Brown 4oz beef with garlic powder. Warm whole wheat tortilla, spread with hummus, add roasted chickpeas, beef, shredded lettuce, tomatoes, 2 tbsp salsa. Roll and serve.",
                    "prep_time": 8,
                    "cook_time": 18,
                    "calories": 420,
                    "protein": 26,
                    "fiber": 10,
                    "carbs": 36,
                    "fat": 18,
                    "ingredients": [
                        "1/2 cup chickpeas",
                        "4oz ground beef",
                        "1 whole wheat tortilla",
                        "2 tbsp hummus",
                        "shredded lettuce",
                        "2 tbsp salsa"
                    ],
                    "dietary_tags": ["high_protein", "portable", "quick"]
                },
                {
                    "name": "Kidney Bean and Beef Chili Bowl",
                    "meal_type": "lunch",
                    "description": "Quick chili bowl with kidney beans, beef, and corn",
                    "instructions": "Brown 3oz ground beef with onion. Add 1/2 cup kidney beans, 1/2 cup corn, 1/4 cup tomato sauce, 1 tsp chili powder, 1/4 tsp cumin. Simmer 8 min. Serve over 1/2 cup brown rice.",
                    "prep_time": 5,
                    "cook_time": 15,
                    "calories": 400,
                    "protein": 24,
                    "fiber": 12,
                    "carbs": 38,
                    "fat": 14,
                    "ingredients": [
                        "3oz ground beef",
                        "1/2 cup kidney beans",
                        "1/2 cup corn",
                        "1/4 cup tomato sauce",
                        "1/2 cup brown rice",
                        "1 tsp chili powder"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "Lentil and Beef Protein Plate",
                    "meal_type": "lunch",
                    "description": "Nutrient-dense plate with lentils, ground beef, and vegetables",
                    "instructions": "Cook 1/2 cup brown lentils. Brown 4oz beef with garlic and herbs. Arrange lentils, beef, 1 cup steamed broccoli, 1/2 cup roasted carrots, 1/4 avocado on plate. Drizzle with 1 tbsp olive oil and lemon juice.",
                    "prep_time": 8,
                    "cook_time": 20,
                    "calories": 440,
                    "protein": 28,
                    "fiber": 14,
                    "carbs": 38,
                    "fat": 18,
                    "ingredients": [
                        "1/2 cup brown lentils",
                        "4oz ground beef",
                        "1 cup broccoli",
                        "1/2 cup carrots",
                        "1/4 avocado",
                        "1 tbsp olive oil"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "Pinto Bean and Beef Tacos",
                    "meal_type": "lunch",
                    "description": "Healthy tacos with pinto beans, seasoned beef, and fresh toppings",
                    "instructions": "Brown 4oz beef with 1 tsp taco seasoning. Warm 3 corn tortillas. Fill each with 1/4 cup pinto beans, beef mixture, shredded lettuce, diced tomatoes, 1 tbsp Greek yogurt.",
                    "prep_time": 8,
                    "cook_time": 12,
                    "calories": 400,
                    "protein": 26,
                    "fiber": 10,
                    "carbs": 34,
                    "fat": 16,
                    "ingredients": [
                        "4oz ground beef",
                        "3/4 cup pinto beans",
                        "3 corn tortillas",
                        "shredded lettuce",
                        "1 tbsp Greek yogurt"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "quick"]
                },
                {
                    "name": "Chickpea and Beef Pasta Salad",
                    "meal_type": "lunch",
                    "description": "Protein-packed pasta salad with chickpeas and ground beef",
                    "instructions": "Cook 2 oz whole wheat pasta. Brown 3oz beef. Cool and combine with pasta, 1/2 cup chickpeas, 1/2 cup diced bell peppers, 1/4 cup red onion, 2 tbsp Italian dressing, 1 tbsp parmesan.",
                    "prep_time": 12,
                    "cook_time": 12,
                    "calories": 420,
                    "protein": 24,
                    "fiber": 8,
                    "carbs": 44,
                    "fat": 14,
                    "ingredients": [
                        "2 oz whole wheat pasta",
                        "3oz ground beef",
                        "1/2 cup chickpeas",
                        "1/2 cup bell peppers",
                        "2 tbsp Italian dressing"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "White Bean and Beef Lettuce Wraps",
                    "meal_type": "lunch",
                    "description": "Low-carb wraps with cannellini beans and seasoned beef",
                    "instructions": "Brown 4oz beef with garlic powder. Mix with 1/2 cup mashed white beans. Serve in large lettuce cups with diced tomatoes, cucumber, 1 tbsp salsa, 2 tbsp shredded cheese.",
                    "prep_time": 8,
                    "cook_time": 8,
                    "calories": 320,
                    "protein": 28,
                    "fiber": 6,
                    "carbs": 14,
                    "fat": 18,
                    "ingredients": [
                        "4oz ground beef",
                        "1/2 cup cannellini beans",
                        "large lettuce leaves",
                        "diced tomatoes",
                        "1 tbsp salsa",
                        "2 tbsp cheese"
                    ],
                    "dietary_tags": ["high_protein", "low_carb", "quick"]
                },
                {
                    "name": "Black Bean and Beef Stuffed Peppers",
                    "meal_type": "lunch",
                    "description": "Colorful bell peppers stuffed with beef and black beans",
                    "instructions": "Halve 2 bell peppers, remove seeds. Brown 4oz beef with 1/2 cup black beans, 1/4 cup rice, 1 tsp cumin. Fill peppers, top with 2 tbsp cheese. Bake at 375°F for 20 min.",
                    "prep_time": 10,
                    "cook_time": 23,
                    "calories": 380,
                    "protein": 26,
                    "fiber": 8,
                    "carbs": 24,
                    "fat": 18,
                    "ingredients": [
                        "2 bell peppers",
                        "4oz ground beef",
                        "1/2 cup black beans",
                        "1/4 cup rice",
                        "2 tbsp cheese",
                        "1 tsp cumin"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "Bean and Beef Buddha Bowl",
                    "meal_type": "lunch",
                    "description": "Comprehensive bowl with beans, beef, vegetables, and grains",
                    "instructions": "Cook 1/2 cup quinoa. Roast 1 cup vegetables. Brown 4oz beef with 1/2 tsp each garlic and onion powder. Assemble bowl with quinoa, roasted vegetables, 1/4 cup chickpeas, beef, 1/4 avocado. Dress with 1 tbsp tahini.",
                    "prep_time": 12,
                    "cook_time": 18,
                    "calories": 480,
                    "protein": 30,
                    "fiber": 12,
                    "carbs": 40,
                    "fat": 20,
                    "ingredients": [
                        "1/2 cup quinoa",
                        "4oz ground beef",
                        "1/4 cup chickpeas",
                        "1 cup vegetables",
                        "1/4 avocado",
                        "1 tbsp tahini"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "Refried Bean and Beef Nachos",
                    "meal_type": "lunch",
                    "description": "Healthy nachos with refried beans, seasoned beef, and vegetables",
                    "instructions": "Brown 3oz beef with taco seasoning. On baking sheet, spread baked tortilla chips, 1/2 cup refried beans, seasoned beef, 1/4 cup corn, 1/4 cup diced tomatoes. Top with 2 tbsp cheese, Bake 5 min. Add fresh toppings.",
                    "prep_time": 8,
                    "cook_time": 10,
                    "calories": 440,
                    "protein": 24,
                    "fiber": 10,
                    "carbs": 38,
                    "fat": 20,
                    "ingredients": [
                        "3oz ground beef",
                        "1/2 cup refried beans",
                        "tortilla chips",
                        "1/4 cup corn",
                        "2 tbsp cheese",
                        "1 tbsp taco seasoning"
                    ],
                    "dietary_tags": ["high_protein", "family_friendly", "quick"]
                }
            ],
            "dinner": [
                {
                    "name": "Beef and Black Bean Enchiladas",
                    "meal_type": "dinner",
                    "description": "Flavorful enchiladas with seasoned ground beef and black beans",
                    "instructions": "Brown 6oz ground beef with 1/2 cup onion, garlic. Add 1 cup black beans, 1/2 tsp cumin, chili powder. Fill 6 corn tortillas, roll, place in dish. Top with 1/2 cup red enchilada sauce and 1/4 cup cheese. Bake 350°F 20 min.",
                    "prep_time": 15,
                    "cook_time": 25,
                    "calories": 520,
                    "protein": 32,
                    "fiber": 14,
                    "carbs": 44,
                    "fat": 22,
                    "ingredients": [
                        "6oz ground beef",
                        "1 cup black beans",
                        "6 corn tortillas",
                        "1/2 cup enchilada sauce",
                        "1/4 cup cheese",
                        "1/2 tsp cumin"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep", "freezer_friendly"]
                },
                {
                    "name": "Three Bean and Beef Stew",
                    "meal_type": "dinner",
                    "description": "Hearty stew with beef and three types of beans",
                    "instructions": "Cut 6oz beef into cubes. Brown in pot with 1 tbsp oil. Add 1 cup each beef broth and water. Add 1/2 cup each kidney beans, black beans, chickpeas. Add carrots, celery, onions, 2 tsp thyme. Simmer 45 min.",
                    "prep_time": 15,
                    "cook_time": 50,
                    "calories": 480,
                    "protein": 36,
                    "fiber": 16,
                    "carbs": 38,
                    "fat": 20,
                    "ingredients": [
                        "6oz beef cubes",
                        "1/2 cup kidney beans",
                        "1/2 cup black beans",
                        "1/2 cup chickpeas",
                        "1 cup beef broth",
                        "carrots, celery, onions"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep", "freezer_friendly"]
                },
                {
                    "name": "White Bean and Beef Ragout",
                    "meal_type": "dinner",
                    "description": "Italian-style ragout with white beans and ground beef",
                    "instructions": "Brown 6oz beef with garlic, onion. Add 1 cup diced tomatoes, 1/2 cup tomato paste, 1 tsp oregano, basil. Simmer 20 min. Add 1 cup cannellini beans, simmer 10 more. Serve over pasta.",
                    "prep_time": 10,
                    "cook_time": 35,
                    "calories": 460,
                    "protein": 34,
                    "fiber": 12,
                    "carbs": 36,
                    "fat": 20,
                    "ingredients": [
                        "6oz ground beef",
                        "1 cup cannellini beans",
                        "1 cup diced tomatoes",
                        "1/2 cup tomato paste",
                        "pasta",
                        "dried oregano, basil"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "family_friendly"]
                },
                {
                    "name": "Black Bean and Beef Shepherd's Pie",
                    "meal_type": "dinner",
                    "description": "Healthy shepherd's pie with black beans and beef",
                    "instructions": "Brown 6oz beef with 1 cup diced vegetables. Add 1/2 cup black beans, 2 tbsp tomato paste. Transfer to baking dish. Top with mashed cauliflower and potato mix. Bake 400°F 20 min until golden.",
                    "prep_time": 20,
                    "cook_time": 35,
                    "calories": 440,
                    "protein": 32,
                    "fiber": 12,
                    "carbs": 32,
                    "fat": 20,
                    "ingredients": [
                        "6oz ground beef",
                        "1/2 cup black beans",
                        "1 cup mixed vegetables",
                        "2 tbsp tomato paste",
                        "cauliflower potato mash"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "family_friendly"]
                },
                {
                    "name": "Bean and Beef Stuffed Cabbage Rolls",
                    "meal_type": "dinner",
                    "description": "Classic stuffed cabbage with beans and beef filling",
                    "instructions": "Steam 8 cabbage leaves. Mix 4oz ground beef, 1/2 cup rice, 1/2 cup kidney beans, 1 egg, 1/4 cup onion, garlic. Fill cabbage leaves, roll. Place in baking dish, cover with tomato sauce. Bake 350°F 45 min.",
                    "prep_time": 25,
                    "cook_time": 50,
                    "calories": 420,
                    "protein": 30,
                    "fiber": 14,
                    "carbs": 30,
                    "fat": 18,
                    "ingredients": [
                        "4oz ground beef",
                        "1/2 cup kidney beans",
                        "1/2 cup rice",
                        "8 cabbage leaves",
                        "1 egg",
                        "tomato sauce"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "Chickpea and Beef Curry",
                    "meal_type": "dinner",
                    "description": "Aromatic curry with chickpeas, beef, and vegetables",
                    "instructions": "Brown 6oz beef with 1 tsp curry powder, ginger, garlic. Add 1 cup chickpeas, 1 cup diced tomatoes, 1 cup coconut milk, 1 cup vegetables. Simmer 25 min. Serve over rice.",
                    "prep_time": 12,
                    "cook_time": 30,
                    "calories": 500,
                    "protein": 32,
                    "fiber": 10,
                    "carbs": 34,
                    "fat": 26,
                    "ingredients": [
                        "6oz ground beef",
                        "1 cup chickpeas",
                        "1 cup coconut milk",
                        "1 cup tomatoes",
                        "1 tsp curry powder",
                        "rice"
                    ],
                    "dietary_tags": ["high_protein", "meal_prep", "freezer_friendly"]
                },
                {
                    "name": "Lentil and Beef Bolognese",
                    "meal_type": "dinner",
                    "description": "Protein-rich Bolognese with lentils and ground beef",
                    "instructions": "Brown 6oz beef with onion, garlic. Add 1 cup brown lentils, 2 cups tomato sauce, 1/2 cup tomato paste, 1 tsp Italian herbs. Simmer 30 min lentils are tender. Serve over pasta.",
                    "prep_time": 10,
                    "cook_time": 35,
                    "calories": 460,
                    "protein": 34,
                    "fiber": 16,
                    "carbs": 42,
                    "fat": 18,
                    "ingredients": [
                        "6oz ground beef",
                        "1 cup brown lentils",
                        "2 cups tomato sauce",
                        "1/2 cup tomato paste",
                        "pasta",
                        "Italian herbs"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "family_friendly"]
                },
                {
                    "name": "Kidney Bean and Beef Chili",
                    "meal_type": "dinner",
                    "description": "Classic chili with kidney beans, beef, and vegetables",
                    "instructions": "Brown 6oz beef with onion, garlic. Add 1 cup kidney beans, 1 cup diced tomatoes, 2 tbsp tomato paste, 1 tsp chili powder, 1/2 tsp cumin. Simmer 30 min. Serve with 1/4 cup cornbread.",
                    "prep_time": 12,
                    "cook_time": 35,
                    "calories": 480,
                    "protein": 36,
                    "fiber": 14,
                    "carbs": 40,
                    "fat": 18,
                    "ingredients": [
                        "6oz ground beef",
                        "1 cup kidney beans",
                        "1 cup tomatoes",
                        "2 tbsp tomato paste",
                        "1 tsp chili powder",
                        "1/2 tsp cumin"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep", "freezer_friendly"]
                },
                {
                    "name": "Pinto Bean and Beef Tostadas",
                    "meal_type": "dinner",
                    "description": "Crispy tostadas topped with seasoned beef and pinto beans",
                    "instructions": "Brown 6oz beef with taco seasoning. heat 4 corn tortillas until crispy. Spread with 1/2 cup refried pinto beans, add seasoned beef, shredded lettuce, tomatoes, 2 tbsp cheese, 1/4 cup salsa.",
                    "prep_time": 10,
                    "cook_time": 15,
                    "calories": 460,
                    "protein": 32,
                    "fiber": 12,
                    "carbs": 40,
                    "fat": 20,
                    "ingredients": [
                        "6oz ground beef",
                        "1/2 cup pinto beans",
                        "4 corn tortillas",
                        "shredded lettuce",
                        "2 tbsp cheese",
                        "1/4 cup salsa"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "family_friendly"]
                },
                {
                    "name": "White Bean and Beef Soup",
                    "meal_type": "dinner",
                    "description": "Comforting soup with white beans, beef, and vegetables",
                    "instructions": "Brown 6oz beef with onion, garlic. Add 8 cups beef broth, 1 cup cannellini beans, 2 cups diced vegetables (carrots, celery, potatoes), 2 tsp thyme. Simmer 40 min. Serve with crusty bread.",
                    "prep_time": 15,
                    "cook_time": 45,
                    "calories": 420,
                    "protein": 32,
                    "fiber": 12,
                    "carbs": 36,
                    "fat": 16,
                    "ingredients": [
                        "6oz ground beef",
                        "1 cup cannellini beans",
                        "8 cups beef broth",
                        "2 cup vegetables",
                        "2 tsp thyme",
                        "crusty bread"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "Black Bean and Beef Burritos",
                    "meal_type": "dinner",
                    "description": "Large burritos with black beans, seasoned beef, and vegetables",
                    "instructions": "Brown 6oz beef with 1 tsp cumin. Warm 4 large tortillas. Fill each with 1/2 cup black beans, seasoned beef, 1/4 cup rice, 1/4 cup corn, salsa, 2 tbsp cheese, Greek yogurt. Roll tightly.",
                    "prep_time": 12,
                    "cook_time": 15,
                    "calories": 520,
                    "protein": 34,
                    "fiber": 14,
                    "carbs": 52,
                    "fat": 22,
                    "ingredients": [
                        "6oz ground beef",
                        "2 cups black beans",
                        "4 large tortillas",
                        "1 cup rice",
                        "1/2 cup corn",
                        "salsa, cheese"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep", "portable"]
                },
                {
                    "name": "Bean and Beef Stuffed Zucchini",
                    "meal_type": "dinner",
                    "description": "Healthy stuffed zucchini boats with beans and beef",
                    "instructions": "Cut 4 zucchini in half, scoop centers. Mix 6oz beef with 1/2 cup kidney beans, 1/4 cup rice, 1/4 cup diced tomatoes, garlic. Fill zucchini, top with 2 tbsp cheese. Bake 375°F 30 min.",
                    "prep_time": 15,
                    "cook_time": 32,
                    "calories": 400,
                    "protein": 32,
                    "fiber": 10,
                    "carbs": 28,
                    "fat": 18,
                    "ingredients": [
                        "4 zucchini",
                        "6oz ground beef",
                        "1/2 cup kidney beans",
                        "1/4 cup rice",
                        "1/4 cup tomatoes",
                        "2 tbsp cheese"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                },
                {
                    "name": "Chickpea and Beef Pilaf",
                    "meal_type": "dinner",
                    "description": "Flavorful pilaf with chickpeas, beef, and aromatic spices",
                    "instructions": "Brown 6oz beef with 1 tsp garam masala. Add 1 cup rice, 2 cups broth, 1 cup chickpeas. Bring to boil, cover, simmer 20 min. Let rest 5 min. Fluff with fork. Serve with yogurt.",
                    "prep_time": 10,
                    "cook_time": 25,
                    "calories": 480,
                    "protein": 34,
                    "fiber": 8,
                    "carbs": 52,
                    "fat": 16,
                    "ingredients": [
                        "6oz ground beef",
                        "1 cup chickpeas",
                        "1 cup rice",
                        "2 cups broth",
                        "1 tsp garam masala",
                        "yogurt"
                    ],
                    "dietary_tags": ["high_protein", "meal_prep", "freezer_friendly"]
                },
                {
                    "name": "Three Bean and Beef Chili Mac",
                    "meal_type": "dinner",
                    "description": "Comfort food fusion of chili and macaroni with beans and beef",
                    "instructions": "Brown 6oz beef with onion. Add 1 each kidney, black, and pinto beans. Add 1 cup tomato sauce, 1 tbsp chili powder, 2 cups water. Simmer 10 min. Add 2 cups cooked macaroni, simmer 5 more. Top with cheese.",
                    "prep_time": 8,
                    "cook_time": 20,
                    "calories": 500,
                    "protein": 32,
                    "fiber": 14,
                    "carbs": 52,
                    "fat": 20,
                    "ingredients": [
                        "6oz ground beef",
                        "1 cup mixed beans",
                        "1 cup tomato sauce",
                        "2 cups macaroni",
                        "1 tbsp chili powder",
                        "cheese"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "family_friendly"]
                },
                {
                    "name": "White Bean and Beef Casserole",
                    "meal_type": "dinner",
                    "description": "Hearty casserole with white beans, beef, and vegetables",
                    "instructions": "Brown 6oz beef with onions. Add 1 cup cannellini beans, 1 cup mixed vegetables, 1 cup diced tomatoes, 1/2 cup tomato sauce. Transfer to baking dish, top with 1/4 cup breadcrumbs and 2 tbsp cheese. Bake 375°F 25 min.",
                    "prep_time": 12,
                    "cook_time": 30,
                    "calories": 440,
                    "protein": 32,
                    "fiber": 12,
                    "carbs": 34,
                    "fat": 18,
                    "ingredients": [
                        "6oz ground beef",
                        "1 cup cannellini beans",
                        "1 cup vegetables",
                        "1 cup tomatoes",
                        "1/4 cup breadcrumbs",
                        "2 tbsp cheese"
                    ],
                    "dietary_tags": ["high_protein", "high_fiber", "meal_prep"]
                }
            ],
            "snack": [
                {
                    "name": "Beef Jerky and Roasted Chickpeas",
                    "meal_type": "snack",
                    "description": "High-protein snack combo of beef jerky and spiced chickpeas",
                    "instructions": "Roast 1/2 cup chickpeas with 1/2 tsp paprika at 400°F for 25 min. Serve with 1 oz beef jerky (store-bought). Enjoy as protein-rich snack.",
                    "prep_time": 2,
                    "cook_time": 25,
                    "calories": 240,
                    "protein": 20,
                    "fiber": 6,
                    "carbs": 18,
                    "fat": 10,
                    "ingredients": [
                        "1/2 cup chickpeas",
                        "1 oz beef jerky",
                        "1/2 tsp paprika"
                    ],
                    "dietary_tags": ["high_protein", "portable", "no_cook"]
                },
                {
                    "name": "White Bean and Beef Trail Mix",
                    "meal_type": "snack",
                    "description": "Custom trail mix with roasted white beans and dried beef",
                    "instructions": "Roast 1/2 cup cannellini beans with sea salt until crispy. Mix with 1/4 cup dried beef strips, 1/4 cup nuts (almonds, cashews), 1/4 cup dried fruit. Portion into snack bags.",
                    "prep_time": 5,
                    "cook_time": 20,
                    "calories": 320,
                    "protein": 16,
                    "fiber": 6,
                    "carbs": 28,
                    "fat": 18,
                    "ingredients": [
                        "1/2 cup cannellini beans",
                        "1/4 cup dried beef",
                        "1/4 cup nuts",
                        "1/4 cup dried fruit"
                    ],
                    "dietary_tags": ["high_protein", "portable", "meal_prep"]
                },
                {
                    "name": "Chickpea and Beef Protein Bites",
                    "meal_type": "snack",
                    "description": "No-bake protein energy balls with chickpea flour",
                    "instructions": "Process 1/2 cup roasted chickpeas into flour. Mix with 1 tbsp protein powder, 2 tbsp almond butter, 1 tbsp honey, 1 tbsp ground beef jerky bits. Form into 8 balls. Chill until firm.",
                    "prep_time": 10,
                    "cook_time": 0,
                    "calories": 200,
                    "protein": 14,
                    "fiber": 4,
                    "carbs": 16,
                    "fat": 12,
                    "ingredients": [
                        "1/2 cup chickpeas",
                        "1 tbsp protein powder",
                        "2 tbsp almond butter",
                        "1 tbsp honey",
                        "1 tbsp beef jerky"
                    ],
                    "dietary_tags": ["high_protein", "portable", "no_cook"]
                },
                {
                    "name": "Black Bean and Beef Wrap Bites",
                    "meal_type": "snack",
                    "description": "Mini wraps with black beans and tiny beef pieces",
                    "instructions": "Heat 1 oz tiny beef pieces with 1/4 tsp cumin. Cut small whole wheat tortilla quarters. Fill each with 1 tbsp black beans, seasoned beef, 1 tsp cheese, shred of lettuce. Secure with toothpick.",
                    "prep_time": 8,
                    "cook_time": 5,
                    "calories": 180,
                    "protein": 14,
                    "fiber": 4,
                    "carbs": 14,
                    "fat": 10,
                    "ingredients": [
                        "1 oz beef pieces",
                        "1/4 cup black beans",
                        "small tortillas",
                        "1 tsp cheese",
                        "lettuce"
                    ],
                    "dietary_tags": ["high_protein", "portable", "quick"]
                },
                {
                    "name": "Bean and Beef Hummus Dip",
                    "meal_type": "snack",
                    "description": "Creamy dip with white beans and beef jerky",
                    "instructions": "Blend 1/2 cup cannellini beans with 1 tbsp tahini, 1 tsp lemon juice, garlic, salt. Stir in 2 tbsp finely chopped beef jerky. Serve with vegetable sticks and crackers.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 180,
                    "protein": 12,
                    "fiber": 4,
                    "carbs": 16,
                    "fat": 10,
                    "ingredients": [
                        "1/2 cup cannellini beans",
                        "2 tbsp beef jerky",
                        "1 tbsp tahini",
                        "vegetable sticks",
                        "crackers"
                    ],
                    "dietary_tags": ["high_protein", "portable", "no_cook"]
                },
                {
                    "name": "Pinto Bean and Beef Crackers",
                    "meal_type": "snack",
                    "description": "Protein-rich topping for crackers with pinto beans and beef",
                    "instructions": "Mix 1/4 cup mashed pinto beans with 1 oz finely chopped beef, 1 tsp taco seasoning, 1 tsp yogurt. Spread on whole grain crackers. Top with shredded lettuce.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 160,
                    "protein": 12,
                    "fiber": 4,
                    "carbs": 14,
                    "fat": 8,
                    "ingredients": [
                        "1/4 cup pinto beans",
                        "1 oz beef",
                        "whole grain crackers",
                        "1 tsp taco seasoning",
                        "1 tsp yogurt"
                    ],
                    "dietary_tags": ["high_protein", "portable", "no_cook"]
                },
                {
                    "name": "Chickpea and Beef Energy Bar",
                    "meal_type": "snack",
                    "description": "Homemade protein bars with chickpeas and beef",
                    "instructions": "Blend 1/2 cup roasted chickpeas with 1 cup dates, 2 tbsp almond butter, 1 tbsp protein powder, 1 tbsp finely chopped beef jerky. Press into pan, chill 1 hour, cut into 6 bars.",
                    "prep_time": 12,
                    "cook_time": 0,
                    "calories": 220,
                    "protein": 14,
                    "fiber": 6,
                    "carbs": 26,
                    "fat": 10,
                    "ingredients": [
                        "1/2 cup chickpeas",
                        "1 cup dates",
                        "2 tbsp almond butter",
                        "1 tbsp protein powder",
                        "1 tbsp beef jerky"
                    ],
                    "dietary_tags": ["high_protein", "portable", "meal_prep"]
                },
                {
                    "name": "Kidney Bean and Beef Salsa",
                    "meal_type": "snack",
                    "description": "Chunky salsa with kidney beans and ground beef",
                    "instructions": "Brown 2 oz ground beef with taco seasoning. Cool. Mix with 1/4 cup kidney beans, 1/4 cup diced tomatoes, 1 tbsp cilantro, onion, lime juice. Serve with tortilla chips.",
                    "prep_time": 10,
                    "cook_time": 8,
                    "calories": 200,
                    "protein": 14,
                    "fiber": 4,
                    "carbs": 16,
                    "fat": 10,
                    "ingredients": [
                        "2 oz ground beef",
                        "1/4 cup kidney beans",
                        "1/4 cup tomatoes",
                        "tortilla chips",
                        "cilantro"
                    ],
                    "dietary_tags": ["high_protein", "portable", "quick"]
                },
                {
                    "name": "White Bean and Beef Toast",
                    "meal_type": "snack",
                    "description": "Protein toast with white bean spread and beef",
                    "instructions": "Mash 1/4 cup cannellini beans with garlic, 1 tsp olive oil. Toast 2 slices whole grain bread. Spread with bean mash, top with 1 oz finely chopped beef, tomato slice, parmesan.",
                    "prep_time": 5,
                    "cook_time": 3,
                    "calories": 220,
                    "protein": 16,
                    "fiber": 6,
                    "carbs": 24,
                    "fat": 8,
                    "ingredients": [
                        "1/4 cup cannellini beans",
                        "1 oz beef",
                        "2 slices bread",
                        "tomato",
                        "parmesan"
                    ],
                    "dietary_tags": ["high_protein", "quick", "vegetarian_option"]
                },
                {
                    "name": "Black Bean and Beef Stuffed Dates",
                    "meal_type": "snack",
                    "description": "Sweet and savory dates stuffed with black beans and beef",
                    "instructions": "Pit 6 dates. Mix 1/4 cup black beans with 1 oz finely chopped beef, 1 tsp cinnamon, 1 tsp honey. Stuff each date with mixture. Chill 30 min.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 180,
                    "protein": 10,
                    "fiber": 4,
                    "carbs": 24,
                    "fat": 6,
                    "ingredients": [
                        "6 dates",
                        "1/4 cup black beans",
                        "1 oz beef",
                        "1 tsp cinnamon",
                        "1 tsp honey"
                    ],
                    "dietary_tags": ["high_protein", "portable", "no_cook"]
                },
                {
                    "name": "Chickpea and Beef Deviled Eggs",
                    "meal_type": "snack",
                    "description": "Protein-packed deviled eggs with chickpea and beef filling",
                    "instructions": "Hard boil 3 eggs, halve. Mix yolks with 1 tbsp mashed chickpeas, 1 oz finely chopped beef, 1 tsp mustard, 1 tsp yogurt. Pipe or spoon into whites. Sprinkle with paprika.",
                    "prep_time": 15,
                    "cook_time": 10,
                    "calories": 180,
                    "protein": 14,
                    "fiber": 2,
                    "carbs": 6,
                    "fat": 12,
                    "ingredients": [
                        "3 eggs",
                        "1 tbsp chickpeas",
                        "1 oz beef",
                        "1 tsp mustard",
                        "1 tsp yogurt"
                    ],
                    "dietary_tags": ["high_protein", "portable", "quick"]
                },
                {
                    "name": "Bean and Beef Pinwheels",
                    "meal_type": "snack",
                    "description": "Spinach tortilla pinwheels with beans and beef",
                    "instructions": "Spread large spinach tortilla with 1/4 cup refried beans. Add 2 oz thin beef slices, cheese, lettuce. Roll tightly, slice into 8 pinwheels.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 240,
                    "protein": 18,
                    "fiber": 4,
                    "carbs": 18,
                    "fat": 14,
                    "ingredients": [
                        "spinach tortilla",
                        "1/4 cup refried beans",
                        "2 oz beef",
                        "cheese",
                        "lettuce"
                    ],
                    "dietary_tags": ["high_protein", "portable", "quick"]
                },
                {
                    "name": "Three Bean and Beef Skewers",
                    "meal_type": "snack",
                    "description": "Fun snack skewers alternating beans and beef",
                    "instructions": "On small skewers, alternate: black bean, piece of beef, kidney bean, piece of beef, chickpea. Serve with dipping sauce (mix yogurt, salsa, lime).",
                    "prep_time": 10,
                    "cook_time": 0,
                    "calories": 160,
                    "protein": 14,
                    "fiber": 4,
                    "carbs": 12,
                    "fat": 8,
                    "ingredients": [
                        "beans",
                        "beef pieces",
                        "yogurt",
                        "salsa",
                        "lime"
                    ],
                    "dietary_tags": ["high_protein", "portable", "fun_kitchen"]
                },
                {
                    "name": "White Bean and Beef Quesadilla Bites",
                    "meal_type": "snack",
                    "description": "Mini quesadillas with white beans and beef",
                    "instructions": "Cut small tortillas in half. Fill each half with 1 tbsp white beans, 1 oz seasoned beef, 1 tsp cheese. Fold, cook in skillet 2-3 min each side until crispy.",
                    "prep_time": 8,
                    "cook_time": 6,
                    "calories": 200,
                    "protein": 14,
                    "fiber": 4,
                    "carbs": 16,
                    "fat": 12,
                    "ingredients": [
                        "small tortillas",
                        "white beans",
                        "1 oz beef",
                        "1 tsp cheese"
                    ],
                    "dietary_tags": ["high_protein", "portable", "quick"]
                },
                {
                    "name": "Bean and Beef Pizza Bites",
                    "meal_type": "snack",
                    "description": "Mini pizza crusts topped with beans and beef",
                    "instructions": "Top 6 mini bagel halves with 1 tbsp pizza sauce, 1/4 cup black beans, 2 oz seasoned beef, 1 tsp cheese. Bake at 400°F for 8-10 min until melted.",
                    "prep_time": 5,
                    "cook_time": 10,
                    "calories": 240,
                    "protein": 16,
                    "fiber": 4,
                    "carbs": 28,
                    "fat": 10,
                    "ingredients": [
                        "6 mini bagels",
                        "1/4 cup black beans",
                        "2 oz beef",
                        "pizza sauce",
                        "cheese"
                    ],
                    "dietary_tags": ["high_protein", "portable", "quick"]
                }
            ]
        }
    
    def add_extra_bean_recipes(self):
        """Add all extra bean-based recipes to the appropriate meal files"""
        extra_recipes = self.get_extra_bean_recipes()
        
        for meal_type, new_recipes in extra_recipes.items():
            if meal_type in self.meal_files:
                existing_recipes = self.load_recipes(meal_type)
                existing_recipes.extend(new_recipes)
                self.save_recipes(meal_type, existing_recipes)
                print(f"✓ Added {len(new_recipes)} {meal_type} recipes")
        
        print("\n🌱 All 45 additional bean-based recipes have been added successfully!")
        print("\nRecipe breakdown:")
        print("• 15 lunch recipes with beans, vegetables, and beef")
        print("• 15 dinner recipes with beans, vegetables, and beef")
        print("• 15 snack recipes with beans, vegetables, and beef")

if __name__ == "__main__":
    adder = ExtraBeanRecipeAdder()
    adder.add_extra_bean_recipes()