"""
Functions to clear herbalism data from the database.
"""

import asyncpg
from db import Ingredient, Product, SubsetRecipe, ConstraintRecipe, FailedBlend


async def clear_herbal_data(conn: asyncpg.Connection):
    """
    Clear all herbalism data from the database.
    """
    await clear_constraint_recipes(conn)
    await clear_subset_recipes(conn)
    await clear_failed_blends(conn)
    await clear_products(conn)
    await clear_ingredients(conn)


async def clear_ingredients(conn: asyncpg.Connection):
    """
    Clear all ingredients from the database.
    """
    await Ingredient.delete_all(conn)


async def clear_products(conn: asyncpg.Connection):
    """
    Clear all products from the database.
    """
    await Product.delete_all(conn)


async def clear_subset_recipes(conn: asyncpg.Connection):
    """
    Clear all subset recipes from the database.
    """
    await SubsetRecipe.delete_all(conn)


async def clear_constraint_recipes(conn: asyncpg.Connection):
    """
    Clear all constraint recipes from the database.
    """
    await ConstraintRecipe.delete_all(conn)


async def clear_failed_blends(conn: asyncpg.Connection):
    """
    Clear all failed blends from the database.
    """
    await FailedBlend.delete_all(conn)
