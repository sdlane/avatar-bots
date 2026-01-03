"""
View command handlers for displaying wargame information.
"""
import asyncpg
from typing import Optional, Tuple, List, Any
from db import (
    Territory, Faction, FactionMember, Unit, UnitType,
    PlayerResources, Character, TerritoryAdjacency
)


async def view_territory(conn: asyncpg.Connection, territory_id: int, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch territory information for display.

    Returns:
        (success, message, data) where data contains:
        - territory: Territory object
        - adjacent_ids: List of adjacent territory IDs
        - controller_name: Name of controlling faction (if any)
    """
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)

    if not territory:
        return False, f"Territory {territory_id} not found.", None

    # Fetch adjacent territories
    adjacent_ids = await TerritoryAdjacency.fetch_adjacent(conn, territory_id, guild_id)

    # Fetch controller character name if exists
    controller_name = None
    if territory.controller_character_id:
        character = await Character.fetch_by_id(conn, territory.controller_character_id)
        if character:
            controller_name = character.name

    return True, "", {
        'territory': territory,
        'adjacent_ids': adjacent_ids,
        'controller_name': controller_name
    }


async def view_faction(conn: asyncpg.Connection, faction_id: str, guild_id: int, show_full_details: bool = True) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch faction information for display.

    Returns:
        (success, message, data) where data contains:
        - faction: Faction object
        - leader: Character object (if show_full_details and exists)
        - members: List of Character objects (if show_full_details)
    """
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)

    if not faction:
        return False, f"Faction '{faction_id}' not found.", None

    leader = None
    members = []

    if show_full_details:
        # Fetch leader
        if faction.leader_character_id:
            leader = await Character.fetch_by_id(conn, faction.leader_character_id)

        # Fetch members
        faction_members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)
        for fm in faction_members:
            char = await Character.fetch_by_id(conn, fm.character_id)
            if char:
                members.append(char)

    return True, "", {
        'faction': faction,
        'leader': leader,
        'members': members
    }


async def view_unit(conn: asyncpg.Connection, unit_id: str, guild_id: int, show_full_details: bool = True) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch unit information for display.

    Returns:
        (success, message, data) where data contains:
        - unit: Unit object
        - unit_type: UnitType object
        - owner: Character object (if show_full_details)
        - commander: Character object (if show_full_details and exists)
        - faction: Faction object (if exists)
    """
    unit = await Unit.fetch_by_unit_id(conn, unit_id, guild_id)

    if not unit:
        return False, f"Unit '{unit_id}' not found.", None

    # Fetch unit type
    unit_type = await UnitType.fetch_by_type_id(conn, unit.unit_type, guild_id)

    # Fetch owner/commander only for admins
    owner = None
    commander = None
    if show_full_details:
        if unit.owner_character_id:
            owner = await Character.fetch_by_id(conn, unit.owner_character_id)
        if unit.commander_character_id:
            commander = await Character.fetch_by_id(conn, unit.commander_character_id)

    # Fetch faction (visible to all)
    faction = None
    if unit.faction_id:
        faction = await Faction.fetch_by_id(conn, unit.faction_id)

    return True, "", {
        'unit': unit,
        'unit_type': unit_type,
        'owner': owner,
        'commander': commander,
        'faction': faction
    }


async def view_unit_type(conn: asyncpg.Connection, type_id: str, nation: Optional[str], guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch unit type information for display.

    Returns:
        (success, message, data) where data contains:
        - unit_type: UnitType object
    """
    unit_type = await UnitType.fetch_by_type_id(conn, type_id, guild_id)

    if not unit_type:
        return False, f"Unit type '{type_id}' not found.", None

    return True, "", {'unit_type': unit_type}


async def view_resources(conn: asyncpg.Connection, user_id: int, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch player's resource inventory.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - resources: PlayerResources object
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)

    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    # Fetch resources
    resources = await PlayerResources.fetch_by_character(conn, character.id, guild_id)

    if not resources:
        # Create empty resources entry
        resources = PlayerResources(
            character_id=character.id,
            ore=0,
            lumber=0,
            coal=0,
            rations=0,
            cloth=0,
            guild_id=guild_id
        )

    return True, "", {
        'character': character,
        'resources': resources
    }


async def view_faction_membership(conn: asyncpg.Connection, user_id: int, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch player's faction membership information.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - faction: Faction object
        - leader: Character object (if exists)
        - members: List of Character objects
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)

    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    # Find faction membership
    faction_member = await FactionMember.fetch_by_character(conn, character.id, guild_id)

    if not faction_member:
        return False, f"{character.name} is not a member of any faction.", None

    # Fetch faction details
    faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

    if not faction:
        return False, "Faction data not found.", None

    # Fetch leader and all members
    leader = None
    if faction.leader_character_id:
        leader = await Character.fetch_by_id(conn, faction.leader_character_id)

    faction_members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)
    members = []
    for fm in faction_members:
        char = await Character.fetch_by_id(conn, fm.character_id)
        if char:
            members.append(char)

    return True, "", {
        'character': character,
        'faction': faction,
        'leader': leader,
        'members': members
    }


async def view_units_for_character(conn: asyncpg.Connection, user_id: int, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch units owned or commanded by player's character.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - owned_units: List of Unit objects
        - commanded_units: List of Unit objects
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)

    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    # Fetch owned and commanded units
    owned_units = await Unit.fetch_by_owner(conn, character.id, guild_id)
    commanded_units = await Unit.fetch_by_commander(conn, character.id, guild_id)

    if not owned_units and not commanded_units:
        return False, f"{character.name} doesn't own or command any units.", None

    return True, "", {
        'character': character,
        'owned_units': owned_units,
        'commanded_units': commanded_units
    }


async def view_territories_for_character(conn: asyncpg.Connection, user_id: int, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch territories controlled by the player's character.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - faction: Faction object (optional, for display)
        - territories: List of Territory objects
        - adjacencies: Dict mapping territory_id to list of adjacent territory IDs
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)

    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    # Fetch territories controlled by this character
    territories = await Territory.fetch_by_controller(conn, character.id, guild_id)

    if not territories:
        return False, f"{character.name} doesn't control any territories.", None

    # Fetch faction for display (optional)
    faction_member = await FactionMember.fetch_by_character(conn, character.id, guild_id)
    faction = None
    if faction_member:
        faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

    # Fetch adjacencies for each territory
    adjacencies = {}
    for territory in territories:
        adjacent_ids = await TerritoryAdjacency.fetch_adjacent(conn, territory.territory_id, guild_id)
        adjacencies[territory.territory_id] = adjacent_ids

    return True, "", {
        'character': character,
        'faction': faction,
        'territories': territories,
        'adjacencies': adjacencies
    }
