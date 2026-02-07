#!/usr/bin/env python3
"""
International Cuisine Recipe Addition Script for RunCoach App

This script adds healthy recipes from Spanish, Portuguese, and Asian cuisines
while ensuring de-duplication by name across all meal categories.
"""

import json
import os
from typing import Dict, List, Set, Any

class InternationalRecipeAdder:
    def __init__(self):
        self.data_dir = "/Users/boliveira/Documents/RunCoach/app/data"
        self.meal_files = {
            "breakfast": "meals_breakfast.json",
            "lunch": "meals_lunch.json", 
            "dinner": "meals_dinner.json",
            "post_workout": "meals_post_workout.json"
        }
        self.existing_names = set()
        
    def load_existing_names(self):
        """Load all existing recipe names to prevent duplicates"""
        print("Loading existing recipe names for de-duplication...")
        
        for meal_type in self.meal_files.keys():
            file_path = os.path.join(self.data_dir, self.meal_files[meal_type])
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    recipes = json.load(f)
                    for recipe in recipes:
                        self.existing_names.add(recipe.get("name", "").lower().strip())
        
        print(f"Found {len(self.existing_names)} existing recipe names")
    
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
    
    def get_international_recipes(self, meal_type: str) -> List[Dict[str, Any]]:
        """Get international cuisine recipes for each meal type"""
        
        if meal_type == "breakfast":
            recipes = [
                # Spanish Breakfast
                {
                    "name": "Spanish Tortilla with Chorizo",
                    "meal_type": "breakfast",
                    "description": "Traditional Spanish potato omelet with chorizo",
                    "instructions": "Heat 2 tbsp olive oil in a 10-inch non-stick skillet over medium heat. Add 1 cup thinly sliced potatoes and cook for 8-10 minutes until tender. Add 1/2 cup sliced Spanish chorizo and 1/4 cup diced onion, cook for 3 minutes. In a bowl, beat 4 eggs with salt and pepper. Pour egg mixture over potatoes in skillet. Cook for 4-5 minutes, gently lifting edges to let uncooked egg flow underneath. Place a plate over skillet and carefully flip tortilla onto plate. Slide back into skillet and cook for 3-4 minutes more. Slide onto serving plate and let rest for 5 minutes before cutting into wedges.",
                    "prep_time": 10,
                    "cook_time": 15,
                    "calories": 420,
                    "protein": 24,
                    "fiber": 6,
                    "carbs": 28,
                    "fat": 26,
                    "ingredients": [
                        "4 eggs",
                        "1 cup potatoes",
                        "1/2 cup Spanish chorizo",
                        "1/4 cup onion",
                        "2 tbsp olive oil",
                        "salt and pepper"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "spanish",
                        "hearty"
                    ]
                },
                # Portuguese Breakfast
                {
                    "name": "Portuguese Sweet Rice Porridge",
                    "meal_type": "breakfast",
                    "description": "Creamy Portuguese rice pudding with cinnamon and lemon",
                    "instructions": "In a saucepan, combine 1/2 cup arborio rice, 1.5 cups milk, 1/2 cup water, 1 cinnamon stick, and 1 strip lemon zest. Bring to a simmer over medium heat, then reduce heat to low and cook for 20-25 minutes, stirring occasionally, until rice is tender and creamy. Remove cinnamon stick and lemon zest. Stir in 2 tbsp honey and 1/4 tsp vanilla extract. Serve warm, sprinkled with ground cinnamon and topped with fresh berries if desired.",
                    "prep_time": 5,
                    "cook_time": 25,
                    "calories": 380,
                    "protein": 12,
                    "fiber": 4,
                    "carbs": 58,
                    "fat": 12,
                    "ingredients": [
                        "1/2 cup arborio rice",
                        "1.5 cups milk",
                        "1/2 cup water",
                        "1 cinnamon stick",
                        "1 strip lemon zest",
                        "2 tbsp honey",
                        "ground cinnamon"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "portuguese",
                        "comfort",
                        "high_carb"
                    ]
                },
                # Asian Breakfast
                {
                    "name": "Japanese Miso Soup with Tofu",
                    "meal_type": "breakfast",
                    "description": "Traditional Japanese breakfast soup with silken tofu and seaweed",
                    "instructions": "In a saucepan, bring 3 cups dashi or vegetable broth to a simmer. Reduce heat to low and add 3 tbsp white miso paste, whisking until dissolved. Add 4 oz cubed silken tofu, 1/4 cup dried wakame seaweed (rehydrated), and 1/2 cup sliced green onions. Simmer for 2 minutes until tofu is warmed through. Serve immediately in bowls, sprinkled with toasted sesame seeds.",
                    "prep_time": 8,
                    "cook_time": 10,
                    "calories": 180,
                    "protein": 14,
                    "fiber": 4,
                    "carbs": 18,
                    "fat": 8,
                    "ingredients": [
                        "3 tbsp white miso paste",
                        "3 cups dashi broth",
                        "4 oz silken tofu",
                        "1/4 cup wakame seaweed",
                        "1/2 cup green onions",
                        "sesame seeds"
                    ],
                    "dietary_tags": [
                        "japanese",
                        "light",
                        "vegetarian",
                        "low_calorie"
                    ]
                },
                {
                    "name": "Korean Kimchi Fried Rice",
                    "meal_type": "breakfast",
                    "description": "Spicy Korean fried rice with kimchi and egg",
                    "instructions": "Heat 1 tbsp sesame oil in a wok over high heat. Add 1 cup chopped kimchi and 1/2 cup diced onion, stir-fry for 2 minutes. Add 2 cups cooked brown rice and 1 tbsp gochujang, stir-fry for 3 minutes until rice is heated through. Push rice to side and add 2 beaten eggs, scrambling until cooked. Mix everything together with 1 tbsp soy sauce and 1 tsp sesame seeds. Serve topped with a fried egg and sliced green onions.",
                    "prep_time": 10,
                    "cook_time": 12,
                    "calories": 480,
                    "protein": 20,
                    "fiber": 8,
                    "carbs": 62,
                    "fat": 18,
                    "ingredients": [
                        "2 cups brown rice",
                        "1 cup kimchi",
                        "2 eggs",
                        "1 tbsp gochujang",
                        "1 tbsp soy sauce",
                        "1 tbsp sesame oil",
                        "green onions"
                    ],
                    "dietary_tags": [
                        "korean",
                        "spicy",
                        "high_protein",
                        "probiotic"
                    ]
                },
                {
                    "name": "Chinese Congee with Chicken",
                    "meal_type": "breakfast",
                    "description": "Comforting Chinese rice porridge with shredded chicken",
                    "instructions": "In a large pot, combine 1/2 cup jasmine rice, 6 cups chicken broth, and 1 tbsp fresh ginger (sliced). Bring to a boil, then reduce heat to low and simmer for 45-60 minutes, stirring occasionally, until rice breaks down into a creamy porridge. Add 1 cup shredded cooked chicken, 2 tbsp soy sauce, and 1 tsp sesame oil. Cook for 5 more minutes. Serve hot, topped with sliced green onions, fried shallots, and a drizzle of sesame oil.",
                    "prep_time": 10,
                    "cook_time": 60,
                    "calories": 380,
                    "protein": 28,
                    "fiber": 4,
                    "carbs": 42,
                    "fat": 12,
                    "ingredients": [
                        "1/2 cup jasmine rice",
                        "6 cups chicken broth",
                        "1 cup shredded chicken",
                        "1 tbsp ginger",
                        "2 tbsp soy sauce",
                        "1 tsp sesame oil",
                        "green onions",
                        "fried shallots"
                    ],
                    "dietary_tags": [
                        "chinese",
                        "comfort",
                        "high_protein",
                        "gluten_free"
                    ]
                }
            ]
        
        elif meal_type == "lunch":
            recipes = [
                # Spanish Lunch
                {
                    "name": "Valencian Paella with Seafood",
                    "meal_type": "lunch",
                    "description": "Authentic Spanish paella with shrimp, mussels, and saffron",
                    "instructions": "Heat 2 tbsp olive oil in a large paella pan over medium heat. Add 1/2 cup diced onion and 2 cloves minced garlic, cook for 3 minutes. Add 1 cup bomba rice and toast for 2 minutes. Add 1/4 tsp saffron threads, 3 cups hot chicken broth, 1 tsp smoked paprika, salt, and pepper. Arrange 8 shrimp, 12 mussels, and 4 oz calamari over rice. Simmer for 15-18 minutes without stirring until liquid is absorbed. Remove from heat and let rest for 5 minutes. Garnish with lemon wedges and fresh parsley.",
                    "prep_time": 20,
                    "cook_time": 25,
                    "calories": 520,
                    "protein": 32,
                    "fiber": 6,
                    "carbs": 58,
                    "fat": 18,
                    "ingredients": [
                        "1 cup bomba rice",
                        "8 shrimp",
                        "12 mussels",
                        "4 oz calamari",
                        "1/4 tsp saffron",
                        "3 cups chicken broth",
                        "1 tsp smoked paprika",
                        "2 tbsp olive oil"
                    ],
                    "dietary_tags": [
                        "spanish",
                        "seafood",
                        "high_protein",
                        "special_occasion"
                    ]
                },
                {
                    "name": "Andalusian Gazpacho",
                    "meal_type": "lunch",
                    "description": "Cold Spanish tomato soup with vegetables and olive oil",
                    "instructions": "In a blender, combine 2 lbs ripe tomatoes, 1 cucumber, 1/2 red bell pepper, 1/2 green bell pepper, 1/4 cup red wine vinegar, 2 cloves garlic, and 1/4 cup olive oil. Blend until smooth. Season with salt and pepper. Strain through a fine-mesh sieve for extra smooth texture. Chill for at least 2 hours. Serve cold in bowls, garnished with diced cucumber, bell pepper, and a drizzle of olive oil.",
                    "prep_time": 15,
                    "cook_time": 0,
                    "calories": 180,
                    "protein": 6,
                    "fiber": 8,
                    "carbs": 18,
                    "fat": 12,
                    "ingredients": [
                        "2 lbs ripe tomatoes",
                        "1 cucumber",
                        "1/2 red bell pepper",
                        "1/2 green bell pepper",
                        "1/4 cup red wine vinegar",
                        "2 cloves garlic",
                        "1/4 cup olive oil"
                    ],
                    "dietary_tags": [
                        "spanish",
                        "vegetarian",
                        "light",
                        "refreshing"
                    ]
                },
                # Portuguese Lunch
                {
                    "name": "Portuguese Bacalhau à Brás",
                    "meal_type": "lunch",
                    "description": "Shredded salt cod with potatoes and eggs",
                    "instructions": "Soak 8 oz salt cod in water for 24 hours, changing water several times. Shred the cod into small pieces. Heat 2 tbsp olive oil in a large skillet over medium heat. Add 1 cup shredded potatoes and 1/2 cup diced onion, cook for 8 minutes until potatoes are golden. Add shredded cod and 2 cloves minced garlic, cook for 3 minutes. Add 4 beaten eggs and stir gently until eggs are just set. Remove from heat and stir in 1/4 cup chopped parsley and 12 black olives. Garnish with matchstick potatoes.",
                    "prep_time": 30,
                    "cook_time": 15,
                    "calories": 480,
                    "protein": 32,
                    "fiber": 6,
                    "carbs": 42,
                    "fat": 22,
                    "ingredients": [
                        "8 oz salt cod",
                        "1 cup potatoes",
                        "4 eggs",
                        "1/2 cup onion",
                        "2 cloves garlic",
                        "1/4 cup parsley",
                        "12 black olives",
                        "2 tbsp olive oil"
                    ],
                    "dietary_tags": [
                        "portuguese",
                        "high_protein",
                        "seafood",
                        "traditional"
                    ]
                },
                {
                    "name": "Portuguese Cataplana with Seafood",
                    "meal_type": "lunch",
                    "description": "Seafood stew cooked in traditional copper pan",
                    "instructions": "Heat 2 tbsp olive oil in a large pot over medium heat. Add 1 onion, 2 cloves garlic, and 1 red bell pepper, cook for 5 minutes. Add 1/2 cup white wine and cook for 3 minutes. Add 1 can crushed tomatoes, 1 tsp smoked paprika, and 1/2 cup clam juice. Add 8 clams, 8 mussels, 8 shrimp, and 4 oz firm white fish. Cover and cook for 8-10 minutes until shellfish open. Season with salt, pepper, and fresh cilantro. Serve with crusty bread.",
                    "prep_time": 20,
                    "cook_time": 20,
                    "calories": 420,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 24,
                    "fat": 18,
                    "ingredients": [
                        "8 clams",
                        "8 mussels", 
                        "8 shrimp",
                        "4 oz white fish",
                        "1/2 cup white wine",
                        "1 can crushed tomatoes",
                        "1 tsp smoked paprika",
                        "fresh cilantro"
                    ],
                    "dietary_tags": [
                        "portuguese",
                        "seafood",
                        "high_protein",
                        "low_carb"
                    ]
                },
                # Asian Lunch
                {
                    "name": "Vietnamese Pho with Beef",
                    "meal_type": "lunch",
                    "description": "Traditional Vietnamese noodle soup with beef and herbs",
                    "instructions": "In a large pot, bring 6 cups beef broth to a simmer. Add 1 star anise, 1 cinnamon stick, 2 cloves, and 1 slice ginger. Simmer for 15 minutes. Cook 6 oz rice noodles according to package directions. In bowls, arrange 4 oz thinly sliced beef, cooked noodles, bean sprouts, and basil. Pour hot broth over beef (it will cook from the heat). Top with sliced green onions, cilantro, and a squeeze of lime. Serve with hoisin sauce and sriracha.",
                    "prep_time": 20,
                    "cook_time": 20,
                    "calories": 480,
                    "protein": 28,
                    "fiber": 6,
                    "carbs": 52,
                    "fat": 16,
                    "ingredients": [
                        "6 oz beef sirloin",
                        "6 oz rice noodles",
                        "6 cups beef broth",
                        "1 star anise",
                        "1 cinnamon stick",
                        "bean sprouts",
                        "fresh basil",
                        "lime wedges"
                    ],
                    "dietary_tags": [
                        "vietnamese",
                        "high_protein",
                        "hearty",
                        "aromatic"
                    ]
                },
                {
                    "name": "Thai Green Curry with Chicken",
                    "meal_type": "lunch",
                    "description": "Aromatic Thai curry with chicken and vegetables",
                    "instructions": "Heat 1 tbsp coconut oil in a large pan over medium heat. Add 2 tbsp green curry paste and cook for 1 minute. Add 1 lb chicken breast (cubed) and cook until browned. Add 1 can coconut milk, 1 cup chicken broth, 1 tbsp fish sauce, and 1 tsp palm sugar. Add 1 cup eggplant, 1/2 cup green beans, and 1/4 cup Thai basil. Simmer for 10-12 minutes until chicken is cooked and vegetables are tender. Serve over jasmine rice.",
                    "prep_time": 20,
                    "cook_time": 20,
                    "calories": 520,
                    "protein": 36,
                    "fiber": 8,
                    "carbs": 28,
                    "fat": 32,
                    "ingredients": [
                        "1 lb chicken breast",
                        "1 can coconut milk",
                        "2 tbsp green curry paste",
                        "1 cup eggplant",
                        "1/2 cup green beans",
                        "1 tbsp fish sauce",
                        "Thai basil",
                        "jasmine rice"
                    ],
                    "dietary_tags": [
                        "thai",
                        "high_protein",
                        "spicy",
                        "creamy"
                    ]
                },
                {
                    "name": "Japanese Chicken Teriyaki Bowl",
                    "meal_type": "lunch",
                    "description": "Glazed chicken with vegetables and rice",
                    "instructions": "In a small bowl, mix 1/4 cup soy sauce, 2 tbsp mirin, 1 tbsp sugar, and 1 tsp cornstarch. Heat 1 tbsp oil in a skillet over medium-high heat. Add 1 lb chicken thighs and cook for 5-6 minutes per side until golden. Pour teriyaki sauce over chicken and cook for 2-3 minutes until sauce thickens and glazes chicken. Serve over 1 cup cooked rice with steamed broccoli and carrots. Garnish with sesame seeds and sliced green onions.",
                    "prep_time": 15,
                    "cook_time": 15,
                    "calories": 580,
                    "protein": 42,
                    "fiber": 6,
                    "carbs": 58,
                    "fat": 18,
                    "ingredients": [
                        "1 lb chicken thighs",
                        "1 cup rice",
                        "1/4 cup soy sauce",
                        "2 tbsp mirin",
                        "1 tbsp sugar",
                        "broccoli",
                        "carrots",
                        "sesame seeds"
                    ],
                    "dietary_tags": [
                        "japanese",
                        "high_protein",
                        "family_friendly",
                        "quick"
                    ]
                }
            ]
        
        elif meal_type == "dinner":
            recipes = [
                # Spanish Dinner
                {
                    "name": "Cordoban Salmorejo with Jamón",
                    "meal_type": "dinner",
                    "description": "Creamy cold tomato soup with Spanish ham",
                    "instructions": "In a blender, combine 2 lbs ripe tomatoes, 1/2 cup stale bread, 1/4 cup olive oil, 2 cloves garlic, and 1 tsp sherry vinegar. Blend until completely smooth. Season with salt. Chill for at least 2 hours. Serve in shallow bowls topped with diced serrano ham, hard-boiled eggs, and a drizzle of olive oil.",
                    "prep_time": 15,
                    "cook_time": 0,
                    "calories": 320,
                    "protein": 16,
                    "fiber": 8,
                    "carbs": 22,
                    "fat": 20,
                    "ingredients": [
                        "2 lbs ripe tomatoes",
                        "1/2 cup stale bread",
                        "1/4 cup olive oil",
                        "2 cloves garlic",
                        "1 tsp sherry vinegar",
                        "serrano ham",
                        "hard-boiled eggs"
                    ],
                    "dietary_tags": [
                        "spanish",
                        "light",
                        "refreshing",
                        "high_protein"
                    ]
                },
                {
                    "name": "Asturian Fabada with Chorizo",
                    "meal_type": "dinner",
                    "description": "Hearty Spanish bean stew with chorizo and morcilla",
                    "instructions": "Soak 1 lb white fabada beans overnight. Drain and place in a large pot with 8 cups water. Add 1/2 lb Spanish chorizo, 1/4 lb morcilla (blood sausage), 1/4 lb pork belly, and 1 saffron thread. Simmer for 2-3 hours until beans are tender. Add salt to taste. Serve hot in bowls with crusty bread.",
                    "prep_time": 240,
                    "cook_time": 180,
                    "calories": 680,
                    "protein": 36,
                    "fiber": 18,
                    "carbs": 62,
                    "fat": 32,
                    "ingredients": [
                        "1 lb fabada beans",
                        "1/2 lb Spanish chorizo",
                        "1/4 lb morcilla",
                        "1/4 lb pork belly",
                        "1 saffron thread",
                        "8 cups water",
                        "crusty bread"
                    ],
                    "dietary_tags": [
                        "spanish",
                        "hearty",
                        "high_protein",
                        "high_fiber",
                        "traditional"
                    ]
                },
                # Portuguese Dinner
                {
                    "name": "Portuguese Francesinha Sandwich",
                    "meal_type": "dinner",
                    "description": "Porto's famous sandwich with multiple meats and spicy sauce",
                    "instructions": "Butter 2 thick slices of brioche bread. Layer with 2 slices ham, 2 slices steak, 2 slices linguiça sausage, and 2 slices cheese. Top with second bread slice. In a saucepan, heat 1 cup beer, 1/4 cup tomato sauce, 1 bay leaf, and 1 tsp hot sauce. Simmer for 10 minutes. Place sandwich in a baking dish, pour sauce over, top with more cheese, and bake at 375°F for 15 minutes until bubbly. Serve with fried potatoes.",
                    "prep_time": 25,
                    "cook_time": 20,
                    "calories": 820,
                    "protein": 42,
                    "fiber": 6,
                    "carbs": 48,
                    "fat": 48,
                    "ingredients": [
                        "2 slices brioche bread",
                        "2 slices ham",
                        "2 slices steak",
                        "2 slices linguiça",
                        "4 slices cheese",
                        "1 cup beer",
                        "1/4 cup tomato sauce",
                        "fried potatoes"
                    ],
                    "dietary_tags": [
                        "portuguese",
                        "hearty",
                        "high_protein",
                        "indulgent"
                    ]
                },
                {
                    "name": "Alentejan Pork with Clams",
                    "meal_type": "dinner",
                    "description": "Traditional Portuguese pork and clam dish",
                    "instructions": "Marinate 1 lb pork shoulder in 4 cloves garlic, 1 tsp paprika, 1 tsp cumin, 1/2 cup white wine, and 2 tbsp olive oil for 2 hours. Heat 2 tbsp olive oil in a large pan and cook pork until browned. Add 1 lb small clams, 2 cups potatoes, and 1/2 cup coriander. Cover and cook for 10 minutes until clams open. Serve with lemon wedges.",
                    "prep_time": 150,
                    "cook_time": 20,
                    "calories": 580,
                    "protein": 38,
                    "fiber": 8,
                    "carbs": 42,
                    "fat": 28,
                    "ingredients": [
                        "1 lb pork shoulder",
                        "1 lb clams",
                        "2 cups potatoes",
                        "1/2 cup white wine",
                        "1 tsp paprika",
                        "1 tsp cumin",
                        "fresh coriander",
                        "lemon wedges"
                    ],
                    "dietary_tags": [
                        "portuguese",
                        "high_protein",
                        "flavorful",
                        "seafood"
                    ]
                },
                # Asian Dinner
                {
                    "name": "Korean Bibimbap with Beef",
                    "meal_type": "dinner",
                    "description": "Korean mixed rice bowl with vegetables and marinated beef",
                    "instructions": "Marinate 8 oz beef in 2 tbsp soy sauce, 1 tbsp sesame oil, 1 tsp sugar, and 2 cloves garlic for 30 minutes. Cook beef in a hot pan until browned. Prepare vegetables: 1 cup spinach (sautéed with sesame oil), 1 cup bean sprouts (blanched), 1 carrot (julienned), 1 zucchini (sautéed). Fry 4 eggs sunny-side up. In bowls, arrange rice, beef, vegetables in sections. Top with fried egg, gochujang, and sesame seeds.",
                    "prep_time": 45,
                    "cook_time": 20,
                    "calories": 620,
                    "protein": 32,
                    "fiber": 12,
                    "carbs": 68,
                    "fat": 22,
                    "ingredients": [
                        "8 oz beef",
                        "2 cups rice",
                        "1 cup spinach",
                        "1 cup bean sprouts",
                        "1 carrot",
                        "1 zucchini",
                        "4 eggs",
                        "gochujang",
                        "sesame seeds"
                    ],
                    "dietary_tags": [
                        "korean",
                        "high_protein",
                        "colorful",
                        "balanced"
                    ]
                },
                {
                    "name": "Sichuan Mapo Tofu",
                    "meal_type": "dinner",
                    "description": "Spicy Sichuan tofu with ground pork",
                    "instructions": "Heat 2 tbsp oil in a wok over high heat. Add 2 cloves garlic and 1 tbsp ginger, stir-fry for 30 seconds. Add 4 oz ground pork and cook until browned. Add 2 tbsp doubanjiang (chili bean paste) and cook for 1 minute. Add 1 block firm tofu (cubed), 1 cup chicken broth, and 1 tsp soy sauce. Simmer for 5 minutes. Thicken with 1 tsp cornstarch mixed with 2 tbsp water. Garnish with Sichuan peppercorns and green onions.",
                    "prep_time": 15,
                    "cook_time": 15,
                    "calories": 420,
                    "protein": 28,
                    "fiber": 8,
                    "carbs": 22,
                    "fat": 26,
                    "ingredients": [
                        "1 block firm tofu",
                        "4 oz ground pork",
                        "2 tbsp doubanjiang",
                        "1 cup chicken broth",
                        "Sichuan peppercorns",
                        "green onions",
                        "garlic",
                        "ginger"
                    ],
                    "dietary_tags": [
                        "chinese",
                        "spicy",
                        "high_protein",
                        "numbing"
                    ]
                },
                {
                    "name": "Filipino Adobo with Chicken",
                    "meal_type": "dinner",
                    "description": "Tangy Filipino chicken stewed in soy and vinegar",
                    "instructions": "In a pot, combine 1 lb chicken pieces, 1/2 cup soy sauce, 1/2 cup vinegar, 1/2 cup water, 4 cloves garlic, 1 bay leaf, and 1 tsp black peppercorns. Bring to a boil, then reduce heat and simmer for 30 minutes. Remove chicken and fry in 2 tbsp oil until golden. Return to pot and simmer for 10 more minutes until sauce reduces and thickens. Serve over steamed rice.",
                    "prep_time": 10,
                    "cook_time": 50,
                    "calories": 480,
                    "protein": 36,
                    "fiber": 4,
                    "carbs": 18,
                    "fat": 28,
                    "ingredients": [
                        "1 lb chicken",
                        "1/2 cup soy sauce",
                        "1/2 cup vinegar",
                        "4 cloves garlic",
                        "1 bay leaf",
                        "1 tsp black peppercorns",
                        "steamed rice"
                    ],
                    "dietary_tags": [
                        "filipino",
                        "tangy",
                        "high_protein",
                        "savory"
                    ]
                },
                {
                    "name": "Malaysian Laksa with Prawns",
                    "meal_type": "dinner",
                    "description": "Spicy coconut noodle soup with seafood",
                    "instructions": "Heat 2 tbsp oil in a pot and sauté 2 tbsp laksa paste for 1 minute. Add 4 cups chicken broth, 1 can coconut milk, and 1 tbsp fish sauce. Simmer for 10 minutes. Add 8 prawns, 4 oz fish cake, and 200g rice noodles. Cook for 5 minutes until prawns are pink. Serve in bowls topped with bean sprouts, mint, cilantro, and a squeeze of lime.",
                    "prep_time": 20,
                    "cook_time": 20,
                    "calories": 520,
                    "protein": 28,
                    "fiber": 6,
                    "carbs": 48,
                    "fat": 28,
                    "ingredients": [
                        "8 prawns",
                        "4 oz fish cake",
                        "200g rice noodles",
                        "2 tbsp laksa paste",
                        "1 can coconut milk",
                        "bean sprouts",
                        "fresh mint",
                        "lime wedges"
                    ],
                    "dietary_tags": [
                        "malaysian",
                        "spicy",
                        "seafood",
                        "creamy"
                    ]
                }
            ]
        
        elif meal_type == "post_workout":
            recipes = [
                # Spanish Post-Workout
                {
                    "name": "Spanish Protein Tortilla",
                    "meal_type": "post_workout",
                    "description": "High-protein Spanish omelet for muscle recovery",
                    "instructions": "In a bowl, whisk 6 eggs with 2 scoops unflavored protein powder, salt, and pepper. Heat 1 tbsp olive oil in a non-stick skillet. Add 1 cup diced cooked potatoes and 1/4 cup diced ham, cook for 2 minutes. Pour egg mixture over and cook for 4-5 minutes. Flip and cook for 3 more minutes. Slide onto plate and cut into wedges.",
                    "prep_time": 8,
                    "cook_time": 10,
                    "calories": 480,
                    "protein": 42,
                    "fiber": 6,
                    "carbs": 28,
                    "fat": 22,
                    "ingredients": [
                        "6 eggs",
                        "2 scoops protein powder",
                        "1 cup cooked potatoes",
                        "1/4 cup ham",
                        "1 tbsp olive oil",
                        "salt and pepper"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "spanish",
                        "recovery",
                        "quick"
                    ]
                },
                # Portuguese Post-Workout
                {
                    "name": "Portuguese Protein Rice Pudding",
                    "meal_type": "post_workout",
                    "description": "Creamy protein-enhanced rice pudding for recovery",
                    "instructions": "In a saucepan, combine 1/2 cup arborio rice, 1.5 cups milk, and 1 scoop vanilla protein powder. Bring to a simmer and cook for 20 minutes, stirring occasionally. Add 1 tbsp honey and 1/4 tsp cinnamon. Cook for 5 more minutes until creamy. Serve warm topped with berries and 1 tbsp slivered almonds.",
                    "prep_time": 5,
                    "cook_time": 25,
                    "calories": 420,
                    "protein": 28,
                    "fiber": 4,
                    "carbs": 52,
                    "fat": 12,
                    "ingredients": [
                        "1/2 cup arborio rice",
                        "1 scoop vanilla protein powder",
                        "1.5 cups milk",
                        "1 tbsp honey",
                        "1/4 tsp cinnamon",
                        "berries",
                        "almonds"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "portuguese",
                        "recovery",
                        "comfort"
                    ]
                },
                # Asian Post-Workout
                {
                    "name": "Japanese Protein Miso Soup",
                    "meal_type": "post_workout",
                    "description": "Enhanced miso soup with added protein for recovery",
                    "instructions": "In a saucepan, bring 2 cups dashi broth to a simmer. Add 2 tbsp white miso paste and 1 scoop unflavored protein powder, whisking until dissolved. Add 4 oz silken tofu, 1/4 cup wakame seaweed, and 2 tbsp edamame. Simmer for 2 minutes. Serve topped with sliced green onions and sesame seeds.",
                    "prep_time": 5,
                    "cook_time": 8,
                    "calories": 280,
                    "protein": 24,
                    "fiber": 6,
                    "carbs": 18,
                    "fat": 8,
                    "ingredients": [
                        "1 scoop protein powder",
                        "2 tbsp miso paste",
                        "2 cups dashi broth",
                        "4 oz silken tofu",
                        "1/4 cup wakame",
                        "2 tbsp edamame",
                        "green onions"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "japanese",
                        "recovery",
                        "light"
                    ]
                },
                {
                    "name": "Korean Protein Kimchi Bowl",
                    "meal_type": "post_workout",
                    "description": "Nutrient-dense kimchi bowl with added protein",
                    "instructions": "Heat 1 tsp sesame oil in a pan. Add 1 cup kimchi and cook for 2 minutes. Add 1 cup cooked brown rice and 1 scoop unflavored protein powder, mix well. Add 1/2 cup black beans and 1 tsp gochujang. Top with 1 fried egg, sliced cucumber, and sesame seeds.",
                    "prep_time": 8,
                    "cook_time": 10,
                    "calories": 480,
                    "protein": 32,
                    "fiber": 12,
                    "carbs": 58,
                    "fat": 16,
                    "ingredients": [
                        "1 scoop protein powder",
                        "1 cup kimchi",
                        "1 cup brown rice",
                        "1/2 cup black beans",
                        "1 egg",
                        "1 tsp gochujang",
                        "sesame seeds"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "korean",
                        "recovery",
                        "probiotic"
                    ]
                },
                {
                    "name": "Thai Protein Smoothie",
                    "meal_type": "post_workout",
                    "description": "Tropical Thai-inspired protein smoothie",
                    "instructions": "In a blender, combine 1 scoop vanilla protein powder, 1 cup coconut milk, 1/2 cup mango chunks, 1/4 cup pineapple chunks, 1 tbsp lime juice, and 1/2 cup ice. Blend on high for 60 seconds until smooth. Pour into a glass and top with 1 tbsp shredded coconut and mint leaves.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 380,
                    "protein": 28,
                    "fiber": 6,
                    "carbs": 42,
                    "fat": 12,
                    "ingredients": [
                        "1 scoop vanilla protein powder",
                        "1 cup coconut milk",
                        "1/2 cup mango",
                        "1/4 cup pineapple",
                        "1 tbsp lime juice",
                        "shredded coconut",
                        "mint leaves"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "thai",
                        "recovery",
                        "tropical"
                    ]
                }
            ]
        
        else:
            recipes = []
        
        # Filter out recipes that already exist by name
        filtered_recipes = []
        for recipe in recipes:
            recipe_name = recipe.get("name", "").lower().strip()
            if recipe_name not in self.existing_names:
                filtered_recipes.append(recipe)
                self.existing_names.add(recipe_name)  # Add to prevent duplicates within this batch
            else:
                print(f"  Skipping duplicate recipe: {recipe['name']}")
        
        return filtered_recipes
    
    def update_consolidated_file(self):
        """Update the main meals.json file with all recipes"""
        all_recipes = []
        for meal_type in self.meal_files.keys():
            recipes = self.load_recipes(meal_type)
            all_recipes.extend(recipes)
        
        # Sort recipes by meal type and name
        all_recipes.sort(key=lambda x: (x["meal_type"], x["name"]))
        
        # Save consolidated file
        consolidated_path = os.path.join(self.data_dir, "meals.json")
        with open(consolidated_path, 'w') as f:
            json.dump(all_recipes, f, indent=2)
        
        print(f"Updated consolidated meals.json with {len(all_recipes)} total recipes")
    
    def process_all_meals(self):
        """Process all meal types: add international recipes"""
        total_added = 0
        
        # First load existing names for de-duplication
        self.load_existing_names()
        
        for meal_type in self.meal_files.keys():
            print(f"\nAdding international {meal_type} recipes...")
            
            # Load existing recipes
            recipes = self.load_recipes(meal_type)
            original_count = len(recipes)
            
            # Get new international recipes (already filtered for duplicates)
            new_recipes = self.get_international_recipes(meal_type)
            
            # Add new recipes to existing ones
            final_recipes = recipes + new_recipes
            final_count = len(final_recipes)
            added_count = len(new_recipes)
            total_added += added_count
            
            # Save updated recipes
            self.save_recipes(meal_type, final_recipes)
            
            print(f"  - Original recipes: {original_count}")
            print(f"  - New international recipes added: {added_count}")
            print(f"  - Final total: {final_count}")
        
        # Update consolidated file
        self.update_consolidated_file()
        
        print(f"\n=== SUMMARY ===")
        print(f"Total international recipes added: {total_added}")
        print("All recipe files have been updated successfully!")
        print("✅ De-duplication by name completed successfully!")


def main():
    """Main function to run the international recipe addition process"""
    print("🌍 RunCoach International Cuisine Recipe Addition Script")
    print("=" * 60)
    print("This script will:")
    print("1. Add healthy Spanish, Portuguese, and Asian cuisine recipes")
    print("2. Ensure de-duplication by recipe name across all categories")
    print("3. Expand recipe diversity with authentic international flavors")
    print("=" * 60)
    
    adder = InternationalRecipeAdder()
    adder.process_all_meals()
    
    print("\n✅ International recipe addition completed successfully!")
    print("🍽️ Recipe database has been expanded with Spanish, Portuguese, and Asian cuisines")
    print("🌏 Added authentic international flavors while preventing duplicates")


if __name__ == "__main__":
    main()