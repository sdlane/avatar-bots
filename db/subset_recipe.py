import asyncpg
from dataclasses import dataclass, field
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class SubsetRecipe:
    """
    Represents a subset recipe in the herbalism system.
    A subset recipe matches when all ingredients in the recipe are present in the blend.
    The largest matching subset wins.
    Data is shared across all guilds (no guild_id).
    """
    id: Optional[int] = None
    product_item_number: str = ""
    product_type: str = ""
    quantity_produced: int = 1
    ingredients: List[str] = field(default_factory=list)  # sorted descending

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this SubsetRecipe entry.
        Note: There's no unique constraint, so this will always insert.
        """
        # Ensure ingredients are sorted descending
        sorted_ingredients = sorted(self.ingredients, reverse=True)

        query = """
        INSERT INTO SubsetRecipe (
            product_item_number, product_type, quantity_produced, ingredients
        )
        VALUES ($1, $2, $3, $4);
        """
        await conn.execute(
            query,
            self.product_item_number, self.product_type,
            self.quantity_produced, sorted_ingredients
        )

    @classmethod
    async def fetch_matching_subsets(
        cls,
        conn: asyncpg.Connection,
        ingredient_numbers: List[str],
        product_type: str
    ) -> List["SubsetRecipe"]:
        """
        Fetch all SubsetRecipes where the recipe's ingredients are a subset
        of the provided ingredient_numbers AND the product_type matches.
        Returns results sorted by the length of the ingredients list descending
        (largest subset first).
        """
        # Query all recipes of the matching product type
        rows = await conn.fetch("""
            SELECT id, product_item_number, product_type, quantity_produced, ingredients
            FROM SubsetRecipe
            WHERE product_type = $1
            ORDER BY array_length(ingredients, 1) DESC NULLS LAST;
        """, product_type)

        # Filter to only those where all recipe ingredients are in ingredient_numbers
        ingredient_set = set(ingredient_numbers)
        matching = []
        for row in rows:
            recipe_ingredients = list(row['ingredients']) if row['ingredients'] else []
            if set(recipe_ingredients).issubset(ingredient_set):
                matching.append(cls(
                    id=row['id'],
                    product_item_number=row['product_item_number'],
                    product_type=row['product_type'],
                    quantity_produced=row['quantity_produced'],
                    ingredients=recipe_ingredients
                ))

        return matching

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection) -> List["SubsetRecipe"]:
        """
        Fetch all SubsetRecipes.
        """
        rows = await conn.fetch("""
            SELECT id, product_item_number, product_type, quantity_produced, ingredients
            FROM SubsetRecipe
            ORDER BY id;
        """)
        result = []
        for row in rows:
            ingredients = list(row['ingredients']) if row['ingredients'] else []
            result.append(cls(
                id=row['id'],
                product_item_number=row['product_item_number'],
                product_type=row['product_type'],
                quantity_produced=row['quantity_produced'],
                ingredients=ingredients
            ))
        return result

    @classmethod
    async def fetch_by_product(
        cls,
        conn: asyncpg.Connection,
        product_item_number: str,
        product_type: str
    ) -> List["SubsetRecipe"]:
        """
        Fetch all SubsetRecipes for a specific product.
        """
        rows = await conn.fetch("""
            SELECT id, product_item_number, product_type, quantity_produced, ingredients
            FROM SubsetRecipe
            WHERE product_item_number = $1 AND LOWER(product_type) = LOWER($2)
            ORDER BY id;
        """, product_item_number, product_type)
        result = []
        for row in rows:
            ingredients = list(row['ingredients']) if row['ingredients'] else []
            result.append(cls(
                id=row['id'],
                product_item_number=row['product_item_number'],
                product_type=row['product_type'],
                quantity_produced=row['quantity_produced'],
                ingredients=ingredients
            ))
        return result

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all SubsetRecipe entries.
        """
        result = await conn.execute("DELETE FROM SubsetRecipe;")
        logger.warning(f"All SubsetRecipe entries deleted. Result: {result}")
