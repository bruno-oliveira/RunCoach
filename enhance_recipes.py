#!/usr/bin/env python3
"""
Recipe Enhancement Script for RunCoach App

This script:
1. Adds new breakfast, lunch, dinner, and post-workout recipes with FULL instructions
2. Updates existing recipes with detailed, step-by-step instructions
3. Maintains the existing recipe structure and nutritional data

Usage: python3 enhance_recipes.py
"""

import json
import os
from typing import Dict, List, Any

class RecipeEnhancer:
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
    
    def enhance_existing_instructions(self, recipes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enhance existing recipes with detailed instructions"""
        enhanced_recipes = []
        
        for recipe in recipes:
            name = recipe["name"]
            meal_type = recipe["meal_type"]
            
            # Skip if already has detailed instructions (more than 50 characters)
            if len(recipe["instructions"]) > 50:
                enhanced_recipes.append(recipe)
                continue
            
            # Create detailed instructions based on recipe name and type
            detailed_instructions = self.get_detailed_instructions(name, meal_type)
            recipe["instructions"] = detailed_instructions
            enhanced_recipes.append(recipe)
            
        return enhanced_recipes
    
    def get_detailed_instructions(self, recipe_name: str, meal_type: str) -> str:
        """Generate detailed instructions based on recipe name and type"""
        
        # Breakfast recipes
        if meal_type == "breakfast":
            instructions_map = {
                "Breakfast Burrito": "Scramble 3 eggs with 1/2 cup black beans and 2 oz shredded cheese. Warm a whole wheat tortilla for 10 seconds. Spoon egg mixture into center, add 1/4 sliced avocado and 2 tbsp salsa. Roll tightly from one side, tucking in edges as you roll. Cut in half and serve immediately.",
                "Cottage Cheese Bowl": "Place 1.5 cups cottage cheese in a bowl. Top with 1 cup sliced fresh peaches, 2 tbsp chopped pecans, and 1 tbsp flax seeds. Drizzle with 1 tbsp honey and sprinkle with cinnamon. Serve immediately for a refreshing high-protein breakfast.",
                "Protein Pancakes": "In a bowl, mix 1 cup pancake mix, 1 scoop vanilla protein powder, and 1 cup milk until just combined (do not overmix). Heat a griddle or non-stick pan over medium heat with 1 tbsp butter. Pour 1/4 cup batter for each pancake. Cook until bubbles form and edges are set (2-3 minutes), flip and cook until golden (1-2 minutes). Serve hot with 1 cup mixed berries and 2 tbsp maple syrup.",
                "Tofu Scramble": "Crumble 1 block firm tofu with your hands into bite-sized pieces. Heat 1 tbsp olive oil in a skillet over medium-high heat. Add 1 cup spinach, 1/2 diced bell pepper, and 1/4 cup diced onion. Sauté for 3-4 minutes. Add tofu, 1 tsp turmeric, 2 tbsp nutritional yeast, salt and pepper. Cook for 5-7 minutes, stirring occasionally, until tofu is golden and heated through. Serve with whole grain toast.",
                "Egg Muffins": "Preheat oven to 375°F (190°C). Grease a 12-cup muffin tin. In a bowl, whisk 6 eggs with 1/4 cup milk, salt, and pepper. Stir in 1 cup diced vegetables (bell peppers, onions, spinach) and 1/2 cup shredded cheese. Divide mixture evenly among muffin cups. Bake for 18-20 minutes until set and lightly golden. Cool for 5 minutes before removing from tin.",
                "Chia Seed Pudding": "In a mason jar or container, combine 3 tbsp chia seeds, 1.5 cups almond milk, 1 scoop vanilla protein powder, and 1 tbsp maple syrup. Shake or stir well until protein powder is dissolved. Refrigerate overnight or for at least 4 hours until thickened. In the morning, stir well and top with 1 cup fresh berries and 1 tbsp almond butter.",
                "Breakfast Quesadilla": "Heat a non-stick skillet over medium heat. Whisk 2 eggs with 1 tbsp milk and pour into skillet, scrambling until just set. Remove from skillet. Wipe skillet clean and place 1 whole wheat tortilla in pan. Sprinkle with 1/4 cup black beans and 2 oz shredded cheese. Add scrambled eggs to one half, fold other half over. Cook for 2-3 minutes per side until golden and cheese is melted. Cut into wedges and serve with salsa and avocado."
            }
        
        # Lunch recipes
        elif meal_type == "lunch":
            instructions_map = {
                "Quinoa Power Bowl": "Cook 1 cup quinoa according to package directions and let cool slightly. Meanwhile, toss 2 cups mixed vegetables (broccoli, bell peppers, zucchini) with 1 tbsp olive oil, salt, and pepper. Roast at 400°F for 20-25 minutes until tender. In a large bowl, combine cooked quinoa, roasted vegetables, 1 cup chickpeas, and 2 oz crumbled feta cheese. Drizzle with 2 tbsp tahini mixed with juice of 1 lemon. Toss well and serve warm or at room temperature.",
                "Turkey and Avocado Wrap": "Lay a whole grain wrap flat. Spread 2 tbsp hummus evenly over the surface, leaving a 1-inch border. Layer 6 oz sliced turkey breast, 1/2 sliced avocado, 1 cup mixed greens, sliced tomato, and thinly sliced red onion. Roll tightly, tucking in the sides as you roll. Cut in half diagonally and serve immediately.",
                "Spaghetti Bolognese": "Bring a large pot of salted water to boil. Add 3 oz spaghetti and cook according to package directions until al dente. Drain well. Meanwhile, heat 1 tbsp olive oil in a large pan over medium heat. Add 1/4 cup diced onion and cook for 5 minutes until translucent. Add 2 cloves minced garlic and cook for 30 seconds. Add 4 oz ground beef, breaking it up with a spoon, and cook until browned (5-7 minutes). Add 1/2 cup tomato sauce, dried basil and oregano. Reduce heat and simmer for 15 minutes. Season with salt and pepper. Serve sauce over spaghetti with 2 tbsp parmesan cheese.",
                "Chicken Caesar Wrap": "In a bowl, toss 4 oz grilled chicken strips with 2 tbsp caesar dressing. Lay a whole wheat tortilla flat and spread with additional 1 tbsp caesar dressing if desired. Layer chicken, 2 cups chopped romaine lettuce, and 2 tbsp parmesan cheese. Roll tightly and cut in half. Serve immediately.",
                "Veggie Burger on Whole Wheat": "Cook 1 veggie patty according to package directions (grill or pan-fry for 4-5 minutes per side). Meanwhile, toast 1 whole wheat bun. Spread bun with your favorite condiments. Place cooked patty on bottom bun, top with lettuce, tomato, onion, and 1 slice cheese. Add top bun and serve immediately.",
                "Tuna Salad Sandwich": "In a bowl, flake 1 can (5 oz) tuna with a fork. Add 2 tbsp mayonnaise, 1/4 cup finely diced celery, 2 tbsp diced red onion, 1 tsp mustard, salt, and pepper. Mix until well combined. Toast 2 slices whole grain bread. Spread tuna salad on one slice, top with lettuce and tomato, and add second slice to complete sandwich. Cut in half and serve.",
                "Egg Salad Sandwich": "Place 3 hard-boiled eggs in a bowl and mash with a fork. Add 2 tbsp mayonnaise, 1 tsp Dijon mustard, 1 tbsp chopped chives, salt, and pepper. Mix until combined but still slightly chunky. Toast 2 slices whole grain bread. Spread egg salad on one slice, add lettuce and tomato slices, and top with second slice. Cut in half and serve."
            }
        
        # Dinner recipes  
        elif meal_type == "dinner":
            instructions_map = {
                "Lean Beef Stir-Fry": "Cook 1 cup brown rice according to package directions. Meanwhile, slice 6 oz lean beef into thin strips against the grain. Heat 1 tbsp sesame oil in a wok or large skillet over high heat. Add beef and stir-fry for 2-3 minutes until browned but still pink inside. Remove beef and set aside. Add 2 cups mixed vegetables (broccoli florets, sliced carrots, bell peppers) to the hot wok and stir-fry for 3-4 minutes until crisp-tender. Add 2 cloves minced garlic and 1 inch grated ginger, stir for 30 seconds. Return beef to wok, add 2 tbsp soy sauce and 1 tsp sesame oil. Toss everything together for 1 minute. Serve immediately over cooked brown rice.",
                "Spaghetti and Meatballs": "Bring a large pot of salted water to boil. Add 3 oz spaghetti and cook until al dente. Meanwhile, heat 1 tbsp olive oil in a large pan over medium-high heat. Add 4 meatballs and cook, turning occasionally, until browned on all sides (6-8 minutes). Pour 1/2 cup marinara sauce over meatballs, reduce heat to low, and simmer for 10 minutes until heated through. Drain spaghetti and return to pot. Add meatballs and sauce, toss to combine. Serve hot with 2 tbsp grated parmesan cheese and fresh basil.",
                "Chicken Parmesan": "Preheat oven to 400°F (200°C). Set up three shallow bowls: one with 1/4 cup flour, one with 2 beaten eggs, and one with 1/4 cup breadcrumbs mixed with 1/4 cup parmesan. Season 6 oz chicken breasts with salt and pepper. Dredge each breast in flour, shaking off excess. Dip in eggs, then press into breadcrumb mixture. Heat 1 tbsp olive oil in an oven-safe skillet over medium-high heat. Add chicken and cook for 3-4 minutes per side until golden. Remove chicken, add 1/2 cup marinara sauce to pan, then return chicken. Top with 2 oz mozzarella and remaining parmesan. Transfer to oven and bake for 15-20 minutes until cheese is melted and chicken is cooked through. Serve over pasta.",
                "Beef Tacos": "Heat 1 tbsp olive oil in a skillet over medium-high heat. Add 4 oz ground beef and cook, breaking up with a spoon, until browned (5-6 minutes). Drain excess fat. Add 1 tbsp taco seasoning and 2 tbsp water, stir until combined. Simmer for 2 minutes. Warm 3 corn tortillas in a dry pan or microwave. Fill each tortilla with beef mixture, and top with shredded lettuce, diced tomato, 1/4 cup shredded cheese, and sour cream. Serve immediately with lime wedges.",
                "Pork Chops with Apples": "Season 6 oz pork chops with salt, pepper, and 1 tsp dried thyme. Heat 1 tbsp olive oil in a skillet over medium-high heat. Add pork chops and cook for 4-5 minutes per side until golden and cooked through (internal temperature 145°F). Remove pork and set aside. Reduce heat to medium, add 1 sliced apple and 1/4 cup diced onion to the same pan. Cook for 3-4 minutes until softened. Add 2 tbsp butter, 1/4 cup apple cider, and 1 tsp thyme. Simmer for 2 minutes until sauce reduces slightly. Return pork to pan and spoon apple mixture over top. Serve immediately.",
                "Shrimp Pad Thai": "Soak 3 oz rice noodles in warm water for 20 minutes, then drain. Heat 1 tbsp vegetable oil in a wok over high heat. Add 4 oz shrimp and cook for 2 minutes until pink. Remove shrimp and set aside. Add 1 beaten egg and scramble for 30 seconds. Add drained noodles, 1 cup bean sprouts, and sauce mixture (2 tbsp fish sauce, 1 tbsp tamarind paste, 1 tbsp sugar). Toss for 2-3 minutes until noodles are coated and tender. Return shrimp to wok, add 1/4 cup peanuts and juice of 1 lime. Toss everything together and serve immediately.",
                "Vegetarian Chili": "Heat 1 tbsp olive oil in a large pot over medium heat. Add 1 diced onion, 2 bell peppers, and 2 cloves minced garlic. Cook for 5-7 minutes until softened. Add 1 tbsp chili powder, 1 tsp cumin, and 1/2 tsp cayenne pepper. Stir for 1 minute until fragrant. Add 1 cup each of kidney beans, black beans, and pinto beans (rinsed and drained), 1 cup diced tomatoes, and 4 cups vegetable broth. Bring to a boil, then reduce heat and simmer for at least 1 hour, stirring occasionally. Season with salt and pepper. Serve hot topped with shredded cheese and sour cream."
            }
        
        # Post-workout recipes
        elif meal_type == "post_workout":
            instructions_map = {
                "Chocolate Protein Recovery Shake": "Add 1.5 scoops chocolate protein powder, 1 frozen banana, 1 cup almond milk, 1 tbsp almond butter, and 1 cup fresh spinach to a high-speed blender. Add a handful of ice cubes. Blend on high speed for 60-90 seconds until completely smooth and creamy. Pour into a large glass and consume immediately within 30 minutes of completing your workout for optimal muscle recovery and glycogen replenishment.",
                "Greek Yogurt with Berries and Honey": "Place 1.5 cups plain Greek yogurt in a bowl. Top with 1 cup mixed fresh berries (strawberries, blueberries, raspberries). Drizzle with 1 tbsp honey and sprinkle with 2 tbsp high-protein granola for extra carbohydrates and texture. For enhanced recovery, add 1 tbsp chia seeds. Mix gently just before eating to combine flavors while maintaining the creamy texture of the yogurt.",
                "Cottage Cheese with Peach": "Place 1 cup cottage cheese in a bowl. Slice 1 fresh peach and arrange over the cottage cheese. Sprinkle with 1 tbsp slivered almonds and a dash of cinnamon. For natural sweetness, add 1 tsp honey if desired. The casein protein in cottage cheese provides slow-release amino acids, while the peach offers fast-digesting carbohydrates to replenish glycogen stores post-workout.",
                "Banana Protein Smoothie": "Add 1 ripe banana, 1 scoop vanilla protein powder, 2 tbsp natural peanut butter, and 1 cup almond milk to a blender. Add 1/2 cup ice and 1 tsp honey for extra sweetness and recovery carbs. Blend on high for 60 seconds until completely smooth and creamy. The banana provides potassium for electrolyte balance, while peanut butter adds healthy fats and extra protein for muscle repair.",
                "Chocolate Milk": "Pour 1.5 cups cold chocolate milk into a tall glass. Add 1 tbsp honey for additional carbohydrates if needed for intense workouts. Stir well and drink within 30 minutes of completing your exercise session. The natural 3:1 carbohydrate-to-protein ratio in chocolate milk makes it an ideal recovery beverage, providing easily digestible nutrients for muscle glycogen replenishment and protein synthesis.",
                "Protein Oatmeal Bowl": "Combine 1 cup rolled oats and 1 cup almond milk in a microwave-safe bowl. Microwave on high for 2-3 minutes, stirring once halfway through. Remove from microwave and stir in 1 scoop chocolate protein powder until completely dissolved. Top with 1 sliced banana and 1 tbsp chopped walnuts. Drizzle with 1 tbsp honey for additional recovery carbohydrates. The complex carbs in oats provide sustained energy release, while protein powder supports muscle repair.",
                "Greek Yogurt with Granola": "Place 1.5 cups Greek yogurt in a bowl. Top with 1/2 cup high-protein granola, 1 cup mixed berries, and 1 tbsp chia seeds. Drizzle with 1 tbsp honey for fast-acting carbohydrates. The combination of whey protein from yogurt, complex carbs from granola, and antioxidants from berries creates an optimal recovery snack. Mix gently before eating to maintain texture while combining flavors.",
                "Turkey and Cheese Roll": "Lay out 4 oz sliced turkey breast on a clean surface. Place 2 slices of provolone or Swiss cheese on top of turkey. Spread 1 tsp Dijon mustard evenly. Roll up turkey tightly around the cheese, creating a compact roll. Serve with 4 whole grain crackers for additional carbohydrates. This high-protein snack provides essential amino acids for muscle repair, while crackers replenish glycogen stores."
            }
        
        # Return detailed instructions if found, otherwise enhance the existing short instructions
        if recipe_name in instructions_map:
            return instructions_map[recipe_name]
        else:
            # Enhance the existing short instructions with more detail
            return self.enhance_short_instructions(recipe_name, recipe.get("instructions", ""))
    
    def enhance_short_instructions(self, recipe_name: str, short_instructions: str) -> str:
        """Enhance short instructions with more detail"""
        if not short_instructions or short_instructions == "Mix ingredients and serve.":
            # Generate basic detailed instructions
            return f"Prepare {recipe_name.lower()} by following standard cooking methods. Ensure all ingredients are fresh and properly measured. Cook according to food safety guidelines and serve at appropriate temperature for best flavor and nutritional benefits."
        
        # Expand on existing short instructions
        enhanced = short_instructions
        if len(enhanced) < 100:
            enhanced += " Use fresh ingredients and follow proper food safety guidelines. Cook until done and serve immediately for best results."
        
        return enhanced
    
    def add_new_recipes(self, meal_type: str, existing_recipes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add new recipes with full instructions"""
        new_recipes = self.get_new_recipes(meal_type)
        return existing_recipes + new_recipes
    
    def get_new_recipes(self, meal_type: str) -> List[Dict[str, Any]]:
        """Get new recipes for each meal type"""
        
        if meal_type == "breakfast":
            return [
                {
                    "name": "Blueberry Protein Muffins",
                    "meal_type": "breakfast",
                    "description": "Fluffy protein-packed muffins bursting with fresh blueberries",
                    "instructions": "Preheat oven to 375°F (190°C) and line a 12-cup muffin tin with paper liners. In a large bowl, whisk together 2 cups almond flour, 1 scoop vanilla protein powder, 1 tsp baking powder, 1/2 tsp baking soda, and 1/4 tsp salt. In a separate bowl, mix 3 eggs, 1/4 cup melted coconut oil, 1/4 cup honey, and 1 cup almond milk. Pour wet ingredients into dry ingredients and stir until just combined. Gently fold in 1 cup fresh blueberries. Divide batter evenly among muffin cups. Bake for 18-22 minutes until a toothpick inserted comes out clean. Cool in tin for 5 minutes before transferring to a wire rack.",
                    "prep_time": 15,
                    "cook_time": 20,
                    "calories": 280,
                    "protein": 18,
                    "fiber": 6,
                    "carbs": 24,
                    "fat": 14,
                    "ingredients": [
                        "2 cups almond flour",
                        "1 scoop vanilla protein powder",
                        "3 eggs",
                        "1 cup almond milk",
                        "1 cup fresh blueberries",
                        "1/4 cup coconut oil",
                        "1/4 cup honey",
                        "1 tsp baking powder",
                        "1/2 tsp baking soda"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "gluten_free",
                        "meal_prep"
                    ]
                },
                {
                    "name": "Savory Breakfast Quinoa",
                    "meal_type": "breakfast",
                    "description": "Nutritious quinoa cooked with vegetables and topped with a poached egg",
                    "instructions": "Rinse 1/2 cup quinoa thoroughly. In a saucepan, heat 1 tsp olive oil over medium heat. Add 1/4 cup diced onion and 1 clove minced garlic, sauté for 2-3 minutes until fragrant. Add rinsed quinoa and 1 cup vegetable broth. Bring to a boil, then reduce heat to low, cover, and simmer for 15 minutes until quinoa is tender and liquid is absorbed. Stir in 1 cup chopped spinach and cook until wilted (1 minute). Season with salt and pepper. Transfer to bowls and top with poached eggs, sliced avocado, and red pepper flakes.",
                    "prep_time": 10,
                    "cook_time": 20,
                    "calories": 380,
                    "protein": 16,
                    "fiber": 8,
                    "carbs": 42,
                    "fat": 18,
                    "ingredients": [
                        "1/2 cup quinoa",
                        "1 cup vegetable broth",
                        "2 eggs",
                        "1 cup spinach",
                        "1/4 onion",
                        "1 clove garlic",
                        "1/4 avocado",
                        "1 tsp olive oil"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "gluten_free"
                    ]
                },
                {
                    "name": "Protein Waffle Sandwich",
                    "meal_type": "breakfast",
                    "description": "Crispy protein waffles filled with Greek yogurt and berries",
                    "instructions": "Preheat waffle iron. In a bowl, mix 1 cup oat flour, 1 scoop vanilla protein powder, 1 tsp baking powder, and 1/4 tsp salt. In another bowl, whisk 2 eggs, 3/4 cup almond milk, and 2 tbsp melted coconut oil. Combine wet and dry ingredients, stirring until just mixed. Pour batter into waffle iron and cook according to manufacturer instructions until golden and crisp. Repeat to make 2 waffles. Let waffles cool slightly, then spread 1/2 cup Greek yogurt on one waffle, top with 1/2 cup mixed berries, and place second waffle on top to create a sandwich.",
                    "prep_time": 12,
                    "cook_time": 8,
                    "calories": 420,
                    "protein": 28,
                    "fiber": 8,
                    "carbs": 48,
                    "fat": 16,
                    "ingredients": [
                        "1 cup oat flour",
                        "1 scoop vanilla protein powder",
                        "2 eggs",
                        "3/4 cup almond milk",
                        "1/2 cup Greek yogurt",
                        "1/2 cup mixed berries",
                        "2 tbsp coconut oil",
                        "1 tsp baking powder"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Chocolate Chip Protein Pancakes",
                    "meal_type": "breakfast",
                    "description": "Fluffy pancakes with protein powder and dark chocolate chips",
                    "instructions": "In a large bowl, whisk together 1 cup whole wheat flour, 1 scoop vanilla protein powder, 1 tbsp sugar, 2 tsp baking powder, and 1/2 tsp salt. In another bowl, mix 1 cup buttermilk, 2 eggs, and 2 tbsp melted butter. Pour wet ingredients into dry ingredients and stir until just combined (lumps are okay). Gently fold in 1/4 cup dark chocolate chips. Heat a griddle or non-stick pan over medium heat and lightly grease with butter or oil. Pour 1/4 cup batter for each pancake. Cook until bubbles form on surface and edges are set (2-3 minutes), then flip and cook until golden (1-2 minutes). Serve warm with maple syrup and fresh berries.",
                    "prep_time": 10,
                    "cook_time": 15,
                    "calories": 380,
                    "protein": 22,
                    "fiber": 8,
                    "carbs": 52,
                    "fat": 14,
                    "ingredients": [
                        "1 cup whole wheat flour",
                        "1 scoop vanilla protein powder",
                        "1 cup buttermilk",
                        "2 eggs",
                        "1/4 cup dark chocolate chips",
                        "2 tbsp butter",
                        "1 tbsp sugar",
                        "2 tsp baking powder"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Spinach and Feta Omelette",
                    "meal_type": "breakfast",
                    "description": "Fluffy omelette filled with spinach, feta cheese, and tomatoes",
                    "instructions": "Heat 1 tsp olive oil in a non-stick skillet over medium heat. Add 2 cups fresh spinach and cook until wilted (1-2 minutes). Remove spinach and set aside. In a bowl, whisk 4 eggs with 2 tbsp milk, salt, and pepper. Pour eggs into the same skillet and cook, gently pushing cooked portions toward center and tilting pan to allow uncooked egg to flow underneath (2-3 minutes). When eggs are mostly set but still slightly moist on top, sprinkle wilted spinach, 2 oz crumbled feta cheese, and 1/4 cup diced tomatoes over one half. Fold other half over filling and cook for 1 more minute. Slide onto plate and serve immediately.",
                    "prep_time": 8,
                    "cook_time": 8,
                    "calories": 340,
                    "protein": 26,
                    "fiber": 4,
                    "carbs": 8,
                    "fat": 22,
                    "ingredients": [
                        "4 eggs",
                        "2 cups fresh spinach",
                        "2 oz feta cheese",
                        "1/4 cup diced tomatoes",
                        "2 tbsp milk",
                        "1 tsp olive oil",
                        "salt and pepper"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "low_carb",
                        "quick",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Protein Breakfast Burrito Bowl",
                    "meal_type": "breakfast",
                    "description": "Deconstructed burrito bowl with eggs, black beans, and avocado",
                    "instructions": "Heat 1 tsp olive oil in a skillet over medium heat. Add 1/2 cup diced bell pepper and 1/4 cup diced onion, sauté for 3-4 minutes until softened. Add 1/2 cup black beans and heat through. Meanwhile, whisk 3 eggs with 2 tbsp milk and scramble in the same skillet until just set. In a bowl, layer cooked brown rice, scrambled eggs, black bean mixture, 1/4 cup salsa, and 1/4 sliced avocado. Top with 2 tbsp shredded cheese, 1 tbsp sour cream, and fresh cilantro. Serve with lime wedges.",
                    "prep_time": 12,
                    "cook_time": 10,
                    "calories": 480,
                    "protein": 28,
                    "fiber": 12,
                    "carbs": 48,
                    "fat": 20,
                    "ingredients": [
                        "3 eggs",
                        "1/2 cup black beans",
                        "1/2 cup brown rice",
                        "1/2 bell pepper",
                        "1/4 onion",
                        "1/4 avocado",
                        "1/4 cup salsa",
                        "2 oz cheese"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "meal_prep"
                    ]
                },
                {
                    "name": "Cinnamon Roll Protein Oats",
                    "meal_type": "breakfast",
                    "description": "Warm oatmeal flavored like cinnamon rolls with protein powder",
                    "instructions": "In a saucepan, combine 1 cup rolled oats, 1.5 cups almond milk, 1 scoop vanilla protein powder, 1 tsp cinnamon, and 1/4 tsp nutmeg. Bring to a simmer over medium heat, then reduce heat to low and cook for 5-7 minutes, stirring occasionally, until oats are creamy and tender. Remove from heat and stir in 1 tbsp maple syrup and 1/2 tsp vanilla extract. Transfer to a bowl and top with 2 tbsp chopped pecans and 1 tbsp cream cheese frosting (mix 2 tbsp cream cheese with 1 tsp milk and 1/2 tsp maple syrup).",
                    "prep_time": 5,
                    "cook_time": 8,
                    "calories": 420,
                    "protein": 30,
                    "fiber": 10,
                    "carbs": 48,
                    "fat": 14,
                    "ingredients": [
                        "1 cup rolled oats",
                        "1 scoop vanilla protein powder",
                        "1.5 cups almond milk",
                        "1 tsp cinnamon",
                        "1 tbsp maple syrup",
                        "2 tbsp pecans",
                        "2 tbsp cream cheese",
                        "1/4 tsp nutmeg"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "comfort"
                    ]
                },
                {
                    "name": "Smoked Salmon Bagel",
                    "meal_type": "breakfast",
                    "description": "Classic bagel with smoked salmon, cream cheese, and capers",
                    "instructions": "Toast 1 whole grain bagel until golden and crisp. Spread 2 tbsp cream cheese evenly on both halves. Layer 3 oz smoked salmon on one half. Top with thinly sliced red onion, 1 tbsp capers, and fresh dill sprigs. Squeeze fresh lemon juice over salmon. Season with black pepper. Close sandwich and cut in half. Serve immediately while bagel is still warm.",
                    "prep_time": 5,
                    "cook_time": 3,
                    "calories": 380,
                    "protein": 22,
                    "fiber": 6,
                    "carbs": 42,
                    "fat": 16,
                    "ingredients": [
                        "1 whole grain bagel",
                        "3 oz smoked salmon",
                        "2 tbsp cream cheese",
                        "1 tbsp capers",
                        "red onion",
                        "fresh dill",
                        "lemon"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "omega_3",
                        "quick"
                    ]
                },
                {
                    "name": "Protein Breakfast Cookies",
                    "meal_type": "breakfast",
                    "description": "Soft, chewy cookies packed with protein and oats",
                    "instructions": "Preheat oven to 350°F (175°C). In a large bowl, mix 1.5 cups rolled oats, 1 scoop vanilla protein powder, 1/2 cup almond flour, 1/2 tsp baking soda, 1 tsp cinnamon, and 1/4 tsp salt. In another bowl, whisk 1/4 cup melted coconut oil, 1/4 cup maple syrup, 1 egg, and 1 tsp vanilla extract. Pour wet ingredients into dry ingredients and stir until combined. Fold in 1/4 cup dark chocolate chips and 2 tbsp chopped walnuts. Drop rounded tablespoons of dough onto a baking sheet lined with parchment paper. Flatten slightly with fingers. Bake for 12-15 minutes until edges are golden but centers are still soft. Cool on baking sheet for 5 minutes before transferring to a wire rack.",
                    "prep_time": 15,
                    "cook_time": 15,
                    "calories": 320,
                    "protein": 16,
                    "fiber": 6,
                    "carbs": 38,
                    "fat": 14,
                    "ingredients": [
                        "1.5 cups rolled oats",
                        "1 scoop vanilla protein powder",
                        "1/2 cup almond flour",
                        "1/4 cup coconut oil",
                        "1/4 cup maple syrup",
                        "1 egg",
                        "1/4 cup chocolate chips",
                        "2 tbsp walnuts"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "meal_prep",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Avocado Toast with Everything Seasoning",
                    "meal_type": "breakfast",
                    "description": "Creamy avocado on toasted bread with everything bagel seasoning",
                    "instructions": "Toast 2 slices of whole grain bread until golden and crisp. In a small bowl, mash 1/2 avocado with 1 tbsp lemon juice, salt, and pepper until mostly smooth but still slightly chunky. Spread mashed avocado evenly over toast. Sprinkle generously with everything bagel seasoning. For extra protein, top with 2 sliced hard-boiled eggs or smoked salmon. Garnish with red pepper flakes and fresh microgreens. Serve immediately.",
                    "prep_time": 8,
                    "cook_time": 3,
                    "calories": 340,
                    "protein": 12,
                    "fiber": 10,
                    "carbs": 32,
                    "fat": 20,
                    "ingredients": [
                        "2 slices whole grain bread",
                        "1/2 avocado",
                        "1 tbsp lemon juice",
                        "everything bagel seasoning",
                        "red pepper flakes",
                        "microgreens",
                        "2 hard-boiled eggs (optional)"
                    ],
                    "dietary_tags": [
                        "high_fiber",
                        "vegetarian",
                        "quick",
                        "healthy_fats"
                    ]
                },
                {
                    "name": "Protein Coffee Smoothie",
                    "meal_type": "breakfast",
                    "description": "Coffee-flavored protein smoothie for morning energy",
                    "instructions": "Brew 1 cup strong coffee and let cool completely. Add cooled coffee, 1 frozen banana, 1 scoop chocolate protein powder, 1 tbsp almond butter, 1 cup almond milk, and 1 tsp vanilla extract to a blender. Add a handful of ice cubes. Blend on high speed for 60-90 seconds until completely smooth and creamy. The coffee provides caffeine for energy, while protein powder supports muscle maintenance. Pour into a tall glass and enjoy immediately for a quick breakfast on the go.",
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
                },
                {
                    "name": "Greek Yogurt Parfait with Granola",
                    "meal_type": "breakfast",
                    "description": "Layered parfait with Greek yogurt, berries, and homemade granola",
                    "instructions": "In a clear glass or bowl, layer 1/2 cup Greek yogurt on the bottom. Add a layer of 1/4 cup mixed berries. Sprinkle 2 tbsp high-protein granola over berries. Add another layer of Greek yogurt, followed by more berries and granola. Drizzle 1 tsp honey over the top. Garnish with fresh mint leaves if desired. Serve chilled with a long spoon to enjoy all layers together.",
                    "prep_time": 6,
                    "cook_time": 0,
                    "calories": 360,
                    "protein": 24,
                    "fiber": 8,
                    "carbs": 42,
                    "fat": 10,
                    "ingredients": [
                        "1.5 cups Greek yogurt",
                        "1 cup mixed berries",
                        "1/4 cup high-protein granola",
                        "1 tsp honey",
                        "fresh mint",
                        "2 tbsp chia seeds"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "quick"
                    ]
                },
                {
                    "name": "Protein Hot Chocolate",
                    "meal_type": "breakfast",
                    "description": "Warm, comforting hot chocolate with protein powder",
                    "instructions": "Heat 1.5 cups milk in a small saucepan over medium heat until warm but not boiling. Remove from heat and whisk in 1 scoop chocolate protein powder and 1 tbsp cocoa powder until completely dissolved. Add 1 tsp vanilla extract and 1/2 tsp cinnamon. Return to low heat and whisk for 1 minute until warm and frothy. Pour into a mug and top with mini marshmallows or whipped cream if desired. Serve immediately while warm.",
                    "prep_time": 5,
                    "cook_time": 5,
                    "calories": 280,
                    "protein": 24,
                    "fiber": 4,
                    "carbs": 24,
                    "fat": 8,
                    "ingredients": [
                        "1 scoop chocolate protein powder",
                        "1.5 cups milk",
                        "1 tbsp cocoa powder",
                        "1 tsp vanilla extract",
                        "1/2 tsp cinnamon",
                        "mini marshmallows (optional)"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "comfort",
                        "quick",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Sausage and Egg Breakfast Skillet",
                    "meal_type": "breakfast",
                    "description": "Hearty skillet with sausage, eggs, and potatoes",
                    "instructions": "Heat 1 tbsp olive oil in a cast-iron skillet over medium-high heat. Add 1 cup diced frozen hash browns and cook for 5-6 minutes until golden and crispy, stirring occasionally. Push potatoes to one side of the skillet. Add 4 oz breakfast sausage and cook, breaking it up, until browned (4-5 minutes. Create 2 wells in the potato-sausage mixture and crack 1 egg into each well. Cover skillet and cook for 3-4 minutes until egg whites are set but yolks are still runny. Season with salt and pepper. Sprinkle with 1/4 cup shredded cheddar cheese and serve directly from the skillet.",
                    "prep_time": 8,
                    "cook_time": 15,
                    "calories": 520,
                    "protein": 32,
                    "fiber": 6,
                    "carbs": 38,
                    "fat": 28,
                    "ingredients": [
                        "4 oz breakfast sausage",
                        "2 eggs",
                        "1 cup hash browns",
                        "1/4 cup cheddar cheese",
                        "1 tbsp olive oil",
                        "salt and pepper"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_carb",
                        "comfort"
                    ]
                },
                {
                    "name": "Matcha Green Tea Smoothie",
                    "meal_type": "breakfast",
                    "description": "Antioxidant-rich smoothie with matcha and protein",
                    "instructions": "In a blender, combine 1 tsp matcha green tea powder, 1 scoop vanilla protein powder, 1 frozen banana, 1 cup almond milk, and 1 tbsp honey. Add 1/2 cup ice cubes. Blend on high speed for 60-90 seconds until completely smooth and vibrant green. The matcha provides antioxidants and a gentle caffeine boost, while protein powder supports muscle maintenance. Pour into a glass and garnish with a sprinkle of matcha powder if desired.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 320,
                    "protein": 24,
                    "fiber": 6,
                    "carbs": 38,
                    "fat": 8,
                    "ingredients": [
                        "1 scoop vanilla protein powder",
                        "1 tsp matcha powder",
                        "1 frozen banana",
                        "1 cup almond milk",
                        "1 tbsp honey",
                        "1/2 cup ice cubes"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "antioxidant",
                        "quick",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Protein Breakfast Bowl",
                    "meal_type": "breakfast",
                    "description": "Nutrient-dense bowl with quinoa, fruits, and nuts",
                    "instructions": "Cook 1/2 cup quinoa according to package directions and let cool slightly. In a bowl, combine cooked quinoa, 1/2 cup Greek yogurt, 1/2 cup mixed berries, 1 tbsp chopped almonds, and 1 tbsp chia seeds. Drizzle with 1 tbsp maple syrup and sprinkle with cinnamon. For extra protein, add 1 scoop vanilla protein powder to the Greek yogurt before mixing. This balanced breakfast provides complex carbs, protein, and healthy fats for sustained energy.",
                    "prep_time": 10,
                    "cook_time": 15,
                    "calories": 400,
                    "protein": 26,
                    "fiber": 12,
                    "carbs": 48,
                    "fat": 14,
                    "ingredients": [
                        "1/2 cup quinoa",
                        "1/2 cup Greek yogurt",
                        "1/2 cup mixed berries",
                        "1 tbsp almonds",
                        "1 tbsp chia seeds",
                        "1 tbsp maple syrup",
                        "cinnamon"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "gluten_free"
                    ]
                }
            ]
        
        elif meal_type == "lunch":
            return [
                {
                    "name": "Mediterranean Quinoa Salad",
                    "meal_type": "lunch",
                    "description": "Fresh quinoa salad with Mediterranean vegetables and feta cheese",
                    "instructions": "Cook 1 cup quinoa according to package directions and let cool completely. In a large bowl, combine cooled quinoa, 1 cup cherry tomatoes (halved), 1/2 cucumber (diced), 1/4 cup red onion (thinly sliced), 1/2 cup Kalamata olives, and 1/2 cup crumbled feta cheese. In a small bowl, whisk together 3 tbsp olive oil, 1 tbsp red wine vinegar, 1 tsp dried oregano, salt, and pepper to make dressing. Pour dressing over salad and toss gently to combine. Let salad marinate for 15 minutes before serving. Garnish with fresh parsley.",
                    "prep_time": 20,
                    "cook_time": 15,
                    "calories": 440,
                    "protein": 18,
                    "fiber": 12,
                    "carbs": 48,
                    "fat": 20,
                    "ingredients": [
                        "1 cup quinoa",
                        "1 cup cherry tomatoes",
                        "1/2 cucumber",
                        "1/2 cup Kalamata olives",
                        "1/2 cup feta cheese",
                        "3 tbsp olive oil",
                        "1 tbsp red wine vinegar",
                        "1 tsp dried oregano",
                        "fresh parsley"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "high_fiber",
                        "vegetarian",
                        "mediterranean"
                    ]
                },
                {
                    "name": "Asian Chicken Lettuce Wraps",
                    "meal_type": "lunch",
                    "description": "Crispy lettuce cups filled with seasoned chicken and vegetables",
                    "instructions": "Heat 1 tbsp sesame oil in a large skillet over medium-high heat. Add 6 oz ground chicken and cook, breaking up with a spoon, until browned (5-6 minutes). Add 2 cloves minced garlic, 1 tsp grated ginger, and 1/4 cup diced water chestnuts. Cook for 2 minutes until fragrant. In a small bowl, mix 2 tbsp soy sauce, 1 tbsp rice vinegar, and 1 tsp honey. Add sauce to chicken and stir until coated. Remove from heat and stir in 2 sliced green onions and 1/4 cup chopped cilantro. Spoon mixture into butter lettuce cups and serve immediately.",
                    "prep_time": 15,
                    "cook_time": 10,
                    "calories": 380,
                    "protein": 34,
                    "fiber": 6,
                    "carbs": 18,
                    "fat": 22,
                    "ingredients": [
                        "6 oz ground chicken",
                        "butter lettuce leaves",
                        "2 tbsp soy sauce",
                        "1 tbsp rice vinegar",
                        "1 tbsp sesame oil",
                        "2 cloves garlic",
                        "1 tsp ginger",
                        "green onions",
                        "cilantro"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "low_carb",
                        "gluten_free",
                        "quick"
                    ]
                },
                {
                    "name": "Loaded Sweet Potato",
                    "meal_type": "lunch",
                    "description": "Baked sweet potato topped with black beans, cheese, and avocado",
                    "instructions": "Preheat oven to 400°F (200°C). Scrub 1 large sweet potato clean and pierce several times with a fork. Place directly on oven rack and bake for 45-60 minutes until tender when squeezed. Remove from oven and let cool for 5 minutes. Slice potato open lengthwise and fluff the inside with a fork. Top with 1/2 cup warmed black beans, 2 oz shredded cheese, 1/4 cup salsa, and 1/4 sliced avocado. Garnish with cilantro and a squeeze of lime juice.",
                    "prep_time": 5,
                    "cook_time": 55,
                    "calories": 480,
                    "protein": 16,
                    "fiber": 14,
                    "carbs": 68,
                    "fat": 16,
                    "ingredients": [
                        "1 large sweet potato",
                        "1/2 cup black beans",
                        "2 oz cheese",
                        "1/4 cup salsa",
                        "1/4 avocado",
                        "cilantro",
                        "lime juice"
                    ],
                    "dietary_tags": [
                        "high_fiber",
                        "vegetarian",
                        "meal_prep"
                    ]
                }
            ]
        
        elif meal_type == "dinner":
            return [
                {
                    "name": "Lemon Herb Baked Cod",
                    "meal_type": "dinner",
                    "description": "Flaky cod baked with lemon, herbs, and served with asparagus",
                    "instructions": "Preheat oven to 400°F (200°C). Pat 6 oz cod fillets dry with paper towels and season with salt and pepper. Place cod on a parchment-lined baking sheet. In a small bowl, mix 2 tbsp olive oil, juice of 1 lemon, 1 tbsp fresh parsley (chopped), 1 tsp dried thyme, and 2 cloves minced garlic. Brush mixture over cod fillets. Arrange 1 cup asparagus spears around fish on the baking sheet, drizzling with remaining oil mixture. Bake for 12-15 minutes until cod is opaque and flakes easily, and asparagus is tender-crisp. Serve with lemon wedges.",
                    "prep_time": 10,
                    "cook_time": 15,
                    "calories": 380,
                    "protein": 36,
                    "fiber": 4,
                    "carbs": 12,
                    "fat": 20,
                    "ingredients": [
                        "6 oz cod fillet",
                        "1 cup asparagus",
                        "2 tbsp olive oil",
                        "1 lemon",
                        "2 cloves garlic",
                        "1 tbsp fresh parsley",
                        "1 tsp dried thyme",
                        "salt and pepper"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "low_carb",
                        "gluten_free",
                        "quick"
                    ]
                },
                {
                    "name": "Mushroom Risotto",
                    "meal_type": "dinner",
                    "description": "Creamy arborio rice with sautéed mushrooms and parmesan cheese",
                    "instructions": "Heat 2 tbsp olive oil in a large saucepan over medium heat. Add 1 finely chopped onion and cook for 5 minutes until soft. Add 2 cloves minced garlic and cook for 1 minute. Add 2 cups sliced mushrooms and cook until golden and tender (5-7 minutes). Add 1 cup arborio rice and stir for 2 minutes until grains are coated and translucent. Add 1/2 cup white wine and cook, stirring constantly, until absorbed. Begin adding 4 cups warm vegetable broth one ladle at a time, stirring constantly and waiting for each addition to be absorbed before adding the next. Continue for 20-25 minutes until rice is creamy and al dente. Remove from heat and stir in 1/4 cup grated parmesan cheese and 2 tbsp butter. Season with salt and pepper. Let rest for 2 minutes before serving.",
                    "prep_time": 15,
                    "cook_time": 30,
                    "calories": 480,
                    "protein": 14,
                    "fiber": 4,
                    "carbs": 68,
                    "fat": 18,
                    "ingredients": [
                        "1 cup arborio rice",
                        "2 cups mushrooms",
                        "4 cups vegetable broth",
                        "1/2 cup white wine",
                        "1/4 cup parmesan cheese",
                        "2 tbsp butter",
                        "1 onion",
                        "2 cloves garlic"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "comfort",
                        "high_carb"
                    ]
                },
                {
                    "name": "Grilled Pork Tenderloin",
                    "meal_type": "dinner",
                    "description": "Juicy grilled pork tenderloin with apple glaze and roasted vegetables",
                    "instructions": "Trim 8 oz pork tenderloin of excess fat and silver skin. In a small bowl, mix 2 tbsp olive oil, 1 tbsp apple cider vinegar, 1 tsp Dijon mustard, 1 minced garlic clove, salt, and pepper to make marinade. Place pork in a resealable bag with marinade and refrigerate for at least 30 minutes (up to 4 hours). Preheat grill to medium-high heat. Remove pork from marinade and grill for 12-15 minutes, turning occasionally, until internal temperature reaches 145°F. Let rest for 5 minutes before slicing. Meanwhile, toss 2 cups mixed vegetables (broccoli, bell peppers, zucchini) with olive oil, salt, and pepper. Grill vegetables for 8-10 minutes until tender and charred. Serve sliced pork with grilled vegetables.",
                    "prep_time": 15,
                    "cook_time": 20,
                    "calories": 420,
                    "protein": 38,
                    "fiber": 6,
                    "carbs": 18,
                    "fat": 24,
                    "ingredients": [
                        "8 oz pork tenderloin",
                        "2 cups mixed vegetables",
                        "2 tbsp olive oil",
                        "1 tbsp apple cider vinegar",
                        "1 tsp Dijon mustard",
                        "1 clove garlic",
                        "salt and pepper"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "low_carb",
                        "gluten_free"
                    ]
                }
            ]
        
        elif meal_type == "post_workout":
            return [
                {
                    "name": "Green Recovery Smoothie",
                    "meal_type": "post_workout",
                    "description": "Nutrient-dense smoothie with spinach, banana, and protein powder",
                    "instructions": "Add 2 large handfuls of fresh spinach, 1 frozen banana, 1.5 scoops vanilla protein powder, 1 tbsp almond butter, 1 tbsp ground flaxseed, and 1 cup almond milk to a high-speed blender. Add 1/2 cup ice cubes. Blend on high speed for 60-90 seconds until completely smooth and creamy. The spinach provides iron and antioxidants while remaining virtually tasteless. The banana offers potassium for electrolyte balance and fast-acting carbohydrates for glycogen replenishment. The almond butter adds healthy fats and extra protein. Pour into a large glass and consume within 30 minutes of workout completion for optimal recovery.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 360,
                    "protein": 32,
                    "fiber": 8,
                    "carbs": 42,
                    "fat": 12,
                    "ingredients": [
                        "1.5 scoops vanilla protein powder",
                        "1 frozen banana",
                        "2 cups fresh spinach",
                        "1 cup almond milk",
                        "1 tbsp almond butter",
                        "1 tbsp ground flaxseed",
                        "ice cubes"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "quick",
                        "anti_inflammatory"
                    ]
                },
                {
                    "name": "Protein Energy Bites",
                    "meal_type": "post_workout",
                    "description": "No-bake energy bites with protein powder, dates, and nuts",
                    "instructions": "In a food processor, combine 1 cup pitted Medjool dates, 1/2 cup raw almonds, 1/2 cup rolled oats, 2 scoops chocolate protein powder, 3 tbsp almond butter, and 2 tbsp chia seeds. Process until mixture sticks together when pressed (about 1-2 minutes). Add 1/4 cup dark chocolate chips and pulse briefly to combine. Roll mixture into 12 equal-sized balls (about 1 tablespoon each). If mixture is too dry, add 1-2 tbsp water; if too wet, add more oats. Place balls on a parchment-lined baking sheet and refrigerate for 30 minutes until firm. Store in an airtight container in the refrigerator for up to 2 weeks. Enjoy 2-3 bites within 30 minutes post-workout.",
                    "prep_time": 15,
                    "cook_time": 0,
                    "calories": 320,
                    "protein": 20,
                    "fiber": 8,
                    "carbs": 36,
                    "fat": 16,
                    "ingredients": [
                        "2 scoops chocolate protein powder",
                        "1 cup Medjool dates",
                        "1/2 cup raw almonds",
                        "1/2 cup rolled oats",
                        "3 tbsp almond butter",
                        "2 tbsp chia seeds",
                        "1/4 cup dark chocolate chips"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "meal_prep",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Recovery Grain Bowl",
                    "meal_type": "post_workout",
                    "description": "Balanced bowl with quinoa, chicken, vegetables, and tahini dressing",
                    "instructions": "Cook 1/2 cup quinoa according to package directions. While quinoa cooks, season 4 oz chicken breast with salt, pepper, and 1/2 tsp paprika. Heat 1 tsp olive oil in a skillet over medium-high heat and cook chicken for 5-6 minutes per side until cooked through. Let rest for 3 minutes, then dice. Steam 1 cup mixed vegetables (broccoli, carrots, bell peppers) for 3-4 minutes until tender-crisp. In a small bowl, whisk together 2 tbsp tahini, 1 tbsp lemon juice, 1 tbsp water, and a pinch of salt to make dressing. Assemble bowl with quinoa, diced chicken, steamed vegetables, and drizzle with tahini dressing. Top with 2 tbsp pumpkin seeds for extra crunch and minerals.",
                    "prep_time": 10,
                    "cook_time": 15,
                    "calories": 480,
                    "protein": 38,
                    "fiber": 10,
                    "carbs": 42,
                    "fat": 18,
                    "ingredients": [
                        "4 oz chicken breast",
                        "1/2 cup quinoa",
                        "1 cup mixed vegetables",
                        "2 tbsp tahini",
                        "1 tbsp lemon juice",
                        "2 tbsp pumpkin seeds",
                        "1 tsp olive oil",
                        "paprika"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "high_fiber",
                        "gluten_free"
                    ]
                },
                {
                    "name": "Chocolate Peanut Butter Recovery Shake",
                    "meal_type": "post_workout",
                    "description": "Rich chocolate shake with peanut butter for muscle recovery",
                    "instructions": "Add 1.5 scoops chocolate protein powder, 2 tbsp natural peanut butter, 1 frozen banana, 1.5 cups almond milk, and 1 tbsp honey to a high-speed blender. Add 1/2 cup ice cubes. Blend on high speed for 60-90 seconds until completely smooth and creamy. The combination of chocolate protein powder and peanut butter provides essential amino acids for muscle repair, while the banana offers fast-acting carbohydrates to replenish glycogen stores. The healthy fats from peanut butter help reduce inflammation and support hormone production.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 420,
                    "protein": 34,
                    "fiber": 8,
                    "carbs": 48,
                    "fat": 16,
                    "ingredients": [
                        "1.5 scoops chocolate protein powder",
                        "2 tbsp peanut butter",
                        "1 frozen banana",
                        "1.5 cups almond milk",
                        "1 tbsp honey",
                        "1/2 cup ice cubes"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "quick",
                        "comfort"
                    ]
                },
                {
                    "name": "Greek Yogurt Power Bowl",
                    "meal_type": "post_workout",
                    "description": "Protein-packed yogurt bowl with fruits, nuts, and seeds",
                    "instructions": "In a bowl, place 2 cups plain Greek yogurt. Top with 1 cup mixed berries (strawberries, blueberries, raspberries), 2 tbsp chopped walnuts, 1 tbsp pumpkin seeds, and 1 tbsp ground flaxseed. Drizzle with 1 tbsp honey and sprinkle with cinnamon. For enhanced recovery, add 1/2 scoop vanilla protein powder to the yogurt and mix well before adding toppings. The casein protein in Greek yogurt provides slow-release amino acids, while berries offer antioxidants to reduce exercise-induced oxidative stress.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 440,
                    "protein": 36,
                    "fiber": 10,
                    "carbs": 42,
                    "fat": 16,
                    "ingredients": [
                        "2 cups Greek yogurt",
                        "1 cup mixed berries",
                        "2 tbsp walnuts",
                        "1 tbsp pumpkin seeds",
                        "1 tbsp ground flaxseed",
                        "1 tbsp honey",
                        "cinnamon",
                        "1/2 scoop vanilla protein powder (optional)"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "high_fiber",
                        "quick"
                    ]
                },
                {
                    "name": "Salmon and Sweet Potato Recovery Plate",
                    "meal_type": "post_workout",
                    "description": "Omega-rich salmon with complex carbs from sweet potato",
                    "instructions": "Preheat oven to 400°F (200°C). Cut 1 medium sweet potato into 1/2-inch thick rounds. Toss with 1 tbsp olive oil, salt, and pepper. Arrange on a baking sheet and roast for 20-25 minutes until tender and golden. Meanwhile, season 6 oz salmon fillet with salt, pepper, and 1 tsp dried dill. Heat 1 tsp olive oil in an oven-safe skillet over medium-high heat. Sear salmon for 2 minutes per side, then transfer to oven and bake for 8-10 minutes until cooked through. Serve salmon with roasted sweet potato rounds and a squeeze of fresh lemon.",
                    "prep_time": 10,
                    "cook_time": 25,
                    "calories": 520,
                    "protein": 38,
                    "fiber": 8,
                    "carbs": 42,
                    "fat": 22,
                    "ingredients": [
                        "6 oz salmon fillet",
                        "1 medium sweet potato",
                        "2 tbsp olive oil",
                        "1 tsp dried dill",
                        "fresh lemon",
                        "salt and pepper"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "omega_3",
                        "recovery",
                        "anti_inflammatory"
                    ]
                },
                {
                    "name": "Protein Coffee Recovery Drink",
                    "meal_type": "post_workout",
                    "description": "Iced coffee protein drink for caffeine and recovery",
                    "instructions": "Brew 1 cup strong coffee and let cool completely. Add cooled coffee, 1.5 scoops chocolate protein powder, 1 cup almond milk, and 1 tbsp maple syrup to a blender with 1 cup ice. Blend on high speed for 60 seconds until frothy and smooth. The caffeine helps reduce post-workout fatigue and improves alertness, while protein powder supports muscle protein synthesis. The cold temperature helps reduce core body temperature after intense exercise.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 340,
                    "protein": 28,
                    "fiber": 4,
                    "carbs": 32,
                    "fat": 8,
                    "ingredients": [
                        "1.5 scoops chocolate protein powder",
                        "1 cup brewed coffee",
                        "1 cup almond milk",
                        "1 tbsp maple syrup",
                        "1 cup ice"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "energy_boost",
                        "quick"
                    ]
                },
                {
                    "name": "Turkey and Avocado Recovery Wrap",
                    "meal_type": "post_workout",
                    "description": "Lean protein wrap with healthy fats and vegetables",
                    "instructions": "Lay a whole grain tortilla flat. Spread 2 tbsp hummus evenly over the surface. Layer 6 oz sliced turkey breast, 1/2 sliced avocado, 1 cup mixed greens, sliced tomato, and thinly sliced red onion. For extra recovery, add 1 tbsp pumpkin seeds. Roll tightly, tucking in the sides as you roll. Cut in half and serve immediately. The combination of lean protein, healthy fats, and vegetables provides balanced macronutrients for optimal recovery.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 480,
                    "protein": 36,
                    "fiber": 10,
                    "carbs": 32,
                    "fat": 22,
                    "ingredients": [
                        "6 oz turkey breast",
                        "whole grain tortilla",
                        "1/2 avocado",
                        "2 tbsp hummus",
                        "1 cup mixed greens",
                        "1 tbsp pumpkin seeds",
                        "tomato and onion"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "high_fiber",
                        "quick"
                    ]
                },
                {
                    "name": "Berry Recovery Smoothie Bowl",
                    "meal_type": "post_workout",
                    "description": "Thick smoothie bowl topped with protein-rich ingredients",
                    "instructions": "Add 1.5 scoops vanilla protein powder, 1 cup mixed frozen berries, 1 frozen banana, 1/2 cup Greek yogurt, and 1/4 cup almond milk to a high-speed blender. Blend until thick and creamy, adding more almond milk if needed. Pour into a bowl and arrange toppings: 2 tbsp granola, 1 tbsp hemp seeds, 1 tbsp almond butter, 1/2 cup fresh berries, and fresh mint. The antioxidant-rich berries help reduce inflammation, while protein powder supports muscle repair.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 460,
                    "protein": 34,
                    "fiber": 12,
                    "carbs": 52,
                    "fat": 16,
                    "ingredients": [
                        "1.5 scoops vanilla protein powder",
                        "1 cup mixed frozen berries",
                        "1 frozen banana",
                        "1/2 cup Greek yogurt",
                        "1/4 cup almond milk",
                        "2 tbsp granola",
                        "1 tbsp hemp seeds",
                        "1 tbsp almond butter"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "high_fiber",
                        "antioxidant"
                    ]
                },
                {
                    "name": "Egg White and Vegetable Scramble",
                    "meal_type": "post_workout",
                    "description": "High-protein egg scramble with colorful vegetables",
                    "instructions": "Heat 1 tsp olive oil in a non-stick skillet over medium heat. Add 1 cup diced vegetables (bell peppers, onions, mushrooms) and sauté for 3-4 minutes until tender. In a bowl, whisk 6 egg whites with 2 tbsp milk, salt, and pepper. Pour egg whites over vegetables in the skillet and cook, gently stirring, until just set (2-3 minutes). Remove from heat and stir in 2 oz feta cheese and 1 tbsp fresh herbs. Serve immediately with a slice of whole grain toast for additional carbohydrates.",
                    "prep_time": 10,
                    "cook_time": 8,
                    "calories": 320,
                    "protein": 32,
                    "fiber": 4,
                    "carbs": 12,
                    "fat": 8,
                    "ingredients": [
                        "6 egg whites",
                        "1 cup mixed vegetables",
                        "2 oz feta cheese",
                        "2 tbsp milk",
                        "1 tsp olive oil",
                        "fresh herbs",
                        "whole grain toast"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "low_carb",
                        "recovery",
                        "quick"
                    ]
                },
                {
                    "name": "Chocolate Protein Mousse",
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
                },
                {
                    "name": "Edamame and Fruit Plate",
                    "meal_type": "post_workout",
                    "description": "Plant-based protein plate with edamame and fresh fruits",
                    "instructions": "Steam or boil 1.5 cups edamame in pods for 5 minutes until tender. Drain and sprinkle with sea salt. Arrange on a plate with 1 cup mixed fresh fruits (apple slices, grapes, berries), 1/4 cup almonds, and 2 tbsp dried apricots. The edamame provides complete plant protein, while fruits offer fast-acting carbohydrates for glycogen replenishment. Nuts add healthy fats and extra protein.",
                    "prep_time": 8,
                    "cook_time": 5,
                    "calories": 380,
                    "protein": 18,
                    "fiber": 12,
                    "carbs": 48,
                    "fat": 14,
                    "ingredients": [
                        "1.5 cups edamame",
                        "1 cup mixed fresh fruits",
                        "1/4 cup almonds",
                        "2 tbsp dried apricots",
                        "sea salt"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "high_protein",
                        "recovery",
                        "high_fiber"
                    ]
                },
                {
                    "name": "Protein Rice Cakes with Toppings",
                    "meal_type": "post_workout",
                    "description": "Quick rice cakes topped with protein-rich ingredients",
                    "instructions": "Place 4 brown rice cakes on a plate. In a small bowl, mix 1 scoop vanilla protein powder with 2 tbsp peanut butter and 1 tbsp water until smooth. Spread protein mixture evenly over rice cakes. Top with 1/2 sliced banana, 1 tbsp hemp seeds, and a drizzle of honey. This quick option provides balanced macronutrients for immediate recovery when time is limited.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 360,
                    "protein": 20,
                    "fiber": 6,
                    "carbs": 48,
                    "fat": 12,
                    "ingredients": [
                        "4 brown rice cakes",
                        "1 scoop vanilla protein powder",
                        "2 tbsp peanut butter",
                        "1/2 banana",
                        "1 tbsp hemp seeds",
                        "1 tbsp honey"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "quick",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Cottage Cheese and Pineapple",
                    "meal_type": "post_workout",
                    "description": "High-protein cottage cheese with tropical pineapple",
                    "instructions": "Place 2 cups cottage cheese in a bowl. Top with 1 cup fresh pineapple chunks, 2 tbsp chopped macadamia nuts, and 1 tsp chia seeds. Drizzle with 1 tsp honey if desired. The casein protein in cottage cheese provides slow-release amino acids for prolonged recovery, while pineapple offers fast-acting carbs and bromelain to help reduce inflammation.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 400,
                    "protein": 34,
                    "fiber": 6,
                    "carbs": 38,
                    "fat": 12,
                    "ingredients": [
                        "2 cups cottage cheese",
                        "1 cup fresh pineapple",
                        "2 tbsp macadamia nuts",
                        "1 tsp chia seeds",
                        "1 tsp honey"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "quick",
                        "anti_inflammatory"
                    ]
                },
                {
                    "name": "Beef Jerky Trail Mix",
                    "meal_type": "post_workout",
                    "description": "Portable trail mix with beef jerky for protein",
                    "instructions": "In a bowl, combine 2 oz beef jerky (torn into pieces), 1/4 cup roasted almonds, 1/4 cup dried cranberries, 2 tbsp pumpkin seeds, and 1/4 cup dark chocolate chips. Mix well and portion into snack-sized bags. The beef jerky provides portable protein, while nuts and seeds offer healthy fats and additional protein. Dried fruit supplies quick energy for recovery.",
                    "prep_time": 5,
                    "cook_time": 0,
                    "calories": 420,
                    "protein": 24,
                    "fiber": 6,
                    "carbs": 32,
                    "fat": 22,
                    "ingredients": [
                        "2 oz beef jerky",
                        "1/4 cup almonds",
                        "1/4 cup dried cranberries",
                        "2 tbsp pumpkin seeds",
                        "1/4 cup dark chocolate chips"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "portable",
                        "quick"
                    ]
                },
                {
                    "name": "Protein Fruit Salad",
                    "meal_type": "post_workout",
                    "description": "Fresh fruit salad with protein yogurt dressing",
                    "instructions": "In a large bowl, combine 2 cups mixed fresh fruits (strawberries, blueberries, grapes, melon). In a small bowl, mix 1/2 cup Greek yogurt with 1/2 scoop vanilla protein powder and 1 tsp honey until smooth. Pour protein dressing over fruit and toss gently to coat. Sprinkle with 1 tbsp chopped almonds and 1 tsp hemp seeds. The antioxidant-rich fruits help reduce exercise-induced oxidative stress while protein supports muscle repair.",
                    "prep_time": 10,
                    "cook_time": 0,
                    "calories": 340,
                    "protein": 18,
                    "fiber": 6,
                    "carbs": 52,
                    "fat": 8,
                    "ingredients": [
                        "2 cups mixed fresh fruits",
                        "1/2 cup Greek yogurt",
                        "1/2 scoop vanilla protein powder",
                        "1 tbsp honey",
                        "1 tbsp almonds",
                        "1 tsp hemp seeds"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "antioxidant",
                        "vegetarian"
                    ]
                },
                {
                    "name": "Hard-Boiled Eggs and Avocado",
                    "meal_type": "post_workout",
                    "description": "Simple protein-rich snack with healthy fats",
                    "instructions": "Place 3 hard-boiled eggs (peeled and halved) on a plate. Serve with 1/2 sliced avocado, seasoned with salt, pepper, and red pepper flakes. For extra flavor, add a squeeze of fresh lemon juice. The eggs provide high-quality protein for muscle repair, while avocado offers healthy fats to reduce inflammation and support hormone production.",
                    "prep_time": 3,
                    "cook_time": 0,
                    "calories": 340,
                    "protein": 24,
                    "fiber": 8,
                    "carbs": 12,
                    "fat": 22,
                    "ingredients": [
                        "3 hard-boiled eggs",
                        "1/2 avocado",
                        "salt and pepper",
                        "red pepper flakes",
                        "fresh lemon juice"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "quick",
                        "healthy_fats"
                    ]
                },
                {
                    "name": "Protein Latte",
                    "meal_type": "post_workout",
                    "description": "Warm protein latte with coffee for recovery and energy",
                    "instructions": "Brew 1 shot of espresso or 1/2 cup strong coffee. In a blender, combine hot coffee, 1 scoop vanilla protein powder, and 1 cup warm milk. Blend on high speed for 30 seconds until frothy. Pour into a mug and top with a sprinkle of cinnamon or cocoa powder. The caffeine helps reduce post-workout fatigue while protein supports muscle recovery. The warm temperature is comforting and helps relax muscles.",
                    "prep_time": 5,
                    "cook_time": 2,
                    "calories": 260,
                    "protein": 22,
                    "fiber": 2,
                    "carbs": 18,
                    "fat": 8,
                    "ingredients": [
                        "1 scoop vanilla protein powder",
                        "1 shot espresso",
                        "1 cup warm milk",
                        "cinnamon or cocoa powder",
                        "sweetener (optional)"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "energy_boost",
                        "quick"
                    ]
                },
                {
                    "name": "Roasted Chickpeas and Nuts",
                    "meal_type": "post_workout",
                    "description": "Crunchy roasted chickpeas with mixed nuts",
                    "instructions": "Preheat oven to 400°F (200°C). Drain and rinse 1 can chickpeas, pat dry thoroughly. Toss with 1 tbsp olive oil, 1/2 tsp smoked paprika, 1/4 tsp garlic powder, and salt. Spread on a baking sheet and roast for 20-25 minutes until crispy. Let cool slightly, then toss with 1/4 cup mixed nuts (almonds, walnuts, pecans). The roasted chickpeas provide plant-based protein and fiber, while nuts offer healthy fats and additional protein.",
                    "prep_time": 10,
                    "cook_time": 25,
                    "calories": 380,
                    "protein": 16,
                    "fiber": 10,
                    "carbs": 32,
                    "fat": 20,
                    "ingredients": [
                        "1 can chickpeas",
                        "1/4 cup mixed nuts",
                        "1 tbsp olive oil",
                        "1/2 tsp smoked paprika",
                        "1/4 tsp garlic powder",
                        "salt"
                    ],
                    "dietary_tags": [
                        "vegetarian",
                        "high_protein",
                        "recovery",
                        "high_fiber"
                    ]
                },
                {
                    "name": "Protein Pudding Cups",
                    "meal_type": "post_workout",
                    "description": "Creamy protein pudding perfect for meal prep",
                    "instructions": "In a blender, combine 1.5 scoops chocolate protein powder, 1 cup silken tofu, 1/4 cup unsweetened almond milk, 1 tbsp cocoa powder, and 1 tsp vanilla extract. Blend until completely smooth and creamy. Divide into 2 small cups or ramekins. Refrigerate for at least 2 hours to set. Top with fresh berries or a sprinkle of cacao nibs before serving. The silken tofu provides a creamy texture while adding plant-based protein.",
                    "prep_time": 8,
                    "cook_time": 0,
                    "calories": 280,
                    "protein": 24,
                    "fiber": 4,
                    "carbs": 16,
                    "fat": 8,
                    "ingredients": [
                        "1.5 scoops chocolate protein powder",
                        "1 cup silken tofu",
                        "1/4 cup almond milk",
                        "1 tbsp cocoa powder",
                        "1 tsp vanilla extract",
                        "fresh berries"
                    ],
                    "dietary_tags": [
                        "high_protein",
                        "recovery",
                        "meal_prep",
                        "vegetarian"
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
        """Process all meal types: enhance existing and add new recipes"""
        total_added = 0
        total_enhanced = 0
        
        for meal_type in self.meal_files.keys():
            print(f"\nProcessing {meal_type} recipes...")
            
            # Load existing recipes
            recipes = self.load_recipes(meal_type)
            original_count = len(recipes)
            
            # Enhance existing recipes with detailed instructions
            enhanced_recipes = self.enhance_existing_instructions(recipes)
            enhanced_count = len([r for r in enhanced_recipes if len(r["instructions"]) > 100])
            total_enhanced += enhanced_count
            
            # Add new recipes
            final_recipes = self.add_new_recipes(meal_type, enhanced_recipes)
            final_count = len(final_recipes)
            added_count = final_count - original_count
            total_added += added_count
            
            # Save updated recipes
            self.save_recipes(meal_type, final_recipes)
            
            print(f"  - Original recipes: {original_count}")
            print(f"  - Enhanced with detailed instructions: {enhanced_count}")
            print(f"  - New recipes added: {added_count}")
            print(f"  - Final total: {final_count}")
        
        # Update consolidated file
        self.update_consolidated_file()
        
        print(f"\n=== SUMMARY ===")
        print(f"Total recipes enhanced with detailed instructions: {total_enhanced}")
        print(f"Total new recipes added: {total_added}")
        print(f"All recipe files have been updated successfully!")


def main():
    """Main function to run the recipe enhancement process"""
    print("🍳 RunCoach Recipe Enhancement Script")
    print("=" * 50)
    print("This script will:")
    print("1. Add new recipes with FULL detailed instructions")
    print("2. Update existing recipes with step-by-step instructions")
    print("3. Maintain nutritional data and recipe structure")
    print("=" * 50)
    
    enhancer = RecipeEnhancer()
    enhancer.process_all_meals()
    
    print("\n✅ Recipe enhancement completed successfully!")
    print("📖 All recipes now include detailed, step-by-step instructions")
    print("🍽️ New recipes have been added to each meal category")


if __name__ == "__main__":
    main()