import asyncpg
from dataclasses import dataclass
from typing import Optional


@dataclass
class ServerConfig:
    guild_id: int
    default_limit: Optional[int] = None
    letter_delay: Optional[int] = None
    category_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this ServerConfig entry.
        If a row with the same guild_id exists, update it instead.
        """
        query = """
        INSERT INTO ServerConfig (guild_id, default_limit, letter_delay, category_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (guild_id) DO UPDATE
        SET default_limit = EXCLUDED.default_limit,
            letter_delay  = EXCLUDED.letter_delay,
            category_id   = EXCLUDED.category_id;
        """

        await conn.execute(
            query,
            self.guild_id,
            self.default_limit,
            self.letter_delay,
            self.category_id
        )

    def verify(self) -> Tuple[bool, str]:
        """
        Verify that all numeric fields are non-negative if not None.
        Returns (True, '') if all valid, else (False, 'name of invalid field').
        """
        for field_name in ["default_limit", "letter_delay", "category_id"]:
            value = getattr(self, field_name)
            if value is not None and value < 0:
                return False, f"Invalid input, {field_name} must be >= 0"

        return True, ""
        
        
    @classmethod
    async def fetch(cls, conn: asyncpg.Connection, guild_id: int) -> Optional["ServerConfig"]:
        """
        Fetch a ServerConfig record by guild_id.
        Returns a ServerConfig instance or None if not found.
        """
        row = await conn.fetchrow("""
            SELECT guild_id, default_limit, letter_delay, category_id
            FROM ServerConfig
            WHERE guild_id = $1;
        """, guild_id)

        if row:
            return cls(**row)
        return None

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete a specific ServerConfig entry by guild_id.
        """
        result = await conn.execute("DELETE FROM ServerConfig WHERE guild_id = $1;", guild_id)
        print(f"🗑️ Deleted entry for guild_id={guild_id}. Result: {result}")

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all entries from the ServerConfig table.
        """
        result = await conn.execute("DELETE FROM ServerConfig;")
        print(f"⚠️ All entries deleted from ServerConfig. Result: {result}")
    
    @classmethod
    async def print_all(cls, conn: asyncpg.Connection):
        """
        Fetch and print all entries from the ServerConfig table.
        """
        rows = await conn.fetch("""
            SELECT guild_id, default_limit, letter_delay, category_id
            FROM ServerConfig
            ORDER BY guild_id;
        """)

        if not rows:
            print("📭 No entries found in ServerConfig.")
            return

        print("📋 ServerConfig entries:\n")
        for row in rows:
            print(
                f"🧩 Guild ID: {row['guild_id']}\n"
                f"   • Default Limit: {row['default_limit']}\n"
                f"   • Letter Delay:  {row['letter_delay']}\n"
                f"   • Category ID:   {row['category_id']}\n"
            )

