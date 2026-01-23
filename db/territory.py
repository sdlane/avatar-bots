import asyncpg
from dataclasses import dataclass
from typing import Optional, List, Union, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from db.character import Character
    from db.faction import Faction

logger = logging.getLogger(__name__)


@dataclass
class Territory:
    id: Optional[int] = None
    territory_id: str = ""
    name: Optional[str] = None
    terrain_type: str = ""
    ore_production: int = 0
    lumber_production: int = 0
    coal_production: int = 0
    rations_production: int = 0
    cloth_production: int = 0
    platinum_production: int = 0
    victory_points: int = 0
    controller_character_id: Optional[int] = None
    controller_faction_id: Optional[int] = None
    original_nation: Optional[str] = None
    keywords: Optional[List[str]] = None
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Territory entry.
        The pair (territory_id, guild_id) must be unique.
        """
        query = """
        INSERT INTO Territory (
            territory_id, name, terrain_type, ore_production, lumber_production,
            coal_production, rations_production, cloth_production, platinum_production,
            victory_points, controller_character_id, controller_faction_id, original_nation, keywords, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        ON CONFLICT (territory_id, guild_id) DO UPDATE
        SET name = EXCLUDED.name,
            terrain_type = EXCLUDED.terrain_type,
            ore_production = EXCLUDED.ore_production,
            lumber_production = EXCLUDED.lumber_production,
            coal_production = EXCLUDED.coal_production,
            rations_production = EXCLUDED.rations_production,
            cloth_production = EXCLUDED.cloth_production,
            platinum_production = EXCLUDED.platinum_production,
            victory_points = EXCLUDED.victory_points,
            controller_character_id = EXCLUDED.controller_character_id,
            controller_faction_id = EXCLUDED.controller_faction_id,
            original_nation = EXCLUDED.original_nation,
            keywords = EXCLUDED.keywords;
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
            self.platinum_production,
            self.victory_points,
            self.controller_character_id,
            self.controller_faction_id,
            self.original_nation,
            self.keywords,
            self.guild_id
        )

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, territory_internal_id: int) -> Optional["Territory"]:
        """
        Fetch a Territory by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, territory_id, name, terrain_type, ore_production, lumber_production,
                   coal_production, rations_production, cloth_production, platinum_production,
                   victory_points, controller_character_id, controller_faction_id, original_nation, keywords, guild_id
            FROM Territory
            WHERE id = $1;
        """, territory_internal_id)
        if not row:
            return None
        data = dict(row)
        data['keywords'] = list(data['keywords']) if data['keywords'] else []
        return cls(**data)

    @classmethod
    async def fetch_by_territory_id(cls, conn: asyncpg.Connection, territory_id: str, guild_id: int) -> Optional["Territory"]:
        """
        Fetch a Territory by its (territory_id, guild_id) pair.
        """
        row = await conn.fetchrow("""
            SELECT id, territory_id, name, terrain_type, ore_production, lumber_production,
                   coal_production, rations_production, cloth_production, platinum_production,
                   victory_points, controller_character_id, controller_faction_id, original_nation, keywords, guild_id
            FROM Territory
            WHERE territory_id = $1 AND guild_id = $2;
        """, territory_id, guild_id)
        if not row:
            return None
        data = dict(row)
        data['keywords'] = list(data['keywords']) if data['keywords'] else []
        return cls(**data)

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["Territory"]:
        """
        Fetch all Territories in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, territory_id, name, terrain_type, ore_production, lumber_production,
                   coal_production, rations_production, cloth_production, platinum_production,
                   victory_points, controller_character_id, controller_faction_id, original_nation, keywords, guild_id
            FROM Territory
            WHERE guild_id = $1
            ORDER BY territory_id;
        """, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['keywords'] = list(data['keywords']) if data['keywords'] else []
            result.append(cls(**data))
        return result

    @classmethod
    async def fetch_by_controller(cls, conn: asyncpg.Connection, character_id: int, guild_id: int) -> List["Territory"]:
        """
        Fetch all Territories controlled by a specific character.
        """
        rows = await conn.fetch("""
            SELECT id, territory_id, name, terrain_type, ore_production, lumber_production,
                   coal_production, rations_production, cloth_production, platinum_production,
                   victory_points, controller_character_id, controller_faction_id, original_nation, keywords, guild_id
            FROM Territory
            WHERE controller_character_id = $1 AND guild_id = $2
            ORDER BY territory_id;
        """, character_id, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['keywords'] = list(data['keywords']) if data['keywords'] else []
            result.append(cls(**data))
        return result

    @classmethod
    async def fetch_by_faction_controller(cls, conn: asyncpg.Connection, faction_id: int, guild_id: int) -> List["Territory"]:
        """
        Fetch all Territories controlled by a specific faction.
        """
        rows = await conn.fetch("""
            SELECT id, territory_id, name, terrain_type, ore_production, lumber_production,
                   coal_production, rations_production, cloth_production, platinum_production,
                   victory_points, controller_character_id, controller_faction_id, original_nation, keywords, guild_id
            FROM Territory
            WHERE controller_faction_id = $1 AND guild_id = $2
            ORDER BY territory_id;
        """, faction_id, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['keywords'] = list(data['keywords']) if data['keywords'] else []
            result.append(cls(**data))
        return result

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, territory_id: str, guild_id: int) -> bool:
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
        if not self.territory_id or len(self.territory_id.strip()) == 0:
            return False, "Territory ID must not be empty"

        if not self.terrain_type or len(self.terrain_type) == 0:
            return False, "Terrain type must not be empty"

        # Check production values are non-negative
        production_fields = [
            ("ore_production", self.ore_production),
            ("lumber_production", self.lumber_production),
            ("coal_production", self.coal_production),
            ("rations_production", self.rations_production),
            ("cloth_production", self.cloth_production),
            ("platinum_production", self.platinum_production),
            ("victory_points", self.victory_points)
        ]

        for field_name, value in production_fields:
            if value < 0:
                return False, f"{field_name} must be >= 0"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        # Ensure mutual exclusivity of controller types
        if self.controller_character_id is not None and self.controller_faction_id is not None:
            return False, "Territory cannot be controlled by both a character and a faction"

        return True, ""

    def get_owner_type(self) -> Optional[str]:
        """
        Returns the type of owner for this territory.
        Returns 'character', 'faction', or None if uncontrolled.
        """
        if self.controller_character_id is not None:
            return 'character'
        elif self.controller_faction_id is not None:
            return 'faction'
        return None

    def get_owner_id(self) -> Optional[int]:
        """
        Returns the internal ID of the owner (character or faction).
        Returns None if uncontrolled.
        """
        if self.controller_character_id is not None:
            return self.controller_character_id
        elif self.controller_faction_id is not None:
            return self.controller_faction_id
        return None

    async def get_owner(self, conn: asyncpg.Connection) -> Optional[Union["Character", "Faction"]]:
        """
        Fetch and return the actual owner object (Character or Faction).
        Returns None if uncontrolled.
        """
        # Import here to avoid circular imports
        from db.character import Character
        from db.faction import Faction

        if self.controller_character_id is not None:
            return await Character.fetch_by_id(conn, self.controller_character_id)
        elif self.controller_faction_id is not None:
            return await Faction.fetch_by_id(conn, self.controller_faction_id)
        return None
