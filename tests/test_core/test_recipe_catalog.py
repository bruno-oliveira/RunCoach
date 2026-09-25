"""Quality guardrails for the recipe catalogue in ``app/data/meals_*.json``.

The catalogue used to ship templated filler ("Prepare X as directed in the
ingredient list…"), an egg-muffin recipe that said to use a blender, and tags
that contradicted the numbers next to them. These tests pin the content
contract so that can't creep back: every recipe has real numbered steps, its
calories agree with its macros, its diet labels agree with its ingredients,
and every idea on the Tips page links to a recipe that exists.
"""

import json
import re
from pathlib import Path

import pytest

from app.contexts.nutrition.meal_database import (
    ALLOWED_TAGS,
    DERIVED_TAGS,
    MEAL_TYPE_FILES,
    MealDatabase,
    derive_nutrient_tags,
    enrich_recipe,
    recipe_slug,
)
from app.contexts.nutrition.nutrition_content import generate_trail_fuel_ideas

DATA_DIR = Path(__file__).resolve().parents[2] / "app" / "data"

REQUIRED_FIELDS = {
    "name": str,
    "meal_type": str,
    "description": str,
    "servings": int,
    "prep_time": int,
    "cook_time": int,
    "calories": int,
    "protein": int,
    "carbs": int,
    "fat": int,
    "fiber": int,
    "ingredients": list,
    "steps": list,
    "tip": str,
    "dietary_tags": list,
}

# Phrases from the old generated filler. None of them describe a real step.
BOILERPLATE = re.compile(
    r"as directed in the ingredient list|according to recipe instructions"
    r"|to the specified temperature|for the time specified|as specified\b"
    r"|the main ingredient|the base ingredient|cook or serve as directed"
    r"|support your training goals|maintaining steady energy levels",
    re.IGNORECASE,
)

MEAT_OR_FISH = re.compile(
    r"\b(chicken|beef|pork|lamb|turkey|bacon|pancetta|ham|chorizo|sausage"
    r"|salmon|tuna|cod|prawn|shrimp|mussel|anchov|fish sauce|oyster sauce"
    r"|worcestershire|gelatin)",
    re.IGNORECASE,
)
ANIMAL_PRODUCT = re.compile(
    r"\b(egg|honey|butter|cheese|cheddar|feta|parmesan|mozzarella|halloumi"
    r"|ricotta|yogurt|yoghurt|skyr|cream|milk|whey|protein powder|ghee)",
    re.IGNORECASE,
)
# Plant ingredients whose names contain an animal-product word.
PLANT_EXCEPTIONS = re.compile(
    r"(peanut|almond|nut|seed) butter|butter beans|(almond|oat|soy|coconut|plant) milk"
    r"|coconut cream|vegan|dairy-free|cream of tartar|or maple",
    re.IGNORECASE,
)
GLUTEN = re.compile(
    r"\b(bread|toast|sourdough|bagel|pitta|pita|tortilla|wrap|naan|flour"
    r"|pasta|spaghetti|penne|fusilli|linguine|ziti|orzo|couscous|noodle"
    r"|soba|barley|bulgur|breadcrumb|panko|crouton|cracker|oatcake|pretzel"
    r"|granola|oats|soy sauce|worcestershire|miso|beer|rye|bun)s?\b",
    re.IGNORECASE,
)
GLUTEN_FREE_EXCEPTIONS = re.compile(
    r"gluten-free|rice noodle|corn tortilla|rice cake|tamari|cornflour",
    re.IGNORECASE,
)


def _raw_recipes() -> list[dict]:
    recipes = []
    for filename in MEAL_TYPE_FILES.values():
        recipes.extend(json.loads((DATA_DIR / filename).read_text()))
    return recipes


RAW = _raw_recipes()
DB = MealDatabase()


def _ids(recipes):
    return [r["name"] for r in recipes]


def test_catalogue_is_substantial_in_every_category():
    counts = DB.get_meal_count()
    assert set(counts) == set(MEAL_TYPE_FILES)
    for meal_type, count in counts.items():
        assert count >= 20, f"{meal_type} has only {count} recipes"


def test_names_and_slugs_are_unique():
    names = [r["name"] for r in RAW]
    assert len(names) == len(set(names))
    slugs = [recipe_slug(n) for n in names]
    assert len(slugs) == len(set(slugs))


def test_each_file_only_holds_its_own_meal_type():
    for meal_type, filename in MEAL_TYPE_FILES.items():
        for recipe in json.loads((DATA_DIR / filename).read_text()):
            assert recipe["meal_type"] == meal_type, recipe["name"]


@pytest.mark.parametrize("recipe", RAW, ids=_ids(RAW))
def test_recipe_has_required_fields(recipe):
    for field, kind in REQUIRED_FIELDS.items():
        assert isinstance(recipe.get(field), kind), f"{field} missing or not {kind}"
    assert recipe["servings"] >= 1
    assert len(recipe["ingredients"]) >= 2
    assert all(isinstance(i, str) and i.strip() for i in recipe["ingredients"])


@pytest.mark.parametrize("recipe", RAW, ids=_ids(RAW))
def test_steps_are_real_instructions(recipe):
    steps = recipe["steps"]
    assert len(steps) >= 3, "a recipe needs at least three steps"
    for step in steps:
        assert len(step) >= 15, f"step too thin: {step!r}"
        assert not BOILERPLATE.search(step), f"boilerplate step: {step!r}"
    assert not BOILERPLATE.search(recipe["tip"])
    assert "instructions" not in recipe, "author steps, not a prose blob"


@pytest.mark.parametrize("recipe", RAW, ids=_ids(RAW))
def test_calories_agree_with_macros(recipe):
    estimate = 4 * recipe["protein"] + 4 * recipe["carbs"] + 9 * recipe["fat"]
    assert abs(estimate - recipe["calories"]) <= 0.15 * recipe["calories"], (
        f"{recipe['calories']} kcal but macros imply {estimate}"
    )
    assert recipe["fiber"] <= recipe["carbs"]


@pytest.mark.parametrize("recipe", RAW, ids=_ids(RAW))
def test_tags_are_from_the_vocabulary_and_not_hand_derived(recipe):
    tags = set(recipe["dietary_tags"])
    assert tags <= ALLOWED_TAGS, f"unknown tags: {tags - ALLOWED_TAGS}"
    assert not tags & DERIVED_TAGS, "nutrient tags are computed, not authored"


@pytest.mark.parametrize("recipe", RAW, ids=_ids(RAW))
def test_diet_labels_agree_with_ingredients(recipe):
    tags = set(recipe["dietary_tags"])
    for ingredient in recipe["ingredients"]:
        if tags & {"vegetarian", "vegan"}:
            if not re.search(r"\bvegan\b", ingredient, re.IGNORECASE):
                assert not MEAT_OR_FISH.search(ingredient), ingredient
        if "vegan" in tags and not PLANT_EXCEPTIONS.search(ingredient):
            assert not ANIMAL_PRODUCT.search(ingredient), ingredient
        if "gluten_free" in tags and not GLUTEN_FREE_EXCEPTIONS.search(ingredient):
            assert not GLUTEN.search(ingredient), ingredient


def test_enriched_recipes_expose_derived_fields():
    for meal in DB.meals:
        assert meal["slug"] == recipe_slug(meal["name"])
        assert meal["instructions"] == " ".join(meal["steps"])
        assert meal["total_time"] == meal["prep_time"] + meal["cook_time"]
        derived = derive_nutrient_tags(meal)
        assert derived <= set(meal["dietary_tags"])
        assert not (set(meal["dietary_tags"]) & DERIVED_TAGS) - derived
        if "vegan" in meal["dietary_tags"]:
            assert "vegetarian" in meal["dietary_tags"]


def test_derived_tags_follow_the_numbers():
    dinner = {"meal_type": "dinner", "calories": 600, "protein": 45, "carbs": 70}
    dinner |= {"fat": 15, "fiber": 9, "prep_time": 10, "cook_time": 30}
    assert derive_nutrient_tags(dinner) == {"high_protein", "high_fiber"}

    gel = {"meal_type": "trail", "calories": 100, "protein": 0, "carbs": 25}
    gel |= {"fat": 0, "fiber": 0, "prep_time": 5, "cook_time": 0}
    assert derive_nutrient_tags(gel) == {"quick", "high_carb"}


def test_enrich_drops_stale_hand_entered_nutrient_tags():
    recipe = {
        "name": "Slow Stew",
        "meal_type": "dinner",
        "calories": 300,
        "protein": 8,
        "carbs": 30,
        "fat": 15,
        "fiber": 2,
        "prep_time": 20,
        "cook_time": 60,
        "steps": ["Brown everything well.", "Simmer for an hour."],
        "dietary_tags": ["quick", "high_protein", "vegan"],
    }
    enriched = enrich_recipe(recipe)
    assert enriched["dietary_tags"] == ["vegetarian", "vegan"]
    assert enriched["instructions"] == "Brown everything well. Simmer for an hour."


def test_slug_lookup_accepts_current_and_legacy_links():
    meal = DB.get_meal_by_slug("salmon-nicoise-salad")
    assert meal and meal["name"] == "Salmon Niçoise Salad"
    assert DB.get_meal_by_slug("salmon-niçoise-salad") is meal
    assert DB.get_meal_by_slug("3-1-recovery-smoothie")["name"] == (
        "3:1 Recovery Smoothie"
    )
    assert DB.get_meal_by_slug("no-such-recipe") is None


def test_related_meals_share_the_meal_type():
    meal = DB.get_meal_by_name("Protein Pancakes")
    related = DB.related_meals(meal)
    assert len(related) == 3
    assert all(m["meal_type"] == "breakfast" for m in related)
    assert meal not in related


def test_search_matches_every_word_across_fields():
    names = {m["name"] for m in DB.search_meals("salmon rice")}
    assert "Sushi Bowl" in names
    assert "Salmon Niçoise Salad" not in names  # has salmon, but no rice


def test_every_tips_fuel_idea_links_to_a_real_recipe():
    for idea in generate_trail_fuel_ideas():
        assert idea.get("recipe"), f"{idea['name']} has no recipe link"
        assert DB.get_meal_by_name(idea["recipe"]), idea["recipe"]
