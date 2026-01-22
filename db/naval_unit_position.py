"""
Naval unit position tracking for the wargame system.

Naval units can occupy multiple territories simultaneously, unlike land units
which occupy exactly one territory at a time. This module tracks the set of
territories each naval unit occupies.
"""
import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class NavalUnitPosition:
    """
    Represents a single position entry for a naval unit.

    Naval units occupy a set of territories. Each NavalUnitPosition entry
    represents one territory in that set, with position_index indicating
    the order in the sequence.

    Attributes:
        id: Internal sequential ID (auto-generated)
        unit_id: Foreign key to Unit.id
        territory_id: Territory ID the unit occupies at this position
        position_index: Order in the sequence (0-based)
        guild_id: Guild ID for multi-server isolation
    """
    id: Optional[int] = None
    unit_id: int = 0
    territory_id: str = ""
    position_index: int = 0
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this naval unit position entry.

        The combination (unit_id, territory_id, guild_id) must be unique.
        """
        query = """
        INSERT INTO NavalUnitPosition (unit_id, territory_id, position_index, guild_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (unit_id, territory_id, guild_id) DO UPDATE
        SET position_index = EXCLUDED.position_index
        RETURNING id;
        """
        row = await conn.fetchrow(
            query,
            self.unit_id, self.territory_id, self.position_index, self.guild_id
        )
        if row:
            self.id = row['id']
        logger.debug(f"Upserted NavalUnitPosition: unit_id={self.unit_id}, "
                    f"territory_id={self.territory_id}, position_index={self.position_index}")

    @classmethod
    async def fetch_by_unit(
        cls,
        conn: asyncpg.Connection,
        unit_id: int,
        guild_id: int
    ) -> List["NavalUnitPosition"]:
        """
        Fetch all territory positions for a naval unit, ordered by position_index.

        Args:
            conn: Database connection
            unit_id: The unit's internal ID
            guild_id: Guild ID

        Returns:
            List of NavalUnitPosition objects ordered by position_index
        """
        rows = await conn.fetch("""
            SELECT id, unit_id, territory_id, position_index, guild_id
            FROM NavalUnitPosition
            WHERE unit_id = $1 AND guild_id = $2
            ORDER BY position_index;
        """, unit_id, guild_id)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def fetch_territories_by_unit(
        cls,
        conn: asyncpg.Connection,
        unit_id: int,
        guild_id: int
    ) -> List[str]:
        """
        Fetch just the territory IDs for a naval unit, ordered by position_index.

        Args:
            conn: Database connection
            unit_id: The unit's internal ID
            guild_id: Guild ID

        Returns:
            List of territory_id strings ordered by position_index
        """
        rows = await conn.fetch("""
            SELECT territory_id
            FROM NavalUnitPosition
            WHERE unit_id = $1 AND guild_id = $2
            ORDER BY position_index;
        """, unit_id, guild_id)
        return [row['territory_id'] for row in rows]

    @classmethod
    async def fetch_units_in_territory(
        cls,
        conn: asyncpg.Connection,
        territory_id: str,
        guild_id: int
    ) -> List[int]:
        """
        Fetch all naval unit IDs that occupy a given territory.

        Args:
            conn: Database connection
            territory_id: Territory ID to check
            guild_id: Guild ID

        Returns:
            List of unit internal IDs that occupy this territory
        """
        rows = await conn.fetch("""
            SELECT DISTINCT unit_id
            FROM NavalUnitPosition
            WHERE territory_id = $1 AND guild_id = $2;
        """, territory_id, guild_id)
        return [row['unit_id'] for row in rows]

    @classmethod
    async def delete_for_unit(
        cls,
        conn: asyncpg.Connection,
        unit_id: int,
        guild_id: int
    ) -> int:
        """
        Delete all position entries for a naval unit.

        Args:
            conn: Database connection
            unit_id: The unit's internal ID
            guild_id: Guild ID

        Returns:
            Number of rows deleted
        """
        result = await conn.execute("""
            DELETE FROM NavalUnitPosition
            WHERE unit_id = $1 AND guild_id = $2;
        """, unit_id, guild_id)
        count = int(result.split()[-1])
        logger.debug(f"Deleted {count} positions for unit_id={unit_id}")
        return count

    @classmethod
    async def set_positions(
        cls,
        conn: asyncpg.Connection,
        unit_id: int,
        territory_ids: List[str],
        guild_id: int
    ) -> List["NavalUnitPosition"]:
        """
        Atomically set all positions for a naval unit.

        Clears existing positions and sets new ones in a single operation.

        Args:
            conn: Database connection
            unit_id: The unit's internal ID
            territory_ids: List of territory IDs in order
            guild_id: Guild ID

        Returns:
            List of created NavalUnitPosition objects
        """
        # Delete existing positions
        await cls.delete_for_unit(conn, unit_id, guild_id)

        # Insert new positions
        positions = []
        for index, territory_id in enumerate(territory_ids):
            position = cls(
                unit_id=unit_id,
                territory_id=territory_id,
                position_index=index,
                guild_id=guild_id
            )
            await position.upsert(conn)
            positions.append(position)

        logger.info(f"Set {len(positions)} positions for unit_id={unit_id}: {territory_ids}")
        return positions

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all NavalUnitPosition entries for a guild.

        Args:
            conn: Database connection
            guild_id: Guild ID
        """
        result = await conn.execute(
            "DELETE FROM NavalUnitPosition WHERE guild_id = $1;",
            guild_id
        )
        logger.warning(f"All NavalUnitPosition entries deleted for guild {guild_id}. Result: {result}")

    @classmethod
    async def check_overlap(
        cls,
        conn: asyncpg.Connection,
        unit_id: int,
        new_territories: List[str],
        guild_id: int
    ) -> bool:
        """
        Check if any territory in new_territories overlaps with unit's current positions.

        Used for order validation - new naval orders must overlap with previous positions.

        Args:
            conn: Database connection
            unit_id: The unit's internal ID
            new_territories: List of territory IDs in the new order
            guild_id: Guild ID

        Returns:
            True if at least one territory overlaps, False otherwise
        """
        if not new_territories:
            return False

        current_positions = await cls.fetch_territories_by_unit(conn, unit_id, guild_id)

        if not current_positions:
            # No current positions - check will be against unit's current_territory_id
            return False

        return bool(set(new_territories) & set(current_positions))
