import asyncpg
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class Character:
    id: Optional[int] = None
    identifier: str = ""
    name: str = ""
    user_id: Optional[int] = None
    channel_id: Optional[int] = None
    letter_limit: Optional[int] = None
    letter_count: int = 0
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Character entry.
        The pair (identifier, guild_id) must be unique.
        """
        query = """
        INSERT INTO Character (
            identifier, name, user_id, channel_id,
            letter_limit, letter_count, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (identifier, guild_id) DO UPDATE
        SET name = EXCLUDED.name,
            user_id = EXCLUDED.user_id,
            channel_id = EXCLUDED.channel_id,
            letter_limit = EXCLUDED.letter_limit,
            letter_count = EXCLUDED.letter_count;
        """
        await conn.execute(
            query,
            self.identifier,
            self.name,
            self.user_id,
            self.channel_id,
            self.letter_limit,
            self.letter_count,
            self.guild_id
        )

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, char_id: int) -> Optional["Character"]:
        """
        Fetch a Character by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id
            FROM Character
            WHERE id = $1;
        """, char_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_by_identifier(cls, conn: asyncpg.Connection, identifier: str, guild_id: int) -> Optional["Character"]:
        """
        Fetch a Character by its (identifier, guild_id) pair.
        """
        row = await conn.fetchrow("""
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id
            FROM Character
            WHERE identifier = $1 AND guild_id = $2;
        """, identifier, guild_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_unowned(cls, conn: asyncpg.Connection, guild_id: int) -> List["Character"]:
        """
        Fetch all Characters in a guild that have no associated user (user_id IS NULL).
        """
        rows = await conn.fetch("""
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id
            FROM Character
            WHERE guild_id = $1 AND user_id IS NULL
            ORDER BY id;
        """, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def reset_letter_count(cls, conn: asyncpg.Connection, guild_id: int) -> int:
        """
        Reset letter_count to 0 for all Characters in the given guild.
        Returns the number of rows affected.
        """
        result = await conn.execute("""
            UPDATE Character
            SET letter_count = 0
            WHERE guild_id = $1;
        """, guild_id)

        # Result looks like "UPDATE X" — extract number of affected rows
        updated_count = int(result.split()[-1]) if result.startswith("UPDATE") else 0
        print(f"🔄 Reset letter_count for {updated_count} characters in guild {guild_id}.")
        return updated_count
    
    @classmethod
    async def print_all(cls, conn: asyncpg.Connection):
        """
        Fetch and print all Character entries.
        """
        rows = await conn.fetch("""
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id
            FROM Character
            ORDER BY id;
        """)

        if not rows:
            print("📭 No entries found in Character table.")
            return

        print("📜 Character entries:\n")
        for row in rows:
            print(
                f"🧙 ID: {row['id']}\n"
                f"   • Identifier:   {row['identifier']}\n"
                f"   • Name:         {row['name']}\n"
                f"   • User ID:      {row['user_id']}\n"
                f"   • Channel ID:   {row['channel_id']}\n"
                f"   • Letter Limit: {row['letter_limit']}\n"
                f"   • Letter Count: {row['letter_count']}\n"
                f"   • Guild ID:     {row['guild_id']}\n"
            )

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, char_id: int) -> bool:
        """
        Delete a Character by ID.
        """
        result = await conn.execute("DELETE FROM Character WHERE id = $1;", char_id)
        deleted = result.startswith("DELETE 1")
        print(f"🗑️ Deleted Character ID={char_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_by_identifier(cls, conn: asyncpg.Connection, identifier: str) -> bool:
        """
        Delete a Character by its identifier (guild-independent).
        Returns True if a row was deleted, False otherwise.
        """
        result = await conn.execute("DELETE FROM Character WHERE identifier = $1;", identifier)
        deleted = result.startswith("DELETE 1")
        print(f"🗑️ Deleted Character with identifier='{identifier}'. Result: {result}")
        return deleted
    
    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all entries from the Character table.
        """
        result = await conn.execute("DELETE FROM Character;")
        print(f"⚠️ All entries deleted from Character table. Result: {result}")
