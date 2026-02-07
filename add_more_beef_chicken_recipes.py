#!/usr/bin/env python3
"""Add more ground beef and chicken recipes to the meal database."""

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

def add_ground_beef_recipes():
    """Add new ground beef recipes to lunch and dinner files."""
    
    # New ground beef recipes for lunch
    lunch_beef_recipes = [
        {
            "name": "Mexican Ground Beef Bowl",
            "meal_type": "lunch",
            "description": "Seasoned ground beef with Mexican toppings over rice",
            "instructions": "Heat a large skillet over medium-high heat. Add ground beef, breaking it up with a spoon. Cook until browned (6-8 minutes). Add taco seasoning and 1/4 cup water, simmer until thickened. In bowls, layer rice, ground beef, black beans, corn, salsa, avocado, and cheese. Top with sour cream and cilantro.",
            "prep_time": 15,
            "cook_time": 15,
            "calories": 580,
            "protein": 36,
            "fiber": 12,
            "carbs": 52,
            "fat": 24,
            "ingredients": [
                "5 oz ground beef",
                "1 cup cooked rice",
                "1/2 cup black beans",
                "1/4 cup corn",
                "1/4 cup salsa",
                "1/4 avocado",
                "2 tbsp cheese",
                "2 tbsp sour cream",
                "taco seasoning",
                "cilantro"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "quick"
            ]
        },
        {
            "name": "Italian Ground Beef Pasta",
            "meal_type": "lunch",
            "description": "Rich ground beef meat sauce with pasta",
            "instructions": "Cook pasta according to package directions. Heat olive oil in a pan, add diced onion and cook until soft. Add ground beef and cook until browned. Add garlic, tomato sauce, Italian herbs, and simmer for 15 minutes. Toss with pasta and top with parmesan.",
            "prep_time": 10,
            "cook_time": 20,
            "calories": 620,
            "protein": 34,
            "fiber": 8,
            "carbs": 68,
            "fat": 22,
            "ingredients": [
                "5 oz ground beef",
                "3 oz pasta",
                "1/2 cup tomato sauce",
                "1/4 cup onion",
                "2 cloves garlic",
                "2 tbsp parmesan",
                "1 tbsp olive oil",
                "Italian herbs"
            ],
            "dietary_tags": [
                "high_protein",
                "high_carb"
            ]
        },
        {
            "name": "Ground Beef Lettuce Wraps",
            "meal_type": "lunch",
            "description": "Asian-inspired ground beef in crisp lettuce cups",
            "instructions": "Heat a wok or large skillet over high heat. Add ground beef, breaking it up and cooking until browned. Add garlic, ginger, and soy sauce. Add water chestnuts and green onions. Spoon into lettuce cups and top with sesame seeds.",
            "prep_time": 15,
            "cook_time": 10,
            "calories": 420,
            "protein": 32,
            "fiber": 6,
            "carbs": 18,
            "fat": 24,
            "ingredients": [
                "5 oz ground beef",
                "4 large lettuce leaves",
                "1/4 cup water chestnuts",
                "2 green onions",
                "2 cloves garlic",
                "1 inch ginger",
                "2 tbsp soy sauce",
                "1 tsp sesame seeds"
            ],
            "dietary_tags": [
                "high_protein",
                "low_carb",
                "quick",
                "gluten_free"
            ]
        },
        {
            "name": "Mediterranean Ground Beef Pitas",
            "meal_type": "lunch",
            "description": "Spiced ground beef in warm pitas with Mediterranean toppings",
            "instructions": "Heat olive oil in a skillet. Add ground beef, breaking it up and cooking until browned. Add cumin, coriander, cinnamon, and allspice. Stir in diced tomatoes and simmer for 5 minutes. Fill pitas with beef mixture and top with tzatziki, cucumber, tomatoes, and feta.",
            "prep_time": 15,
            "cook_time": 12,
            "calories": 520,
            "protein": 34,
            "fiber": 8,
            "carbs": 42,
            "fat": 26,
            "ingredients": [
                "5 oz ground beef",
                "2 whole wheat pitas",
                "1/4 cup tzatziki",
                "1/4 cup cucumber, diced",
                "1/4 cup tomatoes, diced",
                "2 tbsp feta cheese",
                "1 tsp cumin",
                "1/2 tsp coriander",
                "1/4 tsp cinnamon",
                "1/8 tsp allspice"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "mediterranean"
            ]
        }
    ]
    
    # New ground beef recipes for dinner
    dinner_beef_recipes = [
        {
            "name": "Classic Cheeseburgers",
            "meal_type": "dinner",
            "description": "Juicy homemade cheeseburgers with all the fixings",
            "instructions": "Form ground beef into 4 patties, season with salt and pepper. Grill or pan-fry for 4-5 minutes per side until internal temperature reaches 160°F. Top with cheese in the last minute of cooking. Serve on buns with lettuce, tomato, onion, pickles, and your favorite condiments.",
            "prep_time": 15,
            "cook_time": 10,
            "calories": 680,
            "protein": 38,
            "fiber": 4,
            "carbs": 42,
            "fat": 38,
            "ingredients": [
                "6 oz ground beef (85/15)",
                "1 whole wheat bun",
                "2 slices cheese",
                "lettuce",
                "tomato",
                "onion",
                "pickles",
                "ketchup",
                "mustard"
            ],
            "dietary_tags": [
                "high_protein",
                "quick"
            ]
        },
        {
            "name": "Stuffed Bell Peppers with Ground Beef",
            "meal_type": "dinner",
            "description": "Bell peppers stuffed with seasoned ground beef and rice",
            "instructions": "Preheat oven to 375°F. Cut tops off bell peppers and remove seeds. Brown ground beef with onion and garlic. Stir in cooked rice, tomato sauce, and seasonings. Stuff peppers with beef mixture. Bake for 25-30 minutes until peppers are tender. Top with cheese and bake until melted.",
            "prep_time": 20,
            "cook_time": 35,
            "calories": 540,
            "protein": 32,
            "fiber": 10,
            "carbs": 38,
            "fat": 28,
            "ingredients": [
                "5 oz ground beef",
                "2 large bell peppers",
                "1/2 cup cooked rice",
                "1/4 cup tomato sauce",
                "1/4 cup onion, diced",
                "2 cloves garlic, minced",
                "1/4 cup cheese",
                "1 tsp Italian seasoning"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber"
            ]
        },
        {
            "name": "Ground Beef Tacos",
            "meal_type": "dinner",
            "description": "Seasoned ground beef tacos with fresh toppings",
            "instructions": "Heat a large skillet over medium-high heat. Add ground beef, breaking it up and cooking until browned. Drain excess fat. Add taco seasoning and water, simmer until thickened. Warm tortillas and fill with beef mixture. Top with lettuce, cheese, tomatoes, sour cream, and salsa.",
            "prep_time": 15,
            "cook_time": 12,
            "calories": 560,
            "protein": 32,
            "fiber": 8,
            "carbs": 42,
            "fat": 30,
            "ingredients": [
                "5 oz ground beef",
                "3 corn tortillas",
                "1/4 cup cheese",
                "lettuce",
                "tomatoes",
                "sour cream",
                "salsa",
                "taco seasoning"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "quick"
            ]
        },
        {
            "name": "Korean Ground Beef and Rice",
            "meal_type": "dinner",
            "description": "Korean-style ground beef with vegetables over steamed rice",
            "instructions": "Heat a large skillet over medium-high heat with sesame oil. Add ground beef, breaking it up and cooking until browned. Add garlic, ginger, and soy sauce. Stir in gochujang and sugar. Add sliced vegetables and stir-fry until crisp-tender. Serve over steamed rice with a fried egg on top and sesame seeds.",
            "prep_time": 15,
            "cook_time": 15,
            "calories": 580,
            "protein": 34,
            "fiber": 8,
            "carbs": 58,
            "fat": 22,
            "ingredients": [
                "5 oz ground beef",
                "1 cup cooked rice",
                "1 cup mixed vegetables",
                "1 egg",
                "2 tbsp soy sauce",
                "1 tbsp gochujang",
                "1 tsp sesame oil",
                "2 cloves garlic, minced",
                "1 inch ginger, grated",
                "1 tsp sugar",
                "1 tsp sesame seeds"
            ],
            "dietary_tags": [
                "high_protein",
                "high_carb",
                "quick"
            ]
        },
        {
            "name": "Ground Beef and Potato Skillet",
            "meal_type": "dinner",
            "description": "Hearty one-pan skillet with ground beef, potatoes, and vegetables",
            "instructions": "Heat a large skillet over medium-high heat with olive oil. Add ground beef, breaking it up and cooking until browned. Remove beef and set aside. Add diced potatoes and cook until golden and tender. Add onions and bell peppers, cooking until softened. Return beef to pan, add garlic and herbs. Season with salt and pepper.",
            "prep_time": 15,
            "cook_time": 25,
            "calories": 560,
            "protein": 32,
            "fiber": 8,
            "carbs": 48,
            "fat": 28,
            "ingredients": [
                "5 oz ground beef",
                "1 potato, diced",
                "1/2 onion, diced",
                "1/2 bell pepper, diced",
                "2 cloves garlic, minced",
                "1 tsp dried herbs",
                "2 tbsp olive oil",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber"
            ]
        }
    ]
    
    # Load existing recipes
    lunch_recipes = load_recipes("meals_lunch.json")
    dinner_recipes = load_recipes("meals_dinner.json")
    
    # Add new recipes
    lunch_recipes.extend(lunch_beef_recipes)
    dinner_recipes.extend(dinner_beef_recipes)
    
    # Save updated recipes
    save_recipes("meals_lunch.json", lunch_recipes)
    save_recipes("meals_dinner.json", dinner_recipes)
    
    print(f"Added {len(lunch_beef_recipes)} ground beef recipes to lunch")
    print(f"Added {len(dinner_beef_recipes)} ground beef recipes to dinner")

def add_chicken_recipes():
    """Add new chicken recipes to lunch and dinner files."""
    
    # New chicken recipes for lunch
    lunch_chicken_recipes = [
        {
            "name": "Buffalo Chicken Wrap",
            "meal_type": "lunch",
            "description": "Spicy buffalo chicken in a whole wheat wrap with ranch",
            "instructions": "Heat a skillet over medium heat. Add cooked chicken and buffalo sauce, stirring until coated. Warm tortilla in microwave or dry pan. Spread ranch dressing on tortilla, add chicken, lettuce, tomatoes, and blue cheese if desired. Roll up tightly and serve.",
            "prep_time": 10,
            "cook_time": 8,
            "calories": 480,
            "protein": 36,
            "fiber": 6,
            "carbs": 38,
            "fat": 22,
            "ingredients": [
                "6 oz cooked chicken, shredded",
                "1 whole wheat tortilla",
                "2 tbsp buffalo sauce",
                "2 tbsp ranch dressing",
                "1 cup lettuce, shredded",
                "1/4 cup tomatoes, diced",
                "2 tbsp blue cheese (optional)"
            ],
            "dietary_tags": [
                "high_protein",
                "quick"
            ]
        },
        {
            "name": "Chicken Caesar Salad",
            "meal_type": "lunch",
            "description": "Classic Caesar salad with grilled chicken",
            "instructions": "Season chicken breast with salt, pepper, and garlic powder. Grill or pan-sear for 6-7 minutes per side until cooked through. Let rest for 5 minutes, then slice. Toss romaine lettuce with Caesar dressing, croutons, and parmesan. Top with sliced chicken.",
            "prep_time": 12,
            "cook_time": 15,
            "calories": 440,
            "protein": 38,
            "fiber": 6,
            "carbs": 18,
            "fat": 24,
            "ingredients": [
                "6 oz chicken breast",
                "3 cups romaine lettuce",
                "2 tbsp Caesar dressing",
                "1/4 cup parmesan cheese",
                "1/2 cup croutons",
                "1 tsp garlic powder",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "low_carb",
                "quick"
            ]
        },
        {
            "name": "Chicken and Hummus Wrap",
            "meal_type": "lunch",
            "description": "Mediterranean-inspired wrap with chicken and hummus",
            "instructions": "Warm tortilla in microwave or dry pan. Spread hummus evenly over tortilla. Layer with sliced chicken, spinach, cucumber, tomatoes, and red onion. Drizzle with lemon juice and olive oil. Roll up tightly and cut in half.",
            "prep_time": 10,
            "cook_time": 0,
            "calories": 460,
            "protein": 34,
            "fiber": 10,
            "carbs": 35,
            "fat": 20,
            "ingredients": [
                "6 oz cooked chicken, sliced",
                "1 whole wheat tortilla",
                "3 tbsp hummus",
                "1 cup spinach",
                "1/4 cup cucumber, sliced",
                "1/4 cup tomatoes, sliced",
                "2 tbsp red onion, sliced",
                "1 tbsp lemon juice",
                "1 tsp olive oil"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "mediterranean",
                "quick"
            ]
        },
        {
            "name": "Thai Chicken Peanut Noodles",
            "meal_type": "lunch",
            "description": "Cold noodles with chicken, peanut sauce, and fresh vegetables",
            "instructions": "Cook noodles according to package directions, rinse with cold water. In a large bowl, whisk together peanut butter, soy sauce, lime juice, honey, and ginger to make sauce. Add cooked noodles, sliced chicken, shredded carrots, bell peppers, and cilantro. Toss everything together until well coated.",
            "prep_time": 20,
            "cook_time": 12,
            "calories": 520,
            "protein": 32,
            "fiber": 8,
            "carbs": 58,
            "fat": 22,
            "ingredients": [
                "6 oz cooked chicken, sliced",
                "3 oz rice noodles",
                "3 tbsp peanut butter",
                "2 tbsp soy sauce",
                "1 tbsp lime juice",
                "1 tsp honey",
                "1 tsp ginger, grated",
                "1/2 cup carrots, shredded",
                "1/2 cup bell peppers, sliced",
                "2 tbsp cilantro, chopped"
            ],
            "dietary_tags": [
                "high_protein",
                "asian",
                "meal_prep"
            ]
        }
    ]
    
    # New chicken recipes for dinner
    dinner_chicken_recipes = [
        {
            "name": "Chicken Marsala",
            "meal_type": "dinner",
            "description": "Tender chicken in rich mushroom Marsala wine sauce",
            "instructions": "Pound chicken breasts to even thickness. Season with salt and pepper. Dredge in flour. Heat olive oil and butter in a large skillet over medium-high heat. Cook chicken for 4-5 minutes per side until golden. Remove chicken. Add mushrooms and cook until browned. Add Marsala wine and broth, simmer until reduced by half. Return chicken to pan and cook through.",
            "prep_time": 15,
            "cook_time": 20,
            "calories": 480,
            "protein": 42,
            "fiber": 4,
            "carbs": 18,
            "fat": 26,
            "ingredients": [
                "6 oz chicken breasts",
                "1 cup mushrooms, sliced",
                "1/4 cup Marsala wine",
                "1/2 cup chicken broth",
                "2 tbsp flour",
                "2 tbsp olive oil",
                "2 tbsp butter",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "low_carb"
            ]
        },
        {
            "name": "Honey Garlic Chicken",
            "meal_type": "dinner",
            "description": "Sweet and savory chicken with honey garlic glaze",
            "instructions": "Preheat oven to 400°F. Mix honey, soy sauce, garlic, and ginger for glaze. Place chicken in baking dish and brush with half the glaze. Bake for 20-25 minutes, brushing with remaining glaze halfway through. Internal temperature should reach 165°F. Let rest for 5 minutes before serving.",
            "prep_time": 10,
            "cook_time": 25,
            "calories": 420,
            "protein": 38,
            "fiber": 2,
            "carbs": 22,
            "fat": 20,
            "ingredients": [
                "6 oz chicken thighs",
                "3 tbsp honey",
                "3 tbsp soy sauce",
                "4 cloves garlic, minced",
                "1 inch ginger, grated",
                "1 tsp sesame oil",
                "sesame seeds",
                "green onions"
            ],
            "dietary_tags": [
                "high_protein",
                "gluten_free",
                "quick"
            ]
        },
        {
            "name": "Chicken Cacciatore",
            "meal_type": "dinner",
            "description": "Italian-style chicken with peppers, onions, and tomatoes",
            "instructions": "Season chicken with salt and pepper. Heat olive oil in a large pot over medium-high heat. Brown chicken on all sides, then remove. Add onions, bell peppers, and garlic, cooking until softened. Add tomatoes, wine, and herbs. Return chicken to pot, cover and simmer for 30-40 minutes until chicken is tender.",
            "prep_time": 15,
            "cook_time": 45,
            "calories": 460,
            "protein": 38,
            "fiber": 8,
            "carbs": 22,
            "fat": 22,
            "ingredients": [
                "6 oz chicken pieces",
                "1 bell pepper, sliced",
                "1 onion, sliced",
                "3 cloves garlic, minced",
                "1 cup tomatoes, diced",
                "1/4 cup white wine",
                "1 tsp dried oregano",
                "1 tsp dried basil",
                "2 tbsp olive oil"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "mediterranean"
            ]
        },
        {
            "name": "Lemon Herb Roasted Chicken",
            "meal_type": "dinner",
            "description": "Whole roasted chicken with lemon and fresh herbs",
            "instructions": "Preheat oven to 425°F. Pat chicken dry and rub with olive oil. Season generously with salt, pepper, and herbs. Stuff cavity with lemon halves and herb sprigs. Place in roasting pan and roast for 1 hour 15 minutes to 1 hour 30 minutes, until internal temperature reaches 165°F. Let rest for 15 minutes before carving.",
            "prep_time": 15,
            "cook_time": 90,
            "calories": 520,
            "protein": 48,
            "fiber": 2,
            "carbs": 8,
            "fat": 34,
            "ingredients": [
                "1 whole chicken (3-4 lbs)",
                "2 lemons, halved",
                "4 tbsp olive oil",
                "2 tbsp fresh herbs, chopped",
                "4 cloves garlic",
                "1 tsp salt",
                "1/2 tsp black pepper"
            ],
            "dietary_tags": [
                "high_protein",
                "low_carb",
                "gluten_free"
            ]
        },
        {
            "name": "Chicken and Vegetable Stir-Fry",
            "meal_type": "dinner",
            "description": "Quick and healthy stir-fry with chicken and colorful vegetables",
            "instructions": "Cut chicken into bite-sized pieces. Heat wok or large skillet over high heat with oil. Add chicken and stir-fry for 4-5 minutes until cooked through. Remove chicken. Add vegetables and stir-fry for 3-4 minutes until crisp-tender. Add garlic and ginger, stir for 30 seconds. Return chicken to pan with sauce and toss to coat.",
            "prep_time": 20,
            "cook_time": 12,
            "calories": 440,
            "protein": 36,
            "fiber": 8,
            "carbs": 32,
            "fat": 18,
            "ingredients": [
                "6 oz chicken breast",
                "3 cups mixed vegetables",
                "2 cloves garlic, minced",
                "1 inch ginger, grated",
                "3 tbsp soy sauce",
                "1 tbsp cornstarch",
                "1 tsp sesame oil",
                "2 tbsp vegetable oil"
            ],
            "dietary_tags": [
                "high_protein",
                "high_fiber",
                "quick",
                "gluten_free"
            ]
        }
    ]
    
    # Load existing recipes
    lunch_recipes = load_recipes("meals_lunch.json")
    dinner_recipes = load_recipes("meals_dinner.json")
    
    # Add new recipes
    lunch_recipes.extend(lunch_chicken_recipes)
    dinner_recipes.extend(dinner_chicken_recipes)
    
    # Save updated recipes
    save_recipes("meals_lunch.json", lunch_recipes)
    save_recipes("meals_dinner.json", dinner_recipes)
    
    print(f"Added {len(lunch_chicken_recipes)} chicken recipes to lunch")
    print(f"Added {len(dinner_chicken_recipes)} chicken recipes to dinner")

def main():
    """Main function to add all new recipes."""
    print("Adding more ground beef and chicken recipes...")
    
    # Add ground beef recipes
    add_ground_beef_recipes()
    
    # Add chicken recipes
    add_chicken_recipes()
    
    print("\nRecipe addition complete!")
    print("\nSummary of additions:")
    print("- 4 new ground beef lunch recipes")
    print("- 5 new ground beef dinner recipes")
    print("- 4 new chicken lunch recipes")
    print("- 5 new chicken dinner recipes")
    print("- Total: 18 new recipes added")

if __name__ == "__main__":
    main()