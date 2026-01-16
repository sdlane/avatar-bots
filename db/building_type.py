import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class BuildingType:
    id: Optional[int] = None
    type_id: str = ""
    name: str = ""
    description: Optional[str] = None
    cost_ore: int = 0
    cost_lumber: int = 0
    cost_coal: int = 0
    cost_rations: int = 0
    cost_cloth: int = 0
    cost_platinum: int = 0
    upkeep_ore: int = 0
    upkeep_lumber: int = 0
    upkeep_coal: int = 0
    upkeep_rations: int = 0
    upkeep_cloth: int = 0
    upkeep_platinum: int = 0
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this BuildingType entry.
        The tuple (type_id, guild_id) must be unique.
        """
        query = """
        INSERT INTO BuildingType (
            type_id, name, description,
            cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth, cost_platinum,
            upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum,
            guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        ON CONFLICT (type_id, guild_id) DO UPDATE
        SET name = EXCLUDED.name,
            description = EXCLUDED.description,
            cost_ore = EXCLUDED.cost_ore,
            cost_lumber = EXCLUDED.cost_lumber,
            cost_coal = EXCLUDED.cost_coal,
            cost_rations = EXCLUDED.cost_rations,
            cost_cloth = EXCLUDED.cost_cloth,
            cost_platinum = EXCLUDED.cost_platinum,
            upkeep_ore = EXCLUDED.upkeep_ore,
            upkeep_lumber = EXCLUDED.upkeep_lumber,
            upkeep_coal = EXCLUDED.upkeep_coal,
            upkeep_rations = EXCLUDED.upkeep_rations,
            upkeep_cloth = EXCLUDED.upkeep_cloth,
            upkeep_platinum = EXCLUDED.upkeep_platinum;
        """
        await conn.execute(
            query,
            self.type_id, self.name, self.description,
            self.cost_ore, self.cost_lumber, self.cost_coal, self.cost_rations, self.cost_cloth, self.cost_platinum,
            self.upkeep_ore, self.upkeep_lumber, self.upkeep_coal, self.upkeep_rations,
            self.upkeep_cloth, self.upkeep_platinum, self.guild_id
        )

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, building_type_internal_id: int) -> Optional["BuildingType"]:
        """
        Fetch a BuildingType by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, type_id, name, description,
                   cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth, cost_platinum,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum,
                   guild_id
            FROM BuildingType
            WHERE id = $1;
        """, building_type_internal_id)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_by_type_id(cls, conn: asyncpg.Connection, type_id: str, guild_id: int) -> Optional["BuildingType"]:
        """
        Fetch a BuildingType by its (type_id, guild_id) tuple.
        """
        row = await conn.fetchrow("""
            SELECT id, type_id, name, description,
                   cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth, cost_platinum,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum,
                   guild_id
            FROM BuildingType
            WHERE type_id = $1 AND guild_id = $2;
        """, type_id, guild_id)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["BuildingType"]:
        """
        Fetch all BuildingTypes in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, type_id, name, description,
                   cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth, cost_platinum,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum,
                   guild_id
            FROM BuildingType
            WHERE guild_id = $1
            ORDER BY type_id;
        """, guild_id)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, type_id: str, guild_id: int) -> bool:
        """
        Delete a BuildingType by (type_id, guild_id).
        """
        result = await conn.execute(
            "DELETE FROM BuildingType WHERE type_id = $1 AND guild_id = $2;",
            type_id, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted BuildingType type_id={type_id} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all BuildingType entries for a guild.
        """
        result = await conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", guild_id)
        logger.warning(f"All BuildingType entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the BuildingType has valid data.
        """
        if not self.type_id or len(self.type_id) == 0:
            return False, "Type ID must not be empty"

        if not self.name or len(self.name) == 0:
            return False, "Name must not be empty"

        cost_fields = [
            ("cost_ore", self.cost_ore),
            ("cost_lumber", self.cost_lumber),
            ("cost_coal", self.cost_coal),
            ("cost_rations", self.cost_rations),
            ("cost_cloth", self.cost_cloth),
            ("cost_platinum", self.cost_platinum),
            ("upkeep_ore", self.upkeep_ore),
            ("upkeep_lumber", self.upkeep_lumber),
            ("upkeep_coal", self.upkeep_coal),
            ("upkeep_rations", self.upkeep_rations),
            ("upkeep_cloth", self.upkeep_cloth),
            ("upkeep_platinum", self.upkeep_platinum)
        ]

        for field_name, value in cost_fields:
            if value < 0:
                return False, f"{field_name} must be >= 0"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
