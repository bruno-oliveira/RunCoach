"""Meal database for nutrition planning.

Loads the recipe catalogue from the per-category JSON files in ``app/data``.

The JSON holds what only a person can author — ingredients, numbered
``steps``, the runner's ``tip``, and judgement tags such as ``vegan`` or
``pre_run``. Everything that can be *derived* is derived here at load time
instead, because hand-entered copies drifted: recipes tagged "quick" that took
half an hour, "high protein" snacks with 8 g of protein. So the nutrient tags
are recomputed from the macros on every load, ``slug`` is computed from the
name, and ``instructions`` (the joined steps) is kept for older consumers —
plan snapshots, the favourites store — that still expect a single string.
"""

import json
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Display names for the meal-type slugs stored on each recipe.
MEAL_TYPE_LABELS = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "dinner": "Dinner",
    "snack": "Snack",
    "post_workout": "Post-run",
    "trail": "Trail fuel",
}

# Meal types eaten as small portions: their nutrient thresholds are scaled down
# so a 150 kcal trail bar isn't judged against a dinner.
SMALL_PORTION_TYPES = frozenset({"snack", "trail"})

# Tags computed from the numbers. Any hand-entered copy in the JSON is dropped
# and replaced, so these can never disagree with the macros beside them.
DERIVED_TAGS = frozenset(
    {"quick", "high_protein", "high_fiber", "low_carb", "high_carb"}
)

# Every tag the catalogue may use. Judgement tags are authored in the JSON;
# derived tags come from ``derive_nutrient_tags``.
ALLOWED_TAGS = DERIVED_TAGS | frozenset(
    {
        "vegetarian",
        "vegan",
        "gluten_free",
        "meal_prep",
        "portable",
        "pre_run",
        "carb_load",
        "omega_3",
        "anti_inflammatory",
    }
)


def meal_type_label(meal_type: str) -> str:
    """Human label for a meal-type slug (``post_workout`` → ``Post-run``)."""
    return MEAL_TYPE_LABELS.get(meal_type, meal_type.replace("_", " ").title())


def recipe_slug(name: str) -> str:
    """URL slug for a recipe name: ASCII, lowercase, hyphen-separated.

    ``"Salmon Niçoise Salad"`` → ``"salmon-nicoise-salad"``;
    ``"3:1 Recovery Smoothie"`` → ``"3-1-recovery-smoothie"``.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def derive_nutrient_tags(recipe: dict[str, Any]) -> set[str]:
    """Nutrient tags implied by a recipe's per-serving macros and timings."""
    small = recipe.get("meal_type") in SMALL_PORTION_TYPES
    calories = recipe.get("calories", 0) or 0
    protein = recipe.get("protein", 0) or 0
    carbs = recipe.get("carbs", 0) or 0
    fiber = recipe.get("fiber", 0) or 0
    total_time = (recipe.get("prep_time", 0) or 0) + (recipe.get("cook_time", 0) or 0)

    tags: set[str] = set()
    if total_time <= 15:
        tags.add("quick")
    if protein >= (12 if small else 20):
        tags.add("high_protein")
    if fiber >= (5 if small else 8):
        tags.add("high_fiber")
    if carbs <= (10 if small else 20):
        tags.add("low_carb")
    if calories and carbs >= (15 if small else 40) and carbs * 4 >= 0.55 * calories:
        tags.add("high_carb")
    return tags


def enrich_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    """Return ``recipe`` with its derived fields filled in.

    Adds ``slug``, ``total_time`` and ``instructions`` (joined ``steps``, unless
    the recipe still carries a legacy prose ``instructions``), and rebuilds
    ``dietary_tags`` as the authored judgement tags plus the derived nutrient
    tags. A vegan recipe is always vegetarian too, so the vegetarian filter
    finds it.
    """
    enriched = dict(recipe)
    steps = enriched.get("steps") or []
    enriched["steps"] = list(steps)
    if steps and not enriched.get("instructions"):
        enriched["instructions"] = " ".join(steps)
    enriched.setdefault("instructions", "")
    enriched["slug"] = recipe_slug(enriched.get("name", ""))
    enriched["total_time"] = (enriched.get("prep_time", 0) or 0) + (
        enriched.get("cook_time", 0) or 0
    )
    enriched.setdefault("servings", 1)

    authored = [t for t in enriched.get("dietary_tags", []) if t not in DERIVED_TAGS]
    if "vegan" in authored and "vegetarian" not in authored:
        authored.insert(0, "vegetarian")
    derived = sorted(derive_nutrient_tags(enriched))
    enriched["dietary_tags"] = authored + derived
    return enriched


# Path to meal data directory
MEALS_DATA_DIR = Path(__file__).parent.parent.parent / "data"

# Individual meal type files
MEAL_TYPE_FILES = {
    "breakfast": "meals_breakfast.json",
    "lunch": "meals_lunch.json",
    "dinner": "meals_dinner.json",
    "snack": "meals_snack.json",
    "post_workout": "meals_post_workout.json",
    "trail": "meals_trail.json",
}


class MealDatabase:
    """Database of healthy, protein and fiber-focused meals for runners."""

    def __init__(self, data_dir: Path | None = None):
        """
        Initialize the meal database.

        Args:
            data_dir: Optional path to meals data directory. Defaults to data/.
        """
        self.data_dir = data_dir or MEALS_DATA_DIR
        self.meals = self._load_meals()

    def _load_meals(self) -> list[dict[str, Any]]:
        """Load meals from dedicated JSON files."""
        meals = []
        for meal_type, filename in MEAL_TYPE_FILES.items():
            file_path = self.data_dir / filename
            try:
                with open(file_path, "r") as f:
                    type_meals = json.load(f)
                    meals.extend(enrich_recipe(meal) for meal in type_meals)
                    logger.info(
                        f"Loaded {len(type_meals)} {meal_type} meals from {file_path}"
                    )
            except FileNotFoundError:
                logger.warning(f"Meals file not found: {file_path}")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing meals file {file_path}: {e}")

        logger.info(f"Loaded {len(meals)} total meals")
        return meals

    def get_meals_by_type(self, meal_type: str) -> list[dict[str, Any]]:
        """Get all meals of a specific type."""
        return [meal for meal in self.meals if meal["meal_type"] == meal_type]

    def get_high_protein_meals(self, min_protein: float = 20) -> list[dict[str, Any]]:
        """Get meals with high protein content."""
        return [meal for meal in self.meals if meal["protein"] >= min_protein]

    def get_high_fiber_meals(self, min_fiber: float = 8) -> list[dict[str, Any]]:
        """Get meals with high fiber content."""
        return [meal for meal in self.meals if meal["fiber"] >= min_fiber]

    def get_meal_by_name(self, name: str) -> dict[str, Any] | None:
        """Get a specific meal by name."""
        for meal in self.meals:
            if meal["name"] == name:
                return meal
        return None

    def get_meal_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Get a meal by its URL slug.

        Also accepts the legacy slug form (``name.lower()`` with spaces turned
        into hyphens), so recipe links shared before slugs were normalised —
        e.g. ``/recipes/salmon-niçoise-salad`` — still resolve.
        """
        wanted = slug.strip().lower()
        for meal in self.meals:
            if meal["slug"] == wanted:
                return meal
        for meal in self.meals:
            if meal["name"].lower().replace(" ", "-") == wanted:
                return meal
        return None

    def related_meals(
        self, meal: dict[str, Any], limit: int = 3
    ) -> list[dict[str, Any]]:
        """Other recipes of the same meal type, most similar tags first."""
        tags = set(meal.get("dietary_tags", []))
        candidates = [
            m
            for m in self.meals
            if m["meal_type"] == meal["meal_type"] and m["name"] != meal["name"]
        ]
        candidates.sort(
            key=lambda m: (-len(tags & set(m.get("dietary_tags", []))), m["name"])
        )
        return candidates[:limit]

    def get_meals_by_tags(
        self, tags: list[str], match_all: bool = False
    ) -> list[dict[str, Any]]:
        """
        Get meals matching dietary tags.

        Args:
            tags: List of dietary tags to match
            match_all: If True, meal must have all tags. If False, any tag matches.
        """
        matching_meals = []
        for meal in self.meals:
            meal_tags = meal.get("dietary_tags", [])
            if match_all:
                if all(tag in meal_tags for tag in tags):
                    matching_meals.append(meal)
            else:
                if any(tag in meal_tags for tag in tags):
                    matching_meals.append(meal)
        return matching_meals

    def get_daily_meal_plan(
        self,
        target_calories: float = 2000,
        target_protein: float = 120,
        target_fiber: float = 30,
    ) -> dict[str, list[dict[str, Any]]]:
        """Generate a balanced daily meal plan."""
        meal_plan = {
            "breakfast": [],
            "lunch": [],
            "dinner": [],
            "snack": [],
            "post_workout": [],
        }

        for meal_type in meal_plan:
            available_meals = self.get_meals_by_type(meal_type)
            if available_meals:
                # Prioritize high protein and fiber meals
                scored_meals = []
                for meal in available_meals:
                    score = 0
                    if meal["protein"] >= 20:
                        score += 2
                    if meal["fiber"] >= 8:
                        score += 2
                    if meal["protein"] >= 15:
                        score += 1
                    if meal["fiber"] >= 5:
                        score += 1
                    scored_meals.append((score, meal))

                scored_meals.sort(key=lambda x: x[0], reverse=True)
                if scored_meals:
                    meal_plan[meal_type].append(scored_meals[0][1])

        return meal_plan

    def get_meal_count(self) -> dict[str, int]:
        """Get count of meals by type."""
        counts = {}
        for meal in self.meals:
            meal_type = meal["meal_type"]
            counts[meal_type] = counts.get(meal_type, 0) + 1
        return counts

    def search_meals(self, query: str) -> list[dict[str, Any]]:
        """Search meals by name, description or ingredient."""
        query = query.lower()
        return [meal for meal in self.meals if meal_matches_query(meal, query)]


def meal_matches_query(meal: dict[str, Any], query: str) -> bool:
    """True when every word of ``query`` appears in the recipe's text.

    Matches against name, description and ingredients, so "salmon rice" finds
    a salmon bowl even though no single field contains the whole phrase.
    """
    words = query.lower().split()
    if not words:
        return True
    haystack = " ".join(
        [meal.get("name", ""), meal.get("description", "")]
        + list(meal.get("ingredients", []))
    ).lower()
    return all(word in haystack for word in words)


@lru_cache(maxsize=1)
def get_meal_database() -> MealDatabase:
    """Get singleton MealDatabase instance (cached)."""
    return MealDatabase()
