#!/usr/bin/env python3
"""Add performance-focused and health-optimized recipes for runners."""

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

def add_performance_recipes():
    """Add performance-focused recipes to different meal types."""
    
    # Performance breakfast recipes
    breakfast_recipes = [
        {
            "name": "Runner's Nitrate-Rich Beet Porridge",
            "meal_type": "breakfast",
            "description": "Beetroot porridge with tart cherry and flax for blood flow and recovery",
            "instructions": "In a blender, combine cooked beetroot, rolled oats, almond milk, and tart cherry juice. Blend until smooth. Transfer to a saucepan and heat over medium heat, stirring constantly for 5-7 minutes until thickened. Stir in ground flaxseed, honey, and cinnamon. Remove from heat and let rest for 2 minutes. Top with walnuts, pomegranate seeds, and a drizzle of maple syrup. This nitrate-rich breakfast improves blood flow and oxygen delivery to muscles.",
            "prep_time": 10,
            "cook_time": 8,
            "calories": 420,
            "protein": 16,
            "fiber": 14,
            "carbs": 58,
            "fat": 16,
            "ingredients": [
                "1 small cooked beetroot",
                "1/2 cup rolled oats",
                "1 cup almond milk",
                "1/4 cup tart cherry juice",
                "1 tbsp ground flaxseed",
                "1 tbsp honey",
                "1/4 tsp cinnamon",
                "2 tbsp walnuts, chopped",
                "2 tbsp pomegranate seeds",
                "1 tsp maple syrup",
                "pinch of salt"
            ],
            "dietary_tags": [
                "nitrate_rich",
                "anti_inflammatory",
                "performance",
                "recovery",
                "gluten_free_option",
                "blood_flow"
            ]
        },
        {
            "name": "Adaptogenic Ashwagandha Chia Bowl",
            "meal_type": "breakfast",
            "description": "Stress-reducing chia bowl with ashwagandha, maca, and antioxidant berries",
            "instructions": "In a bowl, mix chia seeds with coconut milk, ashwagandha powder, maca powder, and maple syrup. Whisk well to prevent clumping. Let sit for 15 minutes or overnight in refrigerator. In the morning, stir in fresh berries, hemp seeds, and almond butter. Top with cacao nibs and goji berries. This adaptogenic breakfast helps reduce cortisol levels and improve stress response for better training adaptation.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 380,
            "protein": 14,
            "fiber": 18,
            "carbs": 32,
            "fat": 22,
            "ingredients": [
                "3 tbsp chia seeds",
                "1 cup coconut milk",
                "1/2 tsp ashwagandha powder",
                "1/2 tsp maca powder",
                "1 tbsp maple syrup",
                "1/2 cup mixed berries",
                "1 tbsp hemp seeds",
                "1 tsp almond butter",
                "1 tsp cacao nibs",
                "1 tsp goji berries",
                "pinch of salt"
            ],
            "dietary_tags": [
                "adaptogenic",
                "stress_reduction",
                "hormone_balance",
                "omega_3",
                "antioxidant",
                "gluten_free"
            ]
        },
        {
            "name": "Korean Ginseng Energy Porridge",
            "meal_type": "breakfast",
            "description": "Traditional Korean jook with ginseng, jujubes, and pine nuts for sustained energy",
            "instructions": "Rinse short-grain rice and soak for 10 minutes. Drain and place in a pot with 4 cups water or bone broth. Bring to a boil, then reduce heat to low and simmer for 30 minutes, stirring occasionally to prevent sticking. Add sliced ginseng root, jujubes, and pine nuts. Continue simmering for 15 minutes until porridge is thick and creamy. Stir in honey and sesame oil. Serve warm, garnished with additional pine nuts and a sprinkle of cinnamon.",
            "prep_time": 15,
            "cook_time": 45,
            "calories": 440,
            "protein": 18,
            "fiber": 6,
            "carbs": 68,
            "fat": 12,
            "ingredients": [
                "1/4 cup short-grain rice",
                "4 cups water or bone broth",
                "1 fresh ginseng root, sliced",
                "6 dried jujubes",
                "2 tbsp pine nuts",
                "1 tbsp honey",
                "1 tsp sesame oil",
                "1/4 tsp cinnamon",
                "pinch of salt"
            ],
            "dietary_tags": [
                "energy_boosting",
                "adaptogenic",
                "immune_supporting",
                "traditional",
                "gluten_free",
                "ginseng"
            ]
        }
    ]
    
    # Performance lunch recipes
    lunch_recipes = [
        {
            "name": "Mediterranean Sardine Power Bowl",
            "meal_type": "lunch",
            "description": "Omega-3 rich sardines with anti-inflammatory olives, capers, and leafy greens",
            "instructions": "In a large bowl, combine mixed greens, arugula, and fresh herbs. Drain canned sardines and break into large chunks over greens. Add cherry tomatoes, sliced red onion, Kalamata olives, and capers. In a small bowl, whisk together olive oil, lemon juice, garlic, and oregano. Pour dressing over salad and toss gently. Top with crumbled feta and toasted pumpkin seeds. This omega-3 rich lunch reduces inflammation and supports joint health.",
            "prep_time": 12,
            "cook_time": 0,
            "calories": 480,
            "protein": 34,
            "fiber": 10,
            "carbs": 22,
            "fat": 32,
            "ingredients": [
                "1 can sardines in olive oil",
                "3 cups mixed greens and arugula",
                "1 cup cherry tomatoes, halved",
                "1/4 red onion, thinly sliced",
                "1/4 cup Kalamata olives",
                "1 tbsp capers",
                "2 tbsp feta cheese",
                "2 tbsp pumpkin seeds, toasted",
                "3 tbsp olive oil",
                "2 tbsp lemon juice",
                "2 cloves garlic, minced",
                "1 tsp dried oregano",
                "fresh parsley"
            ],
            "dietary_tags": [
                "omega_3",
                "anti_inflammatory",
                "bone_health",
                "mediterranean",
                "gluten_free",
                "high_protein"
            ]
        },
        {
            "name": "Japanese Miso-Glazed Tempeh Bowl",
            "meal_type": "lunch",
            "description": "Fermented tempeh with miso, seaweed, and pickled vegetables for gut health",
            "instructions": "Steam tempeh for 10 minutes, then cut into cubes. In a bowl, mix white miso, mirin, maple syrup, and ginger to make glaze. Heat oil in a skillet over medium-high heat. Add tempeh cubes and cook until golden on all sides. Pour miso glaze over tempeh and toss to coat, cooking for 2 minutes until caramelized. In a bowl, layer brown rice, steamed broccoli, wakame seaweed, and pickled ginger. Top with glazed tempeh and sprinkle with sesame seeds and scallions.",
            "prep_time": 15,
            "cook_time": 15,
            "calories": 460,
            "protein": 28,
            "fiber": 14,
            "carbs": 48,
            "fat": 18,
            "ingredients": [
                "5 oz tempeh",
                "1 cup brown rice",
                "1 cup broccoli florets",
                "2 tbsp white miso",
                "1 tbsp mirin",
                "1 tsp maple syrup",
                "1 tsp ginger, grated",
                "1 tbsp wakame seaweed",
                "1 tbsp pickled ginger",
                "1 tsp sesame seeds",
                "1 scallion, sliced",
                "1 tsp avocado oil"
            ],
            "dietary_tags": [
                "fermented",
                "plant_based",
                "gut_health",
                "complete_protein",
                "japanese",
                "gluten_free"
            ]
        },
        {
            "name": "Ayurvedic Mung Bean Kitchari",
            "meal_type": "lunch",
            "description": "Detoxifying mung beans and basmati rice with healing spices for digestion",
            "instructions": "Rinse mung beans and basmati rice. In a pot, heat ghee and add cumin seeds, mustard seeds, and turmeric, stirring for 30 seconds until fragrant. Add mung beans, rice, ginger, and water or vegetable broth. Bring to a boil, then reduce heat to low, cover, and simmer for 25-30 minutes until tender and porridge-like. Stir in chopped spinach and lemon juice. Let rest for 5 minutes. Serve warm, garnished with fresh cilantro.",
            "prep_time": 10,
            "cook_time": 35,
            "calories": 420,
            "protein": 20,
            "fiber": 16,
            "carbs": 58,
            "fat": 12,
            "ingredients": [
                "1/4 cup mung beans",
                "1/4 cup basmati rice",
                "3 cups water or vegetable broth",
                "2 tbsp ghee",
                "1 tsp cumin seeds",
                "1 tsp mustard seeds",
                "1/2 tsp turmeric",
                "1 inch ginger, minced",
                "2 cups spinach",
                "1 tbsp lemon juice",
                "fresh cilantro",
                "salt"
            ],
            "dietary_tags": [
                "detoxifying",
                "digestive_health",
                "anti_inflammatory",
                "ayurvedic",
                "plant_based",
                "gluten_free"
            ]
        },
        {
            "name": "Peruvian Quinoa Kiwicha Power Bowl",
            "meal_type": "lunch",
            "description": "Complete protein quinoa with amaranth, camu camu, and Andean superfoods",
            "instructions": "Cook quinoa and kiwicha (amaranth) according to package directions. In a large bowl, combine cooked grains with black beans, corn, and diced bell peppers. Add diced sweet potato that has been roasted until tender. In a small bowl, whisk together lime juice, olive oil, aji amarillo paste, and camu camu powder for dressing. Pour dressing over grain mixture and toss. Top with avocado slices, toasted pumpkin seeds, and fresh cilantro.",
            "prep_time": 15,
            "cook_time": 20,
            "calories": 500,
            "protein": 24,
            "fiber": 18,
            "carbs": 62,
            "fat": 20,
            "ingredients": [
                "1/2 cup quinoa",
                "2 tbsp kiwicha (amaranth)",
                "1/2 cup black beans",
                "1/4 cup corn",
                "1/2 cup roasted sweet potato",
                "1/4 cup bell peppers, diced",
                "1/4 avocado, sliced",
                "2 tbsp pumpkin seeds, toasted",
                "2 tbsp lime juice",
                "1 tbsp olive oil",
                "1 tsp aji amarillo paste",
                "1/2 tsp camu camu powder",
                "fresh cilantro"
            ],
            "dietary_tags": [
                "complete_protein",
                "antioxidant",
                "andean_superfoods",
                "gluten_free",
                "high_fiber",
                "vitamin_c"
            ]
        }
    ]
    
    # Performance dinner recipes
    dinner_recipes = [
        {
            "name": "Turmeric-Ginger Salmon with Broccoli Sprouts",
            "meal_type": "dinner",
            "description": "Anti-inflammatory salmon with broccoli sprouts for maximum sulforaphane content",
            "instructions": "Preheat oven to 400°F. In a small bowl, mix turmeric, ginger, garlic powder, and olive oil to create paste. Rub salmon fillets with paste and season with salt and pepper. Place salmon on baking sheet lined with parchment paper. Arrange broccoli sprouts around salmon. Drizzle sprouts with lemon juice and olive oil. Bake for 12-15 minutes until salmon is cooked through and sprouts are bright green. Serve immediately with a side of fermented vegetables.",
            "prep_time": 10,
            "cook_time": 15,
            "calories": 480,
            "protein": 38,
            "fiber": 6,
            "carbs": 18,
            "fat": 28,
            "ingredients": [
                "6 oz salmon fillet",
                "2 cups broccoli sprouts",
                "1 tbsp turmeric powder",
                "1 tsp ginger, grated",
                "1 tsp garlic powder",
                "2 tbsp olive oil",
                "2 tbsp lemon juice",
                "1/4 cup fermented vegetables",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "anti_inflammatory",
                "omega_3",
                "sulforaphane",
                "detoxifying",
                "gluten_free",
                "high_protein"
            ]
        },
        {
            "name": "Bone Broth Beef with Bone Marrow",
            "meal_type": "dinner",
            "description": "Grass-fed beef with bone marrow and collagen-rich vegetables for joint health",
            "instructions": "Preheat oven to 425°F. Season beef short ribs with salt and pepper. Heat bone broth in a Dutch oven over medium-high heat. Brown beef on all sides, then remove. Add root vegetables (carrots, parsnips, turnips) and cook until slightly softened. Return beef to pot, add bone marrow bones, thyme, and bay leaves. Cover and transfer to oven. Braise for 2.5-3 hours until beef is tender. Remove marrow bones and scoop marrow onto plates. Serve beef and vegetables with broth.",
            "prep_time": 15,
            "cook_time": 180,
            "calories": 520,
            "protein": 42,
            "fiber": 8,
            "carbs": 28,
            "fat": 32,
            "ingredients": [
                "8 oz grass-fed beef short ribs",
                "2 beef marrow bones",
                "3 cups bone broth",
                "2 carrots, chopped",
                "1 parsnip, chopped",
                "1 turnip, chopped",
                "2 sprigs thyme",
                "1 bay leaf",
                "2 cloves garlic",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "collagen_rich",
                "joint_health",
                "bone_broth",
                "grass_fed",
                "gluten_free",
                "high_protein"
            ]
        },
        {
            "name": "Lion's Mane Mushroom Steak with Adaptogenic Sauce",
            "meal_type": "dinner",
            "description": "Cognitive-enhancing lion's mane mushroom with reishi and cordyceps sauce",
            "instructions": "Clean lion's mane mushroom and slice into thick 'steaks'. Heat avocado oil in a cast-iron skillet over medium-high heat. Sear mushroom steaks for 3-4 minutes per side until golden brown. Reduce heat and add butter, garlic, and thyme, basting mushrooms for 2 minutes. Remove mushrooms and set aside. In the same pan, add reishi powder, cordyceps powder, coconut aminos, and maple syrup. Simmer for 2 minutes to create sauce. Pour sauce over mushroom steaks and serve with wild rice.",
            "prep_time": 10,
            "cook_time": 12,
            "calories": 380,
            "protein": 16,
            "fiber": 8,
            "carbs": 32,
            "fat": 24,
            "ingredients": [
                "8 oz lion's mane mushroom",
                "1 tsp reishi powder",
                "1 tsp cordyceps powder",
                "2 tbsp coconut aminos",
                "1 tsp maple syrup",
                "2 tbsp avocado oil",
                "1 tbsp butter",
                "2 cloves garlic, minced",
                "1 sprig thyme",
                "1 cup wild rice, cooked",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "nootropic",
                "cognitive_enhancing",
                "adaptogenic",
                "plant_based",
                "gluten_free",
                "immune_supporting"
            ]
        },
        {
            "name": "Grass-Fed Lamb with Rosemary and Berries",
            "meal_type": "dinner",
            "description": "Iron-rich lamb with antioxidant berries and rosemary for blood building",
            "instructions": "Preheat oven to 425°F. Rub lamb rack with crushed garlic, fresh rosemary, salt, and pepper. Heat olive oil in an oven-safe skillet over high heat. Sear lamb on all sides for 2 minutes. Add mixed berries and balsamic vinegar to skillet. Transfer to oven and roast for 12-15 minutes for medium-rare. Remove lamb and let rest for 5 minutes. Slice and serve with berry reduction and roasted root vegetables.",
            "prep_time": 15,
            "cook_time": 20,
            "calories": 540,
            "protein": 38,
            "fiber": 8,
            "carbs": 28,
            "fat": 32,
            "ingredients": [
                "8 oz grass-fed lamb rack",
                "1/2 cup mixed berries",
                "2 tbsp balsamic vinegar",
                "2 tbsp olive oil",
                "3 cloves garlic, crushed",
                "2 sprigs fresh rosemary",
                "1 cup root vegetables",
                "salt",
                "pepper"
            ],
            "dietary_tags": [
                "iron_rich",
                "antioxidant",
                "blood_building",
                "grass_fed",
                "gluten_free",
                "high_protein"
            ]
        },
        {
            "name": "Fermented Kimchi Jjigae with Tofu",
            "meal_type": "dinner",
            "description": "Probiotic-rich Korean stew with fermented kimchi and protein-rich tofu",
            "instructions": "In a pot, heat sesame oil and add pork belly (optional) or mushrooms, cooking until browned. Add kimchi with its juice and gochugaru, stirring for 2 minutes. Add water or vegetable broth and bring to a boil. Reduce heat and simmer for 10 minutes. Add cubed tofu and continue simmering for 5 minutes. Add green onions and serve hot with brown rice. This probiotic-rich stew supports gut health and immune function.",
            "prep_time": 10,
            "cook_time": 20,
            "calories": 420,
            "protein": 24,
            "fiber": 8,
            "carbs": 38,
            "fat": 22,
            "ingredients": [
                "6 oz firm tofu",
                "1 cup kimchi",
                "2 cups water or vegetable broth",
                "1 tsp gochugaru (Korean chili flakes)",
                "1 tsp sesame oil",
                "2 oz pork belly or 1 cup mushrooms",
                "2 green onions, sliced",
                "1 cup brown rice",
                "optional: soft-boiled egg"
            ],
            "dietary_tags": [
                "probiotic",
                "fermented",
                "gut_health",
                "korean",
                "plant_based_option",
                "immune_supporting"
            ]
        }
    ]
    
    # Performance post-workout recipes
    post_workout_recipes = [
        {
            "name": "Collagen Recovery Smoothie with Tart Cherry",
            "meal_type": "post_workout",
            "description": "Muscle-repairing collagen smoothie with tart cherry and electrolytes",
            "instructions": "In a blender, combine collagen peptides, tart cherry juice, frozen banana, Greek yogurt, almond milk, and spinach. Blend until smooth. Add ice and blend again until thick and creamy. Pour into a glass and top with hemp seeds and a sprinkle of cinnamon. This recovery smoothie provides collagen for joint repair, tart cherry for muscle recovery, and electrolytes for hydration.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 420,
            "protein": 32,
            "fiber": 8,
            "carbs": 48,
            "fat": 12,
            "ingredients": [
                "1 scoop collagen peptides",
                "1 cup tart cherry juice",
                "1/2 frozen banana",
                "1/2 cup Greek yogurt",
                "1 cup almond milk",
                "1 cup spinach",
                "1 tbsp hemp seeds",
                "1/2 tsp cinnamon",
                "ice cubes",
                "pinch of salt"
            ],
            "dietary_tags": [
                "collagen",
                "muscle_recovery",
                "electrolyte",
                "anti_inflammatory",
                "gluten_free",
                "high_protein"
            ]
        },
        {
            "name": "Electrolyte-Rich Coconut Water Recovery Bowl",
            "meal_type": "post_workout",
            "description": "Hydrating bowl with coconut water, sea salt, and performance minerals",
            "instructions": "In a bowl, mix chia seeds with coconut water and let sit for 10 minutes. Add mashed banana, pineapple chunks, and sea salt. Stir in whey or plant protein powder and maca powder. Top with coconut flakes, sliced banana, and a sprinkle of Himalayan pink salt. This electrolyte-rich bowl replenishes sodium, potassium, and magnesium lost during exercise.",
            "prep_time": 5,
            "cook_time": 0,
            "calories": 460,
            "protein": 28,
            "fiber": 12,
            "carbs": 58,
            "fat": 14,
            "ingredients": [
                "3 tbsp chia seeds",
                "1.5 cups coconut water",
                "1 banana, mashed",
                "1/2 cup pineapple chunks",
                "1 scoop protein powder",
                "1/2 tsp maca powder",
                "2 tbsp coconut flakes",
                "1/2 banana, sliced",
                "1/4 tsp sea salt",
                "1/8 tsp Himalayan pink salt"
            ],
            "dietary_tags": [
                "electrolyte",
                "hydration",
                "recovery",
                "gluten_free",
                "high_protein",
                "tropical"
            ]
        },
        {
            "name": "Beetroot and Pomegranate Recovery Elixir",
            "meal_type": "post_workout",
            "description": "Nitrate-rich beet juice with pomegranate for blood flow and antioxidant recovery",
            "instructions": "In a juicer, juice fresh beetroot, carrots, ginger, and apple. Alternatively, use high-quality cold-pressed juices. In a blender, combine beet juice mixture with pomegranate juice, pea protein powder, and fresh lemon juice. Blend until smooth. Pour into a glass and add a few pomegranate seeds on top. This nitrate-rich elixir improves blood flow and oxygen delivery to recovering muscles.",
            "prep_time": 8,
            "cook_time": 0,
            "calories": 380,
            "protein": 24,
            "fiber": 6,
            "carbs": 52,
            "fat": 8,
            "ingredients": [
                "1 small beetroot, juiced",
                "1 carrot, juiced",
                "1 inch ginger, juiced",
                "1/2 apple, juiced",
                "1/2 cup pomegranate juice",
                "1 scoop pea protein powder",
                "1 tbsp lemon juice",
                "pomegranate seeds for garnish",
                "ice"
            ],
            "dietary_tags": [
                "nitrate_rich",
                "antioxidant",
                "blood_flow",
                "recovery",
                "gluten_free",
                "plant_based"
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
    
    print(f"Added {len(breakfast_recipes)} performance breakfast recipes")
    print(f"Added {len(lunch_recipes)} performance lunch recipes")
    print(f"Added {len(dinner_recipes)} performance dinner recipes")
    print(f"Added {len(post_workout_recipes)} performance post-workout recipes")

def main():
    """Main function to add all performance-focused recipes."""
    print("Adding performance-focused and health-optimized recipes...")
    
    add_performance_recipes()
    
    print("\nPerformance recipe addition complete!")
    print("\nSummary of additions:")
    print("- 3 performance breakfast recipes")
    print("- 4 performance lunch recipes")
    print("- 5 performance dinner recipes")
    print("- 3 performance post-workout recipes")
    print("- Total: 15 performance-focused recipes added")
    print("\nPerformance focus areas:")
    print("- Blood flow and oxygen delivery (nitrates)")
    print("- Anti-inflammatory and recovery (omega-3, turmeric)")
    print("- Stress reduction and adaptation (adaptogens)")
    print("- Joint and bone health (collagen, bone broth)")
    print("- Cognitive enhancement (lion's mane, reishi)")
    print("- Gut health and immunity (fermented foods)")
    print("- Electrolyte balance and hydration")
    print("- Complete proteins and amino acids")
    print("- Antioxidant protection and detoxification")
    print("- Blood building and oxygen transport")

if __name__ == "__main__":
    main()