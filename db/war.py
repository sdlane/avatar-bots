import asyncpg
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class War:
    """
    Represents a war in the wargame.

    Wars are identified by their objective - if a faction declares war with the
    same objective as an existing war, they join that war instead of creating a new one.
    """
    id: Optional[int] = None
    war_id: str = ""                      # User-facing ID (e.g., "war-001")
    objective: str = ""                   # Text describing war goals
    declared_turn: int = 0                # Turn war was first declared
    created_at: Optional[datetime] = None
    guild_id: Optional[int] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert this War entry.
        Uses ON CONFLICT DO NOTHING to avoid duplicates.
        """
        query = """
        INSERT INTO War (
            war_id, objective, declared_turn, created_at, guild_id
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (war_id, guild_id) DO NOTHING
        RETURNING id;
        """
        result = await conn.fetchrow(
            query,
            self.war_id,
            self.objective,
            self.declared_turn,
            self.created_at or datetime.now(),
            self.guild_id
        )
        if result:
            self.id = result['id']

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this War entry.
        """
        query = """
        INSERT INTO War (
            war_id, objective, declared_turn, created_at, guild_id
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (war_id, guild_id) DO UPDATE
        SET objective = EXCLUDED.objective
        RETURNING id;
        """
        result = await conn.fetchrow(
            query,
            self.war_id,
            self.objective,
            self.declared_turn,
            self.created_at or datetime.now(),
            self.guild_id
        )
        if result:
            self.id = result['id']

    @classmethod
    async def fetch_by_id(
        cls,
        conn: asyncpg.Connection,
        war_id: str,
        guild_id: int
    ) -> Optional["War"]:
        """
        Fetch a War by its war_id.
        """
        row = await conn.fetchrow("""
            SELECT id, war_id, objective, declared_turn, created_at, guild_id
            FROM War
            WHERE war_id = $1
            AND guild_id = $2;
        """, war_id, guild_id)

        return cls(**row) if row else None

    @classmethod
    async def fetch_by_internal_id(
        cls,
        conn: asyncpg.Connection,
        internal_id: int
    ) -> Optional["War"]:
        """
        Fetch a War by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, war_id, objective, declared_turn, created_at, guild_id
            FROM War
            WHERE id = $1;
        """, internal_id)

        return cls(**row) if row else None

    @classmethod
    async def fetch_by_objective(
        cls,
        conn: asyncpg.Connection,
        objective: str,
        guild_id: int
    ) -> Optional["War"]:
        """
        Fetch a War by its objective (case-insensitive exact match).
        """
        row = await conn.fetchrow("""
            SELECT id, war_id, objective, declared_turn, created_at, guild_id
            FROM War
            WHERE LOWER(objective) = LOWER($1)
            AND guild_id = $2;
        """, objective, guild_id)

        return cls(**row) if row else None

    @classmethod
    async def fetch_all(
        cls,
        conn: asyncpg.Connection,
        guild_id: int
    ) -> List["War"]:
        """
        Fetch all wars in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, war_id, objective, declared_turn, created_at, guild_id
            FROM War
            WHERE guild_id = $1
            ORDER BY declared_turn DESC, created_at DESC;
        """, guild_id)

        return [cls(**row) for row in rows]

    @classmethod
    async def delete(
        cls,
        conn: asyncpg.Connection,
        war_id: str,
        guild_id: int
    ) -> bool:
        """
        Delete a war by war_id.
        This will cascade delete all WarParticipant entries.
        """
        result = await conn.execute("""
            DELETE FROM War
            WHERE war_id = $1
            AND guild_id = $2;
        """, war_id, guild_id)

        deleted = result.startswith("DELETE") and not result.startswith("DELETE 0")
        logger.info(f"Deleted War {war_id} in guild {guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all_for_guild(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all War entries for a guild.
        """
        result = await conn.execute("DELETE FROM War WHERE guild_id = $1;", guild_id)
        logger.warning(f"All War entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the War has valid data.
        """
        if not self.war_id or len(self.war_id) == 0:
            return False, "war_id must not be empty"

        if not self.objective or len(self.objective) == 0:
            return False, "objective must not be empty"

        if self.declared_turn < 0:
            return False, "declared_turn must be non-negative"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
