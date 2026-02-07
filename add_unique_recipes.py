#!/usr/bin/env python3
"""Add unique and diverse recipes to the meal database."""

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

def add_unique_recipes():
    """Add unique recipes to different meal types."""
    
    # Unique breakfast recipes
    breakfast_recipes = [
        {
            "name": "Shakshuka with Feta",
            "meal_type": "breakfast",
            "description": "Middle Eastern poached eggs in spicy tomato sauce with feta",
            "instructions": "Heat olive oil in a large skillet over medium heat. Add diced onion and bell pepper, cooking until softened (5-7 minutes). Add garlic and cook for 30 seconds until fragrant. Add cumin, paprika, and red pepper flakes, stirring for 1 minute. Pour in crushed tomatoes and simmer for 10 minutes. Create wells in the sauce and crack eggs into each well. Sprinkle feta cheese over the top. Cover and cook for 5-7 minutes until egg whites are set but yolks are still runny. Garnish with fresh parsley or cilantro and serve with crusty bread for dipping.",
            "prep_time": 10,
            "cook_time": 20,
            "calories": 380,
            "protein": 22,
            "fiber": 8,
            "carbs": 28,
            "fat": 20,
            "ingredients": [
                "3 eggs",
                "1 cup crushed tomatoes",
                "1/2 onion, diced",
                "1/2 bell pepper, diced",
                "2 cloves garlic, minced",
                "2 oz feta cheese, crumbled",
                "2 tbsp olive oil",
                "1 tsp cumin",
                "1 tsp paprika",
                "1/4 tsp red pepper flakes",
                "fresh parsley",
                "crusty bread"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "mediterranean",
                "gluten_free_option"
            ]
        },
        {
            "name": "Japanese Savory Omelette (Tamagoyaki)",
            "meal_type": "breakfast",
            "description": "Rolled Japanese omelette with dashi and soy sauce",
            "instructions": "Beat eggs with dashi, soy sauce, mirin, and sugar until well combined. Heat a rectangular tamagoyaki pan or small non-stick skillet over medium heat and lightly oil. Pour in 1/3 of egg mixture, tilting to cover the bottom. When eggs are mostly set but still slightly wet on top, roll from one end to the other using chopsticks or spatula. Push rolled omelette to one end, oil the empty part of pan, and pour in another 1/3 of egg mixture. Lift the rolled omelette to let egg flow underneath. When set, roll again. Repeat with remaining egg mixture. Remove from pan and let cool for 1 minute. Slice into 1-inch pieces and serve warm.",
            "prep_time": 8,
            "cook_time": 10,
            "calories": 280,
            "protein": 18,
            "fiber": 1,
            "carbs": 12,
            "fat": 18,
            "ingredients": [
                "3 large eggs",
                "2 tbsp dashi stock",
                "1 tsp soy sauce",
                "1 tsp mirin",
                "1/2 tsp sugar",
                "1 tsp vegetable oil",
                "optional: nori strips for garnish"
            ],
            "dietary_tags": [
                "high_protein",
                "low_carb",
                "japanese",
                "quick"
            ]
        }
    ]
    
    # Unique lunch recipes
    lunch_recipes = [
        {
            "name": "Vietnamese Banh Mi Bowl",
            "meal_type": "lunch",
            "description": "Deconstructed banh mi with grilled pork, pickled vegetables, and herbs",
            "instructions": "Marinate pork in soy sauce, fish sauce, garlic, and sugar for 15 minutes. Grill or pan-sear pork until cooked through, let rest and slice. Quick pickle carrots and daikon in rice vinegar and sugar for 10 minutes. In a bowl, layer jasmine rice, sliced pork, pickled vegetables, fresh herbs, cucumber, and jalapeño. Drizzle with sriracha mayo and serve with lime wedges.",
            "prep_time": 20,
            "cook_time": 12,
            "calories": 520,
            "protein": 32,
            "fiber": 6,
            "carbs": 58,
            "fat": 22,
            "ingredients": [
                "5 oz pork tenderloin",
                "1 cup jasmine rice",
                "1/4 cup carrots, julienned",
                "1/4 cup daikon, julienned",
                "1/4 cup cucumber, sliced",
                "fresh cilantro and mint",
                "2 tbsp soy sauce",
                "1 tbsp fish sauce",
                "1 tbsp rice vinegar",
                "1 tsp sugar",
                "2 cloves garlic, minced",
                "sriracha mayo",
                "lime wedges"
            ],
            "dietary_tags": [
                "high_protein",
                "vietnamese",
                "quick"
            ]
        },
        {
            "name": "Ethiopian Beef Tibs with Injera",
            "meal_type": "lunch",
            "description": "Spiced Ethiopian beef strips served with sourdough injera bread",
            "instructions": "Cut beef into thin strips against the grain. Heat niter kibbeh or clarified butter in a large skillet over high heat. Add beef and quickly stir-fry for 2-3 minutes until browned but still tender. Add berbere spice, minced garlic, and ginger, tossing for 30 seconds. Add diced onions and tomatoes, cooking for 2 minutes until onions are slightly softened. Season with salt and lemon juice. Serve immediately on injera bread with extra injera for scooping.",
            "prep_time": 15,
            "cook_time": 10,
            "calories": 540,
            "protein": 36,
            "fiber": 8,
            "carbs": 52,
            "fat": 20,
            "ingredients": [
                "6 oz beef sirloin, thinly sliced",
                "1 large injera bread",
                "1 tbsp berbere spice",
                "1/2 red onion, diced",
                "1 tomato, diced",
                "2 cloves garlic, minced",
                "1 inch ginger, grated",
                "2 tbsp niter kibbeh or ghee",
                "1 tbsp lemon juice",
                "salt"
            ],
            "dietary_tags": [
                "high_protein",
                "ethiopian",
                "spicy",
                "gluten_free"
            ]
        },
        {
            "name": "Moroccan Chicken Tagine",
            "meal_type": "lunch",
            "description": "Slow-cooked chicken with preserved lemons, olives, and aromatic spices",
            "instructions": "Season chicken thighs with salt, pepper, turmeric, ginger, and cinnamon. Heat olive oil in a heavy pot or Dutch oven over medium-high heat. Brown chicken on both sides, then remove. Add onions and cook until softened. Add garlic, preserved lemon, and olives. Return chicken to pot, add chicken broth and honey. Bring to a simmer, reduce heat to low, cover and cook for 30-40 minutes until chicken is tender. Garnish with fresh cilantro and serve over couscous or with crusty bread.",
            "prep_time": 15,
            "cook_time": 40,
            "calories": 480,
            "protein": 34,
            "fiber": 6,
            "carbs": 28,
            "fat": 24,
            "ingredients": [
                "6 oz chicken thighs, boneless",
                "1/2 cup couscous",
                "1/4 cup preserved lemon, chopped",
                "1/4 cup green olives",
                "1 onion, sliced",
                "3 cloves garlic, minced",
                "1 tsp turmeric",
                "1 tsp ginger",
                "1/2 tsp cinnamon",
                "1 tbsp honey",
                "1/2 cup chicken broth",
                "2 tbsp olive oil",
                "fresh cilantro"
            ],
            "dietary_tags": [
                "high_protein",
                "moroccan",
                "mediterranean",
                "gluten_free_option"
            ]
        }
    ]
    
    # Unique dinner recipes
    dinner_recipes = [
        {
            "name": "Peruvian Lomo Saltado",
            "meal_type": "dinner",
            "description": "Peruvian stir-fry with beef, onions, tomatoes, and french fries",
            "instructions": "Cut beef into strips and marinate in soy sauce, vinegar, and garlic for 15 minutes. Heat oil in a large wok or skillet over high heat. Stir-fry beef for 2-3 minutes until browned, then remove. Add onions and cook for 2 minutes until slightly softened. Add tomatoes and aji amarillo, cooking for 1 minute. Return beef to pan with vinegar and soy sauce. Add french fries and toss everything together. Garnish with cilantro and serve immediately with white rice.",
            "prep_time": 20,
            "cook_time": 15,
            "calories": 620,
            "protein": 36,
            "fiber": 6,
            "carbs": 68,
            "fat": 26,
            "ingredients": [
                "7 oz beef sirloin, strips",
                "1 cup french fries",
                "1/2 cup white rice",
                "1 red onion, sliced",
                "2 tomatoes, quartered",
                "1 tbsp aji amarillo paste",
                "3 tbsp soy sauce",
                "2 tbsp red wine vinegar",
                "3 cloves garlic, minced",
                "2 tbsp vegetable oil",
                "fresh cilantro"
            ],
            "dietary_tags": [
                "high_protein",
                "peruvian",
                "spicy"
            ]
        },
        {
            "name": "Korean Jjajangmyeon",
            "meal_type": "dinner",
            "description": "Korean-Chinese noodles with savory black bean sauce and pork",
            "instructions": "Cook noodles according to package directions, drain and set aside. Heat oil in a wok or large skillet over medium-high heat. Add pork belly and cook until crispy. Add onion, potatoes, and zucchini, stir-frying for 3-4 minutes. Add chunjang (black bean paste) and stir-fry for 1 minute. Add water or broth and bring to a boil. Reduce heat and simmer for 10 minutes until vegetables are tender. Mix cornstarch with water and add to thicken sauce. Add noodles and toss to coat. Serve with cucumber slices.",
            "prep_time": 15,
            "cook_time": 20,
            "calories": 580,
            "protein": 24,
            "fiber": 8,
            "carbs": 82,
            "fat": 20,
            "ingredients": [
                "5 oz udon noodles",
                "3 oz pork belly, diced",
                "3 tbsp chunjang (black bean paste)",
                "1/2 onion, diced",
                "1/4 cup potato, diced",
                "1/4 cup zucchini, diced",
                "1 cup water or broth",
                "1 tbsp cornstarch",
                "2 tbsp vegetable oil",
                "cucumber slices"
            ],
            "dietary_tags": [
                "high_carb",
                "korean",
                "comfort"
            ]
        },
        {
            "name": "Brazilian Moqueca with Fish",
            "meal_type": "dinner",
            "description": "Brazilian fish stew with coconut milk, tomatoes, and dendê oil",
            "instructions": "Season fish fillets with lime juice, salt, and pepper. In a large clay pot or heavy saucepan, heat olive oil and dendê oil over medium heat. Add onions and bell peppers, cooking until softened. Add garlic and cook for 30 seconds. Add tomatoes and cook until they start to break down. Pour in coconut milk and bring to a gentle simmer. Add fish fillets and simmer for 5-7 minutes until fish is cooked through. Add cilantro and adjust seasoning. Serve hot with rice and pirão (fish manioc porridge) if available.",
            "prep_time": 20,
            "cook_time": 25,
            "calories": 480,
            "protein": 34,
            "fiber": 8,
            "carbs": 28,
            "fat": 24,
            "ingredients": [
                "6 oz white fish fillets (cod, halibut)",
                "1 cup coconut milk",
                "1 tomato, diced",
                "1/2 bell pepper, diced",
                "1/2 onion, diced",
                "3 cloves garlic, minced",
                "2 tbsp olive oil",
                "1 tbsp dendê oil (palm oil)",
                "1 lime, juiced",
                "fresh cilantro",
                "cooked white rice",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "brazilian",
                "seafood",
                "gluten_free"
            ]
        },
        {
            "name": "Afghan Mantu",
            "meal_type": "dinner",
            "description": "Steamed dumplings filled with seasoned beef and onion, topped with yogurt sauce",
            "instructions": "For filling: brown ground beef with chopped onion until cooked. Season with salt, pepper, and coriander. Let cool. For dough: mix flour, water, and salt to form smooth dough. Roll into thin sheets and cut into 3-inch squares. Place 1 tsp filling in center of each square, fold into triangles and pinch edges to seal. Place mantu in a steamer basket over boiling water. Steam for 15-20 minutes until dough is cooked. For sauce: mix yogurt with garlic and dried mint. To serve: arrange mantu on a plate, drizzle with yogurt sauce, and top with split pea sauce and ground beef if desired.",
            "prep_time": 45,
            "cook_time": 20,
            "calories": 520,
            "protein": 28,
            "fiber": 6,
            "carbs": 58,
            "fat": 20,
            "ingredients": [
                "4 oz ground beef",
                "1 cup all-purpose flour",
                "1/2 cup plain yogurt",
                "1 onion, finely chopped",
                "2 cloves garlic, minced",
                "1 tsp dried mint",
                "1 tsp coriander",
                "1/4 cup split peas (optional for topping)",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "afghan",
                "dumplings",
                "comfort"
            ]
        },
        {
            "name": "Georgian Khachapuri",
            "meal_type": "dinner",
            "description": "Georgian cheese-filled bread with egg and butter topping",
            "instructions": "For dough: mix flour, yeast, sugar, salt, warm water, and olive oil. Knead for 8-10 minutes until smooth. Let rise for 1 hour. For filling: mix grated cheeses with egg and salt. Divide dough into 4 pieces. Roll each into oval, spread cheese filling in center, leaving border. Fold edges toward center to form boat shape. Let rise 20 minutes. Bake at 400°F for 15-20 minutes until golden. Crack an egg into center of each, return to oven for 3-5 minutes until egg white is set. Top with butter and serve immediately.",
            "prep_time": 90,
            "cook_time": 25,
            "calories": 680,
            "protein": 24,
            "fiber": 4,
            "carbs": 68,
            "fat": 36,
            "ingredients": [
                "2 cups all-purpose flour",
                "1 cup mozzarella, grated",
                "1 cup feta, crumbled",
                "1/4 cup farmer's cheese",
                "2 eggs",
                "2 tbsp butter",
                "1 tsp yeast",
                "1 tsp sugar",
                "1/2 tsp salt",
                "1/2 cup warm water",
                "1 tbsp olive oil"
            ],
            "dietary_tags": [
                "high_carb",
                "georgian",
                "cheese",
                "comfort"
            ]
        }
    ]
    
    # Unique post-workout recipes
    post_workout_recipes = [
        {
            "name": "Japanese Recovery Bowl with Tororo",
            "meal_type": "post_workout",
            "description": "Grated yam over rice with salmon and egg for rapid recovery",
            "instructions": "Cook Japanese rice according to package directions. While rice cooks, season salmon with salt and grill or pan-sear for 4-5 minutes per side. Grate nagaimo (Japanese yam) into a smooth paste. In a bowl, layer rice, flaked salmon, and grated yam. Top with a raw or soft-boiled egg, nori strips, and sprinkle with bonito flakes. Drizzle with soy sauce and serve immediately.",
            "prep_time": 10,
            "cook_time": 15,
            "calories": 520,
            "protein": 38,
            "fiber": 4,
            "carbs": 58,
            "fat": 18,
            "ingredients": [
                "6 oz salmon fillet",
                "1 cup Japanese rice",
                "4 oz nagaimo (Japanese yam)",
                "1 egg",
                "2 tbsp soy sauce",
                "nori strips",
                "bonito flakes",
                "salt"
            ],
            "dietary_tags": [
                "high_protein",
                "high_carb",
                "japanese",
                "recovery",
                "quick"
            ]
        },
        {
            "name": "Korean Samgyetang (Ginseng Chicken Soup)",
            "meal_type": "post_workout",
            "description": "Young chicken stuffed with rice, ginseng, and dates for recovery",
            "instructions": "Clean chicken cavity and stuff with sweet rice, ginseng, garlic, and jujubes. Place chicken in a pot with water to cover. Bring to a boil, then reduce heat to low and simmer for 1-1.5 hours until chicken is very tender and meat falls off the bone. Season with salt and pepper. Serve hot in the broth, which is considered medicinal. Eat the stuffing ingredients along with the chicken.",
            "prep_time": 20,
            "cook_time": 90,
            "calories": 580,
            "protein": 42,
            "fiber": 6,
            "carbs": 48,
            "fat": 22,
            "ingredients": [
                "1 small young chicken (Cornish hen)",
                "1/4 cup sweet rice",
                "1 fresh ginseng root",
                "6 cloves garlic",
                "6 dried jujubes (red dates)",
                "6 cups water",
                "salt",
                "black pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "korean",
                "recovery",
                "medicinal",
                "gluten_free"
            ]
        }
    ]
    
    # Load existing recipes
    breakfast_existing = load_recipes("meals_breakfast.json")
    lunch_existing = load_recipes("meals_lunch.json")
    dinner_existing = load_recipes("meals_dinner.json")
    post_workout_existing = load_recipes("meals_post_workout.json")
    
    # Add new recipes
    breakfast_existing.extend(breakfast_recipes)
    lunch_existing.extend(lunch_recipes)
    dinner_existing.extend(dinner_recipes)
    post_workout_existing.extend(post_workout_recipes)
    
    # Save updated recipes
    save_recipes("meals_breakfast.json", breakfast_existing)
    save_recipes("meals_lunch.json", lunch_existing)
    save_recipes("meals_dinner.json", dinner_existing)
    save_recipes("meals_post_workout.json", post_workout_existing)
    
    print(f"Added {len(breakfast_recipes)} unique breakfast recipes")
    print(f"Added {len(lunch_recipes)} unique lunch recipes")
    print(f"Added {len(dinner_recipes)} unique dinner recipes")
    print(f"Added {len(post_workout_recipes)} unique post-workout recipes")

def main():
    """Main function to add all unique recipes."""
    print("Adding unique and diverse recipes...")
    
    add_unique_recipes()
    
    print("\nUnique recipe addition complete!")
    print("\nSummary of additions:")
    print("- 2 unique breakfast recipes")
    print("- 3 unique lunch recipes")
    print("- 5 unique dinner recipes")
    print("- 2 unique post-workout recipes")
    print("- Total: 12 unique recipes added")
    print("\nFeatured cuisines:")
    print("- Middle Eastern (Shakshuka)")
    print("- Japanese (Tamagoyaki, Recovery Bowl)")
    print("- Vietnamese (Banh Mi Bowl)")
    print("- Ethiopian (Beef Tibs)")
    print("- Moroccan (Chicken Tagine)")
    print("- Peruvian (Lomo Saltado)")
    print("- Korean (Jjajangmyeon, Samgyetang)")
    print("- Brazilian (Moqueca)")
    print("- Afghan (Mantu)")
    print("- Georgian (Khachapuri)")

if __name__ == "__main__":
    main()