import asyncpg
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class Ingredient:
    """
    Represents an herbal ingredient used in the herbalism system.
    Data is shared across all guilds (no guild_id).
    """
    id: Optional[int] = None
    item_number: str = ""
    name: str = ""
    macro: Optional[str] = None
    rarity: Optional[str] = None
    primary_chakra: Optional[str] = None
    primary_chakra_strength: Optional[int] = None
    secondary_chakra: Optional[str] = None
    secondary_chakra_strength: Optional[int] = None
    properties: Optional[str] = None  # comma-separated
    flavor_text: Optional[str] = None
    rules_text: Optional[str] = None
    skip_export: bool = False

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Ingredient entry.
        The item_number must be unique.
        """
        query = """
        INSERT INTO Ingredient (
            item_number, name, macro, rarity, primary_chakra, primary_chakra_strength,
            secondary_chakra, secondary_chakra_strength, properties, flavor_text,
            rules_text, skip_export
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (item_number) DO UPDATE
        SET name = EXCLUDED.name,
            macro = EXCLUDED.macro,
            rarity = EXCLUDED.rarity,
            primary_chakra = EXCLUDED.primary_chakra,
            primary_chakra_strength = EXCLUDED.primary_chakra_strength,
            secondary_chakra = EXCLUDED.secondary_chakra,
            secondary_chakra_strength = EXCLUDED.secondary_chakra_strength,
            properties = EXCLUDED.properties,
            flavor_text = EXCLUDED.flavor_text,
            rules_text = EXCLUDED.rules_text,
            skip_export = EXCLUDED.skip_export;
        """
        await conn.execute(
            query,
            self.item_number, self.name, self.macro, self.rarity,
            self.primary_chakra, self.primary_chakra_strength,
            self.secondary_chakra, self.secondary_chakra_strength,
            self.properties, self.flavor_text, self.rules_text, self.skip_export
        )

    @classmethod
    async def fetch_by_item_number(cls, conn: asyncpg.Connection, item_number: str) -> Optional["Ingredient"]:
        """
        Fetch an Ingredient by its item_number.
        """
        row = await conn.fetchrow("""
            SELECT id, item_number, name, macro, rarity, primary_chakra,
                   primary_chakra_strength, secondary_chakra, secondary_chakra_strength,
                   properties, flavor_text, rules_text, skip_export
            FROM Ingredient
            WHERE item_number = $1;
        """, item_number)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection) -> List["Ingredient"]:
        """
        Fetch all Ingredients.
        """
        rows = await conn.fetch("""
            SELECT id, item_number, name, macro, rarity, primary_chakra,
                   primary_chakra_strength, secondary_chakra, secondary_chakra_strength,
                   properties, flavor_text, rules_text, skip_export
            FROM Ingredient
            ORDER BY item_number;
        """)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all Ingredient entries.
        """
        result = await conn.execute("DELETE FROM Ingredient;")
        logger.warning(f"All Ingredient entries deleted. Result: {result}")

    @classmethod
    async def delete_by_item_number(cls, conn: asyncpg.Connection, item_number: str) -> bool:
        """
        Delete an Ingredient by item_number.
        """
        result = await conn.execute(
            "DELETE FROM Ingredient WHERE item_number = $1;",
            item_number
        )
        deleted = result.startswith("DELETE 1")
        logger.info(f"Deleted Ingredient item_number={item_number}. Result: {result}")
        return deleted

    def has_property(self, property_name: str) -> bool:
        """
        Check if this ingredient has a specific property.
        Properties are stored as a comma-separated string.
        """
        if not self.properties:
            return False
        props = [p.strip().lower() for p in self.properties.split(",")]
        return property_name.lower() in props

    def get_properties_list(self) -> List[str]:
        """
        Return the properties as a list of strings.
        """
        if not self.properties:
            return []
        return [p.strip() for p in self.properties.split(",") if p.strip()]
