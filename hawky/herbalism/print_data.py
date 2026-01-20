"""
Script to print herbalism data from the database to stdout.

Usage:
    python print_data.py
"""

import asyncio
import asyncpg
import sys
from pathlib import Path

# Handle direct execution
if __name__ == "__main__":
    herbalism_dir = Path(__file__).parent
    hawky_dir = herbalism_dir.parent
    avatar_bots_dir = hawky_dir.parent
    sys.path.insert(0, str(herbalism_dir))
    sys.path.insert(0, str(hawky_dir))
    sys.path.insert(0, str(avatar_bots_dir))

from db import Ingredient, Product, SubsetRecipe, ConstraintRecipe, FailedBlend

DB_URL = "postgresql://AVATAR:password@db:5432/AVATAR"


async def print_ingredients(conn: asyncpg.Connection):
    """Print all ingredients."""
    ingredients = await Ingredient.fetch_all(conn)
    print("=" * 60)
    print(f"INGREDIENTS ({len(ingredients)} total)")
    print("=" * 60)
    for ing in ingredients:
        chakras = []
        if ing.primary_chakra:
            sign = "+" if ing.primary_chakra_strength and ing.primary_chakra_strength > 0 else ""
            chakras.append(f"{ing.primary_chakra} {sign}{ing.primary_chakra_strength}")
        if ing.secondary_chakra:
            sign = "+" if ing.secondary_chakra_strength and ing.secondary_chakra_strength > 0 else ""
            chakras.append(f"{ing.secondary_chakra} {sign}{ing.secondary_chakra_strength}")
        chakra_str = ", ".join(chakras) if chakras else "None"
        props = ing.properties or "None"
        print(f"  [{ing.item_number}] {ing.name}")
        print(f"      Chakras: {chakra_str}")
        print(f"      Properties: {props}")
        print()


async def print_products(conn: asyncpg.Connection):
    """Print all products."""
    products = await Product.fetch_all(conn)
    print("=" * 60)
    print(f"PRODUCTS ({len(products)} total)")
    print("=" * 60)
    current_type = None
    for prod in sorted(products, key=lambda p: (p.product_type or "", p.item_number)):
        if prod.product_type != current_type:
            current_type = prod.product_type
            print(f"\n  --- {(current_type or 'Unknown').upper()} ---")
        print(f"  [{prod.item_number}] {prod.name or 'Unnamed'}")
        if prod.flavor_text:
            print(f"      Flavor: {prod.flavor_text[:60]}...")
        if prod.rules_text:
            print(f"      Rules: {prod.rules_text[:60]}...")
        print()


async def print_subset_recipes(conn: asyncpg.Connection):
    """Print all subset recipes."""
    recipes = await SubsetRecipe.fetch_all(conn)
    print("=" * 60)
    print(f"SUBSET RECIPES ({len(recipes)} total)")
    print("=" * 60)
    for recipe in recipes:
        ings = ", ".join(recipe.ingredients)
        print(f"  [{recipe.product_item_number}] {recipe.product_type}")
        print(f"      Ingredients: {ings}")
        print(f"      Quantity: {recipe.quantity_produced}")
        print()


async def print_constraint_recipes(conn: asyncpg.Connection):
    """Print all constraint recipes."""
    recipes = await ConstraintRecipe.fetch_all(conn)
    print("=" * 60)
    print(f"CONSTRAINT RECIPES ({len(recipes)} total)")
    print("=" * 60)
    for recipe in recipes:
        print(f"  [{recipe.product_item_number}] {recipe.product_type}")
        constraints = []
        if recipe.primary_chakra:
            constraints.append(f"Primary: {recipe.primary_chakra} ({recipe.primary_is_boon})")
        if recipe.secondary_chakra:
            constraints.append(f"Secondary: {recipe.secondary_chakra} ({recipe.secondary_is_boon})")
        if recipe.tier is not None:
            constraints.append(f"Tier: {recipe.tier}")
        if recipe.ingredients:
            constraints.append(f"Ingredients: {', '.join(recipe.ingredients)}")
        print(f"      Constraints: {'; '.join(constraints) if constraints else 'None'}")
        print(f"      Quantity: {recipe.quantity_produced}")
        print()


async def print_failed_blends(conn: asyncpg.Connection):
    """Print all failed blend mappings."""
    failed_blends = await FailedBlend.fetch_all(conn)
    print("=" * 60)
    print(f"FAILED BLENDS ({len(failed_blends)} total)")
    print("=" * 60)
    for fb in failed_blends:
        print(f"  {fb.product_type} -> [{fb.product_item_number}]")
    print()


async def main():
    """Main entry point."""
    conn = await asyncpg.connect(DB_URL)

    try:
        await print_ingredients(conn)
        await print_products(conn)
        await print_subset_recipes(conn)
        await print_constraint_recipes(conn)
        await print_failed_blends(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
