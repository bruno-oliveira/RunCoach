#!/usr/bin/env python3
"""Add Mediterranean performance recipes with NL-sourced ingredients."""

import json
import os
from pathlib import Path

# Data directory path
DATA_DIR = Path(__file__).parent / "app" / "data"

def load_recipes(filename):
    """Load recipes from JSON file."""
    file_path = DATA_DIR / filename
    if not file_path.exists():
        print(f"Warning: {file_path} does not exist")
        return []
    
    with open(file_path, 'r') as f:
        return json.load(f)

def save_recipes(filename, recipes):
    """Save recipes to JSON file."""
    file_path = DATA_DIR / filename
    with open(file_path, 'w') as f:
        json.dump(recipes, f, indent=2)

def add_nl_sourced_mediterranean_recipes():
    """Add Mediterranean recipes using ingredients easily sourced in Netherlands."""
    
    # Breakfast recipes with NL ingredients
    breakfast_recipes = [
        {
            "name": "Dutch-Mediterranean Power Ontbijtkoek",
            "meal_type": "breakfast",
            "description": "Spiced breakfast cake with Greek yogurt and Dutch berries for morning energy",
            "instructions": "Toast a slice of ontbijtkoek (Dutch spiced cake). Top with Greek yogurt, mixed Dutch berries (aardbeien, bosbessen, frambozen), and a sprinkle of chopped walnuts. Drizzle with honey and add a side of boiled egg for complete protein. This provides complex carbs, antioxidants, and protein for morning runs.",
            "prep_time": 5,
            "cook_time": 2,
            "calories": 420,
            "protein": 22,
            "fiber": 8,
            "carbs": 58,
            "fat": 14,
            "ingredients": [
                "1 slice ontbijtkoek",
                "1 cup Greek yogurt",
                "1/2 cup mixed Dutch berries",
                "2 tbsp walnuts, chopped",
                "1 tbsp honey",
                "1 boiled egg",
                "cinnamon",
                "vanilla"
            ],
            "dietary_tags": [
                "complex_carbs",
                "antioxidant",
                "dutch_mediterranean",
                "quick",
                "high_protein"
            ]
        },
        {
            "name": "Mediterranean Hagelslag Power Bowl",
            "meal_type": "breakfast",
            "description": "Oatmeal with Dutch chocolate hagelslag and Mediterranean nuts",
            "instructions": "Cook rolled oats with milk until creamy. Stir in protein powder and cinnamon. Top with Dutch chocolate hagelslag, mixed nuts (almonds, hazelnuts), and dried apricots. Add a spoonful of peanut butter for healthy fats. This energy-rich breakfast fuels long training sessions.",
            "prep_time": 8,
            "cook_time": 10,
            "calories": 480,
            "protein": 24,
            "fiber": 10,
            "carbs": 62,
            "fat": 18,
            "ingredients": [
                "1/2 cup rolled oats",
                "1 cup milk",
                "1 scoop protein powder",
                "2 tbsp chocolate hagelslag",
                "2 tbsp mixed nuts",
                "2 dried apricots, chopped",
                "1 tbsp peanut butter",
                "cinnamon",
                "vanilla extract"
            ],
            "dietary_tags": [
                "high_protein",
                "energy_boosting",
                "dutch_mediterranean",
                "complex_carbs",
                "quick"
            ]
        },
        {
            "name": "Dutch Cheese Mediterranean Omelette",
            "meal_type": "breakfast",
            "description": "Three-egg omelette with aged Dutch cheese and Mediterranean vegetables",
            "instructions": "Beat 3 eggs with salt and pepper. Sauté sliced mushrooms, spinach, and cherry tomatoes in olive oil. Pour eggs over vegetables and cook until set. Top with grated aged Gouda or Edam cheese. Add fresh basil and serve with a slice of whole grain bread. This high-protein breakfast supports muscle maintenance.",
            "prep_time": 10,
            "cook_time": 8,
            "calories": 460,
            "protein": 32,
            "fiber": 6,
            "carbs": 22,
            "fat": 28,
            "ingredients": [
                "3 eggs",
                "1/4 cup mushrooms, sliced",
                "1 cup spinach",
                "1/4 cup cherry tomatoes",
                "2 tbsp aged Gouda cheese",
                "1 tbsp olive oil",
                "fresh basil",
                "whole grain bread",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "dutch_mediterranean",
                "vegetable_rich",
                "quick",
                "complete_protein"
            ]
        }
    ]
    
    # Lunch recipes with NL ingredients
    lunch_recipes = [
        {
            "name": "Dutch Herring Mediterranean Power Bowl",
            "meal_type": "lunch",
            "description": "Raw herring with quinoa and Mediterranean vegetables for omega-3 recovery",
            "instructions": "Cook quinoa and let cool. Arrange in a bowl with chopped Dutch herring, cherry tomatoes, cucumber, red onion, and Kalamata olives. Drizzle with lemon-olive oil dressing and top with fresh dill and capers. Serve with a side of whole grain crackers. This omega-3 rich meal supports recovery and brain health.",
            "prep_time": 15,
            "cook_time": 12,
            "calories": 480,
            "protein": 28,
            "fiber": 10,
            "carbs": 42,
            "fat": 22,
            "ingredients": [
                "2 Dutch herring fillets",
                "1 cup quinoa",
                "1 cup cherry tomatoes",
                "1/2 cucumber",
                "1/4 red onion",
                "2 tbsp Kalamata olives",
                "2 tbsp olive oil",
                "1 tbsp lemon juice",
                "fresh dill",
                "capers",
                "whole grain crackers"
            ],
            "dietary_tags": [
                "omega_3",
                "anti_inflammatory",
                "dutch_mediterranean",
                "high_protein",
                "gluten_free_option"
            ]
        },
        {
            "name": "Mediterranean Stamppot Runner's Style",
            "meal_type": "lunch",
            "description": "Dutch stamppot with Mediterranean herbs and lean protein",
            "instructions": "Boil potatoes and kale until tender. Mash with olive oil, garlic, and Mediterranean herbs (oregano, basil). Top with grilled chicken breast or lean beef. Add a side of roasted root vegetables (carrots, parsnips) and a dollop of Greek yogurt. This high-carb, high-protein meal supports endurance training.",
            "prep_time": 20,
            "cook_time": 25,
            "calories": 520,
            "protein": 36,
            "fiber": 12,
            "carbs": 58,
            "fat": 18,
            "ingredients": [
                "2 potatoes",
                "2 cups kale",
                "5 oz grilled chicken or beef",
                "2 tbsp olive oil",
                "2 cloves garlic",
                "Mediterranean herbs",
                "Greek yogurt",
                "root vegetables",
                "sea salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "complex_carbs",
                "dutch_mediterranean",
                "endurance",
                "gluten_free_option"
            ]
        },
        {
            "name": "Dutch Pea Soup Mediterranean Style",
            "meal_type": "lunch",
            "description": "Split pea soup with Mediterranean vegetables and herbs",
            "instructions": "Simmer split peas with vegetable broth, carrots, celery, and onions. Add Mediterranean herbs (thyme, rosemary) and a bay leaf. Cook until peas are tender. Stir in spinach and serve with a drizzle of olive oil and grated Parmesan cheese. Add a side of whole grain bread. This fiber-rich soup supports digestive health.",
            "prep_time": 15,
            "cook_time": 45,
            "calories": 440,
            "protein": 24,
            "fiber": 18,
            "carbs": 52,
            "fat": 12,
            "ingredients": [
                "1 cup split peas",
                "4 cups vegetable broth",
                "2 carrots",
                "2 celery stalks",
                "1 onion",
                "2 cups spinach",
                "Mediterranean herbs",
                "bay leaf",
                "Parmesan cheese",
                "olive oil",
                "whole grain bread"
            ],
            "dietary_tags": [
                "high_fiber",
                "plant_based",
                "dutch_mediterranean",
                "digestive_health",
                "gluten_free_option"
            ]
        },
        {
            "name": "Mediterranean Uitsmijter Power Plate",
            "meal_type": "lunch",
            "description": "Dutch uitsmijter with Mediterranean toppings and whole grain bread",
            "instructions": "Fry or poach 2 eggs. Serve on whole grain bread with sliced avocado, cherry tomatoes, and feta cheese. Drizzle with pesto and sprinkle with red pepper flakes. Add a side of mixed greens with lemon-olive oil dressing. This balanced meal provides protein, healthy fats, and complex carbs.",
            "prep_time": 10,
            "cook_time": 8,
            "calories": 500,
            "protein": 26,
            "fiber": 10,
            "carbs": 42,
            "fat": 24,
            "ingredients": [
                "2 eggs",
                "2 slices whole grain bread",
                "1/2 avocado",
                "1/2 cup cherry tomatoes",
                "2 tbsp feta cheese",
                "1 tbsp pesto",
                "mixed greens",
                "lemon",
                "olive oil",
                "red pepper flakes"
            ],
            "dietary_tags": [
                "balanced",
                "dutch_mediterranean",
                "healthy_fats",
                "complete_protein",
                "quick"
            ]
        },
        {
            "name": "Rotterdam Mediterranean Kapsalon",
            "meal_type": "lunch",
            "description": "Healthier kapsalon with grilled chicken and Mediterranean vegetables",
            "instructions": "Layer fries (or sweet potato fries) with grilled chicken, Mediterranean vegetables (zucchini, bell peppers, onions), and feta cheese. Add garlic sauce and yogurt sauce. Top with fresh herbs and a squeeze of lemon. This protein-rich meal supports muscle recovery.",
            "prep_time": 15,
            "cook_time": 20,
            "calories": 580,
            "protein": 38,
            "fiber": 10,
            "carbs": 58,
            "fat": 24,
            "ingredients": [
                "5 oz grilled chicken",
                "1 sweet potato, cut into fries",
                "Mediterranean vegetables",
                "2 tbsp feta cheese",
                "garlic sauce",
                "yogurt sauce",
                "fresh herbs",
                "lemon",
                "olive oil"
            ],
            "dietary_tags": [
                "high_protein",
                "dutch_mediterranean",
                "recovery",
                "balanced",
                "gluten_free_option"
            ]
        }
    ]
    
    # Dinner recipes with NL ingredients
    dinner_recipes = [
        {
            "name": "Dutch Seafood Paella with Local Fish",
            "meal_type": "dinner",
            "description": "Paella using Dutch seafood with Mediterranean spices",
            "instructions": "Heat olive oil in a paella pan. Sauté onions, bell peppers, and garlic. Add short-grain rice and saffron. Add fish stock and bring to simmer. Add local Dutch fish (cod, haddock), mussels, and shrimp. Cook for 15 minutes until rice is tender. Garnish with lemon wedges and fresh parsley.",
            "prep_time": 20,
            "cook_time": 25,
            "calories": 540,
            "protein": 38,
            "fiber": 6,
            "carbs": 58,
            "fat": 18,
            "ingredients": [
                "6 oz mixed Dutch fish",
                "1 cup short-grain rice",
                "1/2 cup mussels",
                "1/4 cup shrimp",
                "3 cups fish stock",
                "1/4 tsp saffron",
                "bell peppers",
                "onion",
                "garlic",
                "olive oil",
                "fresh parsley",
                "lemon"
            ],
            "dietary_tags": [
                "high_protein",
                "omega_3",
                "dutch_mediterranean",
                "seafood",
                "complete_meal"
            ]
        },
        {
            "name": "Mediterranean Boerenkool met Worst",
            "meal_type": "dinner",
            "description": "Dutch kale with Mediterranean herbs and lean sausage",
            "instructions": "Boil kale and potatoes until tender. Mash with olive oil, garlic, and Mediterranean herbs (rosemary, thyme). Serve with lean Dutch sausage (rookworst) and a side of roasted root vegetables. Add a dollop of Greek yogurt. This iron-rich meal supports oxygen transport.",
            "prep_time": 15,
            "cook_time": 30,
            "calories": 480,
            "protein": 28,
            "fiber": 12,
            "carbs": 48,
            "fat": 18,
            "ingredients": [
                "2 cups kale",
                "2 potatoes",
                "4 oz lean rookworst",
                "2 tbsp olive oil",
                "3 cloves garlic",
                "Mediterranean herbs",
                "Greek yogurt",
                "root vegetables",
                "sea salt",
                "pepper"
            ],
            "dietary_tags": [
                "iron_rich",
                "high_fiber",
                "dutch_mediterranean",
                "traditional",
                "gluten_free_option"
            ]
        },
        {
            "name": "Mediterranean Zuurkoolschotel",
            "meal_type": "dinner",
            "description": "Sauerkraut casserole with Mediterranean flavors and lean protein",
            "instructions": "Layer sauerkraut with cooked potatoes, lean pork, and apples. Add Mediterranean herbs (caraway seeds, thyme) and a splash of white wine. Bake for 30 minutes until bubbly. Top with Greek yogurt and fresh herbs. This probiotic-rich meal supports gut health.",
            "prep_time": 20,
            "cook_time": 35,
            "calories": 460,
            "protein": 26,
            "fiber": 14,
            "carbs": 48,
            "fat": 16,
            "ingredients": [
                "2 cups sauerkraut",
                "2 potatoes, cooked",
                "4 oz lean pork",
                "1 apple, sliced",
                "caraway seeds",
                "thyme",
                "white wine",
                "Greek yogurt",
                "fresh herbs",
                "sea salt"
            ],
            "dietary_tags": [
                "probiotic",
                "high_fiber",
                "dutch_mediterranean",
                "gut_health",
                "gluten_free_option"
            ]
        },
        {
            "name": "Dutch Lamb Chops Mediterranean Style",
            "meal_type": "dinner",
            "description": "New Zealand lamb chops with Mediterranean herbs and Dutch vegetables",
            "instructions": "Season lamb chops with garlic, rosemary, and sea salt. Grill or pan-sear for 4-5 minutes per side. Serve with roasted Dutch vegetables (carrots, parsnips, onions) and a side of couscous with herbs and lemon. Add a dollop of tzatziki. This iron-rich meal supports performance.",
            "prep_time": 15,
            "cook_time": 15,
            "calories": 520,
            "protein": 38,
            "fiber": 8,
            "carbs": 38,
            "fat": 24,
            "ingredients": [
                "6 oz lamb chops",
                "Dutch root vegetables",
                "1 cup couscous",
                "garlic",
                "rosemary",
                "tzatziki",
                "lemon",
                "olive oil",
                "sea salt",
                "pepper"
            ],
            "dietary_tags": [
                "iron_rich",
                "high_protein",
                "dutch_mediterranean",
                "grilled",
                "gluten_free_option"
            ]
        },
        {
            "name": "Mediterranean Indische Rijsttafel Bowl",
            "meal_type": "dinner",
            "description": "Dutch-Indonesian rice table with Mediterranean healthy twists",
            "instructions": "Prepare brown rice with Mediterranean herbs. Top with grilled chicken satay, steamed vegetables, and a side of peanut sauce made with olive oil. Add fresh cucumber salad with lemon-olive oil dressing. Serve with prawn crackers. This balanced meal provides complete protein.",
            "prep_time": 20,
            "cook_time": 25,
            "calories": 540,
            "protein": 32,
            "fiber": 12,
            "carbs": 62,
            "fat": 20,
            "ingredients": [
                "5 oz chicken",
                "1 cup brown rice",
                "mixed vegetables",
                "peanut sauce",
                "cucumber salad",
                "prawn crackers",
                "Mediterranean herbs",
                "lemon",
                "olive oil",
                "soy sauce"
            ],
            "dietary_tags": [
                "complete_protein",
                "dutch_mediterranean",
                "fusion",
                "balanced",
                "high_fiber"
            ]
        },
        {
            "name": "Mediterranean Bitterballen with Healthy Twist",
            "meal_type": "dinner",
            "description": "Baked bitterballen with Mediterranean herbs and lean beef",
            "instructions": "Make bitterballen with lean beef ragout, Mediterranean herbs, and less butter. Instead of frying, bake until golden. Serve with a side of Mediterranean salad and a yogurt-dill dip. This lighter version provides protein without excess fat.",
            "prep_time": 25,
            "cook_time": 20,
            "calories": 420,
            "protein": 28,
            "fiber": 6,
            "carbs": 38,
            "fat": 18,
            "ingredients": [
                "4 oz lean beef",
                "Mediterranean herbs",
                "flour",
                "egg",
                "bread crumbs",
                "Mediterranean salad",
                "yogurt-dill dip",
                "olive oil",
                "sea salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "dutch_mediterranean",
                "light_version",
                "baked",
                "balanced"
            ]
        }
    ]
    
    # Post-workout recipes with NL ingredients
    post_workout_recipes = [
        {
            "name": "Dutch Whey Protein Vla",
            "meal_type": "post_workout",
            "description": "Protein-enriched vla with Dutch berries for quick recovery",
            "instructions": "Mix Dutch vla (custard) with whey protein powder and vanilla. Top with mixed Dutch berries and a sprinkle of chopped almonds. Serve chilled. This protein-rich dessert supports muscle recovery with familiar Dutch flavors.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 320,
            "protein": 24,
            "fiber": 6,
            "carbs": 32,
            "fat": 12,
            "ingredients": [
                "1 cup Dutch vla",
                "1 scoop whey protein",
                "1/2 cup mixed berries",
                "1 tbsp almonds",
                "vanilla extract",
                "cinnamon"
            ],
            "dietary_tags": [
                "recovery",
                "high_protein",
                "dutch_mediterranean",
                "quick",
                "familiar"
            ]
        },
        {
            "name": "Mediterranean Dropjes Energy Bites",
            "meal_type": "post_workout",
            "description": "Energy bites using Dutch dropjes with Mediterranean nuts and protein",
            "instructions": "Process dates, almonds, protein powder, and a few Dutch dropjes (licorice candies) in a food processor. Roll into balls and coat with crushed pistachios. Chill for 30 minutes. These energy bites provide quick recovery carbohydrates and protein.",
            "prep_time": 10,
            "cook_time": 0,
            "calories": 280,
            "protein": 12,
            "fiber": 6,
            "carbs": 38,
            "fat": 12,
            "ingredients": [
                "1 cup dates",
                "1/2 cup almonds",
                "1/2 scoop protein powder",
                "3 Dutch dropjes",
                "crushed pistachios",
                "coconut oil",
                "vanilla extract"
            ],
            "dietary_tags": [
                "recovery",
                "energy_bites",
                "dutch_mediterranean",
                "portable",
                "quick"
            ]
        },
        {
            "name": "Dutch Buttermilk Mediterranean Smoothie",
            "meal_type": "post_workout",
            "description": "Buttermilk smoothie with Mediterranean fruits and protein powder",
            "instructions": "Blend Dutch buttermilk with mixed berries, banana, protein powder, and honey. Add a spoonful of tahini for healthy fats. Serve immediately. This hydrating smoothie provides electrolytes and protein for recovery.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 380,
            "protein": 26,
            "fiber": 8,
            "carbs": 48,
            "fat": 14,
            "ingredients": [
                "1.5 cups Dutch buttermilk",
                "1 cup mixed berries",
                "1/2 banana",
                "1 scoop protein powder",
                "1 tbsp tahini",
                "1 tbsp honey",
                "ice"
            ],
            "dietary_tags": [
                "recovery",
                "hydrating",
                "dutch_mediterranean",
                "electrolyte",
                "quick"
            ]
        },
        {
            "name": "Mediterranean Poffertjes with Protein",
            "meal_type": "post_workout",
            "description": "Protein-enriched poffertjes with Greek yogurt and berries",
            "instructions": "Make poffertjes batter with added protein powder. Cook mini pancakes in a special poffertjes pan. Serve with Greek yogurt, mixed berries, and a drizzle of honey. These protein-rich pancakes support muscle recovery.",
            "prep_time": 10,
            "cook_time": 10,
            "calories": 420,
            "protein": 22,
            "fiber": 6,
            "carbs": 58,
            "fat": 14,
            "ingredients": [
                "poffertjes mix",
                "1/2 scoop protein powder",
                "Greek yogurt",
                "mixed berries",
                "honey",
                "butter",
                "powdered sugar"
            ],
            "dietary_tags": [
                "recovery",
                "high_protein",
                "dutch_mediterranean",
                "comfort",
                "quick"
            ]
        }
    ]
    
    # Load existing recipes
    breakfast_existing = load_recipes("meals_breakfast.json")
    lunch_existing = load_recipes("meals_lunch.json")
    dinner_existing = load_recipes("meals_dinner.json")
    post_workout_existing = load_recipes("meals_post_workout.json")
    
    # Add all new recipes
    breakfast_existing.extend(breakfast_recipes)
    lunch_existing.extend(lunch_recipes)
    dinner_existing.extend(dinner_recipes)
    post_workout_existing.extend(post_workout_recipes)
    
    # Save updated recipes
    save_recipes("meals_breakfast.json", breakfast_existing)
    save_recipes("meals_lunch.json", lunch_existing)
    save_recipes("meals_dinner.json", dinner_existing)
    save_recipes("meals_post_workout.json", post_workout_existing)
    
    # Count recipes
    total_added = (len(breakfast_recipes) + len(lunch_recipes) + 
                   len(dinner_recipes) + len(post_workout_recipes))
    
    print(f"Added {total_added} NL-sourced Mediterranean performance recipes")
    print(f"Breakfast: {len(breakfast_recipes)} recipes")
    print(f"Lunch: {len(lunch_recipes)} recipes")
    print(f"Dinner: {len(dinner_recipes)} recipes")
    print(f"Post-workout: {len(post_workout_recipes)} recipes")

def main():
    """Main function to add NL-sourced Mediterranean recipes."""
    print("Adding Mediterranean performance recipes with NL-sourced ingredients...")
    
    add_nl_sourced_mediterranean_recipes()
    
    print("\nNL-sourced Mediterranean recipe addition complete!")
    print("\n🥐 Dutch-Mediterranean Breakfast Recipes:")
    print("- Dutch-Mediterranean Power Ontbijtkoek")
    print("- Mediterranean Hagelslag Power Bowl")
    print("- Dutch Cheese Mediterranean Omelette")
    print("\n🥗 Dutch-Mediterranean Lunch Recipes:")
    print("- Dutch Herring Mediterranean Power Bowl")
    print("- Mediterranean Stamppot Runner's Style")
    print("- Dutch Pea Soup Mediterranean Style")
    print("- Mediterranean Uitsmijter Power Plate")
    print("- Rotterdam Mediterranean Kapsalon")
    print("\n🍽️ Dutch-Mediterranean Dinner Recipes:")
    print("- Dutch Seafood Paella with Local Fish")
    print("- Mediterranean Boerenkool met Worst")
    print("- Mediterranean Zuurkoolschotel")
    print("- Dutch Lamb Chops Mediterranean Style")
    print("- Mediterranean Indische Rijsttafel Bowl")
    print("- Mediterranean Bitterballen with Healthy Twist")
    print("\n🏃 Dutch-Mediterranean Post-Workout Recipes:")
    print("- Dutch Whey Protein Vla")
    print("- Mediterranean Dropjes Energy Bites")
    print("- Dutch Buttermilk Mediterranean Smoothie")
    print("- Mediterranean Poffertjes with Protein")
    print("\n🛒 Key NL-Sourced Ingredients:")
    print("- Ontbijtkoek (Dutch spiced breakfast cake)")
    print("- Hagelslag (chocolate sprinkles)")
    print("- Dutch cheeses (Gouda, Edam, Maasdam)")
    print("- Dutch herring and seafood")
    print("- Stamppot vegetables (potatoes, kale, endive)")
    print("- Dutch berries (aardbeien, bosbessen, frambozen)")
    print("- Vla (Dutch custard)")
    print("- Dropjes (licorice candies)")
    print("- Poffertjes (mini pancakes)")
    print("- Buttermilk and dairy products")
    print("\n🎯 Performance Benefits:")
    print("- Local accessibility for Dutch athletes")
    print("- Familiar flavors with Mediterranean nutrition")
    print("- Complete protein combinations")
    print("- Complex carbohydrates from Dutch staples")
    print("- Omega-3 from local North Sea fish")
    print("- Probiotics from Dutch dairy products")
    print("- Antioxidants from local berries")
    print("- Iron-rich traditional combinations")

if __name__ == "__main__":
    main()