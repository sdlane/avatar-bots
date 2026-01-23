"""
Territory management command handlers.
"""
import asyncpg
from typing import Optional, Tuple
from db import Territory, Character, TerritoryAdjacency, Faction


async def create_territory(conn: asyncpg.Connection, territory_id: str, terrain_type: str, guild_id: int, name: Optional[str] = None) -> Tuple[bool, str]:
    """Create a new territory."""
    # Validate terrain type
    valid_terrains = ["plains", "mountain", "desert", "ocean", "lake", "city"]
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
        controller_character_id=None,
        original_nation=None,
        guild_id=guild_id
    )

    await territory.upsert(conn)

    if name:
        return True, f"Territory {territory_id} '{name}' created successfully."
    else:
        return True, f"Territory {territory_id} created successfully."

async def delete_territory(conn: asyncpg.Connection, territory_id: str, guild_id: int) -> Tuple[bool, str]:
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


async def set_territory_controller(
    conn: asyncpg.Connection,
    territory_id: str,
    controller_identifier: str,
    guild_id: int,
    controller_type: str = 'character'
) -> Tuple[bool, str]:
    """
    Change the controller of a territory.

    Args:
        conn: Database connection
        territory_id: Territory ID
        controller_identifier: Character identifier or faction_id
        guild_id: Guild ID
        controller_type: 'character' or 'faction'

    Returns:
        (success, message)
    """
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False, f"Territory {territory_id} not found."

    # Handle removing controller
    if controller_identifier.lower() == 'none':
        territory.controller_character_id = None
        territory.controller_faction_id = None
        await territory.upsert(conn)
        return True, f"Territory {territory_id} is now uncontrolled."

    if controller_type == 'character':
        # Validate character
        character = await Character.fetch_by_identifier(conn, controller_identifier, guild_id)
        if not character:
            return False, f"Character '{controller_identifier}' not found."

        # Update controller (clear faction controller)
        territory.controller_character_id = character.id
        territory.controller_faction_id = None
        await territory.upsert(conn)

        return True, f"Territory {territory_id} is now controlled by {character.name}."

    elif controller_type == 'faction':
        # Validate faction
        faction = await Faction.fetch_by_faction_id(conn, controller_identifier, guild_id)
        if not faction:
            return False, f"Faction '{controller_identifier}' not found."

        # Update controller (clear character controller)
        territory.controller_character_id = None
        territory.controller_faction_id = faction.id
        await territory.upsert(conn)

        return True, f"Territory {territory_id} is now controlled by faction {faction.name}."

    else:
        return False, f"Invalid controller_type '{controller_type}'. Must be 'character' or 'faction'."


async def add_adjacency(conn: asyncpg.Connection, territory_id_1: str, territory_id_2: str, guild_id: int) -> Tuple[bool, str]:
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

    # Check if adjacency already exists
    already_adjacent = await TerritoryAdjacency.are_adjacent(conn, territory_id_1, territory_id_2, guild_id)
    if already_adjacent:
        return False, f"Territories {territory_id_1} and {territory_id_2} are already adjacent."

    # Create adjacency
    adjacency = TerritoryAdjacency(
        territory_a_id=min(territory_id_1, territory_id_2),
        territory_b_id=max(territory_id_1, territory_id_2),
        guild_id=guild_id
    )

    await adjacency.upsert(conn)
    return True, f"Territories {territory_id_1} and {territory_id_2} are now adjacent."


async def remove_adjacency(conn: asyncpg.Connection, territory_id_1: str, territory_id_2: str, guild_id: int) -> Tuple[bool, str]:
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


async def edit_territory_siege_defense(
    conn: asyncpg.Connection,
    territory_id: str,
    siege_defense: int,
    guild_id: int
) -> Tuple[bool, str]:
    """Set the base siege defense of a territory."""
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False, f"Territory '{territory_id}' not found."

    if siege_defense < 0:
        return False, "Siege defense cannot be negative."

    territory.siege_defense = siege_defense
    await territory.upsert(conn)

    return True, f"Territory '{territory_id}' siege defense set to {siege_defense}."
