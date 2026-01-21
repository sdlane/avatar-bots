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

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this FactionMember entry.
        A character can now be a member of multiple factions.
        """
        query = """
        INSERT INTO FactionMember (
            faction_id, character_id, joined_turn, guild_id
        )
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (faction_id, character_id, guild_id) DO UPDATE
        SET joined_turn = EXCLUDED.joined_turn;
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
        For multi-faction support, this returns the represented faction membership if set,
        otherwise returns the most recent membership (by joined_turn).

        For checking all memberships, use fetch_all_by_character().
        """
        # First try to get the membership matching the character's represented faction
        row = await conn.fetchrow("""
            SELECT fm.id, fm.faction_id, fm.character_id, fm.joined_turn, fm.guild_id
            FROM FactionMember fm
            JOIN Character c ON c.id = fm.character_id AND c.guild_id = fm.guild_id
            WHERE fm.character_id = $1 AND fm.guild_id = $2
              AND fm.faction_id = c.represented_faction_id;
        """, character_id, guild_id)

        if row:
            return cls(**row)

        # Fall back to most recent membership by joined_turn
        row = await conn.fetchrow("""
            SELECT id, faction_id, character_id, joined_turn, guild_id
            FROM FactionMember
            WHERE character_id = $1 AND guild_id = $2
            ORDER BY joined_turn DESC
            LIMIT 1;
        """, character_id, guild_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_all_by_character(cls, conn: asyncpg.Connection, character_id: int, guild_id: int) -> List["FactionMember"]:
        """
        Fetch all FactionMember entries for a character.
        Returns list of all faction memberships ordered by joined_turn (newest first).
        """
        rows = await conn.fetch("""
            SELECT id, faction_id, character_id, joined_turn, guild_id
            FROM FactionMember
            WHERE character_id = $1 AND guild_id = $2
            ORDER BY joined_turn DESC;
        """, character_id, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def fetch_membership(cls, conn: asyncpg.Connection, faction_id: int, character_id: int, guild_id: int) -> Optional["FactionMember"]:
        """
        Fetch a specific faction membership by faction_id, character_id, and guild_id.
        Returns the membership if exists, None otherwise.
        """
        row = await conn.fetchrow("""
            SELECT id, faction_id, character_id, joined_turn, guild_id
            FROM FactionMember
            WHERE faction_id = $1 AND character_id = $2 AND guild_id = $3;
        """, faction_id, character_id, guild_id)
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
    async def delete(cls, conn: asyncpg.Connection, character_id: int, guild_id: int, faction_id: Optional[int] = None) -> bool:
        """
        Delete a FactionMember by character_id and guild_id.
        If faction_id is provided, only delete that specific membership.
        If faction_id is None, delete all memberships for that character in the guild.
        """
        if faction_id is not None:
            result = await conn.execute(
                "DELETE FROM FactionMember WHERE faction_id = $1 AND character_id = $2 AND guild_id = $3;",
                faction_id, character_id, guild_id
            )
            deleted = result.startswith("DELETE 1")
            logger.info(f"Deleted FactionMember faction_id={faction_id} character_id={character_id} guild_id={guild_id}. Result: {result}")
        else:
            result = await conn.execute(
                "DELETE FROM FactionMember WHERE character_id = $1 AND guild_id = $2;",
                character_id, guild_id
            )
            deleted_count = int(result.split()[-1]) if result.startswith("DELETE") else 0
            deleted = deleted_count > 0
            logger.info(f"Deleted all FactionMember entries for character_id={character_id} guild_id={guild_id}. Count: {deleted_count}")
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
