import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class Faction:
    id: Optional[int] = None
    faction_id: str = ""
    name: str = ""
    leader_character_id: Optional[int] = None
    created_turn: int = 0
    has_declared_war: bool = False  # True after first-ever war declaration
    guild_id: Optional[int] = None
    # Resource spending per turn (deducted during upkeep phase)
    ore_spending: int = 0
    lumber_spending: int = 0
    coal_spending: int = 0
    rations_spending: int = 0
    cloth_spending: int = 0
    platinum_spending: int = 0

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Faction entry.
        The pair (faction_id, guild_id) must be unique.
        """
        query = """
        INSERT INTO Faction (
            faction_id, name, leader_character_id, created_turn, has_declared_war, guild_id,
            ore_spending, lumber_spending, coal_spending, rations_spending, cloth_spending, platinum_spending
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (faction_id, guild_id) DO UPDATE
        SET name = EXCLUDED.name,
            leader_character_id = EXCLUDED.leader_character_id,
            created_turn = EXCLUDED.created_turn,
            has_declared_war = EXCLUDED.has_declared_war,
            ore_spending = EXCLUDED.ore_spending,
            lumber_spending = EXCLUDED.lumber_spending,
            coal_spending = EXCLUDED.coal_spending,
            rations_spending = EXCLUDED.rations_spending,
            cloth_spending = EXCLUDED.cloth_spending,
            platinum_spending = EXCLUDED.platinum_spending;
        """
        await conn.execute(
            query,
            self.faction_id,
            self.name,
            self.leader_character_id,
            self.created_turn,
            self.has_declared_war,
            self.guild_id,
            self.ore_spending,
            self.lumber_spending,
            self.coal_spending,
            self.rations_spending,
            self.cloth_spending,
            self.platinum_spending
        )

    @classmethod
    async def fetch_by_id(cls, conn: asyncpg.Connection, faction_internal_id: int) -> Optional["Faction"]:
        """
        Fetch a Faction by its internal sequential ID.
        """
        row = await conn.fetchrow("""
            SELECT id, faction_id, name, leader_character_id, created_turn, has_declared_war, guild_id,
                   ore_spending, lumber_spending, coal_spending, rations_spending, cloth_spending, platinum_spending
            FROM Faction
            WHERE id = $1;
        """, faction_internal_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_by_faction_id(cls, conn: asyncpg.Connection, faction_id: str, guild_id: int) -> Optional["Faction"]:
        """
        Fetch a Faction by its (faction_id, guild_id) pair.
        """
        row = await conn.fetchrow("""
            SELECT id, faction_id, name, leader_character_id, created_turn, has_declared_war, guild_id,
                   ore_spending, lumber_spending, coal_spending, rations_spending, cloth_spending, platinum_spending
            FROM Faction
            WHERE faction_id = $1 AND guild_id = $2;
        """, faction_id, guild_id)
        return cls(**row) if row else None

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection, guild_id: int) -> List["Faction"]:
        """
        Fetch all Factions in a guild.
        """
        rows = await conn.fetch("""
            SELECT id, faction_id, name, leader_character_id, created_turn, has_declared_war, guild_id,
                   ore_spending, lumber_spending, coal_spending, rations_spending, cloth_spending, platinum_spending
            FROM Faction
            WHERE guild_id = $1
            ORDER BY faction_id;
        """, guild_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def delete(cls, conn: asyncpg.Connection, faction_id: str, guild_id: int) -> bool:
        """
        Delete a Faction by faction_id and guild_id.
        """
        result = await conn.execute(
            "DELETE FROM Faction WHERE faction_id = $1 AND guild_id = $2;",
            faction_id, guild_id
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted Faction faction_id={faction_id} guild_id={guild_id}. Result: {result}")
        return deleted

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection, guild_id: int):
        """
        Delete all Faction entries for a guild.
        """
        result = await conn.execute("DELETE FROM Faction WHERE guild_id = $1;", guild_id)
        logger.warning(f"All Faction entries deleted for guild {guild_id}. Result: {result}")

    def verify(self) -> tuple[bool, str]:
        """
        Verify that the Faction has valid data.
        """
        if not self.faction_id or len(self.faction_id) == 0:
            return False, "Faction ID must not be empty"

        if not self.name or len(self.name) == 0:
            return False, "Faction name must not be empty"

        if self.guild_id is None or self.guild_id < 0:
            return False, "guild_id must be valid"

        # Validate spending values are non-negative
        spending_fields = [
            ("ore_spending", self.ore_spending),
            ("lumber_spending", self.lumber_spending),
            ("coal_spending", self.coal_spending),
            ("rations_spending", self.rations_spending),
            ("cloth_spending", self.cloth_spending),
            ("platinum_spending", self.platinum_spending)
        ]
        for field_name, value in spending_fields:
            if value < 0:
                return False, f"{field_name} must be >= 0"

        return True, ""
