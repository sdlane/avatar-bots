import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class WarParticipant:
    """
    Represents a faction's participation in a war.

    Each faction can only be on one side of a war.
    Side values: "SIDE_A" or "SIDE_B"
    """
    id: Optional[int] = None
    war_id: int = 0                       # References War.id (internal ID)
    faction_id: int = 0                   # References Faction.id (internal ID)
    side: str = ""                        # "SIDE_A" or "SIDE_B"
    joined_turn: int = 0                  # Turn they joined the war
    is_original_declarer: bool = False    # True if they declared war (not dragged in)
    guild_id: Optional[int] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert this WarParticipant entry.
        Uses ON CONFLICT DO NOTHING to avoid duplicates.
        """
        query = """
        INSERT INTO WarParticipant (
            war_id, faction_id, side, joined_turn, is_original_declarer, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (war_id, faction_id, guild_id) DO NOTHING
        RETURNING id;
        """
        result = await conn.fetchrow(
            query,
            self.war_id,
            self.faction_id,
            self.side,
            self.joined_turn,
            self.is_original_declarer,
            self.guild_id
        )
        if result:
            self.id = result['id']

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this WarParticipant entry.
        """
        query = """
        INSERT INTO WarParticipant (
            war_id, faction_id, side, joined_turn, is_original_declarer, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (war_id, faction_id, guild_id) DO UPDATE
        SET side = EXCLUDED.side,
            is_original_declarer = EXCLUDED.is_original_declarer
        RETURNING id;
        """
        result = await conn.fetchrow(
            query,
            self.war_id,
            self.faction_id,
            self.side,
            self.joined_turn,
            self.is_original_declarer,
            self.guild_id
        )
        if result:
            self.id = result['id']

    @classmethod
    async def fetch_by_war(
        cls,
        conn: asyncpg.Connection,
        war_id: int,
        guild_id: int
    ) -> List["WarParticipant"]:
        """
        Fetch all participants in a war.
        """
        rows = await conn.fetch("""
            SELECT id, war_id, faction_id, side, joined_turn, is_original_declarer, guild_id
            FROM WarParticipant
            WHERE war_id = $1
            AND guild_id = $2
            ORDER BY side, joined_turn;
        """, war_id, guild_id)

        return [cls(**row) for row in rows]

    @classmethod
    async def fetch_by_faction(
        cls,
        conn: asyncpg.Connection,
        faction_id: int,
        guild_id: int
    ) -> List["WarParticipant"]:
        """
        Fetch all wars a faction is participating in.
        """
        rows = await conn.fetch("""
            SELECT id, war_id, faction_id, side, joined_turn, is_original_declarer, guild_id
            FROM WarParticipant
            WHERE faction_id = $1
            AND guild_id = $2
            ORDER BY joined_turn DESC;
        """, faction_id, guild_id)

        return [cls(**row) for row in rows]

    @classmethod
    async def fetch_by_war_and_faction(
        cls,
        conn: asyncpg.Connection,
        war_id: int,
        faction_id: int,
        guild_id: int
    ) -> Optional["WarParticipant"]:
        """
        Check if a faction is participating in a specific war.
        """
        row = await conn.fetchrow("""
            SELECT id, war_id, faction_id, side, joined_turn, is_original_declarer, guild_id
            FROM WarParticipant
            WHERE war_id = $1
            AND faction_id = $2
            AND guild_id = $3;
        """, war_id, faction_id, guild_id)

        return cls(**row) if row else None

    @classmethod
    async def fetch_by_war_and_side(
        cls,
        conn: asyncpg.Connection,
        war_id: int,
        side: str,
        guild_id: int
    ) -> List["WarParticipant"]:
        """
        Fetch all participants on a specific side of a war.
        """
        rows = await conn.fetch("""
            SELECT id, war_id, faction_id, side, joined_turn, is_original_declarer, guild_id
            FROM WarParticipant
            WHERE war_id = $1
            AND side = $2
            AND guild_id = $3
            ORDER BY joined_turn;
        """, war_id, side, guild_id)

        return [cls(**row) for row in rows]

    @classmethod
    async def delete(
        cls,
        conn: asyncpg.Connection,
        war_id: int,
        faction_id: int,
        guild_id: int
    ) -> bool:
        """
        Remove a faction from a war.
        """
        result = await conn.execute("""
            DELETE FROM WarParticipant
            WHERE war_id = $1
            AND faction_id = $2
            AND guild_id = $3;
        """, war_id, faction_id, guild_id)

        deleted = result.startswith("DELETE") and not result.startswith("DELETE 0")
        logger.info(f"Removed faction {faction_id} from war {war_id} in guild {guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all_for_war(
        cls,
        conn: asyncpg.Connection,
        war_id: int,
        guild_id: int
    ):
        """
        Delete all participants from a war.
        """
        result = await conn.execute("""
            DELETE FROM WarParticipant
            WHERE war_id = $1
            AND guild_id = $2;
        """, war_id, guild_id)
        logger.info(f"All participants deleted from war {war_id} in guild {guild_id}. Result: {result}")

    @classmethod
    async def delete_all_for_guild(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all WarParticipant entries for a guild.
        """
        result = await conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", guild_id)
        logger.warning(f"All WarParticipant entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the WarParticipant has valid data.
        """
        if self.war_id <= 0:
            return False, "war_id must be a positive integer"

        if self.faction_id <= 0:
            return False, "faction_id must be a positive integer"

        if self.side not in ("SIDE_A", "SIDE_B"):
            return False, f"Invalid side: {self.side}. Must be 'SIDE_A' or 'SIDE_B'"

        if self.joined_turn < 0:
            return False, "joined_turn must be non-negative"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
