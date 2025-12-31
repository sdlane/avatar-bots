import asyncpg
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class Order:
    id: Optional[int] = None
    order_id: str = ""
    order_type: str = ""
    unit_ids: List[int] = field(default_factory=list)
    character_id: int = 0
    turn_number: int = 0
    phase: str = ""
    priority: int = 0
    status: str = "PENDING"
    order_data: Dict[str, Any] = field(default_factory=dict)
    result_data: Optional[Dict[str, Any]] = None
    submitted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    updated_turn: Optional[int] = None
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Order entry.
        The pair (order_id, guild_id) must be unique.
        """
        query = """
        INSERT INTO "Order" (
            order_id, order_type, unit_ids, character_id, turn_number,
            phase, priority, status, order_data, result_data,
            submitted_at, updated_at, updated_turn, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ON CONFLICT (order_id, guild_id) DO UPDATE
        SET order_type = EXCLUDED.order_type,
            unit_ids = EXCLUDED.unit_ids,
            character_id = EXCLUDED.character_id,
            turn_number = EXCLUDED.turn_number,
            phase = EXCLUDED.phase,
            priority = EXCLUDED.priority,
            status = EXCLUDED.status,
            order_data = EXCLUDED.order_data,
            result_data = EXCLUDED.result_data,
            updated_at = EXCLUDED.updated_at,
            updated_turn = EXCLUDED.updated_turn;
        """
        await conn.execute(
            query,
            self.order_id,
            self.order_type,
            self.unit_ids,
            self.character_id,
            self.turn_number,
            self.phase,
            self.priority,
            self.status,
            json.dumps(self.order_data) if self.order_data else '{}',
            json.dumps(self.result_data) if self.result_data else None,
            self.submitted_at,
            self.updated_at,
            self.updated_turn,
            self.guild_id
        )

    @classmethod
    async def fetch_by_order_id(cls, conn: asyncpg.Connection, order_id: str, guild_id: int) -> Optional["Order"]:
        """
        Fetch an Order by order_id and guild_id.
        """
        row = await conn.fetchrow("""
            SELECT id, order_id, order_type, unit_ids, character_id, turn_number,
                   phase, priority, status, order_data, result_data,
                   submitted_at, updated_at, updated_turn, guild_id
            FROM "Order"
            WHERE order_id = $1 AND guild_id = $2;
        """, order_id, guild_id)
        if not row:
            return None
        data = dict(row)
        data['order_data'] = json.loads(data['order_data']) if data['order_data'] else {}
        data['result_data'] = json.loads(data['result_data']) if data['result_data'] else None
        return cls(**data)

    @classmethod
    async def fetch_by_turn_and_phase(
        cls, conn: asyncpg.Connection, turn_number: int, phase: str, status: List[str], guild_id: int
    ) -> List["Order"]:
        """
        Fetch all orders for a specific turn and phase with given statuses.
        Orders are returned sorted by priority then submitted_at (FIFO).
        """
        rows = await conn.fetch("""
            SELECT id, order_id, order_type, unit_ids, character_id, turn_number,
                   phase, priority, status, order_data, result_data,
                   submitted_at, updated_at, updated_turn, guild_id
            FROM "Order"
            WHERE turn_number = $1 AND phase = $2 AND status = ANY($3) AND guild_id = $4
            ORDER BY priority, submitted_at;
        """, turn_number, phase, status, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['order_data'] = json.loads(data['order_data']) if data['order_data'] else {}
            data['result_data'] = json.loads(data['result_data']) if data['result_data'] else None
            result.append(cls(**data))
        return result

    @classmethod
    async def fetch_by_units(
        cls, conn: asyncpg.Connection, unit_ids: List[int], statuses: List[str], guild_id: int
    ) -> List["Order"]:
        """
        Fetch all orders that include any of the given unit_ids with the given statuses.
        """
        rows = await conn.fetch("""
            SELECT id, order_id, order_type, unit_ids, character_id, turn_number,
                   phase, priority, status, order_data, result_data,
                   submitted_at, updated_at, updated_turn, guild_id
            FROM "Order"
            WHERE unit_ids && $1::INTEGER[] AND status = ANY($2) AND guild_id = $3;
        """, unit_ids, statuses, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['order_data'] = json.loads(data['order_data']) if data['order_data'] else {}
            data['result_data'] = json.loads(data['result_data']) if data['result_data'] else None
            result.append(cls(**data))
        return result

    @classmethod
    async def fetch_by_character(
        cls, conn: asyncpg.Connection, character_id: int, guild_id: int
    ) -> List["Order"]:
        """
        Fetch all orders for a character (not completed or cancelled).
        """
        rows = await conn.fetch("""
            SELECT id, order_id, order_type, unit_ids, character_id, turn_number,
                   phase, priority, status, order_data, result_data,
                   submitted_at, updated_at, updated_turn, guild_id
            FROM "Order"
            WHERE character_id = $1 AND guild_id = $2
            AND status NOT IN ('SUCCESS', 'FAILED', 'CANCELLED')
            ORDER BY submitted_at;
        """, character_id, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['order_data'] = json.loads(data['order_data']) if data['order_data'] else {}
            data['result_data'] = json.loads(data['result_data']) if data['result_data'] else None
            result.append(cls(**data))
        return result

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, order_id: str, guild_id: int) -> bool:
        """
        Delete an Order by order_id and guild_id.
        """
        result = await conn.execute('DELETE FROM "Order" WHERE order_id = $1 AND guild_id = $2;', order_id, guild_id)
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted Order with order_id='{order_id}'. Result: {result}")
        return deleted
