import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class FactionMember:
    id: Optional[int] = None
    faction_id: int = 0
    character_id: int = 0
    joined_turn: int = 0
    guild_id: Optional[int] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert this FactionMember entry.
        """
        query = """
        INSERT INTO FactionMember (
            faction_id, character_id, joined_turn, guild_id
        )
        VALUES ($1, $2, $3, $4);
        """
        await conn.execute(
            query,
            self.faction_id,
            self.character_id,
            self.joined_turn,
            self.guild_id
        )

    @classmethod
    async def fetch_by_character(cls, conn: asyncpg.Connection, character_id: int, guild_id: int) -> Optional["FactionMember"]:
        """
        Fetch a FactionMember by character_id and guild_id.
        """
        row = await conn.fetchrow("""
            SELECT id, faction_id, character_id, joined_turn, guild_id
            FROM FactionMember
            WHERE character_id = $1 AND guild_id = $2;
        """, character_id, guild_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_by_faction(cls, conn: asyncpg.Connection, faction_id: int, guild_id: int) -> List["FactionMember"]:
        """
        Fetch all members of a faction.
        """
        rows = await conn.fetch("""
            SELECT id, faction_id, character_id, joined_turn, guild_id
            FROM FactionMember
            WHERE faction_id = $1 AND guild_id = $2
            ORDER BY joined_turn;
        """, faction_id, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, character_id: int, guild_id: int) -> bool:
        """
        Delete a FactionMember by character_id and guild_id.
        """
        result = await conn.execute(
            "DELETE FROM FactionMember WHERE character_id = $1 AND guild_id = $2;",
            character_id, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted FactionMember character_id={character_id} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all FactionMember entries for a guild.
        """
        result = await conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", guild_id)
        logger.warning(f"All FactionMember entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the FactionMember has valid data.
        """
        if self.faction_id <= 0:
            return False, "Faction ID must be valid"

        if self.character_id <= 0:
            return False, "Character ID must be valid"

        if self.joined_turn < 0:
            return False, "Joined turn must be >= 0"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
