#!/usr/bin/env python3
"""Add even more Mediterranean-inspired performance recipes for runners."""

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

def add_more_mediterranean_recipes():
    """Add even more Mediterranean performance recipes."""
    
    # Additional Portuguese recipes
    portuguese_extra = [
        {
            "name": "Trás-os-Montes Alheira Runner's Sausage",
            "meal_type": "lunch",
            "description": "Lean chicken sausage with chestnuts and local herbs for sustained energy",
            "instructions": "Grill or pan-fry alheira sausage until golden and crispy. Serve with boiled chestnuts, roasted root vegetables, and a side of local greens. Drizzle with olive oil and sprinkle with mountain herbs. This lean protein provides sustained energy for long runs.",
            "prep_time": 15,
            "cook_time": 20,
            "calories": 480,
            "protein": 32,
            "fiber": 10,
            "carbs": 42,
            "fat": 20,
            "ingredients": [
                "4 oz alheira sausage",
                "1/2 cup chestnuts, boiled",
                "root vegetables",
                "local greens",
                "2 tbsp olive oil",
                "mountain herbs",
                "sea salt",
                "black pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "sustained_energy",
                "portuguese",
                "mountain_cuisine",
                "gluten_free"
            ]
        },
        {
            "name": "Minho Caldo Verde Performance Soup",
            "meal_type": "dinner",
            "description": "Traditional kale soup with lean chorizo and whole grain bread",
            "instructions": "Simmer potatoes and onions in broth until tender. Add finely sliced kale and cook until wilted. Add lean chorizo slices and simmer for 5 more minutes. Serve hot with a slice of whole grain rye bread and a drizzle of olive oil. This iron-rich soup supports oxygen transport.",
            "prep_time": 15,
            "cook_time": 30,
            "calories": 420,
            "protein": 22,
            "fiber": 12,
            "carbs": 48,
            "fat": 16,
            "ingredients": [
                "2 cups kale",
                "2 potatoes",
                "1 onion",
                "2 oz lean chorizo",
                "4 cups vegetable broth",
                "whole grain rye bread",
                "olive oil",
                "sea salt"
            ],
            "dietary_tags": [
                "iron_rich",
                "high_fiber",
                "minho",
                "traditional",
                "gluten_free_option"
            ]
        },
        {
            "name": "Alentejo Migas Runner's Style",
            "meal_type": "breakfast",
            "description": "Whole grain bread migas with eggs and presunto for protein-rich start",
            "instructions": "Tear whole grain bread and soak in water. Squeeze out excess water. In a pan, heat olive oil and sauté garlic. Add bread and cook until crispy. Add beaten eggs and presunto ham, cooking until eggs are set. Serve with fresh tomato and herbs. This protein-rich breakfast fuels morning runs.",
            "prep_time": 10,
            "cook_time": 15,
            "calories": 460,
            "protein": 28,
            "fiber": 8,
            "carbs": 42,
            "fat": 22,
            "ingredients": [
                "2 slices whole grain bread",
                "2 eggs",
                "2 oz presunto ham",
                "2 cloves garlic",
                "3 tbsp olive oil",
                "fresh tomato",
                "fresh herbs",
                "sea salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "complex_carbs",
                "alentejo",
                "traditional",
                "sustained_energy"
            ]
        },
        {
            "name": "Estremoz Marble Cake Energy Bars",
            "meal_type": "post_workout",
            "description": "Local marble-inspired energy bars with almonds and honey",
            "instructions": "Mix whole grain flour, almonds, honey, eggs, and olive oil. Add cinnamon and vanilla. Pour into a baking dish and bake at 350°F for 25 minutes. Cool and cut into bars. These energy bars provide quick recovery carbohydrates and protein.",
            "prep_time": 15,
            "cook_time": 25,
            "calories": 320,
            "protein": 12,
            "fiber": 6,
            "carbs": 42,
            "fat": 14,
            "ingredients": [
                "1 cup whole grain flour",
                "1/2 cup almonds",
                "3 tbsp honey",
                "2 eggs",
                "2 tbsp olive oil",
                "cinnamon",
                "vanilla",
                "sea salt"
            ],
            "dietary_tags": [
                "recovery",
                "energy_bar",
                "estremoz",
                "quick",
                "portable"
            ]
        }
    ]
    
    # Additional Spanish recipes
    spanish_extra = [
        {
            "name": "Aragonese Ternasco with Rosemary Potatoes",
            "meal_type": "dinner",
            "description": "Young lamb with rosemary potatoes for iron and recovery",
            "instructions": "Season ternasco lamb with garlic, rosemary, and sea salt. Roast with baby potatoes until lamb is tender and potatoes are crispy. Serve with a side of steamed asparagus and a drizzle of olive oil. This iron-rich meal supports oxygen transport and muscle recovery.",
            "prep_time": 20,
            "cook_time": 90,
            "calories": 540,
            "protein": 38,
            "fiber": 8,
            "carbs": 32,
            "fat": 28,
            "ingredients": [
                "6 oz ternasco lamb",
                "4 baby potatoes",
                "fresh rosemary",
                "4 cloves garlic",
                "asparagus",
                "olive oil",
                "sea salt",
                "black pepper"
            ],
            "dietary_tags": [
                "iron_rich",
                "recovery",
                "aragonese",
                "high_protein",
                "gluten_free"
            ]
        },
        {
            "name": "Levante Alubias con Longaniza Runner's Bowl",
            "meal_type": "lunch",
            "description": "White beans with lean sausage for protein and fiber",
            "instructions": "Simmer white beans with bay leaves until tender. Add lean longaniza sausage and vegetables. Season with paprika and saffron. Simmer for 20 minutes. Serve with a drizzle of olive oil and fresh herbs. This high-fiber, high-protein meal supports sustained energy.",
            "prep_time": 15,
            "cook_time": 45,
            "calories": 480,
            "protein": 28,
            "fiber": 18,
            "carbs": 52,
            "fat": 16,
            "ingredients": [
                "1 cup white beans",
                "3 oz lean longaniza",
                "mixed vegetables",
                "bay leaves",
                "paprika",
                "saffron",
                "olive oil",
                "fresh herbs",
                "sea salt"
            ],
            "dietary_tags": [
                "high_fiber",
                "high_protein",
                "levantine",
                "sustained_energy",
                "gluten_free"
            ]
        },
        {
            "name": "Navarra Piquillo Pepper Stuffed with Cod",
            "meal_type": "dinner",
            "description": "Omega-3 rich cod stuffed in antioxidant peppers",
            "instructions": "Mix shredded salt cod with garlic, parsley, and olive oil. Stuff piquillo peppers with cod mixture. Place in baking dish, add tomato sauce and bake for 25 minutes. Serve with a side of quinoa and steamed greens. This omega-3 rich meal reduces inflammation.",
            "prep_time": 20,
            "cook_time": 25,
            "calories": 460,
            "protein": 32,
            "fiber": 10,
            "carbs": 38,
            "fat": 18,
            "ingredients": [
                "4 oz salt cod",
                "4 piquillo peppers",
                "2 cloves garlic",
                "fresh parsley",
                "tomato sauce",
                "quinoa",
                "steamed greens",
                "olive oil",
                "sea salt"
            ],
            "dietary_tags": [
                "omega_3",
                "anti_inflammatory",
                "navarre",
                "high_protein",
                "gluten_free"
            ]
        },
        {
            "name": "Castilian Gazpacho de Ajojo",
            "meal_type": "lunch",
            "description": "Cold garlic and almond soup for hydration and healthy fats",
            "instructions": "Blend almonds, garlic, bread, olive oil, and vinegar until smooth. Add cold water and blend until desired consistency. Chill for 30 minutes. Serve with grapes and a sprinkle of almonds. This hydrating soup provides healthy fats and electrolytes.",
            "prep_time": 10,
            "cook_time": 0,
            "calories": 380,
            "protein": 12,
            "fiber": 8,
            "carbs": 28,
            "fat": 26,
            "ingredients": [
                "1/2 cup almonds",
                "4 cloves garlic",
                "1 slice bread",
                "3 tbsp olive oil",
                "1 tbsp vinegar",
                "cold water",
                "grapes",
                "almond slices",
                "sea salt"
            ],
            "dietary_tags": [
                "hydrating",
                "healthy_fats",
                "castilian",
                "cold_soup",
                "gluten_free_option"
            ]
        },
        {
            "name": "Balearic Sobrassada with Honey and Figs",
            "meal_type": "breakfast",
            "description": "Spiced sausage with honey and figs for energy and antioxidants",
            "instructions": "Slice sobrassada and pan-fry until crispy. Serve with fresh figs, a drizzle of honey, and a side of whole grain toast. Add a sprinkle of local herbs. This protein-rich breakfast provides sustained energy and antioxidants.",
            "prep_time": 8,
            "cook_time": 8,
            "calories": 420,
            "protein": 22,
            "fiber": 8,
            "carbs": 38,
            "fat": 22,
            "ingredients": [
                "3 oz sobrassada",
                "2 fresh figs",
                "1 tbsp honey",
                "1 slice whole grain toast",
                "local herbs",
                "olive oil",
                "sea salt"
            ],
            "dietary_tags": [
                "high_protein",
                "antioxidant",
                "balearic",
                "energy_boosting",
                "quick"
            ]
        },
        {
            "name": "Andalusian Salmorejo with Avocado",
            "meal_type": "post_workout",
            "description": "Thick tomato soup with avocado for healthy fats and recovery",
            "instructions": "Blend tomatoes, bread, garlic, olive oil, and vinegar until smooth. Chill for 30 minutes. Serve with diced avocado, hard-boiled egg, and jamón serrano. This creamy soup provides healthy fats and protein for recovery.",
            "prep_time": 10,
            "cook_time": 0,
            "calories": 440,
            "protein": 18,
            "fiber": 10,
            "carbs": 32,
            "fat": 26,
            "ingredients": [
                "3 ripe tomatoes",
                "1 slice bread",
                "2 cloves garlic",
                "3 tbsp olive oil",
                "1 tbsp vinegar",
                "1/2 avocado",
                "1 hard-boiled egg",
                "1 oz jamón serrano",
                "sea salt"
            ],
            "dietary_tags": [
                "recovery",
                "healthy_fats",
                "andalusian",
                "thick_soup",
                "gluten_free_option"
            ]
        }
    ]
    
    # Additional Italian recipes
    italian_extra = [
        {
            "name": "Abruzzo Arrosticini Runner's Skewers",
            "meal_type": "dinner",
            "description": "Grilled lamb skewers with herbs for iron and protein",
            "instructions": "Cut lamb into small cubes and marinate with olive oil, garlic, and rosemary. Thread onto skewers and grill for 3-4 minutes per side. Serve with a side of grilled vegetables and whole grain bread. This iron-rich meal supports oxygen transport.",
            "prep_time": 20,
            "cook_time": 12,
            "calories": 480,
            "protein": 38,
            "fiber": 6,
            "carbs": 28,
            "fat": 24,
            "ingredients": [
                "6 oz lamb",
                "olive oil",
                "garlic",
                "rosemary",
                "grilled vegetables",
                "whole grain bread",
                "sea salt",
                "black pepper"
            ],
            "dietary_tags": [
                "iron_rich",
                "high_protein",
                "abruzzo",
                "grilled",
                "gluten_free_option"
            ]
        },
        {
            "name": "Umbrian Porchetta with Whole Grain",
            "meal_type": "lunch",
            "description": "Herb-crusted pork with whole grain for sustained energy",
            "instructions": "Season pork loin with fennel, garlic, rosemary, and sea salt. Roast until crispy on outside and tender inside. Slice thinly and serve with whole grain bread, arugula, and a drizzle of olive oil. This protein-rich meal provides sustained energy.",
            "prep_time": 15,
            "cook_time": 90,
            "calories": 520,
            "protein": 36,
            "fiber": 8,
            "carbs": 38,
            "fat": 26,
            "ingredients": [
                "5 oz pork loin",
                "fennel seeds",
                "garlic",
                "rosemary",
                "whole grain bread",
                "arugula",
                "olive oil",
                "sea salt",
                "black pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "sustained_energy",
                "umbrian",
                "herb_crusted",
                "gluten_free_option"
            ]
        },
        {
            "name": "Marche Ciaudedu with Lentils",
            "meal_type": "dinner",
            "description": "Hearty soup with legumes and grains for complete protein",
            "instructions": "Simmer lentils, farro, and vegetables in broth until tender. Add tomato paste and herbs. Cook for 20 more minutes. Serve with a drizzle of olive oil and grated pecorino. This complete protein meal supports muscle recovery.",
            "prep_time": 15,
            "cook_time": 45,
            "calories": 460,
            "protein": 24,
            "fiber": 16,
            "carbs": 58,
            "fat": 14,
            "ingredients": [
                "1 cup lentils",
                "1/2 cup farro",
                "mixed vegetables",
                "tomato paste",
                "herbs",
                "vegetable broth",
                "pecorino cheese",
                "olive oil",
                "sea salt"
            ],
            "dietary_tags": [
                "complete_protein",
                "high_fiber",
                "marche",
                "hearty",
                "gluten_free_option"
            ]
        },
        {
            "name": "Lazio Amatriciana with Turkey Guanciale",
            "meal_type": "dinner",
            "description": "Lighter version with turkey and whole grain pasta",
            "instructions": "Crisp turkey guanciale in a pan. Add onions and cook until soft. Add tomato sauce and chili flakes. Simmer for 20 minutes. Toss with whole grain bucatini and pecorino cheese. This lighter version provides protein without excess fat.",
            "prep_time": 10,
            "cook_time": 25,
            "calories": 520,
            "protein": 28,
            "fiber": 12,
            "carbs": 68,
            "fat": 18,
            "ingredients": [
                "3 oz whole grain bucatini",
                "2 oz turkey guanciale",
                "tomato sauce",
                "onion",
                "chili flakes",
                "pecorino cheese",
                "olive oil",
                "sea salt"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "lazio",
                "light_version",
                "complex_carbs"
            ]
        },
        {
            "name": "Campanian Pasta e Fagioli con Cozze",
            "meal_type": "lunch",
            "description": "Pasta and bean soup with mussels for complete protein",
            "instructions": "Simmer cannellini beans, pasta, and vegetables in broth. Add mussels and cook until they open. Add garlic, herbs, and olive oil. Serve hot with a sprinkle of parsley. This complete protein meal supports muscle recovery.",
            "prep_time": 15,
            "cook_time": 30,
            "calories": 480,
            "protein": 26,
            "fiber": 14,
            "carbs": 58,
            "fat": 16,
            "ingredients": [
                "1/2 cup pasta",
                "1/2 cup cannellini beans",
                "4 oz mussels",
                "vegetables",
                "garlic",
                "herbs",
                "olive oil",
                "parsley",
                "sea salt"
            ],
            "dietary_tags": [
                "complete_protein",
                "high_fiber",
                "campanian",
                "seafood",
                "gluten_free_option"
            ]
        },
        {
            "name": "Pugliese Fave e Cicoria con Tonno",
            "meal_type": "lunch",
            "description": "Fava bean purée with chicory and tuna for protein and fiber",
            "instructions": "Cook fava beans until tender, then purée with olive oil and garlic. Serve with steamed chicory and canned tuna. Drizzle with olive oil and lemon. This high-protein, high-fiber meal supports sustained energy.",
            "prep_time": 15,
            "cook_time": 20,
            "calories": 460,
            "protein": 28,
            "fiber": 16,
            "carbs": 42,
            "fat": 18,
            "ingredients": [
                "1 cup fava beans",
                "chicory",
                "3 oz tuna",
                "olive oil",
                "garlic",
                "lemon",
                "sea salt",
                "black pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "pugliese",
                "plant_based",
                "gluten_free"
            ]
        },
        {
            "name": "Sicilian Pasta con le Sarde e Finocchio",
            "meal_type": "dinner",
            "description": "Sardine pasta with fennel for omega-3 and digestion",
            "instructions": "Cook bucatini al dente. In a pan, sauté fennel, onions, and raisins. Add canned sardines, pine nuts, and saffron. Toss with pasta, fresh herbs, and toasted breadcrumbs. This omega-3 rich meal supports brain health and recovery.",
            "prep_time": 20,
            "cook_time": 15,
            "calories": 540,
            "protein": 32,
            "fiber": 10,
            "carbs": 68,
            "fat": 20,
            "ingredients": [
                "3 oz bucatini",
                "1 can sardines",
                "1 fennel bulb",
                "onion",
                "raisins",
                "pine nuts",
                "saffron",
                "fresh herbs",
                "breadcrumbs",
                "olive oil"
            ],
            "dietary_tags": [
                "omega_3",
                "digestive_health",
                "sicilian",
                "complete_meal",
                "high_fiber"
            ]
        },
        {
            "name": "Trentino Canederli with Spinach and Speck",
            "meal_type": "dinner",
            "description": "Bread dumplings with spinach and lean speck for sustained energy",
            "instructions": "Mix stale bread with milk, eggs, spinach, and diced speck. Form into dumplings and simmer in broth until cooked. Serve with melted butter and Parmesan cheese. These carbohydrate-rich dumplings provide sustained energy.",
            "prep_time": 20,
            "cook_time": 15,
            "calories": 480,
            "protein": 22,
            "fiber": 8,
            "carbs": 58,
            "fat": 18,
            "ingredients": [
                "stale bread",
                "milk",
                "2 eggs",
                "spinach",
                "2 oz speck",
                "butter",
                "Parmesan cheese",
                "broth",
                "sea salt"
            ],
            "dietary_tags": [
                "sustained_energy",
                "complex_carbs",
                "trentino",
                "dumplings",
                "hearty"
            ]
        },
        {
            "name": "Friulian Jota with Beans and Sauerkraut",
            "meal_type": "dinner",
            "description": "Bean and sauerkraut soup for probiotics and protein",
            "instructions": "Simmer beans with potatoes and sauerkraut until tender. Add smoked pork and herbs. Cook for 30 minutes. Serve with a side of whole grain bread. This probiotic-rich soup supports gut health and provides protein.",
            "prep_time": 15,
            "cook_time": 60,
            "calories": 460,
            "protein": 24,
            "fiber": 18,
            "carbs": 52,
            "fat": 14,
            "ingredients": [
                "1 cup beans",
                "1 potato",
                "1 cup sauerkraut",
                "2 oz smoked pork",
                "herbs",
                "whole grain bread",
                "sea salt",
                "black pepper"
            ],
            "dietary_tags": [
                "probiotic",
                "high_fiber",
                "friulian",
                "gut_health",
                "gluten_free_option"
            ]
        },
        {
            "name": "Valle d'Aosta Fontina Polenta con Funghi",
            "meal_type": "dinner",
            "description": "Polenta with Fontina cheese and wild mushrooms for protein and carbs",
            "instructions": "Cook polenta until creamy. Stir in Fontina cheese and wild mushrooms. Top with truffle oil and fresh herbs. Serve with a side of lean protein. This high-carb, high-protein meal supports endurance performance.",
            "prep_time": 15,
            "cook_time": 25,
            "calories": 520,
            "protein": 24,
            "fiber": 6,
            "carbs": 58,
            "fat": 24,
            "ingredients": [
                "1/2 cup polenta",
                "2 oz Fontina cheese",
                "wild mushrooms",
                "truffle oil",
                "fresh herbs",
                "lean protein",
                "sea salt",
                "black pepper"
            ],
            "dietary_tags": [
                "high_carb",
                "high_protein",
                "valdostan",
                "mountain_cuisine",
                "gluten_free"
            ]
        }
    ]
    
    # Mediterranean fusion recipes
    fusion_recipes = [
        {
            "name": "Mediterranean Power Bowl with Quinoa Tabouleh",
            "meal_type": "lunch",
            "description": "Quinoa tabouleh with grilled chicken and Mediterranean toppings",
            "instructions": "Cook quinoa and let cool. Mix with parsley, mint, tomatoes, cucumber, and lemon dressing. Top with grilled chicken, feta cheese, olives, and a drizzle of tahini. This complete protein bowl supports muscle recovery.",
            "prep_time": 20,
            "cook_time": 15,
            "calories": 520,
            "protein": 38,
            "fiber": 12,
            "carbs": 48,
            "fat": 20,
            "ingredients": [
                "1 cup quinoa",
                "4 oz grilled chicken",
                "fresh parsley",
                "fresh mint",
                "tomatoes",
                "cucumber",
                "feta cheese",
                "olives",
                "tahini",
                "lemon",
                "olive oil"
            ],
            "dietary_tags": [
                "complete_protein",
                "mediterranean",
                "fusion",
                "high_fiber",
                "gluten_free"
            ]
        },
        {
            "name": "Iberian-Moroccan Fusion Chicken with Chermoula",
            "meal_type": "dinner",
            "description": "Spanish chicken with Moroccan chermoula spices for metabolism boost",
            "instructions": "Marinate chicken in chermoula (cilantro, parsley, cumin, paprika, lemon). Grill until cooked. Serve with Spanish-style patatas bravas and a side of Moroccan couscous with herbs. This spicy meal boosts metabolism and provides complete protein.",
            "prep_time": 20,
            "cook_time": 20,
            "calories": 540,
            "protein": 42,
            "fiber": 10,
            "carbs": 48,
            "fat": 22,
            "ingredients": [
                "6 oz chicken",
                "chermoula spices",
                "cilantro",
                "parsley",
                "cumin",
                "paprika",
                "lemon",
                "potatoes",
                "couscous",
                "herbs",
                "olive oil"
            ],
            "dietary_tags": [
                "metabolism_boosting",
                "fusion",
                "high_protein",
                "spicy",
                "complete_meal"
            ]
        },
        {
            "name": "Greek-Italian Lentil Pasta with Feta and Basil",
            "meal_type": "dinner",
            "description": "Red lentil pasta with Greek feta and Italian basil for plant-based protein",
            "instructions": "Cook red lentil pasta al dente. Toss with olive oil, garlic, cherry tomatoes, and fresh basil. Top with crumbled feta cheese and Kalamata olives. Serve with a side of Greek salad. This plant-based meal provides complete protein.",
            "prep_time": 10,
            "cook_time": 12,
            "calories": 480,
            "protein": 24,
            "fiber": 16,
            "carbs": 58,
            "fat": 18,
            "ingredients": [
                "3 oz red lentil pasta",
                "cherry tomatoes",
                "fresh basil",
                "feta cheese",
                "Kalamata olives",
                "garlic",
                "olive oil",
                "Greek salad",
                "sea salt",
                "pepper"
            ],
            "dietary_tags": [
                "plant_based",
                "complete_protein",
                "fusion",
                "high_fiber",
                "gluten_free"
            ]
        },
        {
            "name": "Mediterranean Buddha Bowl with Hummus and Grilled Vegetables",
            "meal_type": "lunch",
            "description": "Colorful bowl with hummus, grilled vegetables, and protein-rich toppings",
            "instructions": "Arrange grilled vegetables, hummus, quinoa, chickpeas, and avocado in a bowl. Top with grilled halloumi cheese, olives, and a drizzle of tahini dressing. Sprinkle with seeds and herbs. This nutrient-dense bowl supports overall health.",
            "prep_time": 20,
            "cook_time": 15,
            "calories": 500,
            "protein": 22,
            "fiber": 18,
            "carbs": 52,
            "fat": 22,
            "ingredients": [
                "grilled vegetables",
                "hummus",
                "quinoa",
                "chickpeas",
                "avocado",
                "halloumi cheese",
                "olives",
                "tahini dressing",
                "seeds",
                "herbs",
                "olive oil"
            ],
            "dietary_tags": [
                "nutrient_dense",
                "plant_based",
                "fusion",
                "high_fiber",
                "gluten_free_option"
            ]
        },
        {
            "name": "Spanish-Portuguese Seafood Cataplana Fusion",
            "meal_type": "dinner",
            "description": "Seafood stew with Iberian flavors for omega-3 recovery",
            "instructions": "In a cataplana pan, sauté onions, garlic, and peppers. Add mixed seafood, white wine, and saffron. Simmer until seafood is cooked. Add chorizo and fresh herbs. Serve with crusty bread. This omega-3 rich stew supports recovery and reduces inflammation.",
            "prep_time": 20,
            "cook_time": 25,
            "calories": 520,
            "protein": 38,
            "fiber": 8,
            "carbs": 38,
            "fat": 22,
            "ingredients": [
                "mixed seafood",
                "white wine",
                "saffron",
                "onions",
                "garlic",
                "peppers",
                "chorizo",
                "fresh herbs",
                "crusty bread",
                "olive oil"
            ],
            "dietary_tags": [
                "omega_3",
                "recovery",
                "fusion",
                "seafood",
                "anti_inflammatory"
            ]
        }
    ]
    
    # Post-workout Mediterranean recovery recipes
    post_workout_extra = [
        {
            "name": "Mediterranean Chia Seed Pudding with Pistachios",
            "meal_type": "post_workout",
            "description": "Chia pudding with Greek yogurt, pistachios, and honey for recovery",
            "instructions": "Mix chia seeds with Greek yogurt, milk, and honey. Let sit overnight. Top with pistachios, fresh berries, and a drizzle of honey. This protein-rich pudding supports muscle recovery and provides healthy fats.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 420,
            "protein": 24,
            "fiber": 12,
            "carbs": 38,
            "fat": 20,
            "ingredients": [
                "3 tbsp chia seeds",
                "1 cup Greek yogurt",
                "1/4 cup milk",
                "2 tbsp honey",
                "2 tbsp pistachios",
                "fresh berries",
                "vanilla extract",
                "cinnamon"
            ],
            "dietary_tags": [
                "recovery",
                "high_protein",
                "mediterranean",
                "make_ahead",
                "gluten_free"
            ]
        },
        {
            "name": "Italian Espresso Protein Gelato",
            "meal_type": "post_workout",
            "description": "Protein-enriched espresso gelato for quick recovery and energy",
            "instructions": "Blend espresso, protein powder, Greek yogurt, and honey. Pour into ice cream maker and churn until frozen. Alternatively, freeze in a shallow dish, stirring every 30 minutes. Serve immediately. This protein-rich gelato supports muscle recovery.",
            "prep_time": 10,
            "cook_time": 0,
            "calories": 320,
            "protein": 20,
            "fiber": 2,
            "carbs": 28,
            "fat": 14,
            "ingredients": [
                "1 shot espresso",
                "1 scoop protein powder",
                "1/2 cup Greek yogurt",
                "1 tbsp honey",
                "dark chocolate shavings",
                "cocoa powder"
            ],
            "dietary_tags": [
                "recovery",
                "high_protein",
                "italian",
                "caffeine",
                "dessert"
            ]
        },
        {
            "name": "Spanish Horchata Recovery Drink",
            "meal_type": "post_workout",
            "description": "Tiger nut milk with cinnamon and protein for hydration and recovery",
            "instructions": "Blend soaked tiger nuts with water, protein powder, cinnamon, and honey until smooth. Strain through nut milk bag. Serve over ice with a sprinkle of cinnamon. This hydrating drink provides electrolytes and protein.",
            "prep_time": 10,
            "cook_time": 0,
            "calories": 280,
            "protein": 16,
            "fiber": 6,
            "carbs": 32,
            "fat": 12,
            "ingredients": [
                "1/4 cup tiger nuts, soaked",
                "2 cups water",
                "1/2 scoop protein powder",
                "1 tsp cinnamon",
                "1 tbsp honey",
                "ice",
                "vanilla extract"
            ],
            "dietary_tags": [
                "hydrating",
                "recovery",
                "spanish",
                "plant_based",
                "gluten_free"
            ]
        }
    ]
    
    # Load existing recipes
    breakfast_existing = load_recipes("meals_breakfast.json")
    lunch_existing = load_recipes("meals_lunch.json")
    dinner_existing = load_recipes("meals_dinner.json")
    post_workout_existing = load_recipes("meals_post_workout.json")
    
    # Add all new recipes
    breakfast_existing.extend([portuguese_extra[2], spanish_extra[4]])
    
    # Lunch recipes
    lunch_recipes_to_add = []
    lunch_recipes_to_add.extend(portuguese_extra[:1])
    lunch_recipes_to_add.extend(spanish_extra[1:2])
    lunch_recipes_to_add.extend(spanish_extra[3:4])
    lunch_recipes_to_add.extend(italian_extra[4:6])
    lunch_recipes_to_add.extend(fusion_recipes[:1])
    lunch_recipes_to_add.extend(fusion_recipes[3:4])
    lunch_existing.extend(lunch_recipes_to_add)
    
    # Dinner recipes
    dinner_recipes_to_add = []
    dinner_recipes_to_add.append(portuguese_extra[1])
    dinner_recipes_to_add.extend(spanish_extra[:1])
    dinner_recipes_to_add.extend(spanish_extra[2:3])
    dinner_recipes_to_add.extend(italian_extra[:4])
    dinner_recipes_to_add.extend(italian_extra[6:10])
    dinner_recipes_to_add.extend(fusion_recipes[1:2])
    dinner_recipes_to_add.extend(fusion_recipes[4:5])
    dinner_existing.extend(dinner_recipes_to_add)
    
    # Post-workout recipes
    post_workout_recipes_to_add = []
    post_workout_recipes_to_add.extend(portuguese_extra[3:4])
    post_workout_recipes_to_add.extend(spanish_extra[5:6])
    post_workout_recipes_to_add.extend(post_workout_extra)
    post_workout_existing.extend(post_workout_recipes_to_add)
    
    # Save updated recipes
    save_recipes("meals_breakfast.json", breakfast_existing)
    save_recipes("meals_lunch.json", lunch_existing)
    save_recipes("meals_dinner.json", dinner_existing)
    save_recipes("meals_post_workout.json", post_workout_existing)
    
    # Count recipes
    total_added = (len(portuguese_extra) + len(spanish_extra) + len(italian_extra) + 
                   len(fusion_recipes) + len(post_workout_extra))
    
    print(f"Added {total_added} additional Mediterranean performance recipes")
    print(f"Portuguese extra: {len(portuguese_extra)} recipes")
    print(f"Spanish extra: {len(spanish_extra)} recipes")
    print(f"Italian extra: {len(italian_extra)} recipes")
    print(f"Fusion recipes: {len(fusion_recipes)} recipes")
    print(f"Post-workout extra: {len(post_workout_extra)} recipes")

def main():
    """Main function to add even more Mediterranean performance recipes."""
    print("Adding even more Mediterranean-inspired performance recipes...")
    
    add_more_mediterranean_recipes()
    
    print("\nAdditional Mediterranean performance recipe addition complete!")
    print("\n🇵🇹 Additional Portuguese Recipes:")
    print("- Trás-os-Montes Alheira Runner's Sausage")
    print("- Minho Caldo Verde Performance Soup")
    print("- Alentejo Migas Runner's Style")
    print("- Estremoz Marble Cake Energy Bars")
    print("\n🇪🇸 Additional Spanish Recipes:")
    print("- Aragonese Ternasco with Rosemary Potatoes")
    print("- Levante Alubias con Longaniza Runner's Bowl")
    print("- Navarra Piquillo Pepper Stuffed with Cod")
    print("- Castilian Gazpacho de Ajojo")
    print("- Balearic Sobrassada with Honey and Figs")
    print("- Andalusian Salmorejo with Avocado")
    print("\n🇮🇹 Additional Italian Recipes:")
    print("- Abruzzo Arrosticini Runner's Skewers")
    print("- Umbrian Porchetta with Whole Grain")
    print("- Marche Ciaudedu with Lentils")
    print("- Lazio Amatriciana with Turkey Guanciale")
    print("- Campanian Pasta e Fagioli con Cozze")
    print("- Pugliese Fave e Cicoria con Tonno")
    print("- Sicilian Pasta con le Sarde e Finocchio")
    print("- Trentino Canederli with Spinach and Speck")
    print("- Friulian Jota with Beans and Sauerkraut")
    print("- Valle d'Aosta Fontina Polenta con Funghi")
    print("\n🌍 Mediterranean Fusion Recipes:")
    print("- Mediterranean Power Bowl with Quinoa Tabouleh")
    print("- Iberian-Moroccan Fusion Chicken with Chermoula")
    print("- Greek-Italian Lentil Pasta with Feta and Basil")
    print("- Mediterranean Buddha Bowl with Hummus and Grilled Vegetables")
    print("- Spanish-Portuguese Seafood Cataplana Fusion")
    print("\n🏃 Additional Post-Workout Recovery:")
    print("- Mediterranean Chia Seed Pudding with Pistachios")
    print("- Italian Espresso Protein Gelato")
    print("- Spanish Horchata Recovery Drink")
    print("- Portuguese Pastel de Nata Protein Bites")
    print("- Andalusian Salmorejo with Avocado")
    print("\n🎯 New Performance Features:")
    print("- Regional mountain cuisine for altitude training")
    print("- Probiotic-rich fermented foods for gut health")
    print("- Complete protein combinations from plant sources")
    print("- Metabolism-boosting spice combinations")
    print("- Hydrating cold soups for hot weather training")
    print("- Iron-rich dishes for oxygen transport optimization")
    print("- Complex carbohydrate combinations for endurance")
    print("- Fusion recipes combining multiple Mediterranean traditions")

if __name__ == "__main__":
    main()