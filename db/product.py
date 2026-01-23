import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class Product:
    """
    Represents an herbal product (tea, salve, tincture, etc.) in the herbalism system.
    Data is shared across all guilds (no guild_id).
    """
    id: Optional[int] = None
    item_number: str = ""
    name: Optional[str] = None
    macro: Optional[str] = None
    product_type: Optional[str] = None  # tea, salve, tincture, decoction, bath, incense
    flavor_text: Optional[str] = None
    rules_text: Optional[str] = None
    skip_export: bool = False
    skip_prod: bool = False

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Product entry.
        The (item_number, product_type) pair must be unique.
        """
        query = """
        INSERT INTO Product (
            item_number, name, macro, product_type, flavor_text, rules_text, skip_export, skip_prod
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (item_number, product_type) DO UPDATE
        SET name = EXCLUDED.name,
            macro = EXCLUDED.macro,
            flavor_text = EXCLUDED.flavor_text,
            rules_text = EXCLUDED.rules_text,
            skip_export = EXCLUDED.skip_export,
            skip_prod = EXCLUDED.skip_prod;
        """
        await conn.execute(
            query,
            self.item_number, self.name, self.macro, self.product_type,
            self.flavor_text, self.rules_text, self.skip_export, self.skip_prod
        )

    @classmethod
    async def fetch_by_item_number(cls, conn: asyncpg.Connection, item_number: str) -> Optional["Product"]:
        """
        Fetch a Product by its item_number.
        Note: With overlapping item numbers by type, this returns the first match.
        Prefer fetch_by_item_number_and_type when type is known.
        """
        row = await conn.fetchrow("""
            SELECT id, item_number, name, macro, product_type, flavor_text, rules_text, skip_export, skip_prod
            FROM Product
            WHERE item_number = $1;
        """, item_number)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_by_item_number_and_type(
        cls, conn: asyncpg.Connection, item_number: str, product_type: str
    ) -> Optional["Product"]:
        """
        Fetch a Product by its item_number and product_type.
        """
        row = await conn.fetchrow("""
            SELECT id, item_number, name, macro, product_type, flavor_text, rules_text, skip_export, skip_prod
            FROM Product
            WHERE item_number = $1 AND LOWER(product_type) = LOWER($2);
        """, item_number, product_type)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection) -> List["Product"]:
        """
        Fetch all Products.
        """
        rows = await conn.fetch("""
            SELECT id, item_number, name, macro, product_type, flavor_text, rules_text, skip_export, skip_prod
            FROM Product
            ORDER BY item_number;
        """)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def fetch_by_type(cls, conn: asyncpg.Connection, product_type: str) -> List["Product"]:
        """
        Fetch all Products of a specific type.
        """
        rows = await conn.fetch("""
            SELECT id, item_number, name, macro, product_type, flavor_text, rules_text, skip_export, skip_prod
            FROM Product
            WHERE product_type = $1
            ORDER BY item_number;
        """, product_type)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all Product entries.
        """
        result = await conn.execute("DELETE FROM Product;")
        logger.warning(f"All Product entries deleted. Result: {result}")

    @classmethod
    async def delete_by_item_number(cls, conn: asyncpg.Connection, item_number: str) -> bool:
        """
        Delete a Product by item_number.
        """
        result = await conn.execute(
            "DELETE FROM Product WHERE item_number = $1;",
            item_number
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted Product item_number={item_number}. Result: {result}")
        return deleted
