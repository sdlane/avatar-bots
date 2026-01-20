import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class Alias:
    id: Optional[int] = None
    character_id: int = 0
    alias: str = ""
    guild_id: int = 0

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert a new Alias entry into the database.
        """
        query = """
        INSERT INTO Alias (character_id, alias, guild_id)
        VALUES ($1, $2, $3)
        RETURNING id;
        """
        row = await conn.fetchrow(query, self.character_id, self.alias, self.guild_id)
        self.id = row['id']

    @classmethod
    async def fetch_by_alias(cls, conn: asyncpg.Connection, alias: str, guild_id: int) -> Optional["Alias"]:
        """
        Fetch an Alias by its alias string and guild_id.
        """
        row = await conn.fetchrow("""
            SELECT id, character_id, alias, guild_id
            FROM Alias
            WHERE alias = $1 AND guild_id = $2;
        """, alias, guild_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_by_character_id(cls, conn: asyncpg.Connection, character_id: int) -> List["Alias"]:
        """
        Fetch all aliases for a given character_id.
        """
        rows = await conn.fetch("""
            SELECT id, character_id, alias, guild_id
            FROM Alias
            WHERE character_id = $1;
        """, character_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def delete_by_id(cls, conn: asyncpg.Connection, alias_id: int):
        """
        Delete an alias by its ID.
        """
        await conn.execute("DELETE FROM Alias WHERE id = $1;", alias_id)

    @classmethod
    async def delete_by_alias(cls, conn: asyncpg.Connection, alias: str, guild_id: int):
        """
        Delete an alias by its alias string and guild_id.
        """
        await conn.execute("DELETE FROM Alias WHERE alias = $1 AND guild_id = $2;", alias, guild_id)

    @classmethod
    async def exists(cls, conn: asyncpg.Connection, alias: str, guild_id: int) -> bool:
        """
        Check if an alias already exists.
        """
        row = await conn.fetchrow("""
            SELECT 1 FROM Alias WHERE alias = $1 AND guild_id = $2;
        """, alias, guild_id)
        return row is not None

    @classmethod
    async def fetch_all_by_guild(cls, conn: asyncpg.Connection, guild_id: int) -> List["Alias"]:
        """
        Fetch all aliases for a given guild_id.
        """
        rows = await conn.fetch("""
            SELECT id, character_id, alias, guild_id
            FROM Alias
            WHERE guild_id = $1
            ORDER BY alias;
        """, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def delete_all_by_guild(cls, conn: asyncpg.Connection, guild_id: int) -> int:
        """
        Delete all aliases for a given guild_id.
        Returns the number of rows deleted.
        """
        result = await conn.execute("DELETE FROM Alias WHERE guild_id = $1;", guild_id)
        deleted_count = int(result.split()[-1]) if result.startswith("DELETE") else 0
        logger.info(f"Deleted {deleted_count} aliases for guild {guild_id}")
        return deleted_count
