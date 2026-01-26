"""
CSV loading functions for herbalism data.
"""

import csv
from typing import List
from db import Ingredient, Product, SubsetRecipe, ConstraintRecipe, FailedBlend


def load_ingredients(filename: str) -> List[Ingredient]:
    """
    Load ingredients from a CSV file.

    CSV columns:
    Name, Macro, Rarity, Item Number, Primary Chakra, Primary Chakra Strength,
    Secondary Chakra, Secondary Chakra Strength, Properties, Flavor Text, Rules Text, Skip Export
    """
    ingredients = []

    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse primary chakra strength
            primary_strength = None
            if row.get('Primary Chakra Strength'):
                try:
                    primary_strength = int(row['Primary Chakra Strength'])
                except ValueError:
                    pass

            # Parse secondary chakra strength
            secondary_strength = None
            if row.get('Secondary Chakra Strength'):
                try:
                    secondary_strength = int(row['Secondary Chakra Strength'])
                except ValueError:
                    pass

            # Parse skip_export - true if column contains a value
            skip_export = bool(row.get('Skip Export', '').strip())

            # Lowercase chakra names for consistent comparison
            primary_chakra_raw = row.get('Primary Chakra', '').strip()
            secondary_chakra_raw = row.get('Secondary Chakra', '').strip()

            ingredient = Ingredient(
                item_number=row.get('Item Number', '').strip(),
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


def load_products(filename: str) -> List[Product]:
    """
    Load products from a CSV file.

    CSV columns:
    Name, Macro, Type, Item Number, Flavor Text, Rules Text, Skip Export, Skip Prod
    Note: 'Notes' column is ignored if present.
    """
    products = []
    
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse skip_export - true if column contains a value
            skip_export = bool(row.get('Skip Export', '').strip())
            skip_prod = bool(row.get('Skip Prod', '').strip())

            product_type_raw=row.get('Type', '').strip() or None
            
            product = Product(
                item_number=row.get('Item Number', '').strip(),
                name=row.get('Name', '').strip() or None,
                macro=row.get('Macro', '').strip() or None,
                product_type= product_type_raw.lower() if product_type_raw else None,
                flavor_text=row.get('Flavor Text', '').strip() or None,
                rules_text=row.get('Rules Text', '').strip() or None,
                skip_export=skip_export,
                skip_prod=skip_prod
            )
            products.append(product)

    return products


def validate_products_unique(products: List[Product]) -> tuple[bool, str]:
    """
    Validate that all products have unique (product_type, item_number) pairs.

    Returns:
        (True, "") if valid
        (False, error_message) if duplicates found
    """
    seen = {}
    duplicates = []

    for i, prod in enumerate(products):
        key = (prod.product_type, prod.item_number)
        if key in seen:
            duplicates.append((key, seen[key], i))
        else:
            seen[key] = i

    if duplicates:
        lines = ["Duplicate products found (product_type, item_number):"]
        for key, first_idx, dup_idx in duplicates:
            lines.append(f"  {key} - rows {first_idx + 2} and {dup_idx + 2}")  # +2 for 1-indexing and header row
        return False, "\n".join(lines)

    return True, ""


def validate_products_have_recipes(
    products: List[Product],
    subset_recipes: List[SubsetRecipe],
    constraint_recipes: List[ConstraintRecipe],
    failed_blends: List[FailedBlend]
) -> tuple[bool, str]:
    """
    Validate that all products have at least one recipe (subset or constraint).

    Excludes:
    - Products listed in failed_blends (ruined products)
    - Sludge product (item_number 6000)

    Returns:
        (True, "") if valid
        (False, error_message) if products without recipes found
    """
    # Collect all product keys referenced by subset recipes
    products_with_recipes = set()
    for recipe in subset_recipes:
        key = (recipe.product_item_number, recipe.product_type)
        products_with_recipes.add(key)

    # Collect all product keys referenced by constraint recipes
    for recipe in constraint_recipes:
        key = (recipe.product_item_number, recipe.product_type)
        products_with_recipes.add(key)

    # Build set of excluded products: failed_blends + sludge (6000)
    excluded_products = set()
    for fb in failed_blends:
        key = (fb.product_item_number, fb.product_type)
        excluded_products.add(key)

    # Find products without recipes (excluding failed blends and sludge)
    orphan_products = []
    for prod in products:
        key = (prod.item_number, prod.product_type)
        # Skip sludge (item_number 6000)
        if prod.item_number == "6000":
            continue
        # Skip failed blends
        if key in excluded_products:
            continue
        # Check if product has a recipe
        if key not in products_with_recipes:
            orphan_products.append(prod)

    if orphan_products:
        lines = ["Products without recipes found:"]
        for prod in orphan_products:
            lines.append(f"  {prod.name} ({prod.product_type}, item_number={prod.item_number})")
        return False, "\n".join(lines)

    return True, ""


def load_subset_recipes(filename: str) -> List[SubsetRecipe]:
    """
    Load subset recipes from a CSV file.

    CSV columns:
    Product Item Number, Product Type, Quantity Produced,
    Ingredient 1, Ingredient 2, Ingredient 3, Ingredient 4, Ingredient 5, Ingredient 6
    """
    recipes = []

    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse quantity produced
            quantity = 1
            if row.get('Quantity Produced'):
                try:
                    quantity = int(row['Quantity Produced'])
                except ValueError:
                    pass

            # Collect ingredient columns and sort descending
            ingredients = []
            for i in range(1, 7):
                col = f'Ingredient {i}'
                if row.get(col) and row[col].strip():
                    ingredients.append(row[col].strip())

            if not ingredients:
                continue  # Skip recipes with no ingredients

            # Sort ingredients descending
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
    """
    Load constraint recipes from a CSV file.

    CSV columns:
    Product Item Number, Product Type, Quantity Produced,
    Ingredient 1, Ingredient 2, Ingredient 3, Ingredient 4, Ingredient 5, Ingredient 6,
    Primary Chakra, Primary Is Boon, Secondary Chakra, Secondary Is Boon, Tier
    """
    recipes = []

    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse quantity produced
            quantity = 1
            if row.get('Quantity Produced'):
                try:
                    quantity = int(row['Quantity Produced'])
                except ValueError:
                    pass

            # Collect ingredient columns (can include wildcards)
            ingredients = []
            for i in range(1, 7):
                col = f'Ingredient {i}'
                if row.get(col) and row[col].strip():
                    ingredients.append(row[col].strip())

            # Ingredients can be None if no ingredients specified
            ingredients_list = ingredients if ingredients else None

            # Parse tier
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


def validate_subset_recipes_unique(recipes: List[SubsetRecipe]) -> tuple[bool, str]:
    """
    Validate that all subset recipes have unique matching criteria.

    Uniqueness key: (product_type, tuple(sorted_ingredients))

    Flags duplicates even if they produce different products, since
    having the same ingredients with different outputs is ambiguous.

    Returns:
        (True, "") if valid
        (False, error_message) if duplicates found
    """
    seen = {}
    duplicates = []

    for i, recipe in enumerate(recipes):
        # Create key from matching criteria only
        key = (recipe.product_type, tuple(sorted(recipe.ingredients)))
        if key in seen:
            first_idx, first_product = seen[key]
            duplicates.append((key, first_idx, first_product, i, recipe.product_item_number))
        else:
            seen[key] = (i, recipe.product_item_number)

    if duplicates:
        lines = ["Duplicate subset recipes found (same product_type and ingredients):"]
        for key, first_idx, first_product, dup_idx, dup_product in duplicates:
            product_type, ingredients = key
            lines.append(
                f"  product_type={product_type}, ingredients={list(ingredients)}"
            )
            lines.append(
                f"    - row {first_idx + 2}: product_item_number={first_product}"
            )
            lines.append(
                f"    - row {dup_idx + 2}: product_item_number={dup_product}"
            )
        return False, "\n".join(lines)

    return True, ""


def validate_constraint_recipes_unique(recipes: List[ConstraintRecipe]) -> tuple[bool, str]:
    """
    Validate that all constraint recipes have unique matching criteria.

    Uniqueness key: (product_type, tuple(ingredients) or None, primary_chakra,
                     primary_is_boon, secondary_chakra, secondary_is_boon, tier)

    Flags duplicates even if they produce different products, since
    having the same constraints with different outputs is ambiguous.

    Returns:
        (True, "") if valid
        (False, error_message) if duplicates found
    """
    seen = {}
    duplicates = []

    for i, recipe in enumerate(recipes):
        # Create key from matching criteria only
        ingredients_key = tuple(sorted(recipe.ingredients)) if recipe.ingredients else None
        key = (
            recipe.product_type,
            ingredients_key,
            recipe.primary_chakra,
            recipe.primary_is_boon,
            recipe.secondary_chakra,
            recipe.secondary_is_boon,
            recipe.tier
        )
        if key in seen:
            first_idx, first_product = seen[key]
            duplicates.append((key, first_idx, first_product, i, recipe.product_item_number))
        else:
            seen[key] = (i, recipe.product_item_number)

    if duplicates:
        lines = ["Duplicate constraint recipes found (same matching criteria):"]
        for key, first_idx, first_product, dup_idx, dup_product in duplicates:
            product_type, ingredients, p_chakra, p_boon, s_chakra, s_boon, tier = key
            lines.append(
                f"  product_type={product_type}, ingredients={list(ingredients) if ingredients else None}, "
                f"primary={p_chakra}/{p_boon}, secondary={s_chakra}/{s_boon}, tier={tier}"
            )
            lines.append(
                f"    - row {first_idx + 2}: product_item_number={first_product}"
            )
            lines.append(
                f"    - row {dup_idx + 2}: product_item_number={dup_product}"
            )
        return False, "\n".join(lines)

    return True, ""


def load_failed_blends(filename: str) -> List[FailedBlend]:
    """
    Load failed blends from a CSV file.

    CSV columns:
    Product Item Number, Type
    """
    failed_blends = []

    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            failed_blend = FailedBlend(
                product_item_number=row.get('Product Item Number', '').strip(),
                product_type=row.get('Type', '').strip().lower()
            )
            failed_blends.append(failed_blend)

    return failed_blends
