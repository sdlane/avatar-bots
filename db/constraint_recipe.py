import asyncpg
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
import logging
import fnmatch

logger = logging.getLogger(__name__)


@dataclass
class ConstraintRecipe:
    """
    Represents a constraint recipe in the herbalism system.
    Constraint recipes match based on various conditions like chakras, tier, and ingredients.
    Ingredients can include wildcards (e.g., "51*1" matches "5101", "5111", etc.).
    Data is shared across all guilds (no guild_id).
    """
    id: Optional[int] = None
    product_item_number: str = ""
    product_type: str = ""
    quantity_produced: int = 1
    ingredients: Optional[List[str]] = None  # can include wildcards
    primary_chakra: Optional[str] = None
    primary_is_boon: Optional[str] = None  # null, "boon", or "bane"
    secondary_chakra: Optional[str] = None
    secondary_is_boon: Optional[str] = None  # null, "boon", or "bane"
    tier: Optional[int] = None
    created_at: Optional[datetime] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert this ConstraintRecipe entry.
        Uses insert (not upsert) because order matters (FIFO).
        """
        query = """
        INSERT INTO ConstraintRecipe (
            product_item_number, product_type, quantity_produced, ingredients,
            primary_chakra, primary_is_boon, secondary_chakra, secondary_is_boon,
            tier, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, COALESCE($10, NOW()))
        RETURNING id, created_at;
        """
        row = await conn.fetchrow(
            query,
            self.product_item_number, self.product_type, self.quantity_produced,
            self.ingredients, self.primary_chakra, self.primary_is_boon,
            self.secondary_chakra, self.secondary_is_boon, self.tier, self.created_at
        )
        if row:
            self.id = row['id']
            self.created_at = row['created_at']

    @classmethod
    async def fetch_matching(
        cls,
        conn: asyncpg.Connection,
        product_type: str,
        ingredient_numbers: List[str],
        primary_chakra: Optional[str],
        primary_is_boon: Optional[str],
        secondary_chakra: Optional[str],
        secondary_is_boon: Optional[str],
        tier: int
    ) -> List["ConstraintRecipe"]:
        """
        Fetch all ConstraintRecipes that match the given parameters.
        Returns results in FIFO order (earliest created_at first).
        """
        # Fetch all recipes of the matching product type, ordered by created_at (FIFO)
        rows = await conn.fetch("""
            SELECT id, product_item_number, product_type, quantity_produced, ingredients,
                   primary_chakra, primary_is_boon, secondary_chakra, secondary_is_boon,
                   tier, created_at
            FROM ConstraintRecipe
            WHERE product_type = $1
            ORDER BY created_at ASC, id ASC;
        """, product_type)

        matching = []
        for row in rows:
            recipe = cls(
                id=row['id'],
                product_item_number=row['product_item_number'],
                product_type=row['product_type'],
                quantity_produced=row['quantity_produced'],
                ingredients=list(row['ingredients']) if row['ingredients'] else None,
                primary_chakra=row['primary_chakra'],
                primary_is_boon=row['primary_is_boon'],
                secondary_chakra=row['secondary_chakra'],
                secondary_is_boon=row['secondary_is_boon'],
                tier=row['tier'],
                created_at=row['created_at']
            )

            if recipe.matches(ingredient_numbers, primary_chakra, primary_is_boon,
                              secondary_chakra, secondary_is_boon, tier):
                matching.append(recipe)

        return matching

    def matches(
        self,
        ingredient_numbers: List[str],
        primary_chakra: Optional[str],
        primary_is_boon: Optional[str],
        secondary_chakra: Optional[str],
        secondary_is_boon: Optional[str],
        tier: int
    ) -> bool:
        """
        Check if the given parameters match this recipe's constraints.
        All non-null constraints must match.
        """
        # Check tier constraint
        if self.tier is not None and self.tier != tier:
            return False

        # Check primary chakra constraint
        if self.primary_chakra is not None:
            if primary_chakra is None or primary_chakra.lower() != self.primary_chakra.lower():
                return False

        # Check primary_is_boon constraint
        if self.primary_is_boon is not None:
            if primary_is_boon is None or primary_is_boon.lower() != self.primary_is_boon.lower():
                return False

        # Check secondary chakra constraint
        if self.secondary_chakra is not None:
            if secondary_chakra is None or secondary_chakra.lower() != self.secondary_chakra.lower():
                return False

        # Check secondary_is_boon constraint
        if self.secondary_is_boon is not None:
            if secondary_is_boon is None or secondary_is_boon.lower() != self.secondary_is_boon.lower():
                return False

        # Check ingredient constraints (with wildcard support)
        if self.ingredients is not None and len(self.ingredients) > 0:
            if not self._ingredients_match(ingredient_numbers):
                return False

        return True

    def _ingredients_match(self, ingredient_numbers: List[str]) -> bool:
        """
        Check if the provided ingredient_numbers match all required recipe ingredients.
        Recipe ingredients can include wildcards (e.g., "51*1").
        """
        if self.ingredients is None or len(self.ingredients) == 0:
            return True

        for required in self.ingredients:
            # Check if any input ingredient matches the pattern
            matched = False
            for actual in ingredient_numbers:
                if self._pattern_matches(required, actual):
                    matched = True
                    break
            if not matched:
                return False

        return True

    @staticmethod
    def _pattern_matches(pattern: str, value: str) -> bool:
        """
        Check if a value matches a pattern.
        Pattern can include '*' as wildcard for any single character.
        """
        if len(pattern) != len(value):
            return False

        for p_char, v_char in zip(pattern, value):
            if p_char != '*' and p_char != v_char:
                return False

        return True

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection) -> List["ConstraintRecipe"]:
        """
        Fetch all ConstraintRecipes.
        """
        rows = await conn.fetch("""
            SELECT id, product_item_number, product_type, quantity_produced, ingredients,
                   primary_chakra, primary_is_boon, secondary_chakra, secondary_is_boon,
                   tier, created_at
            FROM ConstraintRecipe
            ORDER BY created_at ASC, id ASC;
        """)
        result = []
        for row in rows:
            ingredients = list(row['ingredients']) if row['ingredients'] else None
            result.append(cls(
                id=row['id'],
                product_item_number=row['product_item_number'],
                product_type=row['product_type'],
                quantity_produced=row['quantity_produced'],
                ingredients=ingredients,
                primary_chakra=row['primary_chakra'],
                primary_is_boon=row['primary_is_boon'],
                secondary_chakra=row['secondary_chakra'],
                secondary_is_boon=row['secondary_is_boon'],
                tier=row['tier'],
                created_at=row['created_at']
            ))
        return result

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all ConstraintRecipe entries.
        """
        result = await conn.execute("DELETE FROM ConstraintRecipe;")
        logger.warning(f"All ConstraintRecipe entries deleted. Result: {result}")
