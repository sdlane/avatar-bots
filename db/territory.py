import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class Territory:
    id: Optional[int] = None
    territory_id: int = 0
    name: Optional[str] = None
    terrain_type: str = ""
    ore_production: int = 0
    lumber_production: int = 0
    coal_production: int = 0
    rations_production: int = 0
    cloth_production: int = 0
    victory_points: int = 0
    controller_character_id: Optional[int] = None
    original_nation: Optional[str] = None
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Territory entry.
        The pair (territory_id, guild_id) must be unique.
        """
        query = """
        INSERT INTO Territory (
            territory_id, name, terrain_type, ore_production, lumber_production,
            coal_production, rations_production, cloth_production, victory_points,
            controller_character_id, original_nation, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (territory_id, guild_id) DO UPDATE
        SET name = EXCLUDED.name,
            terrain_type = EXCLUDED.terrain_type,
            ore_production = EXCLUDED.ore_production,
            lumber_production = EXCLUDED.lumber_production,
            coal_production = EXCLUDED.coal_production,
            rations_production = EXCLUDED.rations_production,
            cloth_production = EXCLUDED.cloth_production,
            victory_points = EXCLUDED.victory_points,
            controller_character_id = EXCLUDED.controller_character_id,
            original_nation = EXCLUDED.original_nation;
        """
        await conn.execute(
            query,
            self.territory_id,
            self.name,
            self.terrain_type,
            self.ore_production,
            self.lumber_production,
            self.coal_production,
            self.rations_production,
            self.cloth_production,
            self.victory_points,
            self.controller_character_id,
            self.original_nation,
            self.guild_id
        )

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, territory_internal_id: int) -> Optional["Territory"]:
        """
        Fetch a Territory by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, territory_id, name, terrain_type, ore_production, lumber_production,
                   coal_production, rations_production, cloth_production, victory_points,
                   controller_character_id, original_nation, guild_id
            FROM Territory
            WHERE id = $1;
        """, territory_internal_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_by_territory_id(cls, conn: asyncpg.Connection, territory_id: int, guild_id: int) -> Optional["Territory"]:
        """
        Fetch a Territory by its (territory_id, guild_id) pair.
        """
        row = await conn.fetchrow("""
            SELECT id, territory_id, name, terrain_type, ore_production, lumber_production,
                   coal_production, rations_production, cloth_production, victory_points,
                   controller_character_id, original_nation, guild_id
            FROM Territory
            WHERE territory_id = $1 AND guild_id = $2;
        """, territory_id, guild_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["Territory"]:
        """
        Fetch all Territories in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, territory_id, name, terrain_type, ore_production, lumber_production,
                   coal_production, rations_production, cloth_production, victory_points,
                   controller_character_id, original_nation, guild_id
            FROM Territory
            WHERE guild_id = $1
            ORDER BY territory_id;
        """, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def fetch_by_controller(cls, conn: asyncpg.Connection, character_id: int, guild_id: int) -> List["Territory"]:
        """
        Fetch all Territories controlled by a specific character.
        """
        rows = await conn.fetch("""
            SELECT id, territory_id, name, terrain_type, ore_production, lumber_production,
                   coal_production, rations_production, cloth_production, victory_points,
                   controller_character_id, original_nation, guild_id
            FROM Territory
            WHERE controller_character_id = $1 AND guild_id = $2
            ORDER BY territory_id;
        """, character_id, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, territory_id: int, guild_id: int) -> bool:
        """
        Delete a Territory by territory_id and guild_id.
        """
        result = await conn.execute(
            "DELETE FROM Territory WHERE territory_id = $1 AND guild_id = $2;",
            territory_id, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted Territory territory_id={territory_id} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all Territory entries for a guild.
        """
        result = await conn.execute("DELETE FROM Territory WHERE guild_id = $1;", guild_id)
        logger.warning(f"All Territory entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the Territory has valid data.
        Returns (bool, message):
          - (False, "<field> invalid") if any value is invalid.
          - (True, "") if all checks pass.
        """
        if self.territory_id < 0:
            return False, "Territory ID must be >= 0"

        if not self.terrain_type or len(self.terrain_type) == 0:
            return False, "Terrain type must not be empty"

        # Check production values are non-negative
        production_fields = [
            ("ore_production", self.ore_production),
            ("lumber_production", self.lumber_production),
            ("coal_production", self.coal_production),
            ("rations_production", self.rations_production),
            ("cloth_production", self.cloth_production),
            ("victory_points", self.victory_points)
        ]

        for field_name, value in production_fields:
            if value < 0:
                return False, f"{field_name} must be >= 0"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
