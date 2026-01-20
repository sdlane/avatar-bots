import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class FailedBlend:
    """
    Maps product types to their corresponding 'ruined' product item numbers.
    Used when a blend fails to produce a valid product.
    Data is shared across all guilds (no guild_id).
    """
    id: Optional[int] = None
    product_item_number: str = ""
    product_type: str = ""  # unique

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this FailedBlend entry.
        The product_type must be unique.
        """
        query = """
        INSERT INTO FailedBlend (product_item_number, product_type)
        VALUES ($1, $2)
        ON CONFLICT (product_type) DO UPDATE
        SET product_item_number = EXCLUDED.product_item_number;
        """
        await conn.execute(query, self.product_item_number, self.product_type)

    @classmethod
    async def fetch_by_type(cls, conn: asyncpg.Connection, product_type: str) -> Optional["FailedBlend"]:
        """
        Fetch a FailedBlend by its product_type.
        """
        row = await conn.fetchrow("""
            SELECT id, product_item_number, product_type
            FROM FailedBlend
            WHERE product_type = $1;
        """, product_type)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection) -> List["FailedBlend"]:
        """
        Fetch all FailedBlend entries.
        """
        rows = await conn.fetch("""
            SELECT id, product_item_number, product_type
            FROM FailedBlend
            ORDER BY product_type;
        """)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all FailedBlend entries.
        """
        result = await conn.execute("DELETE FROM FailedBlend;")
        logger.warning(f"All FailedBlend entries deleted. Result: {result}")
