import asyncpg
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class HawkyTask:
    id: Optional[int] = None
    task: str = ""
    recipient_id: Optional[int] = None
    parameter: Optional[str] = None
    scheduled_time: Optional[datetime] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Inserts a new task or updates an existing one if ID already exists.
        """
        query = """
        INSERT INTO HawkyTask (id, task, recipient_id, parameter, scheduled_time)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE
        SET task = EXCLUDED.task,
            recipient_id = EXCLUDED.recipient_id,
            parameter = EXCLUDED.parameter,
            scheduled_time = EXCLUDED.scheduled_time
        RETURNING id;
        """
        row = await conn.fetchrow(
            query,
            self.id,
            self.task,
            self.recipient_id,
            self.parameter,
            self.scheduled_time,
        )
        self.id = row["id"]
        return self.id

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection) -> List["HawkyTask"]:
        """
        Retrieve all tasks.
        """
        rows = await conn.fetch("SELECT id, task, recipient_id, parameter, scheduled_time FROM HawkyTask ORDER BY scheduled_time;")
        return [cls(**row) for row in rows]

    @classmethod
    async def pop_next_task(cls, conn: asyncpg.Connection, before_time: datetime) -> Optional["HawkyTask"]:
        """
        Retrieves and removes the next task scheduled before the given time.
        Returns the task or None if no tasks are due.
        """
        async with conn.transaction():
            row = await conn.fetchrow("""
                SELECT id, task, recipient_id, parameter, scheduled_time
                FROM HawkyTask
                WHERE scheduled_time <= $1
                ORDER BY scheduled_time ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED;
            """, before_time)

            if not row:
                return None

            # Delete the retrieved row
            await conn.execute("DELETE FROM HawkyTask WHERE id = $1;", row["id"])

            return cls(**row)

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, task_id: int) -> bool:
        """
        Deletes a specific task by ID.
        Returns True if a row was deleted.
        """
        result = await conn.execute("DELETE FROM HawkyTask WHERE id = $1;", task_id)
        return result.endswith("1")

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Deletes all tasks from the table.
        """
        await conn.execute("DELETE FROM HawkyTask;")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that no numeric field is less than 0.
        Returns (True, "") if valid, otherwise (False, "field < 0").
        """
        for field_name in ["recipient_id"]:
            value = getattr(self, field_name)
            if value is not None and value < 0:
                return False, f"{field_name} less than 0"
        return True, ""
