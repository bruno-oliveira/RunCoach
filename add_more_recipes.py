#!/usr/bin/env python3
"""
Additional Recipe Addition Script for RunCoach App

This script adds more recipes to expand the database with diverse options
including snacks, more dietary preferences, and international cuisines.
"""

import json
import os
from typing import Dict, List, Any

class AdditionalRecipeAdder:
    def __init__(self):
        self.data_dir = "/Users/boliveira/Documents/RunCoach/app/data"
        self.meal_files = {
            "breakfast": "meals_breakfast.json",
            "lunch": "meals_lunch.json", 
            "dinner": "meals_dinner.json",
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
    
    def add_additional_recipes(self, meal_type: str, existing_recipes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add additional recipes to expand the database"""
        additional_recipes = self.get_additional_recipes(meal_type)
        return existing_recipes + additional_recipes
    
    def get_additional_recipes(self, meal_type: str) -> List[Dict[str, Any]]:
        """Get additional recipes for each meal type"""
        
        if meal_type == "breakfast":
            return [
                {
                    "name": "Protein Coffee Smoothie",
                    "meal_type": "breakfast",
                    "description": "Energy-boosting smoothie with coffee and protein powder",
                    "instructions": "Brew 1 cup strong coffee and let cool completely. Add cooled coffee, 1 frozen banana, 1 scoop chocolate protein powder, 1 tbsp almond butter, and 1 cup almond milk to a high-speed blender. Add 1/2 cup ice cubes. Blend on high speed for 60-90 seconds until completely smooth and creamy. The coffee provides caffeine for morning energy, while protein powder supports muscle maintenance. Pour into a tall glass and enjoy immediately for a quick breakfast on the go.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 360,
                    "protein": 28,
                    "fiber": 6,
                    "carbs": 38,
                    "fat": 12,
                    "ingredients": [
                        "1 scoop chocolate protein powder",
                        "1 frozen banana",
                        "1 cup brewed coffee",
                        "1 cup almond milk",
                        "1 tbsp almond butter",
                        "1 tsp vanilla extract",
                        "ice cubes"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "quick",
                        "energy_boost"
                    ]
                },
                {
                    "name": "Savory Oatmeal Bowl",
                    "meal_type": "breakfast",
                    "description": "Savory oatmeal topped with egg, cheese, and vegetables",
                    "instructions": "In a saucepan, bring 1 cup water or vegetable broth to a boil. Add 1/2 cup rolled oats and reduce heat to medium-low. Cook for 5-7 minutes, stirring occasionally, until oats are tender and creamy. Stir in 1 tbsp nutritional yeast, 1/4 tsp garlic powder, salt, and pepper. Transfer to a bowl and top with a fried egg, 2 oz shredded cheddar cheese, sautéed mushrooms, and fresh chives. The savory flavors make this a satisfying alternative to sweet oatmeal.",
                    "prep_time": 8,
                    "cook_time": 10,
                    "calories": 380,
                    "protein": 20,
                    "fiber": 8,
                    "carbs": 42,
                    "fat": 16,
                    "ingredients": [
                        "1/2 cup rolled oats",
                        "1 cup water or vegetable broth",
                        "1 egg",
                        "2 oz cheddar cheese",
                        "1/2 cup mushrooms",
                        "1 tbsp nutritional yeast",
                        "fresh chives"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "savory"
                    ]
                },
                {
                    "name": "Berry Protein Smoothie Bowl",
                    "meal_type": "breakfast",
                    "description": "Thick smoothie bowl topped with fresh fruits and granola",
                    "instructions": "Add 1.5 scoops vanilla protein powder, 1 frozen banana, 1 cup mixed frozen berries, 1/2 cup Greek yogurt, and 1/4 cup almond milk to a high-speed blender. Blend on high until thick and creamy, adding more almond milk if needed to achieve desired consistency. Pour into a bowl and arrange toppings in rows: 1/4 cup granola, 1/2 cup fresh berries, 1 tbsp chia seeds, 1 tbsp coconut flakes, and fresh mint leaves. Drizzle with 1 tsp honey if desired.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 400,
                    "protein": 32,
                    "fiber": 10,
                    "carbs": 48,
                    "fat": 12,
                    "ingredients": [
                        "1.5 scoops vanilla protein powder",
                        "1 frozen banana",
                        "1 cup mixed frozen berries",
                        "1/2 cup Greek yogurt",
                        "1/4 cup almond milk",
                        "1/4 cup granola",
                        "1/2 cup fresh berries",
                        "1 tbsp chia seeds"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "quick"
                    ]
                },
                {
                    "name": "Egg and Cheese Breakfast Sandwich",
                    "meal_type": "breakfast",
                    "description": "Homemade breakfast sandwich with egg, cheese, and turkey",
                    "instructions": "Toast 2 English muffin halves until golden. Heat 1 tsp butter in a small non-stick skillet over medium heat. Crack 2 eggs into the skillet and cook sunny-side up or over-easy to your preference. Place 1 slice of cheddar cheese on each English muffin half. Top one half with cooked eggs and 2 slices of turkey bacon. Season with salt and pepper. Close sandwich and serve immediately while eggs are still warm.",
                    "prep_time": 8,
                    "cook_time": 6,
                    "calories": 420,
                    "protein": 28,
                    "fiber": 6,
                    "carbs": 32,
                    "fat": 22,
                    "ingredients": [
                        "2 English muffin halves",
                        "2 eggs",
                        "2 slices cheddar cheese",
                        "2 slices turkey bacon",
                        "1 tsp butter",
                        "salt and pepper"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "quick",
                        "comfort"
                    ]
                },
                {
                    "name": "Pumpkin Spice Protein Oatmeal",
                    "meal_type": "breakfast",
                    "description": "Fall-inspired oatmeal with pumpkin and warming spices",
                    "instructions": "In a saucepan, combine 1 cup rolled oats, 1.5 cups almond milk, 1/2 cup pumpkin purée, 1 scoop vanilla protein powder, 1 tsp pumpkin pie spice, and 1 tbsp maple syrup. Bring to a simmer over medium heat, then reduce heat to low and cook for 5-7 minutes, stirring occasionally, until oats are creamy and tender. Remove from heat and stir in 1/2 tsp vanilla extract. Transfer to a bowl and top with 2 tbsp toasted pecans and a sprinkle of cinnamon.",
                    "prep_time": 5,
                    "cook_time": 8,
                    "calories": 440,
                    "protein": 28,
                    "fiber": 12,
                    "carbs": 52,
                    "fat": 14,
                    "ingredients": [
                        "1 cup rolled oats",
                        "1 scoop vanilla protein powder",
                        "1/2 cup pumpkin purée",
                        "1.5 cups almond milk",
                        "1 tbsp maple syrup",
                        "1 tsp pumpkin pie spice",
                        "2 tbsp pecans"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "seasonal"
                    ]
                }
            ]
        
        elif meal_type == "lunch":
            return [
                {
                    "name": "Mediterranean Chickpea Salad",
                    "meal_type": "lunch",
                    "description": "Fresh chickpea salad with Mediterranean vegetables and feta",
                    "instructions": "In a large bowl, combine 1 can chickpeas (rinsed and drained), 1 cup cherry tomatoes (halved), 1/2 cucumber (diced), 1/4 red onion (thinly sliced), and 1/2 cup Kalamata olives. In a small bowl, whisk together 3 tbsp olive oil, 1 tbsp red wine vinegar, 1 tsp dried oregano, salt, and pepper. Pour dressing over salad and toss gently. Add 1/2 cup crumbled feta cheese and 1/4 cup fresh parsley. Let marinate for 15 minutes before serving.",
                    "prep_time": 15,
                    "cook_time": 0,
                    "calories": 420,
                    "protein": 18,
                    "fiber": 14,
                    "carbs": 48,
                    "fat": 18,
                    "ingredients": [
                        "1 can chickpeas",
                        "1 cup cherry tomatoes",
                        "1/2 cucumber",
                        "1/2 cup Kalamata olives",
                        "1/2 cup feta cheese",
                        "3 tbsp olive oil",
                        "1 tbsp red wine vinegar",
                        "fresh parsley"
                    ],
                    "dietary_tags": [
                        "high_fiber",
                        "vegetarian",
                        "mediterranean",
                        "quick"
                    ]
                },
                {
                    "name": "Thai Peanut Noodle Bowl",
                    "meal_type": "lunch",
                    "description": "Cold noodle salad with peanut sauce and fresh vegetables",
                    "instructions": "Cook 4 oz rice noodles according to package directions, then rinse with cold water and drain. In a small bowl, whisk together 3 tbsp peanut butter, 1 tbsp soy sauce, 1 tbsp rice vinegar, 1 tsp sesame oil, and 1 tsp honey. Add 2 tbsp water to thin sauce if needed. In a large bowl, combine cooled noodles, 2 cups shredded cabbage, 1 cup shredded carrots, 1 cup edamame, and 1/2 cup chopped peanuts. Pour peanut sauce over mixture and toss well. Garnish with fresh cilantro and lime wedges.",
                    "prep_time": 20,
                    "cook_time": 10,
                    "calories": 480,
                    "protein": 20,
                    "fiber": 10,
                    "carbs": 58,
                    "fat": 20,
                    "ingredients": [
                        "4 oz rice noodles",
                        "3 tbsp peanut butter",
                        "2 cups cabbage",
                        "1 cup carrots",
                        "1 cup edamame",
                        "1/2 cup peanuts",
                        "fresh cilantro",
                        "lime wedges"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "high_fiber",
                        "meal_prep"
                    ]
                },
                {
                    "name": "Grilled Vegetable Panini",
                    "meal_type": "lunch",
                    "description": "Warm pressed sandwich with grilled vegetables and cheese",
                    "instructions": "Slice 1 zucchini, 1 red bell pepper, and 1 red onion into 1/4-inch thick slices. Heat 1 tbsp olive oil in a grill pan over medium-high heat. Grill vegetables for 3-4 minutes per side until tender and charred. Spread 2 tbsp pesto on 2 slices of sourdough bread. Layer grilled vegetables, 2 oz fresh mozzarella, and fresh basil on one bread slice. Top with second bread slice. Heat a panini press or skillet over medium heat and grill sandwich for 3-4 minutes per side until golden and cheese is melted.",
                    "prep_time": 15,
                    "cook_time": 8,
                    "calories": 460,
                    "protein": 18,
                    "fiber": 8,
                    "carbs": 52,
                    "fat": 20,
                    "ingredients": [
                        "2 slices sourdough bread",
                        "1 zucchini",
                        "1 red bell pepper",
                        "1 red onion",
                        "2 oz fresh mozzarella",
                        "2 tbsp pesto",
                        "fresh basil",
                        "1 tbsp olive oil"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "comfort",
                        "quick"
                    ]
                },
                {
                    "name": "Mexican Street Corn Bowl",
                    "meal_type": "lunch",
                    "description": "Grilled corn bowl with cotija cheese and lime",
                    "instructions": "Grill 2 ears of corn over medium-high heat for 10-12 minutes, turning occasionally, until charred and tender. Let cool slightly, then cut kernels from cobs. In a bowl, combine corn kernels with 1/2 cup black beans, 1/4 cup diced red onion, and 1/4 cup chopped cilantro. In a small bowl, mix juice of 1 lime, 2 tbsp mayonnaise, 1 tsp chili powder, and salt. Pour dressing over corn mixture and toss well. Top with 1/4 cup crumbled cotija cheese and additional chili powder.",
                    "prep_time": 15,
                    "cook_time": 12,
                    "calories": 440,
                    "protein": 16,
                    "fiber": 12,
                    "carbs": 58,
                    "fat": 18,
                    "ingredients": [
                        "2 ears corn",
                        "1/2 cup black beans",
                        "1/4 cup cotija cheese",
                        "2 tbsp mayonnaise",
                        "1 lime",
                        "1 tsp chili powder",
                        "fresh cilantro",
                        "red onion"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "high_fiber",
                        "quick"
                    ]
                },
                {
                    "name": "Sushi Bowl with Edamame",
                    "meal_type": "lunch",
                    "description": "Deconstructed sushi bowl with fresh fish and vegetables",
                    "instructions": "Cook 1 cup sushi rice according to package directions and let cool slightly. In a bowl, add cooled rice and top with 4 oz cubed fresh salmon or tuna, 1/2 cup steamed edamame, 1/4 cup shredded carrots, 1/4 cup sliced cucumber, and 1 avocado (sliced). In a small bowl, mix 2 tbsp soy sauce, 1 tsp rice vinegar, and 1 tsp sesame seeds. Drizzle sauce over bowl. Garnish with pickled ginger and wasabi if desired.",
                    "prep_time": 20,
                    "cook_time": 15,
                    "calories": 480,
                    "protein": 28,
                    "fiber": 8,
                    "carbs": 52,
                    "fat": 18,
                    "ingredients": [
                        "1 cup sushi rice",
                        "4 oz fresh salmon or tuna",
                        "1/2 cup edamame",
                        "1 avocado",
                        "1/4 cup carrots",
                        "1/4 cup cucumber",
                        "2 tbsp soy sauce",
                        "sesame seeds"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "omega_3",
                        "quick"
                    ]
                }
            ]
        
        elif meal_type == "dinner":
            return [
                {
                    "name": "Coconut Curry with Tofu",
                    "meal_type": "dinner",
                    "description": "Creamy Thai curry with tofu and vegetables",
                    "instructions": "Press 1 block firm tofu to remove excess water, then cut into 1-inch cubes. Heat 1 tbsp coconut oil in a large pot over medium heat. Add 1 diced onion and cook for 5 minutes until soft. Add 2 cloves minced garlic and 1 tbsp grated ginger, cook for 1 minute. Add 1 tbsp red curry paste and cook for 30 seconds. Add 1 can (13.5 oz) coconut milk, 1 cup vegetable broth, 2 cups mixed vegetables (broccoli, bell peppers, snap peas), and tofu cubes. Simmer for 10-15 minutes until vegetables are tender. Season with soy sauce and lime juice. Serve over jasmine rice.",
                    "prep_time": 15,
                    "cook_time": 20,
                    "calories": 480,
                    "protein": 24,
                    "fiber": 8,
                    "carbs": 42,
                    "fat": 28,
                    "ingredients": [
                        "1 block firm tofu",
                        "1 can coconut milk",
                        "1 tbsp red curry paste",
                        "2 cups mixed vegetables",
                        "1 onion",
                        "2 cloves garlic",
                        "1 tbsp ginger",
                        "soy sauce",
                        "lime juice"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "high_fiber",
                        "anti_inflammatory"
                    ]
                },
                {
                    "name": "Lemon Herb Grilled Chicken",
                    "meal_type": "dinner",
                    "description": "Juicy grilled chicken with bright lemon and herbs",
                    "instructions": "In a bowl, mix 1/4 cup olive oil, juice of 1 lemon, 2 tbsp fresh parsley (chopped), 1 tbsp fresh thyme, 2 cloves minced garlic, salt, and pepper. Add 4 chicken breasts and marinate for at least 30 minutes (up to 4 hours). Preheat grill to medium-high heat. Grill chicken for 6-8 minutes per side until internal temperature reaches 165°F. Let rest for 5 minutes before slicing. Serve with grilled vegetables and a side of quinoa.",
                    "prep_time": 15,
                    "cook_time": 20,
                    "calories": 420,
                    "protein": 38,
                    "fiber": 4,
                    "carbs": 12,
                    "fat": 24,
                    "ingredients": [
                        "4 chicken breasts",
                        "1/4 cup olive oil",
                        "1 lemon",
                        "2 tbsp fresh parsley",
                        "1 tbsp fresh thyme",
                        "2 cloves garlic",
                        "salt and pepper"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "low_carb",
                        "gluten_free"
                    ]
                },
                {
                    "name": "Vegetable Pad Thai",
                    "meal_type": "dinner",
                    "description": "Classic Thai stir-fried noodles with vegetables",
                    "instructions": "Soak 8 oz rice noodles in warm water for 20 minutes, then drain. Heat 2 tbsp vegetable oil in a wok over high heat. Add 2 cloves minced garlic and 1 tbsp grated ginger, stir-fry for 30 seconds. Add 2 cups mixed vegetables (bell peppers, carrots, snap peas) and stir-fry for 3-4 minutes. Push vegetables to side, add 2 beaten eggs and scramble. Add drained noodles and sauce mixture (3 tbsp fish sauce, 2 tbsp tamarind paste, 1 tbsp sugar). Toss everything together for 2-3 minutes. Serve with bean sprouts, crushed peanuts, and lime wedges.",
                    "prep_time": 25,
                    "cook_time": 15,
                    "calories": 460,
                    "protein": 16,
                    "fiber": 8,
                    "carbs": 68,
                    "fat": 16,
                    "ingredients": [
                        "8 oz rice noodles",
                        "2 cups mixed vegetables",
                        "2 eggs",
                        "3 tbsp fish sauce",
                        "2 tbsp tamarind paste",
                        "1 tbsp sugar",
                        "crushed peanuts",
                        "lime wedges"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "high_carb",
                        "quick"
                    ]
                },
                {
                    "name": "Beef and Broccoli Stir-Fry",
                    "meal_type": "dinner",
                    "description": "Classic Chinese takeout made healthy at home",
                    "instructions": "Slice 1 lb beef sirloin into thin strips against the grain. In a bowl, toss beef with 1 tbsp soy sauce and 1 tbsp cornstarch. Heat 1 tbsp vegetable oil in a wok over high heat. Add beef and stir-fry for 2-3 minutes until browned. Remove beef and set aside. Add 1 tbsp oil to wok, add 3 cloves minced garlic and 1 tbsp ginger, stir-fry for 30 seconds. Add 4 cups broccoli florets and 1 sliced red bell pepper, stir-fry for 3-4 minutes until crisp-tender. Return beef to wok with sauce mixture (2 tbsp soy sauce, 1 tbsp oyster sauce, 1 tsp sesame oil). Toss for 1 minute. Serve over brown rice.",
                    "prep_time": 20,
                    "cook_time": 15,
                    "calories": 520,
                    "protein": 42,
                    "fiber": 8,
                    "carbs": 48,
                    "fat": 20,
                    "ingredients": [
                        "1 lb beef sirloin",
                        "4 cups broccoli",
                        "1 red bell pepper",
                        "2 tbsp soy sauce",
                        "1 tbsp oyster sauce",
                        "1 tbsp cornstarch",
                        "3 cloves garlic",
                        "1 tbsp ginger"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "quick"
                    ]
                },
                {
                    "name": "Eggplant Parmesan",
                    "meal_type": "dinner",
                    "description": "Italian comfort food with breaded eggplant and cheese",
                    "instructions": "Slice 1 large eggplant into 1/2-inch thick rounds. Sprinkle with salt and let sit for 30 minutes, then pat dry. Set up breading station with 1/2 cup flour, 2 beaten eggs, and 1 cup breadcrumbs mixed with 1/4 cup parmesan. Dip eggplant in flour, then egg, then breadcrumbs. Heat 1/2 cup olive oil in a large skillet over medium-high heat. Fry eggplant in batches for 3-4 minutes per side until golden. Drain on paper towels. In a baking dish, layer marinara sauce, eggplant slices, and mozzarella cheese. Repeat layers. Top with parmesan and bake at 375°F for 25-30 minutes until bubbly.",
                    "prep_time": 30,
                    "cook_time": 35,
                    "calories": 480,
                    "protein": 22,
                    "fiber": 12,
                    "carbs": 42,
                    "fat": 24,
                    "ingredients": [
                        "1 large eggplant",
                        "1 cup breadcrumbs",
                        "1/2 cup flour",
                        "2 eggs",
                        "2 cups marinara sauce",
                        "2 cups mozzarella",
                        "1/4 cup parmesan",
                        "1/2 cup olive oil"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "high_fiber",
                        "comfort"
                    ]
                }
            ]
        
        elif meal_type == "post_workout":
            return [
                {
                    "name": "Chocolate Recovery Mousse",
                    "meal_type": "post_workout",
                    "description": "Light and airy chocolate mousse with protein powder",
                    "instructions": "In a blender, combine 1 scoop chocolate protein powder, 1 cup plain Greek yogurt, 1/4 cup unsweetened almond milk, 1 tbsp cocoa powder, and 1 tsp vanilla extract. Blend on high speed for 60 seconds until smooth and airy. In a separate bowl, whip 1 egg white until stiff peaks form (2-3 minutes). Gently fold whipped egg white into chocolate mixture until combined. Divide into 2 serving glasses and refrigerate for 30 minutes to set. Top with fresh berries before serving.",
                    "prep_time": 10,
                    "cook_time": 0,
                    "calories": 280,
                    "protein": 24,
                    "fiber": 4,
                    "carbs": 18,
                    "fat": 8,
                    "ingredients": [
                        "1 scoop chocolate protein powder",
                        "1 cup Greek yogurt",
                        "1 egg white",
                        "1 tbsp cocoa powder",
                        "1/4 cup almond milk",
                        "1 tsp vanilla extract",
                        "fresh berries"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "low_carb",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Tuna and Crackers Recovery Plate",
                    "meal_type": "post_workout",
                    "description": "Simple tuna plate with whole grain crackers and vegetables",
                    "instructions": "Drain 1 can (5 oz) tuna and flake into a bowl. Add 2 tbsp Greek yogurt, 1 tsp Dijon mustard, 1/4 cup diced celery, and black pepper. Mix until combined. Arrange on a plate with 8 whole grain crackers, 1 cup cucumber slices, 1 cup cherry tomatoes, and 1/4 cup olives. The lean protein from tuna combined with complex carbs from crackers provides balanced recovery nutrition.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 380,
                    "protein": 34,
                    "fiber": 6,
                    "carbs": 28,
                    "fat": 14,
                    "ingredients": [
                        "1 can tuna",
                        "2 tbsp Greek yogurt",
                        "8 whole grain crackers",
                        "1 cup cucumber slices",
                        "1 cup cherry tomatoes",
                        "1/4 cup olives",
                        "1 tsp Dijon mustard"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "quick",
                        "omega_3"
                    ]
                },
                {
                    "name": "Protein Hot Chocolate",
                    "meal_type": "post_workout",
                    "description": "Warm, comforting hot chocolate with protein powder",
                    "instructions": "Heat 1.5 cups milk in a small saucepan over medium heat until warm but not boiling. Remove from heat and whisk in 1 scoop chocolate protein powder and 1 tbsp cocoa powder until completely dissolved. Add 1 tsp vanilla extract and a pinch of cinnamon. Return to low heat and whisk for 1 minute until warm and frothy. Pour into a mug and top with mini marshmallows if desired. The warm temperature helps relax muscles while protein supports recovery.",
                    "prep_time": 5,
                    "cook_time": 5,
                    "calories": 300,
                    "protein": 24,
                    "fiber": 4,
                    "carbs": 24,
                    "fat": 8,
                    "ingredients": [
                        "1 scoop chocolate protein powder",
                        "1.5 cups milk",
                        "1 tbsp cocoa powder",
                        "1 tsp vanilla extract",
                        "pinch of cinnamon",
                        "mini marshmallows (optional)"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "comfort",
                        "quick"
                    ]
                },
                {
                    "name": "Chicken and Rice Recovery Bowl",
                    "meal_type": "post_workout",
                    "description": "Simple bowl with chicken, brown rice, and vegetables",
                    "instructions": "Cook 1/2 cup brown rice according to package directions. Season 6 oz chicken breast with salt, pepper, and garlic powder. Heat 1 tsp olive oil in a skillet over medium-high heat and cook chicken for 5-6 minutes per side until cooked through. Let rest for 3 minutes, then dice. Steam 1 cup mixed vegetables (broccoli, carrots) for 3-4 minutes. Assemble bowl with brown rice, diced chicken, and steamed vegetables. Drizzle with 1 tbsp soy sauce and sprinkle with sesame seeds.",
                    "prep_time": 10,
                    "cook_time": 20,
                    "calories": 480,
                    "protein": 42,
                    "fiber": 6,
                    "carbs": 48,
                    "fat": 14,
                    "ingredients": [
                        "6 oz chicken breast",
                        "1/2 cup brown rice",
                        "1 cup mixed vegetables",
                        "1 tbsp soy sauce",
                        "1 tsp olive oil",
                        "sesame seeds",
                        "garlic powder"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "high_carb",
                        "gluten_free"
                    ]
                },
                {
                    "name": "Protein Overnight Oats",
                    "meal_type": "post_workout",
                    "description": "No-cook oats prepared the night before for quick recovery",
                    "instructions": "In a mason jar or container, combine 1/2 cup rolled oats, 1 scoop vanilla protein powder, 1 tbsp chia seeds, 1 tbsp ground flaxseed, and 1.5 cups almond milk. Stir well until protein powder is completely dissolved. Cover and refrigerate overnight or for at least 4 hours. In the morning, stir well and top with 1/2 cup mixed berries, 1 tbsp almond butter, and 1 tsp honey. The complex carbs provide sustained energy release while protein supports muscle repair.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 420,
                    "protein": 28,
                    "fiber": 12,
                    "carbs": 52,
                    "fat": 14,
                    "ingredients": [
                        "1/2 cup rolled oats",
                        "1 scoop vanilla protein powder",
                        "1.5 cups almond milk",
                        "1 tbsp chia seeds",
                        "1 tbsp ground flaxseed",
                        "1/2 cup mixed berries",
                        "1 tbsp almond butter",
                        "1 tsp honey"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "high_fiber",
                        "meal_prep"
                    ]
                }
            ]
        
        return []
    
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
        """Process all meal types: add additional recipes"""
        total_added = 0
        
        for meal_type in self.meal_files.keys():
            print(f"\nAdding additional {meal_type} recipes...")
            
            # Load existing recipes
            recipes = self.load_recipes(meal_type)
            original_count = len(recipes)
            
            # Add additional recipes
            final_recipes = self.add_additional_recipes(meal_type, recipes)
            final_count = len(final_recipes)
            added_count = final_count - original_count
            total_added += added_count
            
            # Save updated recipes
            self.save_recipes(meal_type, final_recipes)
            
            print(f"  - Original recipes: {original_count}")
            print(f"  - Additional recipes added: {added_count}")
            print(f"  - Final total: {final_count}")
        
        # Update consolidated file
        self.update_consolidated_file()
        
        print(f"\n=== SUMMARY ===")
        print(f"Total additional recipes added: {total_added}")
        print("All recipe files have been updated successfully!")


def main():
    """Main function to run the additional recipe addition process"""
    print("🍳 RunCoach Additional Recipe Addition Script")
    print("=" * 50)
    print("This script will:")
    print("1. Add 5 more recipes to each meal category")
    print("2. Expand recipe diversity with international cuisines")
    print("3. Add more dietary preference options")
    print("=" * 50)
    
    adder = AdditionalRecipeAdder()
    adder.process_all_meals()
    
    print("\n✅ Additional recipe addition completed successfully!")
    print("📖 Recipe database has been expanded with more options")
    print("🍽️ Added more variety to each meal category")


if __name__ == "__main__":
    main()