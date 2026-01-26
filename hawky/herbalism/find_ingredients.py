#!/usr/bin/env python3
"""
Find ingredient combinations that produce a specified recipe.

Usage:
    python3 find_ingredients.py <product_item_number> <product_type> [--max-results N]

Examples:
    python3 find_ingredients.py 6111 tea
    python3 find_ingredients.py 6312 tincture --max-results 5
    python3 find_ingredients.py 9999 tea  # No recipe found -> prompts for constraints
"""

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from itertools import combinations
from typing import List, Optional

# Add parent directory to path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)

# Try to import from blending.py for consistency with actual blending logic.
# Fall back to local implementations if asyncpg is not available.
try:
    from blending import (
        calculate_chakras,
        ChakraResult,
        all_have_property,
        has_property,
        count_property,
        VALID_PRODUCT_TYPES,
    )
    _USING_BLENDING_MODULE = True
except ImportError:
    _USING_BLENDING_MODULE = False
    # Local implementations below - MUST BE KEPT IN SYNC WITH blending.py
    from dataclasses import dataclass as _dataclass

    VALID_PRODUCT_TYPES = {"tea", "salve", "tincture", "decoction", "bath", "incense"}

    @_dataclass
    class ChakraResult:
        """Result of chakra calculation."""
        primary_chakra: Optional[str] = None
        primary_magnitude: int = 0
        primary_is_boon: Optional[str] = None
        secondary_chakra: Optional[str] = None
        secondary_magnitude: int = 0
        secondary_is_boon: Optional[str] = None
        tier: int = 0

    def all_have_property(ingredients, property_name: str) -> bool:
        if not ingredients:
            return False
        return all(ing.has_property(property_name) for ing in ingredients)

    def has_property(ingredients, property_name: str) -> bool:
        if not ingredients:
            return False
        return any(ing.has_property(property_name) for ing in ingredients)

    def count_property(ingredients, property_name: str) -> int:
        return sum(1 for ing in ingredients if ing.has_property(property_name))

    def calculate_chakras(ingredients) -> ChakraResult:
        """Calculate chakras - LOCAL FALLBACK. Keep in sync with blending.py!"""
        if not ingredients:
            return ChakraResult()

        chakra_totals: dict = {}
        for ing in ingredients:
            if ing.primary_chakra and ing.primary_chakra_strength is not None:
                chakra = ing.primary_chakra.lower()
                chakra_totals[chakra] = chakra_totals.get(chakra, 0) + ing.primary_chakra_strength
            if ing.secondary_chakra and ing.secondary_chakra_strength is not None:
                chakra = ing.secondary_chakra.lower()
                chakra_totals[chakra] = chakra_totals.get(chakra, 0) + ing.secondary_chakra_strength

        if not chakra_totals:
            return ChakraResult()

        sorted_chakras = sorted(chakra_totals.items(), key=lambda x: abs(x[1]), reverse=True)
        result = ChakraResult()

        if len(sorted_chakras) >= 1:
            result.primary_chakra = sorted_chakras[0][0]
            result.primary_magnitude = sorted_chakras[0][1]
            result.primary_is_boon = "boon" if sorted_chakras[0][1] > 0 else "bane"

        if len(sorted_chakras) >= 2:
            result.secondary_chakra = sorted_chakras[1][0]
            result.secondary_magnitude = sorted_chakras[1][1]
            result.secondary_is_boon = "boon" if sorted_chakras[1][1] > 0 else "bane"

        primary_abs = abs(result.primary_magnitude)
        secondary_abs = abs(result.secondary_magnitude) if result.secondary_chakra else 0
        diff = primary_abs - secondary_abs

        if diff > 10:
            result.tier = 3
        elif 8 <= diff <= 10:
            result.tier = 2
        elif 4 <= diff <= 7:
            result.tier = 1
        else:
            result.tier = 0

        if result.secondary_chakra is None and result.tier >= 1:
            result.tier += 1

        return result

    print("Warning: Using local fallback functions (asyncpg not available)", file=sys.stderr)

# --- Configuration ---
INGREDIENTS_FILE = "production_data/herbal_ingredients.csv"
PRODUCTS_FILE = "production_data/herbal_products.csv"
SUBSET_RECIPES_FILE = "production_data/subset_recipes.csv"
CONSTRAINT_RECIPES_FILES: List[str] = [
    "production_data/healing.csv",
    "production_data/two_chakra.csv",
    "production_data/one_chakra.csv"
]

# Valid chakras for reference
VALID_CHAKRAS = ["earth", "water", "fire", "air", "sound", "light", "thought"]

# Item numbers to exclude from search (sludge, etc.)
EXCLUDED_ITEM_NUMBERS = {"5000"}


# --- Local Dataclasses (compatible with db.Ingredient interface) ---

@dataclass
class Ingredient:
    """Local ingredient dataclass for standalone script.

    Must maintain same interface as db.Ingredient for compatibility with
    blending.py functions.
    """
    item_number: str
    name: str
    macro: Optional[str] = None
    rarity: Optional[str] = None
    primary_chakra: Optional[str] = None
    primary_chakra_strength: Optional[int] = None
    secondary_chakra: Optional[str] = None
    secondary_chakra_strength: Optional[int] = None
    properties: Optional[str] = None
    flavor_text: Optional[str] = None
    rules_text: Optional[str] = None
    skip_export: bool = False

    def has_property(self, property_name: str) -> bool:
        """Check if the ingredient has a specific property."""
        if self.properties is None:
            return False
        props = [p.strip().lower() for p in self.properties.split(",")]
        return property_name.lower() in props


@dataclass
class SubsetRecipe:
    """Local subset recipe dataclass."""
    product_item_number: str
    product_type: str
    quantity_produced: int = 1
    ingredients: Optional[List[str]] = None


@dataclass
class ConstraintRecipe:
    """Local constraint recipe dataclass."""
    product_item_number: str
    product_type: str
    quantity_produced: int = 1
    ingredients: Optional[List[str]] = None
    primary_chakra: Optional[str] = None
    primary_is_boon: Optional[str] = None
    secondary_chakra: Optional[str] = None
    secondary_is_boon: Optional[str] = None
    tier: Optional[int] = None

    @staticmethod
    def _pattern_matches(pattern: str, value: str) -> bool:
        """Check if a value matches a pattern with '*' as single-char wildcard."""
        if len(pattern) != len(value):
            return False
        for p_char, v_char in zip(pattern, value):
            if p_char != '*' and p_char != v_char:
                return False
        return True

    def _ingredients_match(self, ingredient_numbers: List[str]) -> bool:
        """Check if provided ingredients match all required recipe ingredients."""
        if self.ingredients is None or len(self.ingredients) == 0:
            return True
        for required in self.ingredients:
            matched = any(
                self._pattern_matches(required, actual)
                for actual in ingredient_numbers
            )
            if not matched:
                return False
        return True


# --- CSV Loading Functions ---

def load_ingredients(filename: str, exclude_items: set = None) -> List[Ingredient]:
    """Load ingredients from a CSV file.

    Args:
        filename: Path to CSV file
        exclude_items: Set of item numbers to exclude (e.g., sludge)
    """
    if exclude_items is None:
        exclude_items = set()

    ingredients = []
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_number = row.get('Item Number', '').strip()

            # Skip excluded items (e.g., sludge)
            if item_number in exclude_items:
                continue

            primary_strength = None
            if row.get('Primary Chakra Strength'):
                try:
                    primary_strength = int(row['Primary Chakra Strength'])
                except ValueError:
                    pass

            secondary_strength = None
            if row.get('Secondary Chakra Strength'):
                try:
                    secondary_strength = int(row['Secondary Chakra Strength'])
                except ValueError:
                    pass

            skip_export = bool(row.get('Skip Export', '').strip())

            # Lowercase chakra names for consistent comparison
            primary_chakra_raw = row.get('Primary Chakra', '').strip()
            secondary_chakra_raw = row.get('Secondary Chakra', '').strip()

            ingredient = Ingredient(
                item_number=item_number,
                name=row.get('Name', '').strip(),
                macro=row.get('Macro', '').strip() or None,
                rarity=row.get('Rarity', '').strip() or None,
                primary_chakra=primary_chakra_raw.lower() if primary_chakra_raw else None,
                primary_chakra_strength=primary_strength,
                secondary_chakra=secondary_chakra_raw.lower() if secondary_chakra_raw else None,
                secondary_chakra_strength=secondary_strength,
                properties=row.get('Properties', '').strip() or None,
                flavor_text=row.get('Flavor Text', '').strip() or None,
                rules_text=row.get('Rules Text', '').strip() or None,
                skip_export=skip_export
            )
            ingredients.append(ingredient)
    return ingredients


def load_subset_recipes(filename: str) -> List[SubsetRecipe]:
    """Load subset recipes from a CSV file."""
    recipes = []
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            quantity = 1
            if row.get('Quantity Produced'):
                try:
                    quantity = int(row['Quantity Produced'])
                except ValueError:
                    pass

            ingredients = []
            for i in range(1, 7):
                col = f'Ingredient {i}'
                if row.get(col) and row[col].strip():
                    ingredients.append(row[col].strip())

            if not ingredients:
                continue

            ingredients.sort(reverse=True)

            product_type_raw = row.get('Product Type', '').strip()
            recipe = SubsetRecipe(
                product_item_number=row.get('Product Item Number', '').strip(),
                product_type=product_type_raw.lower() if product_type_raw else "",
                quantity_produced=quantity,
                ingredients=ingredients
            )
            recipes.append(recipe)
    return recipes


def load_constraint_recipes(filename: str) -> List[ConstraintRecipe]:
    """Load constraint recipes from a CSV file."""
    recipes = []
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            quantity = 1
            if row.get('Quantity Produced'):
                try:
                    quantity = int(row['Quantity Produced'])
                except ValueError:
                    pass

            ingredients = []
            for i in range(1, 7):
                col = f'Ingredient {i}'
                if row.get(col) and row[col].strip():
                    ingredients.append(row[col].strip())

            ingredients_list = ingredients if ingredients else None

            tier = None
            if row.get('Tier'):
                try:
                    tier = int(row['Tier'])
                except ValueError:
                    pass

            # Lowercase chakra and is_boon fields for consistent comparison
            primary_chakra_raw = row.get('Primary Chakra', '').strip()
            primary_is_boon_raw = row.get('Primary Is Boon', '').strip()
            secondary_chakra_raw = row.get('Secondary Chakra', '').strip()
            secondary_is_boon_raw = row.get('Secondary Is Boon', '').strip()

            product_type_raw = row.get('Product Type', '').strip()
            recipe = ConstraintRecipe(
                product_item_number=row.get('Product Item Number', '').strip(),
                product_type=product_type_raw.lower() if product_type_raw else "",
                quantity_produced=quantity,
                ingredients=ingredients_list,
                primary_chakra=primary_chakra_raw.lower() if primary_chakra_raw else None,
                primary_is_boon=primary_is_boon_raw.lower() if primary_is_boon_raw else None,
                secondary_chakra=secondary_chakra_raw.lower() if secondary_chakra_raw else None,
                secondary_is_boon=secondary_is_boon_raw.lower() if secondary_is_boon_raw else None,
                tier=tier
            )
            recipes.append(recipe)
    return recipes


# --- Product Type Logic (sync version for standalone use) ---

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
    """Pre-filter ingredients that could potentially work for the target product type."""
    if product_type == "tea":
        return [i for i in ingredients
                if i.has_property("ingestible") and not i.has_property("alcohol")]
    elif product_type == "tincture":
        return [i for i in ingredients if i.has_property("ingestible")]
    elif product_type == "decoction":
        return [i for i in ingredients
                if i.has_property("alcohol") or not i.has_property("ingestible")]
    elif product_type == "incense":
        return [i for i in ingredients
                if i.has_property("alcohol") or i.has_property("aromatic")
                or not i.has_property("ingestible")]
    elif product_type == "bath":
        return [i for i in ingredients if not i.has_property("alcohol")]
    else:  # salve
        return [i for i in ingredients
                if not i.has_property("alcohol") and not i.has_property("salt")]


def filter_for_chakra(
    ingredients: List[Ingredient],
    chakra_name: str,
    is_boon: str
) -> List[Ingredient]:
    """Filter to ingredients that contribute to the required chakra direction."""
    matching = []
    for ing in ingredients:
        if ing.primary_chakra and ing.primary_chakra.lower() == chakra_name.lower():
            strength = ing.primary_chakra_strength or 0
            if (is_boon == "boon" and strength > 0) or (is_boon == "bane" and strength < 0):
                matching.append(ing)
                continue
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


# --- Recipe Matching ---

def matches_constraint_recipe(
    recipe: ConstraintRecipe,
    ingredients: List[Ingredient],
    chakra_result: ChakraResult
) -> bool:
    """Check if the given ingredients match a constraint recipe."""
    if recipe.tier is not None and recipe.tier != chakra_result.tier:
        return False

    if recipe.primary_chakra is not None:
        if chakra_result.primary_chakra is None:
            return False
        if chakra_result.primary_chakra.lower() != recipe.primary_chakra.lower():
            return False

    if recipe.primary_is_boon is not None:
        if chakra_result.primary_is_boon is None:
            return False
        if chakra_result.primary_is_boon.lower() != recipe.primary_is_boon.lower():
            return False

    if recipe.secondary_chakra is not None:
        if chakra_result.secondary_chakra is None:
            return False
        if chakra_result.secondary_chakra.lower() != recipe.secondary_chakra.lower():
            return False

    if recipe.secondary_is_boon is not None:
        if chakra_result.secondary_is_boon is None:
            return False
        if chakra_result.secondary_is_boon.lower() != recipe.secondary_is_boon.lower():
            return False

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
    """Find ingredient combinations that match a constraint recipe."""
    results = []

    type_filtered = filter_for_product_type(all_ingredients, target_type)

    if recipe.primary_chakra and recipe.primary_is_boon:
        core_ingredients = filter_for_chakra(
            type_filtered,
            recipe.primary_chakra,
            recipe.primary_is_boon
        )
        core_ingredients.sort(
            key=lambda i: abs(get_chakra_strength(i, recipe.primary_chakra)),
            reverse=True
        )
    else:
        core_ingredients = type_filtered

    required_ingredients = []
    if recipe.ingredients:
        for pattern in recipe.ingredients:
            for ing in all_ingredients:
                if ConstraintRecipe._pattern_matches(pattern, ing.item_number):
                    required_ingredients.append(ing)
                    break

    for combo_size in range(1, 7):
        if len(results) >= max_results:
            break

        if required_ingredients:
            remaining_slots = combo_size - len(required_ingredients)
            if remaining_slots < 0:
                continue

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

            actual_type = get_product_type(combo_list_ing)
            if actual_type != target_type:
                continue

            chakra_result = calculate_chakras(combo_list_ing)

            if matches_constraint_recipe(recipe, combo_list_ing, chakra_result):
                results.append(combo_list_ing)

    return results


# --- Interactive Mode ---

def prompt_for_constraints(product_type: str) -> dict:
    """Prompt user for constraint parameters interactively."""
    print(f"No recipe found. Enter constraints for {product_type}:")
    print(f"Valid chakras: {', '.join(VALID_CHAKRAS)}")
    print()

    primary_chakra = input("Primary chakra: ").strip().lower()
    while primary_chakra and primary_chakra not in VALID_CHAKRAS:
        print(f"Invalid chakra. Valid options: {', '.join(VALID_CHAKRAS)}")
        primary_chakra = input("Primary chakra: ").strip().lower()

    primary_is_boon = None
    if primary_chakra:
        primary_is_boon = input("Primary is boon (boon/bane): ").strip().lower()
        while primary_is_boon not in ("boon", "bane"):
            print("Please enter 'boon' or 'bane'")
            primary_is_boon = input("Primary is boon (boon/bane): ").strip().lower()

    secondary_chakra = input("Secondary chakra (or press Enter for none): ").strip().lower()
    if secondary_chakra and secondary_chakra not in VALID_CHAKRAS:
        while secondary_chakra and secondary_chakra not in VALID_CHAKRAS:
            print(f"Invalid chakra. Valid options: {', '.join(VALID_CHAKRAS)}")
            secondary_chakra = input("Secondary chakra (or press Enter for none): ").strip().lower()

    secondary_is_boon = None
    if secondary_chakra:
        secondary_is_boon = input("Secondary is boon (boon/bane): ").strip().lower()
        while secondary_is_boon not in ("boon", "bane"):
            print("Please enter 'boon' or 'bane'")
            secondary_is_boon = input("Secondary is boon (boon/bane): ").strip().lower()
    else:
        secondary_chakra = None

    tier_input = input("Tier (1-3): ").strip()
    tier = None
    if tier_input:
        try:
            tier = int(tier_input)
            if tier < 1 or tier > 3:
                print("Tier must be 1, 2, or 3. Ignoring tier constraint.")
                tier = None
        except ValueError:
            print("Invalid tier. Ignoring tier constraint.")

    return {
        "primary_chakra": primary_chakra or None,
        "primary_is_boon": primary_is_boon,
        "secondary_chakra": secondary_chakra,
        "secondary_is_boon": secondary_is_boon,
        "tier": tier,
    }


# --- Output ---

def print_ingredients_latex(ingredients: List[Ingredient], show_verification: bool = True):
    """Print ingredients in LaTeX format with optional verification info."""
    for ing in ingredients:
        if ing.macro:
            print(f"\\i{ing.macro}{{}}")
        else:
            safe_name = ing.name.replace(" ", "")
            print(f"\\i{safe_name}{{}}")

    if show_verification:
        # Verify using actual blending functions
        chakra = calculate_chakras(ingredients)
        product_type = get_product_type(ingredients)
        product_type_display = product_type.title() if product_type else "Ruined"
        print(f"% Verification: Type={product_type_display}, "
              f"Primary={chakra.primary_chakra}/{chakra.primary_is_boon} (mag={chakra.primary_magnitude}), "
              f"Secondary={chakra.secondary_chakra}/{chakra.secondary_is_boon} (mag={chakra.secondary_magnitude}), "
              f"Tier={chakra.tier}")


# --- Main ---

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
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Disable verification output showing chakra calculations"
    )
    args = parser.parse_args()
    show_verify = not args.no_verify

    product_type = args.product_type.lower()
    if product_type not in VALID_PRODUCT_TYPES:
        print(f"Error: Invalid product type '{product_type}'", file=sys.stderr)
        print(f"Valid types: {', '.join(sorted(VALID_PRODUCT_TYPES))}", file=sys.stderr)
        sys.exit(1)

    # Load data (excluding sludge and other non-ingredient items)
    ingredients = load_ingredients(INGREDIENTS_FILE, exclude_items=EXCLUDED_ITEM_NUMBERS)
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
        print(f"% Subset recipe for {args.product_item_number} ({product_type})")
        print(f"% Required ingredients: {matching_subset.ingredients}")

        result_ingredients = []
        for item_num in matching_subset.ingredients:
            for ing in ingredients:
                if ing.item_number == item_num:
                    result_ingredients.append(ing)
                    break

        print_ingredients_latex(result_ingredients, show_verification=show_verify)
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
            print_ingredients_latex(combo, show_verification=show_verify)
        return

    # No recipe found - prompt for constraints interactively
    constraints = prompt_for_constraints(product_type)

    # Create a temporary constraint recipe from user input
    user_recipe = ConstraintRecipe(
        product_item_number=args.product_item_number,
        product_type=product_type,
        **constraints
    )

    print()
    print(f"% Searching for {product_type} with constraints:")
    constraint_desc = []
    if constraints["primary_chakra"]:
        constraint_desc.append(f"primary={constraints['primary_chakra']}/{constraints['primary_is_boon']}")
    if constraints["secondary_chakra"]:
        constraint_desc.append(f"secondary={constraints['secondary_chakra']}/{constraints['secondary_is_boon']}")
    if constraints["tier"]:
        constraint_desc.append(f"tier={constraints['tier']}")
    print(f"% {', '.join(constraint_desc)}")
    print()

    results = find_combinations_for_constraint(
        ingredients,
        user_recipe,
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
        print_ingredients_latex(combo, show_verification=show_verify)


if __name__ == "__main__":
    main()
