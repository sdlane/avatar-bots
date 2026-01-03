"""
Unit management command handlers.
"""
import asyncpg
from typing import Tuple
from db import Unit, UnitType, Character, FactionMember, Faction, Territory


async def create_unit(conn: asyncpg.Connection, unit_id: str, unit_type: str, owner_identifier: str, territory_id: int, nation: str, guild_id: int) -> Tuple[bool, str]:
    """
    Create a new unit.

    Args:
        conn: Database connection
        unit_id: Unique identifier for the unit
        unit_type: Type identifier for the unit type
        owner_identifier: Character identifier for the owner
        territory_id: Territory where unit is created
        nation: Nation for the unit (required)
        guild_id: Guild ID

    Returns:
        (success, message) tuple
    """
    # Check if unit already exists
    existing = await Unit.fetch_by_unit_id(conn, unit_id, guild_id)
    if existing:
        return False, f"Unit '{unit_id}' already exists."

    # Validate owner character
    owner_char = await Character.fetch_by_identifier(conn, owner_identifier, guild_id)
    if not owner_char:
        return False, f"Character '{owner_identifier}' not found."

    # Get owner's faction
    faction_member = await FactionMember.fetch_by_character(conn, owner_char.id, guild_id)
    faction_id = faction_member.faction_id if faction_member else None

    # Fetch unit type - must match the specified nation
    unit_type_obj = await UnitType.fetch_by_type_id(conn, unit_type, guild_id)

    if not unit_type_obj:
        return False, f"Unit type '{unit_type}' not found."

    # Validate that unit type matches the specified nation
    if unit_type_obj.nation and unit_type_obj.nation != nation:
        return False, f"Unit type '{unit_type}' belongs to nation '{unit_type_obj.nation}', but you specified nation '{nation}'."

    # Validate territory
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False, f"Territory {territory_id} not found."

    # Create unit from unit type
    unit = Unit(
        unit_id=unit_id,
        name=None,
        unit_type=unit_type,
        owner_character_id=owner_char.id,
        commander_character_id=None,
        commander_assigned_turn=None,
        faction_id=faction_id,
        movement=unit_type_obj.movement,
        organization=unit_type_obj.organization,
        max_organization=unit_type_obj.organization,
        attack=unit_type_obj.attack,
        defense=unit_type_obj.defense,
        siege_attack=unit_type_obj.siege_attack,
        siege_defense=unit_type_obj.siege_defense,
        size=unit_type_obj.size,
        capacity=unit_type_obj.capacity,
        current_territory_id=territory_id,
        is_naval=unit_type_obj.is_naval,
        upkeep_ore=unit_type_obj.upkeep_ore,
        upkeep_lumber=unit_type_obj.upkeep_lumber,
        upkeep_coal=unit_type_obj.upkeep_coal,
        upkeep_rations=unit_type_obj.upkeep_rations,
        upkeep_cloth=unit_type_obj.upkeep_cloth,
        keywords=unit_type_obj.keywords.copy() if unit_type_obj.keywords else [],
        guild_id=guild_id
    )

    await unit.upsert(conn)

    return True, f"Unit '{unit_id}' created successfully in territory {territory_id}."


async def delete_unit(conn: asyncpg.Connection, unit_id: str, guild_id: int) -> Tuple[bool, str]:
    """Delete a unit."""
    unit = await Unit.fetch_by_unit_id(conn, unit_id, guild_id)

    if not unit:
        return False, f"Unit '{unit_id}' not found."

    # Delete unit
    await Unit.delete(conn, unit_id, guild_id)

    return True, f"Unit '{unit_id}' has been deleted."


async def set_unit_commander(conn: asyncpg.Connection, unit_id: str, commander_identifier: str, guild_id: int) -> Tuple[bool, str]:
    """Assign a commander to a unit."""
    unit = await Unit.fetch_by_unit_id(conn, unit_id, guild_id)

    if not unit:
        return False, f"Unit '{unit_id}' not found."

    # Handle removing commander
    if commander_identifier.lower() == 'none':
        unit.commander_character_id = None
        unit.commander_assigned_turn = None
        await unit.upsert(conn)
        return True, f"Removed commander from unit '{unit_id}'."

    # Validate commander character
    commander_char = await Character.fetch_by_identifier(conn, commander_identifier, guild_id)
    if not commander_char:
        return False, f"Character '{commander_identifier}' not found."

    # Check if commander is in the same faction as the unit
    if unit.faction_id:
        commander_faction = await FactionMember.fetch_by_character(conn, commander_char.id, guild_id)
        if not commander_faction or commander_faction.faction_id != unit.faction_id:
            faction = await Faction.fetch_by_id(conn, unit.faction_id)
            return False, f"{commander_char.name} is not a member of {faction.name}. Commanders must be in the same faction as their unit."

    # Get current turn
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Assign commander
    unit.commander_character_id = commander_char.id
    unit.commander_assigned_turn = current_turn
    await unit.upsert(conn)

    return True, f"{commander_char.name} is now the commander of unit '{unit_id}'."
