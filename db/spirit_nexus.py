import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class SpiritNexus:
    """
    Represents a mystical spirit nexus point in the world.
    Health can go negative (damaged beyond baseline).
    """
    id: Optional[int] = None
    identifier: str = ""        # e.g., "north-pole", "south-pole"
    health: int = 0             # Can go negative
    territory_id: str = ""      # Reference to Territory
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this SpiritNexus entry.
        The tuple (identifier, guild_id) must be unique.
        """
        query = """
        INSERT INTO SpiritNexus (
            identifier, health, territory_id, guild_id
        )
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (identifier, guild_id) DO UPDATE
        SET health = EXCLUDED.health,
            territory_id = EXCLUDED.territory_id
        RETURNING id;
        """
        result = await conn.fetchrow(
            query,
            self.identifier, self.health, self.territory_id, self.guild_id
        )
        if result:
            self.id = result['id']

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, nexus_id: int) -> Optional["SpiritNexus"]:
        """
        Fetch a SpiritNexus by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, identifier, health, territory_id, guild_id
            FROM SpiritNexus
            WHERE id = $1;
        """, nexus_id)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_by_identifier(cls, conn: asyncpg.Connection, identifier: str, guild_id: int) -> Optional["SpiritNexus"]:
        """
        Fetch a SpiritNexus by its (identifier, guild_id) tuple.
        """
        row = await conn.fetchrow("""
            SELECT id, identifier, health, territory_id, guild_id
            FROM SpiritNexus
            WHERE identifier = $1 AND guild_id = $2;
        """, identifier, guild_id)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_by_territory(cls, conn: asyncpg.Connection, territory_id: str, guild_id: int) -> Optional["SpiritNexus"]:
        """
        Fetch a SpiritNexus located at a specific territory.
        """
        row = await conn.fetchrow("""
            SELECT id, identifier, health, territory_id, guild_id
            FROM SpiritNexus
            WHERE territory_id = $1 AND guild_id = $2;
        """, territory_id, guild_id)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["SpiritNexus"]:
        """
        Fetch all SpiritNexus entries in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, identifier, health, territory_id, guild_id
            FROM SpiritNexus
            WHERE guild_id = $1
            ORDER BY identifier;
        """, guild_id)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, identifier: str, guild_id: int) -> bool:
        """
        Delete a SpiritNexus by (identifier, guild_id).
        """
        result = await conn.execute(
            "DELETE FROM SpiritNexus WHERE identifier = $1 AND guild_id = $2;",
            identifier, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted SpiritNexus identifier={identifier} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all SpiritNexus entries for a guild.
        """
        result = await conn.execute("DELETE FROM SpiritNexus WHERE guild_id = $1;", guild_id)
        logger.warning(f"All SpiritNexus entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the SpiritNexus has valid data.
        """
        if not self.identifier or len(self.identifier.strip()) == 0:
            return False, "Identifier must not be empty"

        if not self.territory_id or len(self.territory_id.strip()) == 0:
            return False, "Territory ID must not be empty"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
