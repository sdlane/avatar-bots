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

            ingredient = Ingredient(
                item_number=row.get('Item Number', '').strip(),
                name=row.get('Name', '').strip(),
                macro=row.get('Macro', '').strip() or None,
                rarity=row.get('Rarity', '').strip() or None,
                primary_chakra=row.get('Primary Chakra', '').strip() or None,
                primary_chakra_strength=primary_strength,
                secondary_chakra=row.get('Secondary Chakra', '').strip() or None,
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

            product = Product(
                item_number=row.get('Item Number', '').strip(),
                name=row.get('Name', '').strip() or None,
                macro=row.get('Macro', '').strip() or None,
                product_type=row.get('Type', '').strip() or None,
                flavor_text=row.get('Flavor Text', '').strip() or None,
                rules_text=row.get('Rules Text', '').strip() or None,
                skip_export=skip_export,
                skip_prod=skip_prod
            )
            products.append(product)

    return products


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

            recipe = SubsetRecipe(
                product_item_number=row.get('Product Item Number', '').strip(),
                product_type=row.get('Product Type', '').strip(),
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

            recipe = ConstraintRecipe(
                product_item_number=row.get('Product Item Number', '').strip(),
                product_type=row.get('Product Type', '').strip(),
                quantity_produced=quantity,
                ingredients=ingredients_list,
                primary_chakra=row.get('Primary Chakra', '').strip() or None,
                primary_is_boon=row.get('Primary Is Boon', '').strip() or None,
                secondary_chakra=row.get('Secondary Chakra', '').strip() or None,
                secondary_is_boon=row.get('Secondary Is Boon', '').strip() or None,
                tier=tier
            )
            recipes.append(recipe)

    return recipes


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
                product_type=row.get('Type', '').strip()
            )
            failed_blends.append(failed_blend)

    return failed_blends
