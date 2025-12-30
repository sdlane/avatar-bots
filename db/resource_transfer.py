import asyncpg
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ResourceTransfer:
    id: Optional[int] = None
    from_character_id: Optional[int] = None
    to_character_id: Optional[int] = None
    ore: int = 0
    lumber: int = 0
    coal: int = 0
    rations: int = 0
    cloth: int = 0
    reason: Optional[str] = None
    transfer_time: Optional[datetime] = None
    turn_number: Optional[int] = None
    guild_id: Optional[int] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert this ResourceTransfer entry (audit log, no updates).
        """
        query = """
        INSERT INTO ResourceTransfer (
            from_character_id, to_character_id, ore, lumber, coal, rations, cloth,
            reason, transfer_time, turn_number, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11);
        """
        await conn.execute(
            query,
            self.from_character_id,
            self.to_character_id,
            self.ore,
            self.lumber,
            self.coal,
            self.rations,
            self.cloth,
            self.reason,
            self.transfer_time if self.transfer_time else datetime.now(),
            self.turn_number,
            self.guild_id
        )

    @classmethod
    async def fetch_by_character(cls, conn: asyncpg.Connection, character_id: int, guild_id: int, limit: int = 50) -> List["ResourceTransfer"]:
        """
        Fetch recent resource transfers involving a character.
        """
        rows = await conn.fetch("""
            SELECT id, from_character_id, to_character_id, ore, lumber, coal, rations, cloth,
                   reason, transfer_time, turn_number, guild_id
            FROM ResourceTransfer
            WHERE (from_character_id = $1 OR to_character_id = $1) AND guild_id = $2
            ORDER BY transfer_time DESC
            LIMIT $3;
        """, character_id, guild_id, limit)
        return [cls(**row) for row in rows]

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all ResourceTransfer entries for a guild.
        """
        result = await conn.execute("DELETE FROM ResourceTransfer WHERE guild_id = $1;", guild_id)
        logger.warning(f"All ResourceTransfer entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the ResourceTransfer has valid data.
        """
        resource_fields = [
            ("ore", self.ore),
            ("lumber", self.lumber),
            ("coal", self.coal),
            ("rations", self.rations),
            ("cloth", self.cloth)
        ]

        for field_name, value in resource_fields:
            if value < 0:
                return False, f"{field_name} must be >= 0"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
