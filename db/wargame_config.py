import asyncpg
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class WargameConfig:
    guild_id: int = 0
    current_turn: int = 0
    turn_resolution_enabled: bool = False
    last_turn_time: Optional[datetime] = None
    max_movement_stat: int = 4
    gm_reports_channel_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this WargameConfig entry.
        guild_id is the primary key.
        """
        query = """
        INSERT INTO WargameConfig (
            guild_id, current_turn, turn_resolution_enabled, last_turn_time,
            max_movement_stat, gm_reports_channel_id
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (guild_id) DO UPDATE
        SET current_turn = EXCLUDED.current_turn,
            turn_resolution_enabled = EXCLUDED.turn_resolution_enabled,
            last_turn_time = EXCLUDED.last_turn_time,
            max_movement_stat = EXCLUDED.max_movement_stat,
            gm_reports_channel_id = EXCLUDED.gm_reports_channel_id;
        """
        await conn.execute(
            query,
            self.guild_id,
            self.current_turn,
            self.turn_resolution_enabled,
            self.last_turn_time,
            self.max_movement_stat,
            self.gm_reports_channel_id
        )

    @classmethod
    async def fetch(cls, conn: asyncpg.Connection, guild_id: int) -> Optional["WargameConfig"]:
        """
        Fetch WargameConfig by guild_id.
        """
        row = await conn.fetchrow("""
            SELECT guild_id, current_turn, turn_resolution_enabled, last_turn_time,
                   max_movement_stat, gm_reports_channel_id
            FROM WargameConfig
            WHERE guild_id = $1;
        """, guild_id)
        return cls(**row) if row else None

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, guild_id: int) -> bool:
        """
        Delete WargameConfig by guild_id.
        """
        result = await conn.execute(
            "DELETE FROM WargameConfig WHERE guild_id = $1;",
            guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted WargameConfig guild_id={guild_id}. Result: {result}")
        return deleted

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the WargameConfig has valid data.
        """
        if self.guild_id < 0:
            return False, "guild_id must be valid"

        if self.current_turn < 0:
            return False, "current_turn must be >= 0"

        if self.max_movement_stat < 0:
            return False, "max_movement_stat must be >= 0"

        return True, ""
