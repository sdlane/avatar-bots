import asyncpg
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class FactionJoinRequest:
    character_id: int
    faction_id: int
    submitted_by: str  # 'character' or 'leader'
    guild_id: int
    id: Optional[int] = None
    submitted_at: Optional[datetime] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert this FactionJoinRequest entry.
        """
        query = """
        INSERT INTO FactionJoinRequest (
            character_id, faction_id, submitted_by, submitted_at, guild_id
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (character_id, faction_id, submitted_by, guild_id) DO NOTHING
        RETURNING id;
        """
        result = await conn.fetchrow(
            query,
            self.character_id,
            self.faction_id,
            self.submitted_by,
            self.submitted_at or datetime.now(),
            self.guild_id
        )
        if result:
            self.id = result['id']

    @classmethod
    async def fetch_matching_request(
        cls,
        conn: asyncpg.Connection,
        character_id: int,
        faction_id: int,
        other_party: str,
        guild_id: int
    ) -> Optional["FactionJoinRequest"]:
        """
        Fetch a matching join request from the other party.

        Args:
            conn: Database connection
            character_id: Character ID wanting to join
            faction_id: Faction internal ID
            other_party: 'character' or 'leader' - the OTHER party we're looking for
            guild_id: Guild ID

        Returns:
            FactionJoinRequest if found, None otherwise
        """
        row = await conn.fetchrow("""
            SELECT id, character_id, faction_id, submitted_by, submitted_at, guild_id
            FROM FactionJoinRequest
            WHERE character_id = $1
            AND faction_id = $2
            AND submitted_by = $3
            AND guild_id = $4;
        """, character_id, faction_id, other_party, guild_id)

        return cls(**row) if row else None

    @classmethod
    async def delete_all_for_character_faction(
        cls,
        conn: asyncpg.Connection,
        character_id: int,
        faction_id: int,
        guild_id: int
    ) -> bool:
        """
        Delete all join requests for a character-faction pair.

        Args:
            conn: Database connection
            character_id: Character ID
            faction_id: Faction internal ID
            guild_id: Guild ID

        Returns:
            True if any rows were deleted
        """
        result = await conn.execute("""
            DELETE FROM FactionJoinRequest
            WHERE character_id = $1
            AND faction_id = $2
            AND guild_id = $3;
        """, character_id, faction_id, guild_id)

        deleted = result.startswith("DELETE") and not result.startswith("DELETE 0")
        logger.info(f"Deleted FactionJoinRequest for character={character_id}, faction={faction_id}, guild={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all_for_guild(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all FactionJoinRequest entries for a guild.
        """
        result = await conn.execute("DELETE FROM FactionJoinRequest WHERE guild_id = $1;", guild_id)
        logger.warning(f"All FactionJoinRequest entries deleted for guild {guild_id}. Result: {result}")
