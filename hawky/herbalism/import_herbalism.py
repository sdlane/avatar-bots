"""
Main script to import all herbalism data from CSV files.

Usage:
    python import_herbalism.py

Configure the file paths below before running.
"""

import asyncio
import asyncpg
import logging
import sys
from pathlib import Path
from typing import List

# Handle both direct execution and module import
if __name__ == "__main__":
    # Add parent directories to path for direct execution
    # Script is in hawky/herbalism/
    herbalism_dir = Path(__file__).parent
    hawky_dir = herbalism_dir.parent
    avatar_bots_dir = hawky_dir.parent
    sys.path.insert(0, str(herbalism_dir))
    sys.path.insert(0, str(hawky_dir))
    sys.path.insert(0, str(avatar_bots_dir))

    from loaders import (
        load_ingredients,
        load_products,
        validate_products_unique,
        validate_products_have_recipes,
        validate_subset_recipes_unique,
        validate_constraint_recipes_unique,
        load_subset_recipes,
        load_constraint_recipes,
        load_failed_blends,
    )
    from clear_data import clear_herbal_data
else:
    from .loaders import (
        load_ingredients,
        load_products,
        validate_products_unique,
        validate_products_have_recipes,
        validate_subset_recipes_unique,
        validate_constraint_recipes_unique,
        load_subset_recipes,
        load_constraint_recipes,
        load_failed_blends,
    )
    from .clear_data import clear_herbal_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - ImportHerbalism - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration ---
# Update these paths to point to your CSV files

INGREDIENTS_FILE = "production_data/herbal_ingredients.csv"
PRODUCTS_FILE = "production_data/herbal_products.csv"
SUBSET_RECIPES_FILE = "production_data/subset_recipes.csv"
CONSTRAINT_RECIPES_FILES: List[str] = [
    "production_data/healing.csv",
    "production_data/two_chakra.csv",
    "production_data/one_chakra.csv"
]
FAILED_BLENDS_FILE = "production_data/failed_blends.csv"

DB_URL = "postgresql://AVATAR:password@db:5432/AVATAR"


async def import_herbalism_data(
    conn: asyncpg.Connection,
    ingredients_file: str,
    products_file: str,
    subset_recipes_file: str,
    constraint_recipes_files: List[str],
    failed_blends_file: str
):
    """
    Import all herbalism data from the specified files.
    Clears existing data before importing.
    """
    # === Phase 1: Load all data ===
    logger.info(f"Loading ingredients from {ingredients_file}...")
    ingredients = load_ingredients(ingredients_file)

    logger.info(f"Loading products from {products_file}...")
    products = load_products(products_file)

    logger.info(f"Loading subset recipes from {subset_recipes_file}...")
    subset_recipes = load_subset_recipes(subset_recipes_file)

    all_constraint_recipes = []
    for file in constraint_recipes_files:
        logger.info(f"Loading constraint recipes from {file}...")
        recipes = load_constraint_recipes(file)
        all_constraint_recipes.extend(recipes)

    logger.info(f"Loading failed blends from {failed_blends_file}...")
    failed_blends = load_failed_blends(failed_blends_file)

    # === Phase 2: Validate all data ===
    logger.info("Validating products...")
    valid, error_msg = validate_products_unique(products)
    if not valid:
        raise ValueError(f"Product validation failed:\n{error_msg}")

    valid, error_msg = validate_products_have_recipes(
        products, subset_recipes, all_constraint_recipes, failed_blends
    )
    if not valid:
        logger.warning(f"Orphaned products found (no recipes):\n{error_msg}")

    logger.info("Validating subset recipes for duplicates...")
    valid, error_msg = validate_subset_recipes_unique(subset_recipes)
    if not valid:
        raise ValueError(f"Subset recipe validation failed:\n{error_msg}")

    logger.info("Validating constraint recipes for duplicates...")
    valid, error_msg = validate_constraint_recipes_unique(all_constraint_recipes)
    if not valid:
        raise ValueError(f"Constraint recipe validation failed:\n{error_msg}")

    # === Phase 3: Clear existing data and insert ===
    logger.info("Clearing existing herbalism data...")
    await clear_herbal_data(conn)

    logger.info(f"Inserting {len(ingredients)} ingredients...")
    for ing in ingredients:
        # Normalize chakra names to lowercase
        if ing.primary_chakra:
            ing.primary_chakra = ing.primary_chakra.lower()
        if ing.secondary_chakra:
            ing.secondary_chakra = ing.secondary_chakra.lower()
        await ing.upsert(conn)

    logger.info(f"Inserting {len(products)} products...")
    for prod in products:
        await prod.upsert(conn)

    logger.info(f"Inserting {len(subset_recipes)} subset recipes...")
    for recipe in subset_recipes:
        await recipe.upsert(conn)

    logger.info(f"Inserting {len(all_constraint_recipes)} constraint recipes...")
    for recipe in all_constraint_recipes:
        await recipe.insert(conn)

    logger.info(f"Inserting {len(failed_blends)} failed blends...")
    for fb in failed_blends:
        await fb.upsert(conn)

    logger.info("Herbalism data import complete!")


async def main():
    """
    Main entry point for the import script.
    """
    logger.info("Connecting to database...")
    conn = await asyncpg.connect(DB_URL)

    try:
        await import_herbalism_data(
            conn,
            INGREDIENTS_FILE,
            PRODUCTS_FILE,
            SUBSET_RECIPES_FILE,
            CONSTRAINT_RECIPES_FILES,
            FAILED_BLENDS_FILE
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
