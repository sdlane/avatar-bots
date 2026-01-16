import asyncpg
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Alliance:
    """
    Represents an alliance between two factions.

    faction_a_id is always < faction_b_id to ensure canonical ordering.
    Status values:
    - PENDING_FACTION_A: Faction A (lower ID) initiated, waiting for Faction B
    - PENDING_FACTION_B: Faction B (higher ID) initiated, waiting for Faction A
    - ACTIVE: Both factions have approved the alliance
    """
    id: Optional[int] = None
    faction_a_id: int = 0
    faction_b_id: int = 0
    status: str = "PENDING_FACTION_A"
    initiated_by_faction_id: int = 0
    created_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    activated_turn: Optional[int] = None
    guild_id: Optional[int] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert this Alliance entry.
        Uses ON CONFLICT DO NOTHING to avoid duplicates.
        """
        query = """
        INSERT INTO Alliance (
            faction_a_id, faction_b_id, status, initiated_by_faction_id,
            created_at, activated_at, activated_turn, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (faction_a_id, faction_b_id, guild_id) DO NOTHING
        RETURNING id;
        """
        result = await conn.fetchrow(
            query,
            self.faction_a_id,
            self.faction_b_id,
            self.status,
            self.initiated_by_faction_id,
            self.created_at or datetime.now(),
            self.activated_at,
            self.activated_turn,
            self.guild_id
        )
        if result:
            self.id = result['id']

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Alliance entry.
        """
        query = """
        INSERT INTO Alliance (
            faction_a_id, faction_b_id, status, initiated_by_faction_id,
            created_at, activated_at, activated_turn, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (faction_a_id, faction_b_id, guild_id) DO UPDATE
        SET status = EXCLUDED.status,
            activated_at = EXCLUDED.activated_at,
            activated_turn = EXCLUDED.activated_turn
        RETURNING id;
        """
        result = await conn.fetchrow(
            query,
            self.faction_a_id,
            self.faction_b_id,
            self.status,
            self.initiated_by_faction_id,
            self.created_at or datetime.now(),
            self.activated_at,
            self.activated_turn,
            self.guild_id
        )
        if result:
            self.id = result['id']

    @classmethod
    async def fetch_by_factions(
        cls,
        conn: asyncpg.Connection,
        faction_id_1: int,
        faction_id_2: int,
        guild_id: int
    ) -> Optional["Alliance"]:
        """
        Fetch an alliance between two factions.
        Automatically handles canonical ordering (a < b).
        """
        # Ensure canonical ordering
        faction_a_id = min(faction_id_1, faction_id_2)
        faction_b_id = max(faction_id_1, faction_id_2)

        row = await conn.fetchrow("""
            SELECT id, faction_a_id, faction_b_id, status, initiated_by_faction_id,
                   created_at, activated_at, activated_turn, guild_id
            FROM Alliance
            WHERE faction_a_id = $1
            AND faction_b_id = $2
            AND guild_id = $3;
        """, faction_a_id, faction_b_id, guild_id)

        return cls(**row) if row else None

    @classmethod
    async def fetch_by_faction(
        cls,
        conn: asyncpg.Connection,
        faction_id: int,
        guild_id: int
    ) -> List["Alliance"]:
        """
        Fetch all alliances involving a specific faction.
        """
        rows = await conn.fetch("""
            SELECT id, faction_a_id, faction_b_id, status, initiated_by_faction_id,
                   created_at, activated_at, activated_turn, guild_id
            FROM Alliance
            WHERE (faction_a_id = $1 OR faction_b_id = $1)
            AND guild_id = $2
            ORDER BY created_at DESC;
        """, faction_id, guild_id)

        return [cls(**row) for row in rows]

    @classmethod
    async def fetch_all_active(
        cls,
        conn: asyncpg.Connection,
        guild_id: int
    ) -> List["Alliance"]:
        """
        Fetch all active alliances in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, faction_a_id, faction_b_id, status, initiated_by_faction_id,
                   created_at, activated_at, activated_turn, guild_id
            FROM Alliance
            WHERE status = 'ACTIVE'
            AND guild_id = $1
            ORDER BY activated_at DESC;
        """, guild_id)

        return [cls(**row) for row in rows]

    @classmethod
    async def fetch_all(
        cls,
        conn: asyncpg.Connection,
        guild_id: int
    ) -> List["Alliance"]:
        """
        Fetch all alliances in a guild (any status).
        """
        rows = await conn.fetch("""
            SELECT id, faction_a_id, faction_b_id, status, initiated_by_faction_id,
                   created_at, activated_at, activated_turn, guild_id
            FROM Alliance
            WHERE guild_id = $1
            ORDER BY status, created_at DESC;
        """, guild_id)

        return [cls(**row) for row in rows]

    @classmethod
    async def delete(
        cls,
        conn: asyncpg.Connection,
        faction_id_1: int,
        faction_id_2: int,
        guild_id: int
    ) -> bool:
        """
        Delete an alliance between two factions.
        Automatically handles canonical ordering.
        """
        # Ensure canonical ordering
        faction_a_id = min(faction_id_1, faction_id_2)
        faction_b_id = max(faction_id_1, faction_id_2)

        result = await conn.execute("""
            DELETE FROM Alliance
            WHERE faction_a_id = $1
            AND faction_b_id = $2
            AND guild_id = $3;
        """, faction_a_id, faction_b_id, guild_id)

        deleted = result.startswith("DELETE") and not result.startswith("DELETE 0")
        logger.info(f"Deleted Alliance between factions {faction_a_id} and {faction_b_id} in guild {guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all_for_guild(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all Alliance entries for a guild.
        """
        result = await conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", guild_id)
        logger.warning(f"All Alliance entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the Alliance has valid data.
        """
        if self.faction_a_id <= 0:
            return False, "faction_a_id must be a positive integer"

        if self.faction_b_id <= 0:
            return False, "faction_b_id must be a positive integer"

        if self.faction_a_id >= self.faction_b_id:
            return False, "faction_a_id must be less than faction_b_id"

        if self.status not in ("PENDING_FACTION_A", "PENDING_FACTION_B", "ACTIVE"):
            return False, f"Invalid status: {self.status}"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
