"""
Pytest configuration for herbalism tests.
"""
import sys
from pathlib import Path
import pytest
import asyncpg

# Add parent directories to path
hawky_dir = Path(__file__).parent.parent.parent
avatar_bots_dir = hawky_dir.parent
sys.path.insert(0, str(hawky_dir))
sys.path.insert(0, str(avatar_bots_dir))

# Import after path setup
from db import Ingredient, Product, SubsetRecipe, ConstraintRecipe, FailedBlend
from hawky.herbalism.scripts.loaders import (
    load_ingredients,
    load_products,
    load_subset_recipes,
    load_constraint_recipes,
    load_failed_blends,
)
from hawky.herbalism.scripts.clear_data import clear_herbal_data

# Path to test data
TEST_DATA_DIR = Path(__file__).parent.parent.parent / "herbalism" / "test_data"


@pytest.fixture(scope="function")
async def db_conn():
    """Provide a database connection for each test."""
    pool = await asyncpg.create_pool(
        host='db',
        port=5432,
        user='AVATAR',
        password='password',
        database='AVATAR',
        min_size=1,
        max_size=3
    )
    try:
        async with pool.acquire() as conn:
            yield conn
    finally:
        await pool.close()


@pytest.fixture(scope="function")
async def clean_herbalism_data(db_conn):
    """Clean up herbalism data before and after each test."""
    await clear_herbal_data(db_conn)
    yield
    await clear_herbal_data(db_conn)


@pytest.fixture(scope="function")
async def loaded_test_data(db_conn, clean_herbalism_data):
    """Load test data into the database."""
    # Load ingredients
    ingredients = load_ingredients(str(TEST_DATA_DIR / "test_ingredients.csv"))
    for ing in ingredients:
        await ing.upsert(db_conn)

    # Load products
    products = load_products(str(TEST_DATA_DIR / "test_products.csv"))
    for prod in products:
        await prod.upsert(db_conn)

    # Load subset recipes
    subset_recipes = load_subset_recipes(str(TEST_DATA_DIR / "test_subset_recipes.csv"))
    for recipe in subset_recipes:
        await recipe.upsert(db_conn)

    # Load constraint recipes
    constraint_recipes = load_constraint_recipes(str(TEST_DATA_DIR / "test_constraint_recipes.csv"))
    for recipe in constraint_recipes:
        await recipe.insert(db_conn)

    # Load failed blends
    failed_blends = load_failed_blends(str(TEST_DATA_DIR / "test_failed_blends.csv"))
    for fb in failed_blends:
        await fb.upsert(db_conn)

    yield {
        "ingredients": ingredients,
        "products": products,
        "subset_recipes": subset_recipes,
        "constraint_recipes": constraint_recipes,
        "failed_blends": failed_blends,
    }
