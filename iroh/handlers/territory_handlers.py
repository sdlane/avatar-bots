"""
Territory management command handlers.
"""
import asyncpg
from typing import Optional, Tuple
from db import Territory, Faction, TerritoryAdjacency


async def create_territory(conn: asyncpg.Connection, territory_id: int, terrain_type: str, guild_id: int, name: Optional[str] = None) -> Tuple[bool, str]:
    """Create a new territory."""
    # Validate terrain type
    valid_terrains = ["plains", "mountain", "desert", "ocean", "lake"]
    if terrain_type.lower() not in valid_terrains:
        return False, f"Invalid terrain type. Must be one of: {', '.join(valid_terrains)}"

    # Check if territory already exists
    existing = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if existing:
        return False, f"Territory {territory_id} already exists."

    # Create territory
    territory = Territory(
        territory_id=territory_id,
        name=name,
        terrain_type=terrain_type.lower(),
        ore_production=0,
        lumber_production=0,
        coal_production=0,
        rations_production=0,
        cloth_production=0,
        controller_faction_id=None,
        original_nation=None,
        guild_id=guild_id
    )

    await territory.upsert(conn)

    if name:
        return True, f"Territory {territory_id} '{name}' created successfully."
    else:
        return True, f"Territory {territory_id} created successfully."


async def edit_territory(conn: asyncpg.Connection, territory_id: int, guild_id: int,
                        name: Optional[str] = None, original_nation: Optional[str] = None,
                        ore: int = 0, lumber: int = 0, coal: int = 0, rations: int = 0, cloth: int = 0) -> Tuple[bool, str, Optional[Territory]]:
    """
    Edit territory properties.

    Returns:
        (success, message, territory) - territory is returned for modal display
    """
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False, f"Territory {territory_id} not found.", None

    # Update fields
    territory.name = name if name else None
    territory.original_nation = original_nation if original_nation else None
    territory.ore_production = ore
    territory.lumber_production = lumber
    territory.coal_production = coal
    territory.rations_production = rations
    territory.cloth_production = cloth

    await territory.upsert(conn)

    return True, f"Territory {territory_id} updated successfully.", territory


async def delete_territory(conn: asyncpg.Connection, territory_id: int, guild_id: int) -> Tuple[bool, str]:
    """Delete a territory."""
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False, f"Territory {territory_id} not found."

    # Check if territory has units
    units = await conn.fetch(
        "SELECT * FROM Unit WHERE current_territory_id = $1 AND guild_id = $2;",
        territory_id,
        guild_id
    )
    if units:
        return False, f"Cannot delete territory {territory_id} - it contains {len(units)} units. Remove or move them first."

    # Delete territory (CASCADE will delete adjacencies)
    await Territory.delete(conn, territory_id, guild_id)

    return True, f"Territory {territory_id} has been deleted."


async def set_territory_controller(conn: asyncpg.Connection, territory_id: int, faction_id: str, guild_id: int) -> Tuple[bool, str]:
    """Change the faction controlling a territory."""
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False, f"Territory {territory_id} not found."

    # Handle removing controller
    if faction_id.lower() == 'none':
        territory.controller_faction_id = None
        await territory.upsert(conn)
        return True, f"Territory {territory_id} is now uncontrolled."

    # Validate faction
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Update controller
    territory.controller_faction_id = faction.id
    await territory.upsert(conn)

    return True, f"Territory {territory_id} is now controlled by {faction.name}."


async def add_adjacency(conn: asyncpg.Connection, territory_id_1: int, territory_id_2: int, guild_id: int) -> Tuple[bool, str]:
    """Mark two territories as adjacent."""
    if territory_id_1 == territory_id_2:
        return False, "A territory cannot be adjacent to itself."

    # Check if both territories exist
    territory1 = await Territory.fetch_by_territory_id(conn, territory_id_1, guild_id)
    territory2 = await Territory.fetch_by_territory_id(conn, territory_id_2, guild_id)

    if not territory1:
        return False, f"Territory {territory_id_1} not found."

    if not territory2:
        return False, f"Territory {territory_id_2} not found."

    # Create adjacency
    adjacency = TerritoryAdjacency(
        territory_a_id=min(territory_id_1, territory_id_2),
        territory_b_id=max(territory_id_1, territory_id_2),
        guild_id=guild_id
    )

    try:
        await adjacency.upsert(conn)
        return True, f"Territories {territory_id_1} and {territory_id_2} are now adjacent."
    except Exception as e:
        if "duplicate key" in str(e).lower():
            return False, f"Territories {territory_id_1} and {territory_id_2} are already adjacent."
        else:
            raise


async def remove_adjacency(conn: asyncpg.Connection, territory_id_1: int, territory_id_2: int, guild_id: int) -> Tuple[bool, str]:
    """Remove adjacency between two territories."""
    # Delete the adjacency
    result = await conn.execute(
        """
        DELETE FROM TerritoryAdjacency
        WHERE guild_id = $1
        AND ((territory_a_id = $2 AND territory_b_id = $3)
             OR (territory_a_id = $3 AND territory_b_id = $2));
        """,
        guild_id,
        min(territory_id_1, territory_id_2),
        max(territory_id_1, territory_id_2)
    )

    if result == "DELETE 0":
        return False, f"Territories {territory_id_1} and {territory_id_2} are not adjacent."
    else:
        return True, f"Removed adjacency between territories {territory_id_1} and {territory_id_2}."
