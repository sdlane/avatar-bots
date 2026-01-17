import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class Building:
    id: Optional[int] = None
    building_id: str = ""
    name: Optional[str] = None
    building_type: str = ""
    territory_id: Optional[str] = None
    durability: int = 10
    status: str = "ACTIVE"
    upkeep_ore: int = 0
    upkeep_lumber: int = 0
    upkeep_coal: int = 0
    upkeep_rations: int = 0
    upkeep_cloth: int = 0
    upkeep_platinum: int = 0
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Building entry.
        The tuple (building_id, guild_id) must be unique.
        """
        query = """
        INSERT INTO Building (
            building_id, name, building_type, territory_id, durability, status,
            upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum,
            guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (building_id, guild_id) DO UPDATE
        SET name = EXCLUDED.name,
            building_type = EXCLUDED.building_type,
            territory_id = EXCLUDED.territory_id,
            durability = EXCLUDED.durability,
            status = EXCLUDED.status,
            upkeep_ore = EXCLUDED.upkeep_ore,
            upkeep_lumber = EXCLUDED.upkeep_lumber,
            upkeep_coal = EXCLUDED.upkeep_coal,
            upkeep_rations = EXCLUDED.upkeep_rations,
            upkeep_cloth = EXCLUDED.upkeep_cloth,
            upkeep_platinum = EXCLUDED.upkeep_platinum;
        """
        await conn.execute(
            query,
            self.building_id, self.name, self.building_type, self.territory_id,
            self.durability, self.status,
            self.upkeep_ore, self.upkeep_lumber, self.upkeep_coal,
            self.upkeep_rations, self.upkeep_cloth, self.upkeep_platinum,
            self.guild_id
        )

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, building_internal_id: int) -> Optional["Building"]:
        """
        Fetch a Building by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, building_id, name, building_type, territory_id, durability, status,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum,
                   guild_id
            FROM Building
            WHERE id = $1;
        """, building_internal_id)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_by_building_id(cls, conn: asyncpg.Connection, building_id: str, guild_id: int) -> Optional["Building"]:
        """
        Fetch a Building by its (building_id, guild_id) tuple.
        """
        row = await conn.fetchrow("""
            SELECT id, building_id, name, building_type, territory_id, durability, status,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum,
                   guild_id
            FROM Building
            WHERE building_id = $1 AND guild_id = $2;
        """, building_id, guild_id)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["Building"]:
        """
        Fetch all Buildings in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, building_id, name, building_type, territory_id, durability, status,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum,
                   guild_id
            FROM Building
            WHERE guild_id = $1
            ORDER BY building_id;
        """, guild_id)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def fetch_by_territory(cls, conn: asyncpg.Connection, territory_id: str, guild_id: int) -> List["Building"]:
        """
        Fetch all Buildings in a specific territory.
        """
        rows = await conn.fetch("""
            SELECT id, building_id, name, building_type, territory_id, durability, status,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum,
                   guild_id
            FROM Building
            WHERE territory_id = $1 AND guild_id = $2
            ORDER BY building_id;
        """, territory_id, guild_id)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, building_id: str, guild_id: int) -> bool:
        """
        Delete a Building by (building_id, guild_id).
        """
        result = await conn.execute(
            "DELETE FROM Building WHERE building_id = $1 AND guild_id = $2;",
            building_id, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted Building building_id={building_id} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all Building entries for a guild.
        """
        result = await conn.execute("DELETE FROM Building WHERE guild_id = $1;", guild_id)
        logger.warning(f"All Building entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the Building has valid data.
        """
        if not self.building_id or len(self.building_id) == 0:
            return False, "Building ID must not be empty"

        if not self.building_type or len(self.building_type) == 0:
            return False, "Building type must not be empty"

        if self.durability < 0:
            return False, "Durability must be >= 0"

        valid_statuses = ["ACTIVE", "DESTROYED"]
        if self.status not in valid_statuses:
            return False, f"Status must be one of: {', '.join(valid_statuses)}"

        upkeep_fields = [
            ("upkeep_ore", self.upkeep_ore),
            ("upkeep_lumber", self.upkeep_lumber),
            ("upkeep_coal", self.upkeep_coal),
            ("upkeep_rations", self.upkeep_rations),
            ("upkeep_cloth", self.upkeep_cloth),
            ("upkeep_platinum", self.upkeep_platinum)
        ]

        for field_name, value in upkeep_fields:
            if value < 0:
                return False, f"{field_name} must be >= 0"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
