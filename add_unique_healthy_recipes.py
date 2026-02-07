#!/usr/bin/env python3
"""Add more unique and healthy recipes to the meal database."""

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

def add_unique_healthy_recipes():
    """Add unique and healthy recipes to different meal types."""
    
    # Healthy breakfast recipes
    breakfast_recipes = [
        {
            "name": "Tibetan Tsampa Porridge",
            "meal_type": "breakfast",
            "description": "Traditional roasted barley porridge with butter and honey",
            "instructions": "In a small saucepan, bring water or milk to a simmer. Slowly whisk in tsampa (roasted barley flour) to prevent lumps. Cook for 2-3 minutes, stirring constantly until thickened. Remove from heat and stir in butter and honey until melted and well combined. Top with fresh berries and a sprinkle of cinnamon. This high-energy breakfast is perfect for morning training sessions.",
            "prep_time": 5,
            "cook_time": 5,
            "calories": 320,
            "protein": 12,
            "fiber": 8,
            "carbs": 48,
            "fat": 10,
            "ingredients": [
                "1/3 cup tsampa (roasted barley flour)",
                "1 cup water or almond milk",
                "1 tsp butter or ghee",
                "1 tsp honey",
                "1/4 cup mixed berries",
                "1/4 tsp cinnamon",
                "pinch of salt"
            ],
            "dietary_tags": [
                "high_fiber",
                "gluten_free",
                "tibetan",
                "quick",
                "anti_inflammatory"
            ]
        },
        {
            "name": "Nordic Buckwheat Porridge with Sea Buckthorn",
            "meal_type": "breakfast",
            "description": "Nutritious buckwheat porridge with vitamin C-rich sea buckthorn berries",
            "instructions": "Rinse buckwheat groats and place in a small saucepan with water and almond milk. Bring to a boil, then reduce heat and simmer for 15-20 minutes until tender and most liquid is absorbed. Stir in vanilla extract and maple syrup. Let rest for 2 minutes. Top with sea buckthorn berries (or cranberries as alternative), chopped almonds, and a sprinkle of cardamom. This antioxidant-rich breakfast supports recovery and immune function.",
            "prep_time": 5,
            "cook_time": 20,
            "calories": 340,
            "protein": 14,
            "fiber": 10,
            "carbs": 52,
            "fat": 12,
            "ingredients": [
                "1/3 cup buckwheat groats",
                "1/2 cup water",
                "1/2 cup almond milk",
                "1 tbsp sea buckthorn berries",
                "1 tbsp almonds, chopped",
                "1 tsp maple syrup",
                "1/4 tsp vanilla extract",
                "1/8 tsp cardamom",
                "pinch of salt"
            ],
            "dietary_tags": [
                "high_fiber",
                "gluten_free",
                "nordic",
                "antioxidant",
                "anti_inflammatory"
            ]
        }
    ]
    
    # Healthy lunch recipes
    lunch_recipes = [
        {
            "name": "Burmese Tea Leaf Salad",
            "meal_type": "lunch",
            "description": "Fermented tea leaves with crunchy vegetables and nuts",
            "instructions": "If using dried tea leaves, rehydrate in warm water for 10 minutes, then drain. In a large bowl, combine fermented tea leaves with shredded cabbage, julienned carrots, sliced tomatoes, and crushed peanuts. Add garlic, lime juice, and fish sauce. Toss well to combine. Let sit for 5 minutes to allow flavors to meld. Top with fried garlic and sesame seeds before serving. This probiotic-rich salad supports gut health and provides sustained energy.",
            "prep_time": 20,
            "cook_time": 0,
            "calories": 380,
            "protein": 16,
            "fiber": 12,
            "carbs": 32,
            "fat": 22,
            "ingredients": [
                "2 tbsp fermented tea leaves",
                "2 cups cabbage, shredded",
                "1 carrot, julienned",
                "1 tomato, sliced",
                "2 tbsp peanuts, crushed",
                "2 cloves garlic, minced",
                "2 tbsp lime juice",
                "1 tsp fish sauce",
                "1 tsp fried garlic",
                "1 tsp sesame seeds",
                "chili flakes (optional)"
            ],
            "dietary_tags": [
                "high_fiber",
                "probiotic",
                "burmese",
                "fermented",
                "quick"
            ]
        },
        {
            "name": "Sri Lankan Kola Kenda",
            "meal_type": "lunch",
            "description": "Traditional green leaf porridge with coconut and herbs",
            "instructions": "Blend gotukola leaves (or spinach as alternative) with coconut milk and water until smooth. Pour into a saucepan and heat over medium heat, stirring constantly. Add rice flour gradually to prevent lumps. Cook for 5-7 minutes until thickened. Stir in jaggery or maple syrup, cardamom, and salt. Serve warm, topped with chopped cashews and a sprinkle of cinnamon. This nutrient-dense green porridge is excellent for recovery and overall health.",
            "prep_time": 10,
            "cook_time": 10,
            "calories": 360,
            "protein": 12,
            "fiber": 8,
            "carbs": 42,
            "fat": 18,
            "ingredients": [
                "1 cup gotukola leaves or fresh spinach",
                "1/2 cup coconut milk",
                "1/2 cup water",
                "2 tbsp rice flour",
                "1 tbsp jaggery or maple syrup",
                "1 tbsp cashews, chopped",
                "1/4 tsp cardamom",
                "1/8 tsp cinnamon",
                "pinch of salt"
            ],
            "dietary_tags": [
                "high_fiber",
                "sri_lankan",
                "leafy_greens",
                "anti_inflammatory",
                "gluten_free"
            ]
        },
        {
            "name": "Mongolian Buuz with Vegetable Filling",
            "meal_type": "lunch",
            "description": "Steamed dumplings with lean meat and root vegetables",
            "instructions": "For dough: mix flour and warm water to form smooth dough. Let rest for 20 minutes. For filling: combine ground lamb with grated carrots, turnips, cabbage, onion, garlic, and cumin. Season with salt and pepper. Roll dough into small circles, place 1 tbsp filling in center, and pleat edges to seal. Place buuz in a steamer and steam for 15-20 minutes until dough is cooked and filling is tender. Serve with a side of fermented milk drink (airag) or yogurt.",
            "prep_time": 30,
            "cook_time": 20,
            "calories": 420,
            "protein": 24,
            "fiber": 8,
            "carbs": 48,
            "fat": 16,
            "ingredients": [
                "4 oz ground lamb",
                "1 cup all-purpose flour",
                "1/2 cup carrot, grated",
                "1/4 cup turnip, grated",
                "1/4 cup cabbage, finely chopped",
                "2 tbsp onion, minced",
                "1 clove garlic, minced",
                "1 tsp cumin",
                "1/2 cup warm water",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "mongolian",
                "root_vegetables",
                "steamed",
                "comfort"
            ]
        }
    ]
    
    # Healthy dinner recipes
    dinner_recipes = [
        {
            "name": "Armenian Lentil and Walnut Stew",
            "meal_type": "dinner",
            "description": "Hearty plant-based stew with red lentils, walnuts, and aromatic spices",
            "instructions": "Heat olive oil in a large pot over medium heat. Add onions and cook until softened. Add garlic, cumin, coriander, and paprika, stirring for 1 minute until fragrant. Add red lentils, vegetable broth, and diced tomatoes. Bring to a boil, then reduce heat and simmer for 25-30 minutes until lentils are tender. Stir in chopped walnuts, spinach, and lemon juice. Season with salt and pepper. Serve hot, garnished with fresh parsley and a dollop of yogurt if desired.",
            "prep_time": 15,
            "cook_time": 35,
            "calories": 440,
            "protein": 22,
            "fiber": 18,
            "carbs": 52,
            "fat": 16,
            "ingredients": [
                "1 cup red lentils",
                "3 cups vegetable broth",
                "1 can diced tomatoes",
                "1/2 cup walnuts, chopped",
                "2 cups spinach",
                "1 onion, diced",
                "3 cloves garlic, minced",
                "2 tbsp olive oil",
                "1 tsp cumin",
                "1 tsp coriander",
                "1/2 tsp paprika",
                "2 tbsp lemon juice",
                "fresh parsley",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "armenian",
                "plant_based",
                "omega_3",
                "anti_inflammatory"
            ]
        },
        {
            "name": "Yemeni Saltah with Fenugreek",
            "meal_type": "dinner",
            "description": "Spiced meat stew with fenugreek foam, served with flatbread",
            "instructions": "For the stew: heat ghee in a pot and brown ground beef with onions and tomatoes. Add spices (cumin, coriander, turmeric) and beef broth. Simmer for 20 minutes. For the foam (hulbah): soak fenugreek seeds in water for 30 minutes, drain and blend with water until frothy. Beat with a whisk or hand mixer until light and foamy. To serve: ladle stew into bowls, top with fenugreek foam, and serve with warm flatbread for dipping.",
            "prep_time": 40,
            "cook_time": 25,
            "calories": 480,
            "protein": 32,
            "fiber": 8,
            "carbs": 38,
            "fat": 22,
            "ingredients": [
                "5 oz ground beef",
                "2 tbsp fenugreek seeds",
                "1 onion, diced",
                "1 tomato, diced",
                "1 cup beef broth",
                "2 tbsp ghee",
                "1 tsp cumin",
                "1 tsp coriander",
                "1/2 tsp turmeric",
                "whole wheat flatbread",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "yemeni",
                "fenugreek",
                "anti_inflammatory",
                "gluten_free_option"
            ]
        },
        {
            "name": "Kazakh Beshbarmak with Horse Meat",
            "meal_type": "dinner",
            "description": "Traditional boiled meat with wide noodles and onion sauce",
            "instructions": "Boil horse meat (or beef as alternative) in salted water with bay leaves for 2 hours until very tender. Remove meat and shred. Use the broth to cook wide egg noodles according to package directions. For onion sauce: thinly slice onions and simmer in meat broth until very soft. To serve: arrange noodles on a large platter, top with shredded meat, and pour onion sauce over everything. Garnish with fresh herbs and serve with bowls of hot broth.",
            "prep_time": 20,
            "cook_time": 120,
            "calories": 520,
            "protein": 38,
            "fiber": 6,
            "carbs": 48,
            "fat": 20,
            "ingredients": [
                "6 oz horse meat or beef",
                "4 oz wide egg noodles",
                "2 onions, thinly sliced",
                "2 bay leaves",
                "fresh dill",
                "fresh parsley",
                "salt",
                "pepper",
                "meat broth for serving"
            ],
            "dietary_tags": [
                "high_protein",
                "kazakh",
                "traditional",
                "hearty",
                "comfort"
            ]
        },
        {
            "name": "Kyrgyz Plov with Carrots and Raisins",
            "meal_type": "dinner",
            "description": "Fragrant rice pilaf with lamb, sweet carrots, and raisins",
            "instructions": "Heat oil in a heavy pot or Dutch oven. Brown lamb pieces on all sides, then remove. Add onions and carrots, cooking until softened. Add garlic and spices (cumin, coriander, paprika). Return lamb to pot, add rice that has been rinsed and drained, and hot broth or water. Bring to a boil, then reduce heat to low, cover, and simmer for 20-25 minutes until rice is tender. Add raisins in the last 5 minutes. Let rest for 10 minutes before fluffing with a fork. Serve hot.",
            "prep_time": 20,
            "cook_time": 35,
            "calories": 540,
            "protein": 32,
            "fiber": 8,
            "carbs": 68,
            "fat": 18,
            "ingredients": [
                "6 oz lamb, cubed",
                "1 cup basmati rice",
                "2 carrots, julienned",
                "1 onion, diced",
                "2 tbsp raisins",
                "2 cups hot broth",
                "2 tbsp vegetable oil",
                "1 tsp cumin",
                "1 tsp coriander",
                "1/2 tsp paprika",
                "3 cloves garlic",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "high_carb",
                "kyrgyz",
                "pilaf",
                "mediterranean"
            ]
        },
        {
            "name": "Tajik Osh Palov with Quince",
            "meal_type": "dinner",
            "description": "Celebratory rice pilaf with lamb, quince, and aromatic spices",
            "instructions": "Heat oil in a large pot. Brown lamb pieces, then remove. Sauté onions until golden, add carrots and cook until tender. Add quince pieces and cook until slightly softened. Add rice, spices (cumin, turmeric, coriander), and hot water or broth. Return lamb to pot. Bring to a boil, reduce heat to low, cover and cook for 25-30 minutes until rice is tender and liquid is absorbed. Let rest for 10 minutes. Fluff rice and serve garnished with fresh herbs.",
            "prep_time": 25,
            "cook_time": 40,
            "calories": 560,
            "protein": 34,
            "fiber": 10,
            "carbs": 72,
            "fat": 16,
            "ingredients": [
                "6 oz lamb, cubed",
                "1 cup basmati rice",
                "1/2 quince, cored and cubed",
                "2 carrots, julienned",
                "1 onion, sliced",
                "2 cups hot water or broth",
                "2 tbsp vegetable oil",
                "1 tsp cumin",
                "1/2 tsp turmeric",
                "1/2 tsp coriander",
                "fresh cilantro",
                "fresh dill",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "tajik",
                "pilaf",
                "fruit",
                "anti_inflammatory"
            ]
        }
    ]
    
    # Healthy post-workout recipes
    post_workout_recipes = [
        {
            "name": "Andean Quinoa Ch'arki Soup",
            "meal_type": "post_workout",
            "description": "High-altitude recovery soup with quinoa, dried meat, and root vegetables",
            "instructions": "Rinse quinoa and set aside. In a large pot, heat oil and sauté onions and garlic until softened. Add diced potatoes, oca (or turnips as alternative), carrots, and vegetable broth. Bring to a boil and simmer for 10 minutes. Add quinoa and dried llama meat (or beef jerky as alternative). Simmer for another 15 minutes until quinoa is cooked and vegetables are tender. Add chuño (freeze-dried potatoes) if available. Season with salt and cumin. Serve hot, garnished with fresh herbs.",
            "prep_time": 15,
            "cook_time": 30,
            "calories": 480,
            "protein": 28,
            "fiber": 12,
            "carbs": 58,
            "fat": 12,
            "ingredients": [
                "1/2 cup quinoa",
                "4 oz dried meat (ch'arki) or beef jerky",
                "1 potato, diced",
                "1/2 cup oca or turnips, diced",
                "1 carrot, diced",
                "1/4 cup chuño (freeze-dried potatoes, optional)",
                "1 onion, diced",
                "2 cloves garlic, minced",
                "3 cups vegetable broth",
                "1 tsp cumin",
                "2 tbsp vegetable oil",
                "fresh cilantro",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "andean",
                "recovery",
                "gluten_free",
                "anti_inflammatory"
            ]
        },
        {
            "name": "Siberian Pine Nut Milk with Berries",
            "meal_type": "post_workout",
            "description": "Nutrient-dense pine nut milk with antioxidant berries for recovery",
            "instructions": "Blend pine nuts with water until very smooth. Strain through a nut milk bag or fine mesh sieve. Pour milk into a blender and add frozen berries, honey, and vanilla. Blend until smooth. Add chia seeds and let sit for 5 minutes to thicken slightly. Pour into a glass and sprinkle with hemp seeds and goji berries. This omega-3 rich recovery drink supports muscle repair and reduces inflammation.",
            "prep_time": 10,
            "cook_time": 0,
            "calories": 420,
            "protein": 16,
            "fiber": 10,
            "carbs": 38,
            "fat": 24,
            "ingredients": [
                "1/4 cup pine nuts",
                "1 cup water",
                "1 cup mixed berries (frozen)",
                "1 tbsp honey",
                "1 tsp vanilla extract",
                "1 tbsp chia seeds",
                "1 tbsp hemp seeds",
                "1 tbsp goji berries",
                "pinch of salt"
            ],
            "dietary_tags": [
                "high_protein",
                "omega_3",
                "siberian",
                "recovery",
                "antioxidant",
                "gluten_free",
                "anti_inflammatory"
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
    
    print(f"Added {len(breakfast_recipes)} healthy breakfast recipes")
    print(f"Added {len(lunch_recipes)} healthy lunch recipes")
    print(f"Added {len(dinner_recipes)} healthy dinner recipes")
    print(f"Added {len(post_workout_recipes)} healthy post-workout recipes")

def main():
    """Main function to add all unique healthy recipes."""
    print("Adding more unique and healthy recipes...")
    
    add_unique_healthy_recipes()
    
    print("\nUnique healthy recipe addition complete!")
    print("\nSummary of additions:")
    print("- 2 healthy breakfast recipes")
    print("- 3 healthy lunch recipes")
    print("- 5 healthy dinner recipes")
    print("- 2 healthy post-workout recipes")
    print("- Total: 12 unique healthy recipes added")
    print("\nFeatured regions and health benefits:")
    print("- Himalayan (Tibetan Tsampa, Nepalese) - High altitude nutrition")
    print("- Nordic (Buckwheat Porridge) - Antioxidant-rich")
    print("- Southeast Asian (Burmese, Sri Lankan) - Probiotic and leafy greens")
    print("- Central Asian (Mongolian, Kazakh, Kyrgyz, Tajik) - Traditional hearty meals")
    print("- Caucasus (Armenian, Yemeni) - Plant-based and anti-inflammatory")
    print("- Arctic/Siberian (Pine Nut Milk) - Omega-3 recovery")
    print("- Andean (Quinoa Soup) - Complete protein and root vegetables")
    print("\nHealth focus areas:")
    print("- Anti-inflammatory ingredients")
    print("- High fiber and probiotic foods")
    print("- Omega-3 rich nuts and seeds")
    print("- Complete protein sources")
    print("- Antioxidant-rich berries and fruits")
    print("- Traditional fermented foods")

if __name__ == "__main__":
    main()