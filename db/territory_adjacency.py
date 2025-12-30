import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class TerritoryAdjacency:
    id: Optional[int] = None
    territory_a_id: int = 0
    territory_b_id: int = 0
    guild_id: Optional[int] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert this TerritoryAdjacency entry.
        Note: territory_a_id must be < territory_b_id due to CHECK constraint.
        """
        # Ensure ordering
        a, b = sorted([self.territory_a_id, self.territory_b_id])

        query = """
        INSERT INTO TerritoryAdjacency (
            territory_a_id, territory_b_id, guild_id
        )
        VALUES ($1, $2, $3)
        ON CONFLICT (territory_a_id, territory_b_id, guild_id) DO NOTHING;
        """
        await conn.execute(query, a, b, self.guild_id)

    @classmethod
    async def fetch_adjacent(cls, conn: asyncpg.Connection, territory_id: int, guild_id: int) -> List[int]:
        """
        Fetch all territory IDs adjacent to the given territory.
        Returns a list of adjacent territory IDs.
        """
        rows = await conn.fetch("""
            SELECT
                CASE
                    WHEN territory_a_id = $1 THEN territory_b_id
                    ELSE territory_a_id
                END as adjacent_id
            FROM TerritoryAdjacency
            WHERE (territory_a_id = $1 OR territory_b_id = $1) AND guild_id = $2;
        """, territory_id, guild_id)
        return [row['adjacent_id'] for row in rows]

    @classmethod
    async def are_adjacent(cls, conn: asyncpg.Connection, territory_1: int, territory_2: int, guild_id: int) -> bool:
        """
        Check if two territories are adjacent.
        """
        a, b = sorted([territory_1, territory_2])
        row = await conn.fetchrow("""
            SELECT id FROM TerritoryAdjacency
            WHERE territory_a_id = $1 AND territory_b_id = $2 AND guild_id = $3;
        """, a, b, guild_id)
        return row is not None

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, territory_1: int, territory_2: int, guild_id: int) -> bool:
        """
        Delete an adjacency relationship between two territories.
        """
        a, b = sorted([territory_1, territory_2])
        result = await conn.execute(
            "DELETE FROM TerritoryAdjacency WHERE territory_a_id = $1 AND territory_b_id = $2 AND guild_id = $3;",
            a, b, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted adjacency {a}<->{b} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all TerritoryAdjacency entries for a guild.
        """
        result = await conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", guild_id)
        logger.warning(f"All TerritoryAdjacency entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the TerritoryAdjacency has valid data.
        """
        if self.territory_a_id < 0 or self.territory_b_id < 0:
            return False, "Territory IDs must be >= 0"

        if self.territory_a_id == self.territory_b_id:
            return False, "A territory cannot be adjacent to itself"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
