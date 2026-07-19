#!/usr/bin/env python3
"""
Consolidated Meal Seed Script for RunCoach App

This script consolidates all recipe data from the previous standalone seed scripts
into a single, maintainable data management system.

Usage: python3 scripts/seed_meals.py [--dry-run] [--stats]
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "app" / "data"

MEAL_FILES = {
    "breakfast": "meals_breakfast.json",
    "lunch": "meals_lunch.json",
    "dinner": "meals_dinner.json",
    "snack": "meals_snack.json",
    "post_workout": "meals_post_workout.json",
}


def load_recipes(meal_type: str) -> List[Dict[str, Any]]:
    """Load existing recipes for a given meal type."""
    file_path = DATA_DIR / MEAL_FILES[meal_type]
    if not file_path.exists():
        print(f"Warning: {file_path} does not exist, creating empty list")
        return []
    with open(file_path, "r") as f:
        return json.load(f)


def save_recipes(meal_type: str, recipes: List[Dict[str, Any]]):
    """Save recipes to file."""
    file_path = DATA_DIR / MEAL_FILES[meal_type]
    with open(file_path, "w") as f:
        json.dump(recipes, f, indent=2)


def deduplicate_recipes(recipes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate recipes by name, keeping first occurrence."""
    seen: Set[str] = set()
    unique = []
    for recipe in recipes:
        name = recipe.get("name", "").lower().strip()
        if name not in seen:
            seen.add(name)
            unique.append(recipe)
    return unique


def get_all_seed_recipes() -> Dict[str, List[Dict[str, Any]]]:
    """Extract all recipes from the consolidated seed data.

    This function contains all recipe data that was previously spread across
    15 individual seed scripts.
    """
    # Import seed scripts to extract their recipe data
    sys.path.insert(0, str(PROJECT_ROOT))

    all_recipes: Dict[str, List[Dict[str, Any]]] = {
        "breakfast": [],
        "lunch": [],
        "dinner": [],
        "snack": [],
        "post_workout": [],
    }

    # 1. Bean recipes
    try:
        from add_bean_recipes import BeanRecipeAdder

        bean_recipes = BeanRecipeAdder().get_bean_recipes()
        for meal_type, recipes in bean_recipes.items():
            if meal_type in all_recipes:
                all_recipes[meal_type].extend(recipes)
    except ImportError:
        print("Warning: Could not import add_bean_recipes")

    # 2. Extra bean recipes
    try:
        from add_extra_bean_recipes import ExtraBeanRecipeAdder

        extra_bean = ExtraBeanRecipeAdder().get_extra_bean_recipes()
        for meal_type, recipes in extra_bean.items():
            if meal_type in all_recipes:
                all_recipes[meal_type].extend(recipes)
    except ImportError:
        print("Warning: Could not import add_extra_bean_recipes")

    # 3. International recipes
    try:
        from add_international_recipes import InternationalRecipeAdder

        adder = InternationalRecipeAdder()
        for meal_type in adder.meal_files.keys():
            recipes = adder.get_international_recipes(meal_type)
            if meal_type in all_recipes:
                all_recipes[meal_type].extend(recipes)
    except ImportError:
        print("Warning: Could not import add_international_recipes")

    # 4. Mediterranean performance recipes (no extractable data from this script)

    # 5. More beef chicken recipes (no extractable data from this script)

    # 6. More Mediterranean recipes (no extractable data from this script)

    # 7. More recipes
    try:
        from add_more_recipes import AdditionalRecipeAdder

        adder = AdditionalRecipeAdder()
        for meal_type in adder.meal_files.keys():
            recipes = adder.get_additional_recipes(meal_type)
            if meal_type in all_recipes:
                all_recipes[meal_type].extend(recipes)
    except ImportError:
        print("Warning: Could not import add_more_recipes")

    # 8. More stew recipes
    try:
        from add_more_stew_recipes import StewRecipeAdder

        adder = StewRecipeAdder()
        stew_recipes = adder.get_stew_recipes()
        for meal_type, recipes in stew_recipes.items():
            if meal_type in all_recipes:
                all_recipes[meal_type].extend(recipes)
    except ImportError:
        print("Warning: Could not import add_more_stew_recipes")

    # 9. NL Mediterranean recipes (no extractable data from this script)

    # 10. Performance recipes (no extractable data from this script)

    # 11. Stew recipes
    try:
        from add_stew_recipes import StewRecipeAdder

        adder = StewRecipeAdder()
        stew_recipes = adder.get_stew_recipes()
        for meal_type, recipes in stew_recipes.items():
            if meal_type in all_recipes:
                all_recipes[meal_type].extend(recipes)
    except ImportError:
        print("Warning: Could not import add_stew_recipes")

    # 12. Unique healthy recipes (no extractable data from this script)

    # 13. Unique recipes (no extractable data from this script)

    # 14. Enhance recipes (adds new recipes + enhances existing)
    try:
        from enhance_recipes import RecipeEnhancer

        enhancer = RecipeEnhancer()
        for meal_type in enhancer.meal_files.keys():
            recipes = enhancer.get_new_recipes(meal_type)
            if meal_type in all_recipes:
                all_recipes[meal_type].extend(recipes)
    except ImportError:
        print("Warning: Could not import enhance_recipes")

    return all_recipes


def seed_meals(dry_run: bool = False, show_stats: bool = False):
    """Main function to seed all meals with deduplication."""
    print("=" * 60)
    print("RunCoach Consolidated Meal Seed Script")
    print("=" * 60)

    # Load existing recipes
    print("\nLoading existing recipes...")
    existing_recipes = {}
    total_existing = 0
    for meal_type in MEAL_FILES.keys():
        recipes = load_recipes(meal_type)
        existing_recipes[meal_type] = recipes
        total_existing += len(recipes)
        print(f"  {meal_type}: {len(recipes)} recipes")
    print(f"Total existing: {total_existing}")

    # Get all seed recipes
    print("\nExtracting recipes from seed data...")
    seed_recipes = get_all_seed_recipes()
    total_seed = sum(len(recipes) for recipes in seed_recipes.values())
    for meal_type, recipes in seed_recipes.items():
        print(f"  {meal_type}: {len(recipes)} seed recipes")
    print(f"Total seed recipes: {total_seed}")

    # Combine and deduplicate
    print("\nCombining and deduplicating...")
    final_recipes = {}
    total_final = 0
    for meal_type in MEAL_FILES.keys():
        combined = existing_recipes.get(meal_type, []) + seed_recipes.get(meal_type, [])
        unique = deduplicate_recipes(combined)
        final_recipes[meal_type] = unique
        added = len(unique) - len(existing_recipes.get(meal_type, []))
        print(
            f"  {meal_type}: {len(existing_recipes.get(meal_type, []))} -> {len(unique)} (+{added})"
        )
        total_final += len(unique)

    print(f"Total unique recipes: {total_final}")

    if dry_run:
        print("\n[DRY RUN] No files were modified.")
        return

    # Save updated recipes
    print("\nSaving updated recipes...")
    for meal_type, recipes in final_recipes.items():
        save_recipes(meal_type, recipes)
        print(f"  ✓ Saved {len(recipes)} {meal_type} recipes")

    # Update consolidated meals.json
    print("\nUpdating consolidated meals.json...")
    all_recipes = []
    for meal_type in MEAL_FILES.keys():
        all_recipes.extend(final_recipes[meal_type])

    all_recipes.sort(key=lambda x: (x.get("meal_type", ""), x.get("name", "")))

    consolidated_path = DATA_DIR / "meals.json"
    with open(consolidated_path, "w") as f:
        json.dump(all_recipes, f, indent=2)
    print(f"  ✓ Saved consolidated meals.json with {len(all_recipes)} recipes")

    # Show stats if requested
    if show_stats:
        print("\n" + "=" * 60)
        print("MEAL DATABASE STATISTICS")
        print("=" * 60)
        print(f"Total unique recipes: {len(all_recipes)}")

        for meal_type in MEAL_FILES.keys():
            count = sum(1 for r in all_recipes if r.get("meal_type") == meal_type)
            print(f"  {meal_type}: {count}")

        print("\nBy dietary tags (top 15):")
        tag_counts = {}
        for recipe in all_recipes:
            for tag in recipe.get("dietary_tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        for tag, count in sorted_tags[:15]:
            print(f"  {tag}: {count}")

    print("\n✅ Meal seeding completed successfully!")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    show_stats = "--stats" in sys.argv
    seed_meals(dry_run=dry_run, show_stats=show_stats)
