import asyncpg
from dataclasses import dataclass
from typing import Optional


@dataclass
class Character:
    id: Optional[int] = None
    identifier: str = ""
    name: str = ""
    user_id: Optional[int] = None
    channel_id: Optional[int] = None
    letter_limit: Optional[int] = None
    letter_count: int = 0
    guild_id: int = 0

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
    async def delete(cls, conn: asyncpg.Connection, char_id: int):
        """
        Delete a Character by ID.
        """
        result = await conn.execute("DELETE FROM Character WHERE id = $1;", char_id)
        print(f"🗑️ Deleted Character ID={char_id}. Result: {result}")

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all entries from the Character table.
        """
        result = await conn.execute("DELETE FROM Character;")
        print(f"⚠️ All entries deleted from Character table. Result: {result}")


# --- Example usage ---
async def main():
    conn = await asyncpg.connect("postgresql://GOBO:password@db:5432/GOBO")

    # Create or update a character
    char = Character(
        identifier="Arcanist01",
        name="Arcanist Vel Dray",
        user_id=123456789012345678,
        channel_id=987654321098765432,
        letter_limit=5,
        letter_count=1,
        guild_id=111111111111111111
    )
    await char.upsert(conn)

    # Print all characters
    await Character.print_all(conn)

    # Delete one
    # await Character.delete(conn, 1)

    # Delete all
    # await Character.delete_all(conn)

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
