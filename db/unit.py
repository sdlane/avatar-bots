import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class Unit:
    id: Optional[int] = None
    unit_id: str = ""
    name: Optional[str] = None
    unit_type: str = ""
    owner_character_id: int = 0
    commander_character_id: Optional[int] = None
    commander_assigned_turn: Optional[int] = None
    faction_id: Optional[int] = None
    movement: int = 1
    organization: int = 0
    max_organization: int = 0
    attack: int = 0
    defense: int = 0
    siege_attack: int = 0
    siege_defense: int = 0
    size: int = 1
    capacity: int = 0
    current_territory_id: Optional[int] = None
    is_naval: bool = False
    upkeep_ore: int = 0
    upkeep_lumber: int = 0
    upkeep_coal: int = 0
    upkeep_rations: int = 0
    upkeep_cloth: int = 0
    keywords: Optional[List[str]] = None
    guild_id: Optional[int] = None

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Unit entry.
        The pair (unit_id, guild_id) must be unique.
        """
        query = """
        INSERT INTO Unit (
            unit_id, name, unit_type, owner_character_id, commander_character_id,
            commander_assigned_turn, faction_id, movement, organization, max_organization,
            attack, defense, siege_attack, siege_defense, size, capacity,
            current_territory_id, is_naval, upkeep_ore, upkeep_lumber, upkeep_coal,
            upkeep_rations, upkeep_cloth, keywords, guild_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25)
        ON CONFLICT (unit_id, guild_id) DO UPDATE
        SET name = EXCLUDED.name,
            unit_type = EXCLUDED.unit_type,
            owner_character_id = EXCLUDED.owner_character_id,
            commander_character_id = EXCLUDED.commander_character_id,
            commander_assigned_turn = EXCLUDED.commander_assigned_turn,
            faction_id = EXCLUDED.faction_id,
            movement = EXCLUDED.movement,
            organization = EXCLUDED.organization,
            max_organization = EXCLUDED.max_organization,
            attack = EXCLUDED.attack,
            defense = EXCLUDED.defense,
            siege_attack = EXCLUDED.siege_attack,
            siege_defense = EXCLUDED.siege_defense,
            size = EXCLUDED.size,
            capacity = EXCLUDED.capacity,
            current_territory_id = EXCLUDED.current_territory_id,
            is_naval = EXCLUDED.is_naval,
            upkeep_ore = EXCLUDED.upkeep_ore,
            upkeep_lumber = EXCLUDED.upkeep_lumber,
            upkeep_coal = EXCLUDED.upkeep_coal,
            upkeep_rations = EXCLUDED.upkeep_rations,
            upkeep_cloth = EXCLUDED.upkeep_cloth,
            keywords = EXCLUDED.keywords;
        """
        await conn.execute(
            query,
            self.unit_id, self.name, self.unit_type, self.owner_character_id,
            self.commander_character_id, self.commander_assigned_turn, self.faction_id,
            self.movement, self.organization, self.max_organization, self.attack,
            self.defense, self.siege_attack, self.siege_defense, self.size,
            self.capacity, self.current_territory_id, self.is_naval, self.upkeep_ore,
            self.upkeep_lumber, self.upkeep_coal, self.upkeep_rations, self.upkeep_cloth,
            self.keywords if self.keywords else [], self.guild_id
        )

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, unit_internal_id: int) -> Optional["Unit"]:
        """
        Fetch a Unit by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, unit_id, name, unit_type, owner_character_id, commander_character_id,
                   commander_assigned_turn, faction_id, movement, organization, max_organization,
                   attack, defense, siege_attack, siege_defense, size, capacity,
                   current_territory_id, is_naval, upkeep_ore, upkeep_lumber, upkeep_coal,
                   upkeep_rations, upkeep_cloth, keywords, guild_id
            FROM Unit
            WHERE id = $1;
        """, unit_internal_id)
        if not row:
            return None
        data = dict(row)
        data['keywords'] = list(data['keywords']) if data['keywords'] else []
        return cls(**data)

    @classmethod
    async def fetch_by_unit_id(cls, conn: asyncpg.Connection, unit_id: str, guild_id: int) -> Optional["Unit"]:
        """
        Fetch a Unit by its (unit_id, guild_id) pair.
        """
        row = await conn.fetchrow("""
            SELECT id, unit_id, name, unit_type, owner_character_id, commander_character_id,
                   commander_assigned_turn, faction_id, movement, organization, max_organization,
                   attack, defense, siege_attack, siege_defense, size, capacity,
                   current_territory_id, is_naval, upkeep_ore, upkeep_lumber, upkeep_coal,
                   upkeep_rations, upkeep_cloth, keywords, guild_id
            FROM Unit
            WHERE unit_id = $1 AND guild_id = $2;
        """, unit_id, guild_id)
        if not row:
            return None
        data = dict(row)
        data['keywords'] = list(data['keywords']) if data['keywords'] else []
        return cls(**data)

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["Unit"]:
        """
        Fetch all Units in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, unit_id, name, unit_type, owner_character_id, commander_character_id,
                   commander_assigned_turn, faction_id, movement, organization, max_organization,
                   attack, defense, siege_attack, siege_defense, size, capacity,
                   current_territory_id, is_naval, upkeep_ore, upkeep_lumber, upkeep_coal,
                   upkeep_rations, upkeep_cloth, keywords, guild_id
            FROM Unit
            WHERE guild_id = $1
            ORDER BY unit_id;
        """, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['keywords'] = list(data['keywords']) if data['keywords'] else []
            result.append(cls(**data))
        return result

    @classmethod
    async def fetch_by_faction(cls, conn: asyncpg.Connection, faction_id: int, guild_id: int) -> List["Unit"]:
        """
        Fetch all Units belonging to a faction.
        """
        rows = await conn.fetch("""
            SELECT id, unit_id, name, unit_type, owner_character_id, commander_character_id,
                   commander_assigned_turn, faction_id, movement, organization, max_organization,
                   attack, defense, siege_attack, siege_defense, size, capacity,
                   current_territory_id, is_naval, upkeep_ore, upkeep_lumber, upkeep_coal,
                   upkeep_rations, upkeep_cloth, keywords, guild_id
            FROM Unit
            WHERE faction_id = $1 AND guild_id = $2
            ORDER BY unit_id;
        """, faction_id, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['keywords'] = list(data['keywords']) if data['keywords'] else []
            result.append(cls(**data))
        return result

    @classmethod
    async def fetch_by_owner(cls, conn: asyncpg.Connection, character_id: int, guild_id: int) -> List["Unit"]:
        """
        Fetch all Units owned by a character.
        """
        rows = await conn.fetch("""
            SELECT id, unit_id, name, unit_type, owner_character_id, commander_character_id,
                   commander_assigned_turn, faction_id, movement, organization, max_organization,
                   attack, defense, siege_attack, siege_defense, size, capacity,
                   current_territory_id, is_naval, upkeep_ore, upkeep_lumber, upkeep_coal,
                   upkeep_rations, upkeep_cloth, keywords, guild_id
            FROM Unit
            WHERE owner_character_id = $1 AND guild_id = $2
            ORDER BY unit_id;
        """, character_id, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['keywords'] = list(data['keywords']) if data['keywords'] else []
            result.append(cls(**data))
        return result

    @classmethod
    async def fetch_by_commander(cls, conn: asyncpg.Connection, character_id: int, guild_id: int) -> List["Unit"]:
        """
        Fetch all Units commanded by a character.
        """
        rows = await conn.fetch("""
            SELECT id, unit_id, name, unit_type, owner_character_id, commander_character_id,
                   commander_assigned_turn, faction_id, movement, organization, max_organization,
                   attack, defense, siege_attack, siege_defense, size, capacity,
                   current_territory_id, is_naval, upkeep_ore, upkeep_lumber, upkeep_coal,
                   upkeep_rations, upkeep_cloth, keywords, guild_id
            FROM Unit
            WHERE commander_character_id = $1 AND guild_id = $2
            ORDER BY unit_id;
        """, character_id, guild_id)
        result = []
        for row in rows:
            data = dict(row)
            data['keywords'] = list(data['keywords']) if data['keywords'] else []
            result.append(cls(**data))
        return result

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, unit_id: str, guild_id: int) -> bool:
        """
        Delete a Unit by unit_id and guild_id.
        """
        result = await conn.execute(
            "DELETE FROM Unit WHERE unit_id = $1 AND guild_id = $2;",
            unit_id, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted Unit unit_id={unit_id} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all Unit entries for a guild.
        """
        result = await conn.execute("DELETE FROM Unit WHERE guild_id = $1;", guild_id)
        logger.warning(f"All Unit entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the Unit has valid data.
        """
        if not self.unit_id or len(self.unit_id) == 0:
            return False, "Unit ID must not be empty"

        if not self.unit_type or len(self.unit_type) == 0:
            return False, "Unit type must not be empty"

        if self.owner_character_id <= 0:
            return False, "Owner character ID must be valid"

        stat_fields = [
            ("movement", self.movement),
            ("organization", self.organization),
            ("max_organization", self.max_organization),
            ("attack", self.attack),
            ("defense", self.defense),
            ("siege_attack", self.siege_attack),
            ("siege_defense", self.siege_defense),
            ("size", self.size),
            ("capacity", self.capacity)
        ]

        for field_name, value in stat_fields:
            if value < 0:
                return False, f"{field_name} must be >= 0"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        return True, ""
