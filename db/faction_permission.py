import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

# Valid permission types (for validation, not an enum)
VALID_PERMISSION_TYPES = ["COMMAND", "FINANCIAL", "MEMBERSHIP", "CONSTRUCTION"]


@dataclass
class FactionPermission:
    id: Optional[int] = None
    faction_id: int = 0  # FK to Faction.id (internal)
    character_id: int = 0  # FK to Character.id
    permission_type: str = ""  # One of VALID_PERMISSION_TYPES
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert this FactionPermission entry.
        Uses ON CONFLICT DO NOTHING to avoid duplicates.
        """
        query = """
        INSERT INTO FactionPermission (
            faction_id, character_id, permission_type, guild_id
        )
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (faction_id, character_id, permission_type, guild_id) DO NOTHING;
        """
        await conn.execute(
            query,
            self.faction_id,
            self.character_id,
            self.permission_type,
            self.guild_id
        )

    async def delete(self, conn: asyncpg.Connection) -> bool:
        """
        Delete this specific permission.
        """
        result = await conn.execute(
            """DELETE FROM FactionPermission
               WHERE faction_id = $1 AND character_id = $2
               AND permission_type = $3 AND guild_id = $4;""",
            self.faction_id,
            self.character_id,
            self.permission_type,
            self.guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted FactionPermission faction_id={self.faction_id} "
                   f"character_id={self.character_id} type={self.permission_type}. Result: {result}")
        return deleted

    @classmethod
    async def has_permission(
        cls,
        conn: asyncpg.Connection,
        faction_id: int,
        character_id: int,
        permission_type: str,
        guild_id: int
    ) -> bool:
        """
        Check if a character has a specific permission for a faction.
        """
        result = await conn.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM FactionPermission
                WHERE faction_id = $1 AND character_id = $2
                AND permission_type = $3 AND guild_id = $4
            );
        """, faction_id, character_id, permission_type, guild_id)
        return result

    @classmethod
    async def fetch_characters_with_permission(
        cls,
        conn: asyncpg.Connection,
        faction_id: int,
        permission_type: str,
        guild_id: int
    ) -> List[int]:
        """
        Get all character IDs with a specific permission for a faction.
        """
        rows = await conn.fetch("""
            SELECT character_id FROM FactionPermission
            WHERE faction_id = $1 AND permission_type = $2 AND guild_id = $3;
        """, faction_id, permission_type, guild_id)
        return [row['character_id'] for row in rows]

    @classmethod
    async def fetch_by_faction(
        cls,
        conn: asyncpg.Connection,
        faction_id: int,
        guild_id: int
    ) -> List["FactionPermission"]:
        """
        Fetch all permissions for a faction.
        """
        rows = await conn.fetch("""
            SELECT id, faction_id, character_id, permission_type, guild_id
            FROM FactionPermission
            WHERE faction_id = $1 AND guild_id = $2
            ORDER BY character_id, permission_type;
        """, faction_id, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def fetch_by_character(
        cls,
        conn: asyncpg.Connection,
        character_id: int,
        guild_id: int
    ) -> List["FactionPermission"]:
        """
        Fetch all permissions for a character across all factions.
        """
        rows = await conn.fetch("""
            SELECT id, faction_id, character_id, permission_type, guild_id
            FROM FactionPermission
            WHERE character_id = $1 AND guild_id = $2
            ORDER BY faction_id, permission_type;
        """, character_id, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def delete_all_for_character_in_faction(
        cls,
        conn: asyncpg.Connection,
        character_id: int,
        faction_id: int,
        guild_id: int
    ):
        """
        Delete all permissions for a character in a specific faction.
        Used when a member leaves or is kicked from a faction.
        """
        result = await conn.execute(
            """DELETE FROM FactionPermission
               WHERE character_id = $1 AND faction_id = $2 AND guild_id = $3;""",
            character_id, faction_id, guild_id
        )
        logger.info(f"Deleted all permissions for character_id={character_id} "
                   f"in faction_id={faction_id}. Result: {result}")

    @classmethod
    async def delete_all_for_faction(
        cls,
        conn: asyncpg.Connection,
        faction_id: int,
        guild_id: int
    ):
        """
        Delete all permissions for a faction.
        Used when resetting faction permissions (e.g., leader change).
        """
        result = await conn.execute(
            "DELETE FROM FactionPermission WHERE faction_id = $1 AND guild_id = $2;",
            faction_id, guild_id
        )
        logger.info(f"Deleted all permissions for faction_id={faction_id}. Result: {result}")

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all FactionPermission entries for a guild.
        """
        result = await conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", guild_id)
        logger.warning(f"All FactionPermission entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the FactionPermission has valid data.
        """
        if self.faction_id <= 0:
            return False, "Faction ID must be valid"

        if self.character_id <= 0:
            return False, "Character ID must be valid"

        if self.permission_type not in VALID_PERMISSION_TYPES:
            return False, f"Permission type must be one of: {', '.join(VALID_PERMISSION_TYPES)}"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
