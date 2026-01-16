"""
List command handlers for viewing all entities.
"""
import asyncpg
from typing import Tuple, List, Optional
from db import Faction, FactionMember, Territory, UnitType, BuildingType, Unit, Character


async def list_factions(conn: asyncpg.Connection, guild_id: int) -> Tuple[bool, str, Optional[List[dict]]]:
    """
    List all factions with member counts.

    Returns:
        (success, message, data) where data is list of dicts with:
        - faction: Faction object
        - member_count: Number of members
    """
    factions = await Faction.fetch_all(conn, guild_id)

    if not factions:
        return False, "No factions found. Use `/create-test-config` to set up a test configuration.", None

    faction_list = []
    for faction in factions:
        # Get member count
        members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)
        faction_list.append({
            'faction': faction,
            'member_count': len(members)
        })

    return True, "", faction_list


async def list_territories(conn: asyncpg.Connection, guild_id: int) -> Tuple[bool, str, Optional[List[dict]]]:
    """
    List all territories with controllers.

    Returns:
        (success, message, data) where data is list of dicts with:
        - territory: Territory object
        - controller_name: Name of controlling character (or "Uncontrolled")
    """
    territories = await Territory.fetch_all(conn, guild_id)

    if not territories:
        return False, "No territories found. Use `/create-test-config` to set up a test configuration.", None

    territory_list = []
    for territory in territories:
        # Get controller character name
        controller_name = "Uncontrolled"
        if territory.controller_character_id:
            character = await Character.fetch_by_id(conn, territory.controller_character_id)
            if character:
                controller_name = character.name

        territory_list.append({
            'territory': territory,
            'controller_name': controller_name
        })

    return True, "", territory_list


async def list_unit_types(conn: asyncpg.Connection, guild_id: int) -> Tuple[bool, str, Optional[List[UnitType]]]:
    """
    List all unit types.

    Returns:
        (success, message, unit_types)
    """
    unit_types = await UnitType.fetch_all(conn, guild_id)

    if not unit_types:
        return False, "No unit types found. Use `/create-test-config` to set up a test configuration.", None

    return True, "", unit_types


async def list_building_types(conn: asyncpg.Connection, guild_id: int) -> Tuple[bool, str, Optional[List[BuildingType]]]:
    """
    List all building types.

    Returns:
        (success, message, building_types)
    """
    building_types = await BuildingType.fetch_all(conn, guild_id)

    if not building_types:
        return False, "No building types found. Use `/create-building-type` to create one.", None

    return True, "", building_types


async def list_units(conn: asyncpg.Connection, guild_id: int) -> Tuple[bool, str, Optional[List[dict]]]:
    """
    List all units with details.

    Returns:
        (success, message, data) where data is list of dicts with:
        - unit: Unit object
        - owner_name: Name of owner character
        - faction_name: Name of faction (or "No faction")
    """
    units = await Unit.fetch_all(conn, guild_id)

    if not units:
        return False, "No units found.", None

    unit_list = []
    for unit in units:
        # Get owner name
        owner = await Character.fetch_by_id(conn, unit.owner_character_id)
        owner_name = owner.name if owner else "Unknown"

        # Get faction name
        faction_name = "No faction"
        if unit.faction_id:
            faction = await Faction.fetch_by_id(conn, unit.faction_id)
            if faction:
                faction_name = faction.name

        unit_list.append({
            'unit': unit,
            'owner_name': owner_name,
            'faction_name': faction_name
        })

    return True, "", unit_list
