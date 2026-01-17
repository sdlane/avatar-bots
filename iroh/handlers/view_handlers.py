"""
View command handlers for displaying wargame information.
"""
import asyncpg
from typing import Optional, Tuple, List, Any
from db import (
    Territory, Faction, FactionMember, Unit, UnitType, BuildingType, Building,
    PlayerResources, Character, TerritoryAdjacency, Order
)
from order_types import OrderType, OrderStatus


async def view_territory(conn: asyncpg.Connection, territory_id: str, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch territory information for display.

    Returns:
        (success, message, data) where data contains:
        - territory: Territory object
        - adjacent_ids: List of adjacent territory IDs
        - controller_name: Name of controlling faction (if any)
        - buildings: List of Building objects in this territory
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

    # Fetch buildings in this territory
    buildings = await Building.fetch_by_territory(conn, territory_id, guild_id)

    return True, "", {
        'territory': territory,
        'adjacent_ids': adjacent_ids,
        'controller_name': controller_name,
        'buildings': buildings
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


async def view_unit_type(conn: asyncpg.Connection, type_id: str, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
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


async def view_building_type(conn: asyncpg.Connection, type_id: str, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch building type information for display.

    Returns:
        (success, message, data) where data contains:
        - building_type: BuildingType object
    """
    building_type = await BuildingType.fetch_by_type_id(conn, type_id, guild_id)

    if not building_type:
        return False, f"Building type '{type_id}' not found.", None

    return True, "", {'building_type': building_type}


async def view_building(conn: asyncpg.Connection, building_id: str, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch building information for display.

    Returns:
        (success, message, data) where data contains:
        - building: Building object
        - building_type: BuildingType object
        - territory: Territory object (if building has a location)
    """
    building = await Building.fetch_by_building_id(conn, building_id, guild_id)

    if not building:
        return False, f"Building '{building_id}' not found.", None

    # Fetch building type
    building_type = await BuildingType.fetch_by_type_id(conn, building.building_type, guild_id)

    # Fetch territory if building has a location
    territory = None
    if building.territory_id:
        territory = await Territory.fetch_by_territory_id(conn, building.territory_id, guild_id)

    return True, "", {
        'building': building,
        'building_type': building_type,
        'territory': territory
    }


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
            platinum=0,
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
        - owned_units: List of ACTIVE Unit objects owned
        - commanded_units: List of ACTIVE Unit objects commanded
        - disbanded_units: List of DISBANDED Unit objects (owned or commanded)
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)

    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    # Fetch owned and commanded units
    owned_units = await Unit.fetch_by_owner(conn, character.id, guild_id)
    commanded_units = await Unit.fetch_by_commander(conn, character.id, guild_id)

    # Separate by status
    active_owned = [u for u in owned_units if u.status == 'ACTIVE']
    active_commanded = [u for u in commanded_units if u.status == 'ACTIVE']

    # Get disbanded units (owned or commanded) - deduplicate by id
    all_units = list({u.id: u for u in owned_units + commanded_units}.values())
    disbanded_units = [u for u in all_units if u.status == 'DISBANDED']

    if not active_owned and not active_commanded and not disbanded_units:
        return False, f"{character.name} doesn't own or command any units.", None

    return True, "", {
        'character': character,
        'owned_units': active_owned,
        'commanded_units': active_commanded,
        'disbanded_units': disbanded_units
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


async def view_victory_points(
    conn: asyncpg.Connection,
    user_id: int,
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch victory point information for a character.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - character_vps: VPs from character's victory_points field
        - territory_vps: Total VPs from territories character controls
        - personal_vps: Total VPs (character_vps + territory_vps)
        - territories: List of (Territory, vp_count) tuples
        - faction: Faction object (if in a faction)
        - faction_total_vps: Total VPs from all faction members
        - faction_members_vps: List of (Character, vp_count) for faction members
        - assigned_to_faction: List of (Character, vp_count) assignments to faction
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)
    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    # Get territories controlled by this character
    territories = await Territory.fetch_by_controller(conn, character.id, guild_id)
    territory_vps = sum(t.victory_points for t in territories)
    territory_data = [(t, t.victory_points) for t in territories if t.victory_points > 0]

    # Character's direct VPs
    character_vps = character.victory_points

    # Total personal VPs = character VPs + territory VPs
    personal_vps = character_vps + territory_vps

    # Check faction membership
    faction_member = await FactionMember.fetch_by_character(conn, character.id, guild_id)
    faction = None
    faction_total_vps = 0
    faction_members_vps = []

    # Check if this character has an active VP assignment to another faction
    own_vp_assignment = await conn.fetchrow("""
        SELECT wo.order_data->>'target_faction_id' as target_faction_id
        FROM WargameOrder wo
        WHERE wo.guild_id = $1
        AND wo.character_id = $2
        AND wo.order_type = $3
        AND wo.status = $4
    """, guild_id, character.id, OrderType.ASSIGN_VICTORY_POINTS.value,
         OrderStatus.ONGOING.value)

    assigning_vps_to = None
    if own_vp_assignment:
        target_faction = await Faction.fetch_by_faction_id(conn, own_vp_assignment['target_faction_id'], guild_id)
        if target_faction:
            assigning_vps_to = target_faction

    if faction_member:
        faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

        # Get all faction members and their VPs (including character VPs)
        # But exclude members who have active VP assignments to OTHER factions
        members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)
        members_assigning_away = []  # Track members assigning VPs elsewhere
        for member in members:
            member_char = await Character.fetch_by_id(conn, member.character_id)
            if member_char:
                # Check if this member has an active VP assignment to another faction
                member_vp_assignment = await conn.fetchrow("""
                    SELECT wo.order_data->>'target_faction_id' as target_faction_id
                    FROM WargameOrder wo
                    WHERE wo.guild_id = $1
                    AND wo.character_id = $2
                    AND wo.order_type = $3
                    AND wo.status = $4
                """, guild_id, member.character_id, OrderType.ASSIGN_VICTORY_POINTS.value,
                     OrderStatus.ONGOING.value)

                member_territories = await Territory.fetch_by_controller(conn, member.character_id, guild_id)
                member_territory_vps = sum(t.victory_points for t in member_territories)
                member_vps = member_territory_vps + member_char.victory_points

                if member_vp_assignment and member_vp_assignment['target_faction_id'] != faction.faction_id:
                    # This member is assigning their VPs to a different faction
                    if member_vps > 0:
                        target_f = await Faction.fetch_by_faction_id(conn, member_vp_assignment['target_faction_id'], guild_id)
                        members_assigning_away.append((member_char, member_vps, target_f))
                else:
                    # Count their VPs toward this faction
                    faction_total_vps += member_vps
                    if member_vps > 0:
                        faction_members_vps.append((member_char, member_vps))

    # Get VP assignments TO this character's faction
    assigned_to_faction = []
    assigned_vps_total = 0
    if faction:
        # Find all ONGOING ASSIGN_VICTORY_POINTS orders targeting this faction
        rows = await conn.fetch("""
            SELECT wo.character_id
            FROM WargameOrder wo
            WHERE wo.guild_id = $1
            AND wo.order_type = $2
            AND wo.status = $3
            AND wo.order_data->>'target_faction_id' = $4
        """, guild_id, OrderType.ASSIGN_VICTORY_POINTS.value,
             OrderStatus.ONGOING.value, faction.faction_id)

        for row in rows:
            assigning_char = await Character.fetch_by_id(conn, row['character_id'])
            if assigning_char:
                assigning_territories = await Territory.fetch_by_controller(conn, assigning_char.id, guild_id)
                assigning_territory_vps = sum(t.victory_points for t in assigning_territories)
                assigning_vps = assigning_territory_vps + assigning_char.victory_points
                if assigning_vps > 0:
                    assigned_to_faction.append((assigning_char, assigning_vps))
                    assigned_vps_total += assigning_vps

        # Include assigned VPs in faction total
        faction_total_vps += assigned_vps_total

    return True, "", {
        'character': character,
        'character_vps': character_vps,
        'territory_vps': territory_vps,
        'personal_vps': personal_vps,
        'territories': territory_data,
        'faction': faction,
        'faction_total_vps': faction_total_vps,
        'faction_members_vps': faction_members_vps,
        'assigned_to_faction': assigned_to_faction,
        'assigning_vps_to': assigning_vps_to,  # Faction this character is assigning VPs to (if any)
        'members_assigning_away': members_assigning_away if faction_member else [],  # Faction members assigning VPs elsewhere
    }


async def view_faction_victory_points(
    conn: asyncpg.Connection,
    faction_id: str,
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch victory point information for a faction (admin view).

    Returns:
        (success, message, data) where data contains:
        - faction: Faction object
        - faction_total_vps: Total VPs from all faction members (territories + character VPs) + assigned VPs
        - faction_members_vps: List of (Character, vp_count) for faction members
        - assigned_to_faction: List of (Character, vp_count) assignments to faction
    """
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found.", None

    faction_total_vps = 0
    faction_members_vps = []
    members_assigning_away = []  # Track members assigning VPs elsewhere

    # Get all faction members and their VPs (including character VPs)
    # But exclude members who have active VP assignments to OTHER factions
    members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)
    for member in members:
        member_char = await Character.fetch_by_id(conn, member.character_id)
        if member_char:
            # Check if this member has an active VP assignment to another faction
            member_vp_assignment = await conn.fetchrow("""
                SELECT wo.order_data->>'target_faction_id' as target_faction_id
                FROM WargameOrder wo
                WHERE wo.guild_id = $1
                AND wo.character_id = $2
                AND wo.order_type = $3
                AND wo.status = $4
            """, guild_id, member.character_id, OrderType.ASSIGN_VICTORY_POINTS.value,
                 OrderStatus.ONGOING.value)

            member_territories = await Territory.fetch_by_controller(conn, member.character_id, guild_id)
            member_territory_vps = sum(t.victory_points for t in member_territories)
            member_vps = member_territory_vps + member_char.victory_points

            if member_vp_assignment and member_vp_assignment['target_faction_id'] != faction.faction_id:
                # This member is assigning their VPs to a different faction
                if member_vps > 0:
                    target_f = await Faction.fetch_by_faction_id(conn, member_vp_assignment['target_faction_id'], guild_id)
                    members_assigning_away.append((member_char, member_vps, target_f))
            else:
                # Count their VPs toward this faction
                faction_total_vps += member_vps
                if member_vps > 0:
                    faction_members_vps.append((member_char, member_vps))

    # Get VP assignments TO this faction
    assigned_to_faction = []
    assigned_vps_total = 0

    # Find all ONGOING ASSIGN_VICTORY_POINTS orders targeting this faction
    rows = await conn.fetch("""
        SELECT wo.character_id
        FROM WargameOrder wo
        WHERE wo.guild_id = $1
        AND wo.order_type = $2
        AND wo.status = $3
        AND wo.order_data->>'target_faction_id' = $4
    """, guild_id, OrderType.ASSIGN_VICTORY_POINTS.value,
         OrderStatus.ONGOING.value, faction.faction_id)

    for row in rows:
        assigning_char = await Character.fetch_by_id(conn, row['character_id'])
        if assigning_char:
            assigning_territories = await Territory.fetch_by_controller(conn, assigning_char.id, guild_id)
            assigning_territory_vps = sum(t.victory_points for t in assigning_territories)
            assigning_vps = assigning_territory_vps + assigning_char.victory_points
            if assigning_vps > 0:
                assigned_to_faction.append((assigning_char, assigning_vps))
                assigned_vps_total += assigning_vps

    # Include assigned VPs in faction total
    faction_total_vps += assigned_vps_total

    return True, "", {
        'faction': faction,
        'faction_total_vps': faction_total_vps,
        'faction_members_vps': faction_members_vps,
        'assigned_to_faction': assigned_to_faction,
        'members_assigning_away': members_assigning_away,  # Faction members assigning VPs elsewhere
    }
