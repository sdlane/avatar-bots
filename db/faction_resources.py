import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class FactionResources:
    id: Optional[int] = None
    faction_id: int = 0  # FK to Faction.id (internal)
    ore: int = 0
    lumber: int = 0
    coal: int = 0
    rations: int = 0
    cloth: int = 0
    platinum: int = 0
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this FactionResources entry.
        The pair (faction_id, guild_id) must be unique.
        """
        query = """
        INSERT INTO FactionResources (
            faction_id, ore, lumber, coal, rations, cloth, platinum, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (faction_id, guild_id) DO UPDATE
        SET ore = EXCLUDED.ore,
            lumber = EXCLUDED.lumber,
            coal = EXCLUDED.coal,
            rations = EXCLUDED.rations,
            cloth = EXCLUDED.cloth,
            platinum = EXCLUDED.platinum;
        """
        await conn.execute(
            query,
            self.faction_id,
            self.ore,
            self.lumber,
            self.coal,
            self.rations,
            self.cloth,
            self.platinum,
            self.guild_id
        )

    @classmethod
    async def fetch_by_faction(cls, conn: asyncpg.Connection, faction_id: int, guild_id: int) -> Optional["FactionResources"]:
        """
        Fetch FactionResources by faction_id (internal) and guild_id.
        """
        row = await conn.fetchrow("""
            SELECT id, faction_id, ore, lumber, coal, rations, cloth, platinum, guild_id
            FROM FactionResources
            WHERE faction_id = $1 AND guild_id = $2;
        """, faction_id, guild_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["FactionResources"]:
        """
        Fetch all FactionResources entries for a guild.
        """
        rows = await conn.fetch("""
            SELECT id, faction_id, ore, lumber, coal, rations, cloth, platinum, guild_id
            FROM FactionResources
            WHERE guild_id = $1;
        """, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, faction_id: int, guild_id: int) -> bool:
        """
        Delete FactionResources by faction_id and guild_id.
        """
        result = await conn.execute(
            "DELETE FROM FactionResources WHERE faction_id = $1 AND guild_id = $2;",
            faction_id, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted FactionResources faction_id={faction_id} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all FactionResources entries for a guild.
        """
        result = await conn.execute("DELETE FROM FactionResources WHERE guild_id = $1;", guild_id)
        logger.warning(f"All FactionResources entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the FactionResources has valid data.
        """
        if self.faction_id <= 0:
            return False, "Faction ID must be valid"

        resource_fields = [
            ("ore", self.ore),
            ("lumber", self.lumber),
            ("coal", self.coal),
            ("rations", self.rations),
            ("cloth", self.cloth),
            ("platinum", self.platinum)
        ]

        for field_name, value in resource_fields:
            if value < 0:
                return False, f"{field_name} must be >= 0"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
