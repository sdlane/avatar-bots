import asyncpg
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class TurnLog:
    id: Optional[int] = None
    turn_number: int = 0
    phase: str = ""
    event_type: str = ""
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    event_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    guild_id: Optional[int] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert this TurnLog entry.
        """
        query = """
        INSERT INTO TurnLog (
            turn_number, phase, event_type, entity_type, entity_id,
            event_data, timestamp, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
        """
        await conn.execute(
            query,
            self.turn_number,
            self.phase,
            self.event_type,
            self.entity_type,
            self.entity_id,
            json.dumps(self.event_data) if self.event_data else '{}',
            self.timestamp or datetime.now(),
            self.guild_id
        )

    @classmethod
    async def fetch_by_turn(cls, conn: asyncpg.Connection, turn_number: int, guild_id: int) -> List["TurnLog"]:
        """
        Fetch all logs for a specific turn.
        """
        rows = await conn.fetch("""
            SELECT id, turn_number, phase, event_type, entity_type, entity_id,
                   event_data, timestamp, guild_id
            FROM TurnLog
            WHERE turn_number = $1 AND guild_id = $2
            ORDER BY timestamp;
        """, turn_number, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['event_data'] = json.loads(data['event_data']) if data['event_data'] else {}
            result.append(cls(**data))
        return result

    @classmethod
    async def fetch_by_entity(
        cls, conn: asyncpg.Connection, entity_type: str, entity_id: int, guild_id: int
    ) -> List["TurnLog"]:
        """
        Fetch all logs for a specific entity.
        """
        rows = await conn.fetch("""
            SELECT id, turn_number, phase, event_type, entity_type, entity_id,
                   event_data, timestamp, guild_id
            FROM TurnLog
            WHERE entity_type = $1 AND entity_id = $2 AND guild_id = $3
            ORDER BY timestamp;
        """, entity_type, entity_id, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['event_data'] = json.loads(data['event_data']) if data['event_data'] else {}
            result.append(cls(**data))
        return result
