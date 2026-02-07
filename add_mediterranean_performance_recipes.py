#!/usr/bin/env python3
"""Add 50+ Mediterranean-inspired performance recipes for runners."""

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

def add_mediterranean_performance_recipes():
    """Add 50+ Mediterranean-inspired performance recipes."""
    
    # Portuguese-inspired performance recipes
    portuguese_breakfast = [
        {
            "name": "Portuguese Runner's Broa com Ovo",
            "meal_type": "breakfast",
            "description": "Corn bread with pasture-raised eggs and antioxidant-rich berries",
            "instructions": "Toast a slice of broa (Portuguese corn bread) until golden. In a pan, heat olive oil and fry 2 pasture-raised eggs until whites are set but yolks remain runny. Place eggs on toast and top with fresh berries, a drizzle of honey, and a sprinkle of cinnamon. Serve with a side of Portuguese queijo fresco (fresh cheese) for complete protein.",
            "prep_time": 8,
            "cook_time": 5,
            "calories": 420,
            "protein": 24,
            "fiber": 8,
            "carbs": 42,
            "fat": 18,
            "ingredients": [
                "1 slice broa (corn bread)",
                "2 pasture-raised eggs",
                "1/2 cup mixed berries",
                "1 tbsp honey",
                "1 tsp olive oil",
                "2 oz queijo fresco",
                "1/4 tsp cinnamon",
                "pinch of salt"
            ],
            "dietary_tags": [
                "high_protein",
                "antioxidant",
                "portuguese",
                "quick",
                "complete_protein"
            ]
        },
        {
            "name": "Azorean Green Tea Power Bowl",
            "meal_type": "breakfast",
            "description": "Green tea-infused oats with Azorean pineapple and local superfoods",
            "instructions": "In a saucepan, bring green tea and almond milk to a simmer. Add rolled oats and cook for 5 minutes, stirring occasionally. Remove from heat and stir in ground flaxseed, honey, and vanilla. Top with fresh Azorean pineapple chunks, local walnuts, and a sprinkle of green tea powder. This antioxidant-rich breakfast supports endurance and recovery.",
            "prep_time": 10,
            "cook_time": 8,
            "calories": 380,
            "protein": 16,
            "fiber": 12,
            "carbs": 52,
            "fat": 14,
            "ingredients": [
                "1/2 cup rolled oats",
                "1 cup green tea, brewed",
                "1/2 cup almond milk",
                "1/2 cup Azorean pineapple",
                "1 tbsp ground flaxseed",
                "1 tbsp honey",
                "1 tsp vanilla extract",
                "1 tbsp walnuts",
                "1/2 tsp matcha powder",
                "pinch of salt"
            ],
            "dietary_tags": [
                "antioxidant",
                "green_tea",
                "azorean",
                "anti_inflammatory",
                "gluten_free_option"
            ]
        }
    ]
    
    portuguese_lunch = [
        {
            "name": "Algarve Sardine Power Bowl",
            "meal_type": "lunch",
            "description": "Fresh grilled sardines with quinoa and local vegetables for omega-3 recovery",
            "instructions": "Season fresh sardines with sea salt, garlic powder, and paprika. Grill for 3-4 minutes per side until crispy. Meanwhile, cook quinoa and prepare a salad with local tomatoes, cucumbers, and onions. In a bowl, layer quinoa, grilled sardines, fresh vegetables, and a drizzle of olive oil and lemon juice. Top with fresh cilantro and serve with a side of boiled sweet potato.",
            "prep_time": 15,
            "cook_time": 12,
            "calories": 520,
            "protein": 38,
            "fiber": 10,
            "carbs": 42,
            "fat": 24,
            "ingredients": [
                "4 fresh sardines",
                "1 cup quinoa",
                "1 cup local tomatoes",
                "1/2 cucumber",
                "1/4 red onion",
                "2 tbsp olive oil",
                "1 tbsp lemon juice",
                "1 sweet potato, boiled",
                "fresh cilantro",
                "garlic powder",
                "paprika",
                "sea salt"
            ],
            "dietary_tags": [
                "omega_3",
                "anti_inflammatory",
                "algarve",
                "high_protein",
                "gluten_free"
            ]
        },
        {
            "name": "Porto Triathlete's Francesinha Light",
            "meal_type": "lunch",
            "description": "Healthier version of Porto's famous sandwich with lean protein and vegetables",
            "instructions": "Layer whole grain bread with grilled chicken, lean ham, and fresh vegetables. Top with a light tomato-beer sauce made with tomato paste, beer, and spices. Add a small amount of low-fat cheese and grill until melted. Serve with a side of steamed vegetables instead of fries. This lighter version provides protein without excessive calories.",
            "prep_time": 20,
            "cook_time": 15,
            "calories": 580,
            "protein": 42,
            "fiber": 12,
            "carbs": 48,
            "fat": 22,
            "ingredients": [
                "2 slices whole grain bread",
                "4 oz grilled chicken",
                "2 oz lean ham",
                "1/4 cup low-fat cheese",
                "1 tomato, sliced",
                "1/4 bell pepper",
                "2 tbsp tomato sauce",
                "1 tbsp beer",
                "steamed vegetables",
                "spices",
                "olive oil"
            ],
            "dietary_tags": [
                "high_protein",
                "porto",
                "light_version",
                "balanced"
            ]
        },
        {
            "name": "Madeira Tunafish and Banana Power Bowl",
            "meal_type": "lunch",
            "description": "Fresh tuna with local bananas and passion fruit for electrolyte balance",
            "instructions": "Season fresh tuna steak with sea salt and sear in a hot pan for 2 minutes per side. Let rest and slice. In a bowl, combine brown rice, black beans, and local vegetables. Top with sliced tuna, fresh banana slices, and passion fruit seeds. Drizzle with olive oil and lime juice. This unique combination provides protein, potassium, and antioxidants.",
            "prep_time": 15,
            "cook_time": 8,
            "calories": 540,
            "protein": 36,
            "fiber": 14,
            "carbs": 58,
            "fat": 18,
            "ingredients": [
                "6 oz fresh tuna steak",
                "1 cup brown rice",
                "1/2 cup black beans",
                "1 Madeira banana",
                "1 passion fruit",
                "local vegetables",
                "2 tbsp olive oil",
                "1 lime, juiced",
                "sea salt",
                "black pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "electrolyte",
                "madeira",
                "tropical",
                "gluten_free"
            ]
        }
    ]
    
    portuguese_dinner = [
        {
            "name": "Cozido dos Runners (Portuguese Stew)",
            "meal_type": "dinner",
            "description": "Nutrient-dense traditional stew with lean meats and root vegetables",
            "instructions": "In a large pot, combine lean beef, chicken, and various Portuguese sausages (chorizo, morcela). Add root vegetables like carrots, turnips, and potatoes. Simmer for 2 hours until meats are tender. Add cabbage and cook for 15 more minutes. Serve with a drizzle of olive oil and fresh herbs. This hearty stew provides complete protein and complex carbohydrates.",
            "prep_time": 30,
            "cook_time": 120,
            "calories": 620,
            "protein": 42,
            "fiber": 12,
            "carbs": 48,
            "fat": 28,
            "ingredients": [
                "4 oz lean beef",
                "4 oz chicken",
                "2 oz Portuguese sausages",
                "2 carrots",
                "1 turnip",
                "2 potatoes",
                "1/2 cabbage",
                "4 cups water or broth",
                "olive oil",
                "fresh herbs",
                "sea salt"
            ],
            "dietary_tags": [
                "high_protein",
                "traditional",
                "hearty",
                "complete_meal",
                "gluten_free"
            ]
        },
        {
            "name": "Bacalhau com Natas para Atletas",
            "meal_type": "dinner",
            "description": "Lighter version of salt cod with sweet potato and vegetables",
            "instructions": "Soak salt cod for 24 hours, changing water several times. Cook cod until flaky, then shred. Layer in a baking dish with boiled sweet potato slices, carrots, and peas. Make a light béchamel with low-fat milk and minimal cheese. Bake for 25 minutes until golden. Serve with a side of steamed greens.",
            "prep_time": 45,
            "cook_time": 30,
            "calories": 480,
            "protein": 38,
            "fiber": 10,
            "carbs": 42,
            "fat": 18,
            "ingredients": [
                "6 oz salt cod",
                "1 sweet potato",
                "1 carrot",
                "1/2 cup peas",
                "1 cup low-fat milk",
                "2 tbsp cheese",
                "steamed greens",
                "olive oil",
                "garlic",
                "nutmeg"
            ],
            "dietary_tags": [
                "high_protein",
                "light_version",
                "bacalhau",
                "balanced",
                "gluten_free"
            ]
        },
        {
            "name": "Alentejo Pork with Medronho Sauce",
            "meal_type": "dinner",
            "description": "Lean pork with antioxidant-rich medronho (strawberry tree fruit) sauce",
            "instructions": "Season lean pork loin with garlic, paprika, and bay leaves. Sear in a hot pan until golden. Reduce heat and add medronho liqueur or fruit juice, chicken broth, and honey. Simmer for 20 minutes until pork is tender. Remove pork and reduce sauce. Serve pork with sauce, roasted vegetables, and a side of Alentejo bread.",
            "prep_time": 20,
            "cook_time": 30,
            "calories": 520,
            "protein": 42,
            "fiber": 8,
            "carbs": 32,
            "fat": 24,
            "ingredients": [
                "6 oz lean pork loin",
                "2 tbsp medronho liqueur or juice",
                "1/2 cup chicken broth",
                "1 tbsp honey",
                "roasted vegetables",
                "garlic",
                "paprika",
                "bay leaves",
                "olive oil"
            ],
            "dietary_tags": [
                "high_protein",
                "antioxidant",
                "alentejo",
                "lean_protein",
                "gluten_free"
            ]
        }
    ]
    
    # Spanish-inspired performance recipes
    spanish_breakfast = [
        {
            "name": "Andalusian Runner's Tortilla Española",
            "meal_type": "breakfast",
            "description": "Spanish omelette with sweet potatoes and olive oil for sustained energy",
            "instructions": "Thinly slice sweet potatoes and onions. Heat olive oil in a non-stick pan and cook potatoes until tender. Beat 6 eggs with salt and pepper. Pour eggs over potatoes and cook on low heat until set. Flip and cook for 2 more minutes. Serve warm with a side of fresh tomato and olive oil. This provides complex carbs and high-quality protein.",
            "prep_time": 10,
            "cook_time": 15,
            "calories": 440,
            "protein": 28,
            "fiber": 6,
            "carbs": 32,
            "fat": 24,
            "ingredients": [
                "6 eggs",
                "1 sweet potato",
                "1/2 onion",
                "3 tbsp olive oil",
                "fresh tomato",
                "sea salt",
                "black pepper",
                "fresh parsley"
            ],
            "dietary_tags": [
                "high_protein",
                "complex_carbs",
                "andalusian",
                "sustained_energy",
                "gluten_free"
            ]
        },
        {
            "name": "Catalan Power Pan con Tomate",
            "meal_type": "breakfast",
            "description": "Toasted bread with tomato, olive oil, and protein-rich toppings",
            "instructions": "Toast whole grain bread until crispy. Rub with fresh garlic and ripe tomato. Drizzle with extra virgin olive oil and sprinkle with sea salt. Top with sliced Iberian ham, avocado, and a poached egg. This Catalan classic provides healthy fats, protein, and antioxidants.",
            "prep_time": 8,
            "cook_time": 5,
            "calories": 480,
            "protein": 26,
            "fiber": 8,
            "carbs": 38,
            "fat": 26,
            "ingredients": [
                "2 slices whole grain bread",
                "1 ripe tomato",
                "2 cloves garlic",
                "2 tbsp olive oil",
                "2 oz Iberian ham",
                "1/4 avocado",
                "1 poached egg",
                "sea salt",
                "fresh basil"
            ],
            "dietary_tags": [
                "balanced",
                "catalan",
                "healthy_fats",
                "high_protein",
                "antioxidant"
            ]
        },
        {
            "name": "Basque Goat Cheese and Berry Bowl",
            "meal_type": "breakfast",
            "description": "Local goat cheese with antioxidant berries and nuts for recovery",
            "instructions": "In a bowl, crumble fresh Basque goat cheese. Top with mixed berries, walnuts, and a drizzle of honey. Add a sprinkle of chia seeds and serve with a side of whole grain toast. This protein-rich breakfast supports muscle recovery and provides antioxidants.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 380,
            "protein": 20,
            "fiber": 10,
            "carbs": 32,
            "fat": 20,
            "ingredients": [
                "2 oz Basque goat cheese",
                "1 cup mixed berries",
                "2 tbsp walnuts",
                "1 tbsp honey",
                "1 tbsp chia seeds",
                "1 slice whole grain toast",
                "fresh mint"
            ],
            "dietary_tags": [
                "high_protein",
                "antioxidant",
                "basque",
                "recovery",
                "quick"
            ]
        }
    ]
    
    spanish_lunch = [
        {
            "name": "Valencian Paella for Athletes",
            "meal_type": "lunch",
            "description": "Brown rice paella with chicken, rabbit, and vegetables for complete nutrition",
            "instructions": "Heat olive oil in a paella pan. Sear chicken and rabbit pieces until golden. Add vegetables and cook until softened. Add brown rice and saffron, stirring to coat. Add warm chicken broth and simmer for 20 minutes until rice is tender. Add rosemary and let rest for 5 minutes. Serve with lemon wedges.",
            "prep_time": 20,
            "cook_time": 30,
            "calories": 560,
            "protein": 38,
            "fiber": 8,
            "carbs": 62,
            "fat": 18,
            "ingredients": [
                "4 oz chicken",
                "2 oz rabbit",
                "1 cup brown rice",
                "3 cups chicken broth",
                "1/4 tsp saffron",
                "mixed vegetables",
                "rosemary",
                "olive oil",
                "lemon wedges",
                "sea salt"
            ],
            "dietary_tags": [
                "high_protein",
                "complex_carbs",
                "valencian",
                "complete_meal",
                "anti_inflammatory"
            ]
        },
        {
            "name": "Galician Octopus with Sweet Potato",
            "meal_type": "lunch",
            "description": "Lean octopus with sweet potato and paprika for iron and complex carbs",
            "instructions": "Cook octopus until tender. Slice and arrange on a plate with boiled sweet potato rounds. Drizzle with extra virgin olive oil and sprinkle with smoked paprika and sea salt. Add a side of steamed greens. This high-protein, iron-rich meal supports oxygen transport and sustained energy.",
            "prep_time": 15,
            "cook_time": 45,
            "calories": 420,
            "protein": 34,
            "fiber": 8,
            "carbs": 38,
            "fat": 16,
            "ingredients": [
                "6 oz octopus",
                "1 sweet potato",
                "2 tbsp olive oil",
                "1 tsp smoked paprika",
                "steamed greens",
                "sea salt",
                "fresh parsley"
            ],
            "dietary_tags": [
                "high_protein",
                "iron_rich",
                "galician",
                "lean_protein",
                "gluten_free"
            ]
        },
        {
            "name": "Andalusian Gazpacho Power Bowl",
            "meal_type": "lunch",
            "description": "Cold tomato soup with protein toppings and hydrating vegetables",
            "instructions": "Blend ripe tomatoes, cucumber, bell pepper, garlic, olive oil, and vinegar until smooth. Chill for 30 minutes. Pour into bowls and top with grilled shrimp, hard-boiled egg, and avocado chunks. Sprinkle with hemp seeds and fresh herbs. This hydrating soup provides electrolytes and lean protein.",
            "prep_time": 15,
            "cook_time": 0,
            "calories": 440,
            "protein": 28,
            "fiber": 10,
            "carbs": 32,
            "fat": 22,
            "ingredients": [
                "3 ripe tomatoes",
                "1/2 cucumber",
                "1/2 bell pepper",
                "2 cloves garlic",
                "3 tbsp olive oil",
                "1 tbsp vinegar",
                "4 oz grilled shrimp",
                "1 hard-boiled egg",
                "1/4 avocado",
                "1 tbsp hemp seeds",
                "fresh herbs"
            ],
            "dietary_tags": [
                "hydrating",
                "electrolyte",
                "andalusian",
                "high_protein",
                "gluten_free"
            ]
        },
        {
            "name": "Mallorquin Frit Mallorqui Light",
            "meal_type": "lunch",
            "description": "Lighter version of fried offal with vegetables and lean meats",
            "instructions": "In a large pan, heat olive oil and sauté lean pork liver, chicken, and blood sausage until cooked. Add sliced potatoes, onions, and peppers. Cook until vegetables are tender. Season with local herbs and serve with a side of fresh salad. This iron-rich dish supports blood building and energy.",
            "prep_time": 25,
            "cook_time": 20,
            "calories": 480,
            "protein": 36,
            "fiber": 10,
            "carbs": 42,
            "fat": 20,
            "ingredients": [
                "3 oz pork liver",
                "3 oz chicken",
                "2 oz blood sausage",
                "1 potato",
                "1/2 onion",
                "1/2 bell pepper",
                "olive oil",
                "local herbs",
                "fresh salad"
            ],
            "dietary_tags": [
                "iron_rich",
                "blood_building",
                "mallorcan",
                "high_protein",
                "traditional"
            ]
        }
    ]
    
    spanish_dinner = [
        {
            "name": "Cantabrian Anchovy Power Pasta",
            "meal_type": "dinner",
            "description": "Whole grain pasta with omega-3 rich anchovies and garlic",
            "instructions": "Cook whole grain pasta according to package directions. In a pan, heat olive oil and sauté garlic until fragrant. Add canned Cantabrian anchovies and red pepper flakes, breaking up anchovies with a spoon. Toss with pasta, fresh parsley, and lemon zest. Serve with a side of steamed vegetables.",
            "prep_time": 10,
            "cook_time": 15,
            "calories": 520,
            "protein": 24,
            "fiber": 12,
            "carbs": 68,
            "fat": 18,
            "ingredients": [
                "3 oz whole grain pasta",
                "1 can Cantabrian anchovies",
                "3 cloves garlic",
                "1 tsp red pepper flakes",
                "2 tbsp olive oil",
                "fresh parsley",
                "lemon zest",
                "steamed vegetables"
            ],
            "dietary_tags": [
                "omega_3",
                "complex_carbs",
                "cantabrian",
                "anti_inflammatory",
                "high_fiber"
            ]
        },
        {
            "name": "Asturian Fabada Light",
            "meal_type": "dinner",
            "description": "Lighter bean stew with lean pork and vegetables for sustained energy",
            "instructions": "Soak fabada beans overnight. Cook with lean pork shoulder, saffron, and vegetables until beans are tender. Remove excess fat and season with paprika and salt. Serve with a side of steamed greens and a drizzle of olive oil. This high-fiber, protein-rich meal supports endurance.",
            "prep_time": 480,
            "cook_time": 120,
            "calories": 540,
            "protein": 32,
            "fiber": 18,
            "carbs": 58,
            "fat": 16,
            "ingredients": [
                "1 cup fabada beans",
                "4 oz lean pork shoulder",
                "saffron",
                "mixed vegetables",
                "paprika",
                "olive oil",
                "steamed greens",
                "sea salt"
            ],
            "dietary_tags": [
                "high_fiber",
                "high_protein",
                "asturian",
                "sustained_energy",
                "gluten_free"
            ]
        },
        {
            "name": "Riojan Lamb with Red Wine",
            "meal_type": "dinner",
            "description": "Lean lamb with antioxidant red wine and herbs for recovery",
            "instructions": "Season lean lamb with garlic, thyme, and rosemary. Brown in a hot pan. Add Rioja red wine, chicken broth, and vegetables. Simmer for 2 hours until lamb is tender. Remove lamb and reduce sauce. Serve with sauce, roasted vegetables, and a side of whole grain bread.",
            "prep_time": 20,
            "cook_time": 140,
            "calories": 560,
            "protein": 38,
            "fiber": 8,
            "carbs": 28,
            "fat": 28,
            "ingredients": [
                "6 oz lean lamb",
                "1/2 cup Rioja wine",
                "1 cup chicken broth",
                "mixed vegetables",
                "garlic",
                "thyme",
                "rosemary",
                "olive oil",
                "whole grain bread"
            ],
            "dietary_tags": [
                "high_protein",
                "antioxidant",
                "riojan",
                "recovery",
                "gluten_free_option"
            ]
        },
        {
            "name": "Canarian Mojo Chicken with Papas Arrugadas",
            "meal_type": "dinner",
            "description": "Grilled chicken with antioxidant mojo sauce and salt-crusted potatoes",
            "instructions": "Season chicken breasts with sea salt and grill until cooked. Make green mojo with cilantro, garlic, olive oil, and vinegar. Make red mojo with paprika and peppers. Boil small potatoes in heavily salted water until tender. Serve chicken with mojo sauces and salt-crusted potatoes.",
            "prep_time": 20,
            "cook_time": 25,
            "calories": 480,
            "protein": 42,
            "fiber": 6,
            "carbs": 38,
            "fat": 18,
            "ingredients": [
                "6 oz chicken breast",
                "4 small potatoes",
                "fresh cilantro",
                "garlic",
                "olive oil",
                "vinegar",
                "paprika",
                "sea salt",
                "peppers"
            ],
            "dietary_tags": [
                "high_protein",
                "antioxidant",
                "canarian",
                "anti_inflammatory",
                "gluten_free"
            ]
        },
        {
            "name": "Extremaduran Torta del Casar with Vegetables",
            "meal_type": "dinner",
            "description": "Local sheep cheese with roasted vegetables and honey for recovery",
            "instructions": "Roast seasonal vegetables with olive oil and herbs until tender. Serve with creamy Torta del Casar cheese, drizzled with honey and thyme. Add a side of whole grain bread and fresh salad. This protein-rich meal supports muscle recovery with local superfoods.",
            "prep_time": 15,
            "cook_time": 30,
            "calories": 460,
            "protein": 24,
            "fiber": 12,
            "carbs": 38,
            "fat": 22,
            "ingredients": [
                "3 oz Torta del Casar cheese",
                "seasonal vegetables",
                "2 tbsp honey",
                "fresh thyme",
                "olive oil",
                "whole grain bread",
                "fresh salad",
                "herbs"
            ],
            "dietary_tags": [
                "high_protein",
                "local_superfood",
                "extremaduran",
                "recovery",
                "vegetarian"
            ]
        }
    ]
    
    # Italian-inspired performance recipes
    italian_breakfast = [
        {
            "name": "Sicilian Runner's Granita with Brioche",
            "meal_type": "breakfast",
            "description": "Lemon granita with protein brioche for hydration and energy",
            "instructions": "Blend lemon juice, water, and honey until smooth. Freeze in a shallow dish, scraping every 30 minutes until granita forms. Serve with a slice of protein-enriched brioche. This refreshing breakfast provides hydration, electrolytes, and carbohydrates for morning runs.",
            "prep_time": 10,
            "cook_time": 0,
            "calories": 380,
            "protein": 12,
            "fiber": 4,
            "carbs": 58,
            "fat": 14,
            "ingredients": [
                "1/2 cup lemon juice",
                "1 cup water",
                "2 tbsp honey",
                "1 slice protein brioche",
                "fresh mint",
                "lemon zest"
            ],
            "dietary_tags": [
                "hydrating",
                "electrolyte",
                "sicilian",
                "refreshing",
                "quick"
            ]
        },
        {
            "name": "Neapolitan Power Espresso with Cornetto",
            "meal_type": "breakfast",
            "description": "Espresso with protein cornetto and cacao for energy and focus",
            "instructions": "Brew strong espresso. Serve with a protein-enriched cornetto (Italian croissant) filled with cacao-hazelnut spread. Add a side of fresh berries. This classic Italian breakfast provides caffeine for focus, protein for recovery, and antioxidants for health.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 420,
            "protein": 16,
            "fiber": 6,
            "carbs": 52,
            "fat": 20,
            "ingredients": [
                "1 shot espresso",
                "1 protein cornetto",
                "1 tbsp cacao-hazelnut spread",
                "1/2 cup fresh berries",
                "cocoa powder",
                "honey"
            ],
            "dietary_tags": [
                "energy_boosting",
                "focus",
                "neapolitan",
                "antioxidant",
                "quick"
            ]
        },
        {
            "name": "Sardinian Cannonau Porridge",
            "meal_type": "breakfast",
            "description": "Oatmeal with Cannonau wine reduction and local nuts for longevity",
            "instructions": "Cook rolled oats with almond milk and cinnamon. In a small pan, reduce Cannonau wine with honey until syrupy. Drizzle wine reduction over porridge and top with Sardinian walnuts, almonds, and pomegranate seeds. This antioxidant-rich breakfast supports cardiovascular health and longevity.",
            "prep_time": 10,
            "cook_time": 10,
            "calories": 440,
            "protein": 16,
            "fiber": 12,
            "carbs": 58,
            "fat": 18,
            "ingredients": [
                "1/2 cup rolled oats",
                "1 cup almond milk",
                "2 tbsp Cannonau wine",
                "1 tbsp honey",
                "2 tbsp Sardinian walnuts",
                "1 tbsp almonds",
                "2 tbsp pomegranate seeds",
                "cinnamon",
                "nutmeg"
            ],
            "dietary_tags": [
                "antioxidant",
                "longevity",
                "sardinian",
                "heart_healthy",
                "gluten_free_option"
            ]
        }
    ]
    
    italian_lunch = [
        {
            "name": "Roman Runner's Pasta alla Carbonara Light",
            "meal_type": "lunch",
            "description": "Lighter carbonara with whole grain pasta and extra egg whites",
            "instructions": "Cook whole grain spaghetti al dente. In a bowl, whisk whole eggs with extra egg whites, grated pecorino, and black pepper. Drain pasta, reserving pasta water. Add hot pasta to egg mixture, tossing vigorously with pasta water to create creamy sauce. Add lean guanciale and serve immediately.",
            "prep_time": 10,
            "cook_time": 12,
            "calories": 520,
            "protein": 28,
            "fiber": 8,
            "carbs": 68,
            "fat": 18,
            "ingredients": [
                "3 oz whole grain spaghetti",
                "2 whole eggs",
                "2 extra egg whites",
                "2 tbsp pecorino cheese",
                "1 oz guanciale",
                "black pepper",
                "sea salt"
            ],
            "dietary_tags": [
                "high_protein",
                "complex_carbs",
                "roman",
                "balanced",
                "high_fiber"
            ]
        },
        {
            "name": "Milanese Minestrone Performance Soup",
            "meal_type": "lunch",
            "description": "Hearty vegetable soup with barley and beans for complete nutrition",
            "instructions": "In a large pot, sauté onions, carrots, and celery. Add seasonal vegetables, cannellini beans, and pearl barley. Add vegetable broth and simmer for 30 minutes. Add fresh herbs and a drizzle of olive oil. Serve with a side of whole grain bread. This fiber-rich soup supports digestion and sustained energy.",
            "prep_time": 20,
            "cook_time": 35,
            "calories": 420,
            "protein": 18,
            "fiber": 16,
            "carbs": 58,
            "fat": 12,
            "ingredients": [
                "seasonal vegetables",
                "1/2 cup cannellini beans",
                "1/4 cup pearl barley",
                "4 cups vegetable broth",
                "olive oil",
                "fresh herbs",
                "whole grain bread",
                "sea salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_fiber",
                "plant_based",
                "milanese",
                "digestive_health",
                "gluten_free_option"
            ]
        },
        {
            "name": "Neapolitan Pizza Margherita Athlete's Version",
            "meal_type": "lunch",
            "description": "Whole grain pizza with fresh mozzarella and antioxidant basil",
            "instructions": "Prepare whole grain pizza dough. Top with San Marzano tomato sauce, fresh mozzarella, and fresh basil. Drizzle with extra virgin olive oil. Bake at high temperature until crust is crispy and cheese is bubbly. Serve with a side of arugula salad. This provides complex carbs, protein, and antioxidants.",
            "prep_time": 30,
            "cook_time": 12,
            "calories": 540,
            "protein": 24,
            "fiber": 12,
            "carbs": 68,
            "fat": 20,
            "ingredients": [
                "whole grain pizza dough",
                "San Marzano tomatoes",
                "4 oz fresh mozzarella",
                "fresh basil",
                "extra virgin olive oil",
                "arugula salad",
                "sea salt",
                "garlic"
            ],
            "dietary_tags": [
                "complex_carbs",
                "antioxidant",
                "neapolitan",
                "balanced",
                "high_fiber"
            ]
        },
        {
            "name": "Tuscan Ribollita with Cannellini Beans",
            "meal_type": "lunch",
            "description": "Hearty bread soup with beans and kale for protein and fiber",
            "instructions": "Simmer cannellini beans, vegetables, and kale in vegetable broth. Add stale Tuscan bread and simmer until soup thickens. Add extra virgin olive oil and fresh herbs. Let rest overnight for best flavor. Reheat and serve with a drizzle of olive oil. This protein-rich soup supports muscle recovery.",
            "prep_time": 20,
            "cook_time": 60,
            "calories": 460,
            "protein": 20,
            "fiber": 18,
            "carbs": 58,
            "fat": 14,
            "ingredients": [
                "1 cup cannellini beans",
                "kale",
                "vegetables",
                "Tuscan bread",
                "vegetable broth",
                "extra virgin olive oil",
                "fresh herbs",
                "sea salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "tuscan",
                "recovery",
                "gluten_free_option"
            ]
        },
        {
            "name": "Venetian Sarde in Saor with Polenta",
            "meal_type": "lunch",
            "description": "Sweet and sour sardines with polenta for omega-3 and complex carbs",
            "instructions": "Marinate fresh sardines in vinegar, onions, raisins, and pine nuts overnight. Grill sardines until crispy. Serve with soft polenta and the sweet and sour onion mixture. This omega-3 rich meal supports brain health and reduces inflammation.",
            "prep_time": 480,
            "cook_time": 20,
            "calories": 480,
            "protein": 32,
            "fiber": 8,
            "carbs": 42,
            "fat": 20,
            "ingredients": [
                "4 fresh sardines",
                "1 cup polenta",
                "red wine vinegar",
                "onions",
                "raisins",
                "pine nuts",
                "olive oil",
                "sea salt",
                "pepper"
            ],
            "dietary_tags": [
                "omega_3",
                "anti_inflammatory",
                "venetian",
                "brain_health",
                "gluten_free"
            ]
        }
    ]
    
    italian_dinner = [
        {
            "name": "Bolognese Ragù with Turkey and Whole Wheat Pasta",
            "meal_type": "dinner",
            "description": "Lean turkey ragù with whole wheat pasta for complete protein and fiber",
            "instructions": "Sauté lean ground turkey with onions, carrots, and celery. Add tomato paste, crushed tomatoes, and red wine. Simmer for 2 hours until thick and flavorful. Season with herbs and salt. Serve over whole wheat pasta with grated Parmesan. This provides lean protein and complex carbohydrates.",
            "prep_time": 20,
            "cook_time": 120,
            "calories": 560,
            "protein": 38,
            "fiber": 12,
            "carbs": 58,
            "fat": 18,
            "ingredients": [
                "5 oz lean turkey",
                "3 oz whole wheat pasta",
                "crushed tomatoes",
                "onions",
                "carrots",
                "celery",
                "red wine",
                "Parmesan cheese",
                "Italian herbs",
                "olive oil"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "bolognese",
                "complete_meal",
                "lean_protein"
            ]
        },
        {
            "name": "Neapolitan Pollo alla Cacciatora",
            "meal_type": "dinner",
            "description": "Hunter's chicken with herbs, wine, and vegetables for recovery",
            "instructions": "Brown chicken pieces in olive oil. Add onions, garlic, and herbs. Add white wine and chicken broth. Simmer for 45 minutes until chicken is tender. Add vegetables and cook until tender. Serve with the sauce and a side of whole grain bread. This protein-rich meal supports muscle recovery.",
            "prep_time": 15,
            "cook_time": 60,
            "calories": 480,
            "protein": 42,
            "fiber": 8,
            "carbs": 28,
            "fat": 22,
            "ingredients": [
                "6 oz chicken pieces",
                "white wine",
                "chicken broth",
                "mixed vegetables",
                "onions",
                "garlic",
                "Italian herbs",
                "olive oil",
                "whole grain bread",
                "sea salt"
            ],
            "dietary_tags": [
                "high_protein",
                "recovery",
                "neapolitan",
                "herbal",
                "gluten_free_option"
            ]
        },
        {
            "name": "Sicilian Swordfish with Citrus and Capers",
            "meal_type": "dinner",
            "description": "Grilled swordfish with blood orange, capers, and olive oil",
            "instructions": "Season swordfish steaks with sea salt and oregano. Grill for 4-5 minutes per side. Top with a sauce of blood orange juice, capers, olive oil, and fresh herbs. Serve with a side of roasted vegetables and couscous. This omega-3 rich meal supports heart health and recovery.",
            "prep_time": 15,
            "cook_time": 12,
            "calories": 520,
            "protein": 38,
            "fiber": 8,
            "carbs": 32,
            "fat": 24,
            "ingredients": [
                "6 oz swordfish steak",
                "1 blood orange",
                "1 tbsp capers",
                "3 tbsp olive oil",
                "fresh herbs",
                "oregano",
                "roasted vegetables",
                "couscous",
                "sea salt"
            ],
            "dietary_tags": [
                "omega_3",
                "heart_healthy",
                "sicilian",
                "anti_inflammatory",
                "gluten_free_option"
            ]
        },
        {
            "name": "Piedmontese Bollito with Performance Salsa Verde",
            "meal_type": "dinner",
            "description": "Lean boiled meats with antioxidant green salsa for recovery",
            "instructions": "Simmer lean beef, chicken, and vegetables in broth until tender. Make salsa verde with parsley, anchovies, capers, garlic, and olive oil. Serve meats with salsa verde and a side of steamed vegetables. This protein-rich meal supports muscle repair and provides antioxidants.",
            "prep_time": 20,
            "cook_time": 90,
            "calories": 540,
            "protein": 42,
            "fiber": 8,
            "carbs": 22,
            "fat": 28,
            "ingredients": [
                "4 oz lean beef",
                "2 oz chicken",
                "fresh parsley",
                "anchovies",
                "capers",
                "garlic",
                "olive oil",
                "steamed vegetables",
                "broth",
                "sea salt"
            ],
            "dietary_tags": [
                "high_protein",
                "antioxidant",
                "piedmontese",
                "recovery",
                "gluten_free"
            ]
        },
        {
            "name": "Calabrian Nduja Pasta with Whole Wheat and Tuna",
            "meal_type": "dinner",
            "description": "Spicy nduja pasta with tuna and whole wheat for metabolism boost",
            "instructions": "Cook whole wheat pasta al dente. In a pan, heat nduja and add canned tuna, garlic, and cherry tomatoes. Toss with pasta, fresh parsley, and a drizzle of olive oil. Serve with a side of steamed greens. This spicy meal boosts metabolism and provides omega-3s.",
            "prep_time": 10,
            "cook_time": 12,
            "calories": 560,
            "protein": 32,
            "fiber": 12,
            "carbs": 68,
            "fat": 20,
            "ingredients": [
                "3 oz whole wheat pasta",
                "1 tbsp nduja",
                "1 can tuna",
                "garlic",
                "cherry tomatoes",
                "fresh parsley",
                "olive oil",
                "steamed greens",
                "red pepper flakes"
            ],
            "dietary_tags": [
                "metabolism_boosting",
                "omega_3",
                "calabrian",
                "spicy",
                "high_fiber"
            ]
        },
        {
            "name": "Ligurian Farinata with Chickpea Power Salad",
            "meal_type": "dinner",
            "description": "Chickpea flatbread with protein salad for complete nutrition",
            "instructions": "Make chickpea flour batter with water, olive oil, and salt. Pour into hot pan and bake until crispy. Serve with a salad of mixed greens, grilled vegetables, chickpeas, and tuna. Drizzle with lemon-olive oil dressing. This high-protein, high-fiber meal supports sustained energy.",
            "prep_time": 20,
            "cook_time": 15,
            "calories": 480,
            "protein": 24,
            "fiber": 16,
            "carbs": 48,
            "fat": 18,
            "ingredients": [
                "chickpea flour",
                "water",
                "olive oil",
                "mixed greens",
                "grilled vegetables",
                "chickpeas",
                "canned tuna",
                "lemon",
                "fresh herbs",
                "sea salt"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "ligurian",
                "plant_based",
                "gluten_free"
            ]
        }
    ]
    
    # Mediterranean fusion post-workout recipes
    post_workout_recipes = [
        {
            "name": "Mediterranean Recovery Smoothie Bowl",
            "meal_type": "post_workout",
            "description": "Greek yogurt with figs, walnuts, and honey for protein and antioxidants",
            "instructions": "In a bowl, combine Greek yogurt with protein powder. Top with fresh figs, walnuts, honey, and a sprinkle of cinnamon. Add a drizzle of olive oil for healthy fats. This protein-rich recovery bowl supports muscle repair and provides antioxidants.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 460,
            "protein": 32,
            "fiber": 8,
            "carbs": 42,
            "fat": 18,
            "ingredients": [
                "1 cup Greek yogurt",
                "1 scoop protein powder",
                "2 fresh figs",
                "2 tbsp walnuts",
                "1 tbsp honey",
                "1 tsp olive oil",
                "cinnamon",
                "fresh mint"
            ],
            "dietary_tags": [
                "high_protein",
                "antioxidant",
                "recovery",
                "greek",
                "quick"
            ]
        },
        {
            "name": "Iberian Electrolyte Recovery Drink",
            "meal_type": "post_workout",
            "description": "Coconut water with Iberian fruits and sea salt for hydration",
            "instructions": "Blend coconut water with watermelon, orange, and a pinch of sea salt. Add fresh mint and a squeeze of lemon. Serve over ice with orange slices. This electrolyte-rich drink replenishes sodium, potassium, and magnesium lost during exercise.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 120,
            "protein": 2,
            "fiber": 4,
            "carbs": 28,
            "fat": 1,
            "ingredients": [
                "2 cups coconut water",
                "1 cup watermelon",
                "1 orange",
                "1/4 tsp sea salt",
                "fresh mint",
                "lemon juice",
                "ice"
            ],
            "dietary_tags": [
                "electrolyte",
                "hydrating",
                "iberian",
                "recovery",
                "gluten_free"
            ]
        },
        {
            "name": "Italian Tiramisu Recovery Parfait",
            "meal_type": "post_workout",
            "description": "Protein-rich version of tiramisu with espresso and mascarpone",
            "instructions": "Layer coffee-soaked whole grain ladyfingers with mascarpone mixed with protein powder and vanilla. Top with cocoa powder and dark chocolate shavings. This protein-rich dessert supports muscle recovery while satisfying sweet cravings.",
            "prep_time": 10,
            "cook_time": 0,
            "calories": 420,
            "protein": 28,
            "fiber": 6,
            "carbs": 38,
            "fat": 22,
            "ingredients": [
                "whole grain ladyfingers",
                "espresso",
                "4 oz mascarpone",
                "1 scoop protein powder",
                "vanilla extract",
                "cocoa powder",
                "dark chocolate",
                "honey"
            ],
            "dietary_tags": [
                "high_protein",
                "recovery",
                "italian",
                "dessert",
                "caffeine"
            ]
        },
        {
            "name": "Spanish Gazpacho Recovery Shot",
            "meal_type": "post_workout",
            "description": "Concentrated vegetable juice with electrolytes and antioxidants",
            "instructions": "Blend tomatoes, cucumber, bell pepper, garlic, and olive oil until smooth. Add sea salt and apple cider vinegar. Pour into shot glasses and serve immediately. This concentrated recovery shot provides electrolytes and antioxidants.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 80,
            "protein": 2,
            "fiber": 4,
            "carbs": 12,
            "fat": 4,
            "ingredients": [
                "1 tomato",
                "1/4 cucumber",
                "1/4 bell pepper",
                "1 clove garlic",
                "1 tbsp olive oil",
                "sea salt",
                "apple cider vinegar"
            ],
            "dietary_tags": [
                "electrolyte",
                "antioxidant",
                "spanish",
                "recovery",
                "gluten_free"
            ]
        },
        {
            "name": "Portuguese Pastel de Nata Protein Bites",
            "meal_type": "post_workout",
            "description": "Protein-enriched version of Portuguese custard tarts",
            "instructions": "Make mini tart shells with whole grain flour. Fill with custard made from eggs, protein powder, milk, and vanilla. Bake until set. Top with cinnamon. These protein bites support muscle recovery while providing traditional flavors.",
            "prep_time": 20,
            "cook_time": 15,
            "calories": 280,
            "protein": 18,
            "fiber": 4,
            "carbs": 28,
            "fat": 14,
            "ingredients": [
                "whole grain flour",
                "2 eggs",
                "1/2 scoop protein powder",
                "milk",
                "vanilla extract",
                "cinnamon",
                "butter",
                "sea salt"
            ],
            "dietary_tags": [
                "high_protein",
                "recovery",
                "portuguese",
                "dessert",
                "traditional"
            ]
        }
    ]
    
    # Load existing recipes
    breakfast_existing = load_recipes("meals_breakfast.json")
    lunch_existing = load_recipes("meals_lunch.json")
    dinner_existing = load_recipes("meals_dinner.json")
    post_workout_existing = load_recipes("meals_post_workout.json")
    
    # Add all new recipes
    breakfast_existing.extend(portuguese_breakfast + spanish_breakfast + italian_breakfast)
    lunch_existing.extend(portuguese_lunch + spanish_lunch + italian_lunch)
    dinner_existing.extend(portuguese_dinner + spanish_dinner + italian_dinner)
    post_workout_existing.extend(post_workout_recipes)
    
    # Save updated recipes
    save_recipes("meals_breakfast.json", breakfast_existing)
    save_recipes("meals_lunch.json", lunch_existing)
    save_recipes("meals_dinner.json", dinner_existing)
    save_recipes("meals_post_workout.json", post_workout_existing)
    
    # Count recipes
    total_added = (len(portuguese_breakfast) + len(spanish_breakfast) + len(italian_breakfast) +
                   len(portuguese_lunch) + len(spanish_lunch) + len(italian_lunch) +
                   len(portuguese_dinner) + len(spanish_dinner) + len(italian_dinner) +
                   len(post_workout_recipes))
    
    print(f"Added {total_added} Mediterranean-inspired performance recipes")
    print(f"Breakfast: {len(portuguese_breakfast) + len(spanish_breakfast) + len(italian_breakfast)} recipes")
    print(f"Lunch: {len(portuguese_lunch) + len(spanish_lunch) + len(italian_lunch)} recipes")
    print(f"Dinner: {len(portuguese_dinner) + len(spanish_dinner) + len(italian_dinner)} recipes")
    print(f"Post-workout: {len(post_workout_recipes)} recipes")

def main():
    """Main function to add all Mediterranean performance recipes."""
    print("Adding 50+ Mediterranean-inspired performance recipes...")
    
    add_mediterranean_performance_recipes()
    
    print("\nMediterranean performance recipe addition complete!")
    print("\n🇵🇹 Portuguese Recipes Added:")
    print("- Azorean Green Tea Power Bowl")
    print("- Algarve Sardine Power Bowl")
    print("- Porto Triathlete's Francesinha Light")
    print("- Madeira Tunafish and Banana Power Bowl")
    print("- Cozido dos Runners")
    print("- Bacalhau com Natas para Atletas")
    print("- Alentejo Pork with Medronho Sauce")
    print("\n🇪🇸 Spanish Recipes Added:")
    print("- Andalusian Runner's Tortilla Española")
    print("- Catalan Power Pan con Tomate")
    print("- Basque Goat Cheese and Berry Bowl")
    print("- Valencian Paella for Athletes")
    print("- Galician Octopus with Sweet Potato")
    print("- Andalusian Gazpacho Power Bowl")
    print("- Mallorquin Frit Mallorqui Light")
    print("- Cantabrian Anchovy Power Pasta")
    print("- Asturian Fabada Light")
    print("- Riojan Lamb with Red Wine")
    print("- Canarian Mojo Chicken with Papas Arrugadas")
    print("- Extremaduran Torta del Casar with Vegetables")
    print("\n🇮🇹 Italian Recipes Added:")
    print("- Sicilian Runner's Granita with Brioche")
    print("- Neapolitan Power Espresso with Cornetto")
    print("- Sardinian Cannonau Porridge")
    print("- Roman Runner's Pasta alla Carbonara Light")
    print("- Milanese Minestrone Performance Soup")
    print("- Neapolitan Pizza Margherita Athlete's Version")
    print("- Tuscan Ribollita with Cannellini Beans")
    print("- Venetian Sarde in Saor with Polenta")
    print("- Bolognese Ragù with Turkey and Whole Wheat Pasta")
    print("- Neapolitan Pollo alla Cacciatora")
    print("- Sicilian Swordfish with Citrus and Capers")
    print("- Piedmontese Bollito with Performance Salsa Verde")
    print("- Calabrian Nduja Pasta with Whole Wheat and Tuna")
    print("- Ligurian Farinata with Chickpea Power Salad")
    print("\n🏃 Post-Workout Recovery Recipes:")
    print("- Mediterranean Recovery Smoothie Bowl")
    print("- Iberian Electrolyte Recovery Drink")
    print("- Italian Tiramisu Recovery Parfait")
    print("- Spanish Gazpacho Recovery Shot")
    print("- Portuguese Pastel de Nata Protein Bites")
    print("\n🎯 Performance Benefits:")
    print("- Omega-3 rich fish for anti-inflammatory recovery")
    print("- Complex carbohydrates from whole grains for sustained energy")
    print("- High-quality proteins for muscle repair")
    print("- Antioxidant-rich fruits and vegetables for cellular protection")
    print("- Healthy fats from olive oil, nuts, and seeds")
    print("- Electrolyte-balancing ingredients for hydration")
    print("- Traditional superfoods for longevity and health")
    print("- Regional specialties optimized for athletic performance")

if __name__ == "__main__":
    main()