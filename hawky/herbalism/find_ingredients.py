#!/usr/bin/env python3
"""
Find ingredient combinations that produce a specified recipe.

Usage:
    python3 find_ingredients.py <product_item_number> <product_type> [--max-results N]

Examples:
    python3 find_ingredients.py 6111 tea
    python3 find_ingredients.py 6312 tincture --max-results 5
"""

import argparse
import os
import sys
from itertools import combinations
from typing import List, Optional, Tuple

# Add parent directories to path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
_hawky_dir = os.path.dirname(_script_dir)
_project_root = os.path.dirname(_hawky_dir)
sys.path.insert(0, _project_root)
sys.path.insert(0, _hawky_dir)
sys.path.insert(0, _script_dir)

from loaders import load_ingredients, load_subset_recipes, load_constraint_recipes
from blending import (
    calculate_chakras,
    ChakraResult,
    all_have_property,
    has_property,
    count_property,
    VALID_PRODUCT_TYPES,
)
from db import Ingredient, SubsetRecipe, ConstraintRecipe

# --- Configuration ---
# Paths are relative to this script's directory
INGREDIENTS_FILE = os.path.join(_script_dir, "test_data/test_ingredients.csv")
SUBSET_RECIPES_FILE = os.path.join(_script_dir, "test_data/test_subset_recipes.csv")
CONSTRAINT_RECIPES_FILES = [os.path.join(_script_dir, "test_data/test_constraint_recipes.csv")]


def get_product_type(ingredients: List[Ingredient]) -> Optional[str]:
    """
    Determine product type from ingredients (sync, no db).
    Returns None if the blend would be ruined.
    """
    alcohol_count = count_property(ingredients, "alcohol")
    is_ingestible = all_have_property(ingredients, "ingestible")
    has_aromatic_prop = has_property(ingredients, "aromatic")
    has_salt_prop = has_property(ingredients, "salt")

    if alcohol_count > 2:
        return None  # ruined
    if alcohol_count == 2:
        return "tincture" if is_ingestible else None
    if alcohol_count == 1:
        if is_ingestible:
            return "tincture"
        elif has_aromatic_prop:
            return "incense"
        else:
            return "decoction"
    # No alcohol
    if is_ingestible:
        return "tea"
    elif has_salt_prop:
        return "bath"
    else:
        return "salve"


def filter_for_product_type(ingredients: List[Ingredient], product_type: str) -> List[Ingredient]:
    """
    Pre-filter ingredients that could potentially work for the target product type.
    """
    if product_type == "tea":
        # Tea requires all ingestible and no alcohol
        return [i for i in ingredients
                if i.has_property("ingestible") and not i.has_property("alcohol")]
    elif product_type == "tincture":
        # Tincture requires all ingestible (alcohol ingredients are also needed)
        return [i for i in ingredients if i.has_property("ingestible")]
    elif product_type == "decoction":
        # Decoction: 1 alcohol + not all ingestible + not aromatic
        # Include alcohol ingredients and non-ingestible ingredients
        return [i for i in ingredients
                if i.has_property("alcohol") or not i.has_property("ingestible")]
    elif product_type == "incense":
        # Incense: 1 alcohol + aromatic + not all ingestible
        # Include alcohol, aromatic, and non-ingestible ingredients
        return [i for i in ingredients
                if i.has_property("alcohol") or i.has_property("aromatic")
                or not i.has_property("ingestible")]
    elif product_type == "bath":
        # Bath: no alcohol, has salt, not all ingestible
        return [i for i in ingredients if not i.has_property("alcohol")]
    else:  # salve
        # Salve: no alcohol, no salt, not all ingestible
        return [i for i in ingredients
                if not i.has_property("alcohol") and not i.has_property("salt")]


def filter_for_chakra(
    ingredients: List[Ingredient],
    chakra_name: str,
    is_boon: str
) -> List[Ingredient]:
    """
    Filter to ingredients that contribute to the required chakra direction.
    """
    matching = []
    for ing in ingredients:
        # Check primary chakra
        if ing.primary_chakra and ing.primary_chakra.lower() == chakra_name.lower():
            strength = ing.primary_chakra_strength or 0
            if (is_boon == "boon" and strength > 0) or (is_boon == "bane" and strength < 0):
                matching.append(ing)
                continue
        # Check secondary chakra
        if ing.secondary_chakra and ing.secondary_chakra.lower() == chakra_name.lower():
            strength = ing.secondary_chakra_strength or 0
            if (is_boon == "boon" and strength > 0) or (is_boon == "bane" and strength < 0):
                matching.append(ing)
    return matching


def get_chakra_strength(ing: Ingredient, chakra_name: str) -> int:
    """Get the total chakra strength for a specific chakra from an ingredient."""
    total = 0
    if ing.primary_chakra and ing.primary_chakra.lower() == chakra_name.lower():
        total += ing.primary_chakra_strength or 0
    if ing.secondary_chakra and ing.secondary_chakra.lower() == chakra_name.lower():
        total += ing.secondary_chakra_strength or 0
    return total


def matches_constraint_recipe(
    recipe: ConstraintRecipe,
    ingredients: List[Ingredient],
    chakra_result: ChakraResult
) -> bool:
    """
    Check if the given ingredients match a constraint recipe.
    """
    # Check tier
    if recipe.tier is not None and recipe.tier != chakra_result.tier:
        return False

    # Check primary chakra
    if recipe.primary_chakra is not None:
        if chakra_result.primary_chakra is None:
            return False
        if chakra_result.primary_chakra.lower() != recipe.primary_chakra.lower():
            return False

    # Check primary_is_boon
    if recipe.primary_is_boon is not None:
        if chakra_result.primary_is_boon is None:
            return False
        if chakra_result.primary_is_boon.lower() != recipe.primary_is_boon.lower():
            return False

    # Check secondary chakra
    if recipe.secondary_chakra is not None:
        if chakra_result.secondary_chakra is None:
            return False
        if chakra_result.secondary_chakra.lower() != recipe.secondary_chakra.lower():
            return False

    # Check secondary_is_boon
    if recipe.secondary_is_boon is not None:
        if chakra_result.secondary_is_boon is None:
            return False
        if chakra_result.secondary_is_boon.lower() != recipe.secondary_is_boon.lower():
            return False

    # Check ingredient wildcards if specified
    if recipe.ingredients is not None and len(recipe.ingredients) > 0:
        ingredient_numbers = [ing.item_number for ing in ingredients]
        if not recipe._ingredients_match(ingredient_numbers):
            return False

    return True


def find_combinations_for_constraint(
    all_ingredients: List[Ingredient],
    recipe: ConstraintRecipe,
    target_type: str,
    max_results: int = 10
) -> List[List[Ingredient]]:
    """
    Find ingredient combinations that match a constraint recipe.
    """
    results = []

    # Pre-filter ingredients by product type
    type_filtered = filter_for_product_type(all_ingredients, target_type)

    # If recipe has chakra constraints, filter by chakra contribution
    if recipe.primary_chakra and recipe.primary_is_boon:
        core_ingredients = filter_for_chakra(
            type_filtered,
            recipe.primary_chakra,
            recipe.primary_is_boon
        )
        # Sort by strength (strongest contributors first)
        core_ingredients.sort(
            key=lambda i: abs(get_chakra_strength(i, recipe.primary_chakra)),
            reverse=True
        )
    else:
        core_ingredients = type_filtered

    # If recipe requires specific ingredients, we need to include them
    required_ingredients = []
    if recipe.ingredients:
        for pattern in recipe.ingredients:
            for ing in all_ingredients:
                if ConstraintRecipe._pattern_matches(pattern, ing.item_number):
                    required_ingredients.append(ing)
                    break

    # Try combinations of increasing size (1-6 ingredients)
    for combo_size in range(1, 7):
        if len(results) >= max_results:
            break

        # If we have required ingredients, they must be in the combo
        if required_ingredients:
            remaining_slots = combo_size - len(required_ingredients)
            if remaining_slots < 0:
                continue

            # Get other eligible ingredients (excluding required ones)
            other_ingredients = [i for i in core_ingredients
                               if i not in required_ingredients]

            if remaining_slots == 0:
                combo_list = [tuple(required_ingredients)]
            else:
                combo_list = [
                    tuple(required_ingredients) + combo
                    for combo in combinations(other_ingredients, remaining_slots)
                ]
        else:
            combo_list = combinations(core_ingredients, combo_size)

        for combo in combo_list:
            if len(results) >= max_results:
                break

            combo_list_ing = list(combo)

            # Check product type matches
            actual_type = get_product_type(combo_list_ing)
            if actual_type != target_type:
                continue

            # Calculate chakras
            chakra_result = calculate_chakras(combo_list_ing)

            # Check if matches recipe constraints
            if matches_constraint_recipe(recipe, combo_list_ing, chakra_result):
                results.append(combo_list_ing)

    return results


def print_ingredients_latex(ingredients: List[Ingredient]):
    """Print ingredients in LaTeX format."""
    for ing in ingredients:
        if ing.macro:
            print(f"\\i{ing.macro}{{}}")
        else:
            # Fallback to name without spaces if no macro
            safe_name = ing.name.replace(" ", "")
            print(f"\\i{safe_name}{{}}")


def main():
    parser = argparse.ArgumentParser(
        description="Find ingredient combinations for a recipe"
    )
    parser.add_argument("product_item_number", help="Product item number to search for")
    parser.add_argument("product_type", help="Product type (tea, tincture, etc.)")
    parser.add_argument(
        "--max-results", "-n",
        type=int,
        default=10,
        help="Maximum number of results to return (default: 10)"
    )
    args = parser.parse_args()

    product_type = args.product_type.lower()
    if product_type not in VALID_PRODUCT_TYPES:
        print(f"Error: Invalid product type '{product_type}'", file=sys.stderr)
        print(f"Valid types: {', '.join(sorted(VALID_PRODUCT_TYPES))}", file=sys.stderr)
        sys.exit(1)

    # Load data
    ingredients = load_ingredients(INGREDIENTS_FILE)
    subset_recipes = load_subset_recipes(SUBSET_RECIPES_FILE)

    constraint_recipes = []
    for recipe_file in CONSTRAINT_RECIPES_FILES:
        constraint_recipes.extend(load_constraint_recipes(recipe_file))

    # First check subset recipes
    matching_subset = None
    for recipe in subset_recipes:
        if (recipe.product_item_number == args.product_item_number and
                recipe.product_type.lower() == product_type):
            matching_subset = recipe
            break

    if matching_subset:
        # For subset recipes, just return the specific ingredients
        print(f"% Subset recipe for {args.product_item_number} ({product_type})")
        print(f"% Required ingredients: {matching_subset.ingredients}")

        # Find the actual ingredient objects
        result_ingredients = []
        for item_num in matching_subset.ingredients:
            for ing in ingredients:
                if ing.item_number == item_num:
                    result_ingredients.append(ing)
                    break

        print_ingredients_latex(result_ingredients)
        return

    # Check constraint recipes
    matching_constraint = None
    for recipe in constraint_recipes:
        if (recipe.product_item_number == args.product_item_number and
                recipe.product_type.lower() == product_type):
            matching_constraint = recipe
            break

    if matching_constraint:
        print(f"% Constraint recipe for {args.product_item_number} ({product_type})")
        constraints = []
        if matching_constraint.primary_chakra:
            constraints.append(f"primary={matching_constraint.primary_chakra}")
        if matching_constraint.primary_is_boon:
            constraints.append(f"primary_is={matching_constraint.primary_is_boon}")
        if matching_constraint.tier is not None:
            constraints.append(f"tier={matching_constraint.tier}")
        if matching_constraint.ingredients:
            constraints.append(f"requires={matching_constraint.ingredients}")
        print(f"% Constraints: {', '.join(constraints)}")
        print()

        results = find_combinations_for_constraint(
            ingredients,
            matching_constraint,
            product_type,
            args.max_results
        )

        if not results:
            print("% No matching combinations found", file=sys.stderr)
            sys.exit(1)

        for i, combo in enumerate(results):
            if i > 0:
                print()
            print(f"% Combination {i + 1}:")
            print_ingredients_latex(combo)
        return

    print(f"Error: No recipe found for {args.product_item_number} ({product_type})",
          file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
