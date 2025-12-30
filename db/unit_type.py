import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class UnitType:
    id: Optional[int] = None
    type_id: str = ""
    name: str = ""
    nation: Optional[str] = None
    movement: int = 1
    organization: int = 0
    attack: int = 0
    defense: int = 0
    siege_attack: int = 0
    siege_defense: int = 0
    size: int = 1
    capacity: int = 0
    is_naval: bool = False
    keywords: Optional[List[str]] = None
    cost_ore: int = 0
    cost_lumber: int = 0
    cost_coal: int = 0
    cost_rations: int = 0
    cost_cloth: int = 0
    upkeep_ore: int = 0
    upkeep_lumber: int = 0
    upkeep_coal: int = 0
    upkeep_rations: int = 0
    upkeep_cloth: int = 0
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this UnitType entry.
        The tuple (type_id, nation, guild_id) must be unique.
        """
        query = """
        INSERT INTO UnitType (
            type_id, name, nation, movement, organization, attack, defense,
            siege_attack, siege_defense, size, capacity, is_naval, keywords,
            cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth,
            upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth,
            guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24)
        ON CONFLICT (type_id, nation, guild_id) DO UPDATE
        SET name = EXCLUDED.name,
            movement = EXCLUDED.movement,
            organization = EXCLUDED.organization,
            attack = EXCLUDED.attack,
            defense = EXCLUDED.defense,
            siege_attack = EXCLUDED.siege_attack,
            siege_defense = EXCLUDED.siege_defense,
            size = EXCLUDED.size,
            capacity = EXCLUDED.capacity,
            is_naval = EXCLUDED.is_naval,
            keywords = EXCLUDED.keywords,
            cost_ore = EXCLUDED.cost_ore,
            cost_lumber = EXCLUDED.cost_lumber,
            cost_coal = EXCLUDED.cost_coal,
            cost_rations = EXCLUDED.cost_rations,
            cost_cloth = EXCLUDED.cost_cloth,
            upkeep_ore = EXCLUDED.upkeep_ore,
            upkeep_lumber = EXCLUDED.upkeep_lumber,
            upkeep_coal = EXCLUDED.upkeep_coal,
            upkeep_rations = EXCLUDED.upkeep_rations,
            upkeep_cloth = EXCLUDED.upkeep_cloth;
        """
        await conn.execute(
            query,
            self.type_id, self.name, self.nation, self.movement, self.organization,
            self.attack, self.defense, self.siege_attack, self.siege_defense,
            self.size, self.capacity, self.is_naval, self.keywords if self.keywords else [],
            self.cost_ore, self.cost_lumber, self.cost_coal, self.cost_rations, self.cost_cloth,
            self.upkeep_ore, self.upkeep_lumber, self.upkeep_coal, self.upkeep_rations,
            self.upkeep_cloth, self.guild_id
        )

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, unit_type_internal_id: int) -> Optional["UnitType"]:
        """
        Fetch a UnitType by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, type_id, name, nation, movement, organization, attack, defense,
                   siege_attack, siege_defense, size, capacity, is_naval, keywords,
                   cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth,
                   guild_id
            FROM UnitType
            WHERE id = $1;
        """, unit_type_internal_id)
        if not row:
            return None
        data = dict(row)
        data['keywords'] = list(data['keywords']) if data['keywords'] else []
        return cls(**data)

    @classmethod
    async def fetch_by_type_id(cls, conn: asyncpg.Connection, type_id: str, nation: Optional[str], guild_id: int) -> Optional["UnitType"]:
        """
        Fetch a UnitType by its (type_id, nation, guild_id) tuple.
        """
        row = await conn.fetchrow("""
            SELECT id, type_id, name, nation, movement, organization, attack, defense,
                   siege_attack, siege_defense, size, capacity, is_naval, keywords,
                   cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth,
                   guild_id
            FROM UnitType
            WHERE type_id = $1 AND (nation = $2 OR (nation IS NULL AND $2 IS NULL)) AND guild_id = $3;
        """, type_id, nation, guild_id)
        if not row:
            return None
        data = dict(row)
        data['keywords'] = list(data['keywords']) if data['keywords'] else []
        return cls(**data)

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["UnitType"]:
        """
        Fetch all UnitTypes in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, type_id, name, nation, movement, organization, attack, defense,
                   siege_attack, siege_defense, size, capacity, is_naval, keywords,
                   cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth,
                   guild_id
            FROM UnitType
            WHERE guild_id = $1
            ORDER BY type_id, nation;
        """, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['keywords'] = list(data['keywords']) if data['keywords'] else []
            result.append(cls(**data))
        return result

    @classmethod
    async def fetch_by_nation(cls, conn: asyncpg.Connection, nation: str, guild_id: int) -> List["UnitType"]:
        """
        Fetch all UnitTypes for a specific nation (including nation-agnostic types where nation IS NULL).
        """
        rows = await conn.fetch("""
            SELECT id, type_id, name, nation, movement, organization, attack, defense,
                   siege_attack, siege_defense, size, capacity, is_naval, keywords,
                   cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth,
                   upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth,
                   guild_id
            FROM UnitType
            WHERE (nation = $1 OR nation IS NULL) AND guild_id = $2
            ORDER BY type_id;
        """, nation, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['keywords'] = list(data['keywords']) if data['keywords'] else []
            result.append(cls(**data))
        return result

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, type_id: str, nation: Optional[str], guild_id: int) -> bool:
        """
        Delete a UnitType by (type_id, nation, guild_id).
        """
        result = await conn.execute(
            "DELETE FROM UnitType WHERE type_id = $1 AND (nation = $2 OR (nation IS NULL AND $2 IS NULL)) AND guild_id = $3;",
            type_id, nation, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted UnitType type_id={type_id} nation={nation} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all UnitType entries for a guild.
        """
        result = await conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", guild_id)
        logger.warning(f"All UnitType entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the UnitType has valid data.
        """
        if not self.type_id or len(self.type_id) == 0:
            return False, "Type ID must not be empty"

        if not self.name or len(self.name) == 0:
            return False, "Name must not be empty"

        stat_fields = [
            ("movement", self.movement),
            ("organization", self.organization),
            ("attack", self.attack),
            ("defense", self.defense),
            ("siege_attack", self.siege_attack),
            ("siege_defense", self.siege_defense),
            ("size", self.size),
            ("capacity", self.capacity),
            ("cost_ore", self.cost_ore),
            ("cost_lumber", self.cost_lumber),
            ("cost_coal", self.cost_coal),
            ("cost_rations", self.cost_rations),
            ("cost_cloth", self.cost_cloth),
            ("upkeep_ore", self.upkeep_ore),
            ("upkeep_lumber", self.upkeep_lumber),
            ("upkeep_coal", self.upkeep_coal),
            ("upkeep_rations", self.upkeep_rations),
            ("upkeep_cloth", self.upkeep_cloth)
        ]

        for field_name, value in stat_fields:
            if value < 0:
                return False, f"{field_name} must be >= 0"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
