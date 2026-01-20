import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


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
    # Resource production per turn
    ore_production: int = 0
    lumber_production: int = 0
    coal_production: int = 0
    rations_production: int = 0
    cloth_production: int = 0
    platinum_production: int = 0
    # Victory points
    victory_points: int = 0

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Character entry.
        The pair (identifier, guild_id) must be unique.
        """
        query = """
        INSERT INTO Character (
            identifier, name, user_id, channel_id,
            letter_limit, letter_count, guild_id,
            ore_production, lumber_production, coal_production,
            rations_production, cloth_production, platinum_production,
            victory_points
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ON CONFLICT (identifier, guild_id) DO UPDATE
        SET name = EXCLUDED.name,
            user_id = EXCLUDED.user_id,
            channel_id = EXCLUDED.channel_id,
            letter_limit = EXCLUDED.letter_limit,
            letter_count = EXCLUDED.letter_count,
            ore_production = EXCLUDED.ore_production,
            lumber_production = EXCLUDED.lumber_production,
            coal_production = EXCLUDED.coal_production,
            rations_production = EXCLUDED.rations_production,
            cloth_production = EXCLUDED.cloth_production,
            platinum_production = EXCLUDED.platinum_production,
            victory_points = EXCLUDED.victory_points;
        """
        await conn.execute(
            query,
            self.identifier,
            self.name,
            self.user_id,
            self.channel_id,
            self.letter_limit,
            self.letter_count,
            self.guild_id,
            self.ore_production,
            self.lumber_production,
            self.coal_production,
            self.rations_production,
            self.cloth_production,
            self.platinum_production,
            self.victory_points
        )

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, char_id: int) -> Optional["Character"]:
        """
        Fetch a Character by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id,
                   ore_production, lumber_production, coal_production,
                   rations_production, cloth_production, platinum_production, victory_points
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
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id,
                   ore_production, lumber_production, coal_production,
                   rations_production, cloth_production, platinum_production, victory_points
            FROM Character
            WHERE identifier = $1 AND guild_id = $2;
        """, identifier, guild_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_by_user(cls, conn: asyncpg.Connection, user_id: int, guild_id: int) -> Optional["Character"]:
        """
        Fetch a Character by its (user_id, guild_id) pair.
        """
        row = await conn.fetchrow("""
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id,
                   ore_production, lumber_production, coal_production,
                   rations_production, cloth_production, platinum_production, victory_points
            FROM Character
            WHERE user_id = $1 AND guild_id = $2;
        """, user_id, guild_id)
        return cls(**row) if row else None

    
    @classmethod
    async def fetch_unowned(cls, conn: asyncpg.Connection, guild_id: int) -> List["Character"]:
        """
        Fetch all Characters in a guild that have no associated user (user_id IS NULL).
        """
        rows = await conn.fetch("""
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id,
                   ore_production, lumber_production, coal_production,
                   rations_production, cloth_production, platinum_production, victory_points
            FROM Character
            WHERE guild_id = $1 AND user_id IS NULL
            ORDER BY identifier;
        """, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["Character"]:
        """
        Fetch all Characters in a guild
        """
        rows = await conn.fetch("""
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id,
                   ore_production, lumber_production, coal_production,
                   rations_production, cloth_production, platinum_production, victory_points
            FROM Character
            WHERE guild_id = $1
            ORDER BY identifier;
        """, guild_id)
        return [cls(**row) for row in rows]

    
    @classmethod
    async def reset_letter_counts(cls, conn: asyncpg.Connection, guild_id: int) -> int:
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
        logger.info(f"🔄 Reset letter_count for {updated_count} characters in guild {guild_id}.")
        return updated_count
    
    @classmethod
    async def print_all(cls, conn: asyncpg.Connection):
        """
        Fetch and print all Character entries.
        """
        rows = await conn.fetch("""
            SELECT id, identifier, name, user_id, channel_id, letter_limit, letter_count, guild_id,
                   ore_production, lumber_production, coal_production,
                   rations_production, cloth_production, platinum_production, victory_points
            FROM Character
            ORDER BY id;
        """)

        if not rows:
            logger.info("📭 No entries found in Character table.")
            return

        logger.info("📜 Character entries:\n")
        for row in rows:
            logger.info(
                f"🧙 ID: {row['id']}\n"
                f"   • Identifier:   {row['identifier']}\n"
                f"   • Name:         {row['name']}\n"
                f"   • User ID:      {row['user_id']}\n"
                f"   • Channel ID:   {row['channel_id']}\n"
                f"   • Letter Limit: {row['letter_limit']}\n"
                f"   • Letter Count: {row['letter_count']}\n"
                f"   • Guild ID:     {row['guild_id']}\n"
                f"   • Production:   ore={row['ore_production']}, lumber={row['lumber_production']}, "
                f"coal={row['coal_production']}, rations={row['rations_production']}, "
                f"cloth={row['cloth_production']}, platinum={row['platinum_production']}\n"
                f"   • Victory Pts:  {row['victory_points']}\n"
            )

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, char_id: int) -> bool:
        """
        Delete a Character by ID.
        """
        result = await conn.execute("DELETE FROM Character WHERE id = $1;", char_id)
        deleted = result.startswith("DELETE 1")
        logger.info(f"🗑️ Deleted Character ID={char_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_by_identifier(cls, conn: asyncpg.Connection, identifier: str) -> bool:
        """
        Delete a Character by its identifier (guild-independent).
        Returns True if a row was deleted, False otherwise.
        """
        result = await conn.execute("DELETE FROM Character WHERE identifier = $1;", identifier)
        deleted = result.startswith("DELETE 1")
        logger.info(f"🗑️ Deleted Character with identifier='{identifier}'. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all entries from the Character table.
        """
        result = await conn.execute("DELETE FROM Character;")
        logger.warning(f"⚠️ All entries deleted from Character table. Result: {result}")

    @classmethod
    async def delete_all_by_guild(cls, conn: asyncpg.Connection, guild_id: int) -> int:
        """
        Delete all characters for a given guild_id.
        Returns the number of rows deleted.
        """
        result = await conn.execute("DELETE FROM Character WHERE guild_id = $1;", guild_id)
        deleted_count = int(result.split()[-1]) if result.startswith("DELETE") else 0
        logger.warning(f"⚠️ Deleted {deleted_count} characters for guild {guild_id}")
        return deleted_count

    def verify(self) -> tuple[bool, str]:
        """
        Verify that no numeric field that can be None is less than 0.
        Returns (bool, message):
          - (False, "<field> less than 0") if any value is negative.
          - (True, "") if all checks pass.
        """
        numeric_fields = [
            "letter_limit",
            "letter_count",
            "channel_id",
            "user_id",
            "guild_id"
        ]

        for field_name in numeric_fields:
            value = getattr(self, field_name)
            if value is not None and value < 0:
                return False, f"Invalid input, {field_name} must be >= 0"

        # Production and VP fields must be non-negative
        production_fields = [
            "ore_production",
            "lumber_production",
            "coal_production",
            "rations_production",
            "cloth_production",
            "platinum_production",
            "victory_points"
        ]

        for field_name in production_fields:
            value = getattr(self, field_name)
            if value < 0:
                return False, f"Invalid input, {field_name} must be >= 0"

        if len(self.name) == 0:
            return False, f"Invalid input, name must not be empty"

        return True, ""
