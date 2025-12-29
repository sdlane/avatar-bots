import asyncpg
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class HawkyTask:
    id: Optional[int] = None
    task: str = ""
    recipient_identifier: Optional[str] = None
    sender_identifier: Option[str] = None
    parameter: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    guild_id: int = 0
    
    async def insert(self, conn: asyncpg.Connection):
        """
        Inserts a new task or updates an existing one if ID already exists.
        """
        query = """
        INSERT INTO HawkyTask (task, recipient_identifier, sender_identifier, parameter, scheduled_time, guild_id)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id;
        """
        row = await conn.fetchrow(
            query,
            self.task,
            self.recipient_identifier,
            self.sender_identifier,
            self.parameter,
            self.scheduled_time,
            self.guild_id
        )
        self.id = row["id"]
        return self.id

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection) -> List["HawkyTask"]:
        """
        Retrieve all tasks.
        """
        rows = await conn.fetch("SELECT id, task, recipient_identifier, sender_identifier, parameter, scheduled_time FROM HawkyTask ORDER BY scheduled_time;")
        return [cls(**row) for row in rows]

    @classmethod
    async def pop_next_task(cls, conn: asyncpg.Connection, before_time: datetime) -> Optional["HawkyTask"]:
        """
        Retrieves and removes the next task scheduled before the given time.
        Returns the task or None if no tasks are due.
        """
        async with conn.transaction():
            row = await conn.fetchrow("""
                SELECT id, task, recipient_identifier, sender_identifier, parameter, scheduled_time, guild_id
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

    @classmethod
    async def exists_for_guild(cls, conn: asyncpg.Connection, task_type: str, guild_id: int) -> bool:
        """
        Check if a task of the given type exists for the specified guild.
        Returns True if at least one task exists.
        """
        row = await conn.fetchrow("""
            SELECT EXISTS(
                SELECT 1
                FROM HawkyTask
                WHERE task = $1 AND guild_id = $2
            );
        """, task_type, guild_id)
        return row['exists']

    @classmethod
    async def print_all(cls, conn: asyncpg.Connection):
        """
        Prints all tasks in the table in a readable format.
        """
        rows = await conn.fetch("""
            SELECT *
            FROM HawkyTask
            ORDER BY scheduled_time;
        """)

        if not rows:
            print("📭 No tasks found in hawky_task.")
            return

        print("📋 Hawky Tasks:\n")
        for row in rows:
            print(
                f"ID: {row['id']}\n"
                f"   Task: {row['task']}\n"
                f"   Recipient identifier: {row['recipient_identifier']}\n"
                f"   Sender identifier: {row['sender_identifier']}\n"
                f"   Parameter: {row['parameter']}\n"
                f"   Scheduled Time: {row['scheduled_time']}\n"
                f"   Guild ID: {row['guild_id']}\n"
            )
