"""
View command handlers for displaying wargame information.
"""
import asyncpg
from typing import Optional, Tuple, List, Any
from db import (
    Territory, Faction, FactionMember, Unit, UnitType, BuildingType, Building,
    PlayerResources, Character, TerritoryAdjacency, Order, FactionPermission
)
from order_types import OrderType, OrderStatus


async def _get_unit_viewer_access(
    conn: asyncpg.Connection,
    unit: Unit,
    viewer_character_id: Optional[int],
    is_admin: bool,
    guild_id: int
) -> bool:
    """
    Determine if viewer has full access to unit details.

    Full access is granted to:
    - Admins (manage_guild permission)
    - Unit owner
    - Unit commander
    - Characters with COMMAND permission if unit is faction-owned

    Args:
        conn: Database connection
        unit: The unit being viewed
        viewer_character_id: Internal character ID of the viewer (or None if no character)
        is_admin: Whether the viewer is a server admin
        guild_id: Guild ID

    Returns:
        True if viewer has full access, False otherwise
    """
    if is_admin:
        return True
    if viewer_character_id is None:
        return False
    if unit.owner_character_id == viewer_character_id:
        return True
    if unit.commander_character_id == viewer_character_id:
        return True
    # Check COMMAND permission if faction-owned
    if unit.faction_id:
        has_command = await FactionPermission.has_permission(
            conn, unit.faction_id, viewer_character_id, "COMMAND", guild_id
        )
        return has_command
    return False


async def _get_faction_viewer_access(
    conn: asyncpg.Connection,
    faction: Faction,
    viewer_character_id: Optional[int],
    is_admin: bool,
    guild_id: int
) -> bool:
    """
    Determine if viewer has member-level access to faction details.

    Full access is granted to:
    - Admins (manage_guild permission)
    - Faction members

    Args:
        conn: Database connection
        faction: The faction being viewed
        viewer_character_id: Internal character ID of the viewer (or None if no character)
        is_admin: Whether the viewer is a server admin
        guild_id: Guild ID

    Returns:
        True if viewer is admin or faction member, False otherwise
    """
    if is_admin:
        return True
    if viewer_character_id is None:
        return False
    membership = await FactionMember.fetch_membership(conn, faction.id, viewer_character_id, guild_id)
    return membership is not None


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


async def view_faction(
    conn: asyncpg.Connection,
    faction_id: str,
    guild_id: int,
    viewer_character_id: Optional[int] = None,
    is_admin: bool = False
) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch faction information for display.

    Args:
        conn: Database connection
        faction_id: The faction ID to view
        guild_id: Guild ID
        viewer_character_id: Internal character ID of the viewer (for permission checks)
        is_admin: Whether the viewer is a server admin

    Returns:
        (success, message, data) where data contains:
        - faction: Faction object
        - leader: Character object (if viewer is member/admin and exists)
        - members: List of Character objects (if viewer is member/admin)
        - viewer_is_member: bool indicating membership status
    """
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)

    if not faction:
        return False, f"Faction '{faction_id}' not found.", None

    # Determine viewer access level
    viewer_is_member = await _get_faction_viewer_access(
        conn, faction, viewer_character_id, is_admin, guild_id
    )

    leader = None
    members = []

    if viewer_is_member:
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
        'members': members,
        'viewer_is_member': viewer_is_member
    }


async def view_unit(
    conn: asyncpg.Connection,
    unit_id: str,
    guild_id: int,
    viewer_character_id: Optional[int] = None,
    is_admin: bool = False
) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch unit information for display.

    Args:
        conn: Database connection
        unit_id: The unit ID to view
        guild_id: Guild ID
        viewer_character_id: Internal character ID of the viewer (for permission checks)
        is_admin: Whether the viewer is a server admin

    Returns:
        (success, message, data) where data contains:
        - unit: Unit object
        - unit_type: UnitType object
        - owner: Character object (if viewer has full access)
        - commander: Character object (if viewer has full access and exists)
        - faction: Faction object (if exists)
        - viewer_has_full_access: bool indicating access level
    """
    unit = await Unit.fetch_by_unit_id(conn, unit_id, guild_id)

    if not unit:
        return False, f"Unit '{unit_id}' not found.", None

    # Determine viewer access level
    viewer_has_full_access = await _get_unit_viewer_access(
        conn, unit, viewer_character_id, is_admin, guild_id
    )

    # Fetch unit type
    unit_type = await UnitType.fetch_by_type_id(conn, unit.unit_type, guild_id)

    # Fetch owner/commander only for authorized viewers
    owner = None
    commander = None
    if viewer_has_full_access:
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
        'faction': faction,
        'viewer_has_full_access': viewer_has_full_access
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
    Supports multi-faction membership - returns all factions with represented faction highlighted.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - faction: Faction object (represented faction, for backwards compatibility)
        - leader: Character object (if exists)
        - members: List of Character objects (for represented faction)
        - all_memberships: List of dicts with faction info and join_turn
        - represented_faction: Faction object (same as 'faction')
        - can_change_representation: bool
        - turns_until_change: int
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)

    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    # Find all faction memberships
    all_faction_memberships = await FactionMember.fetch_all_by_character(conn, character.id, guild_id)

    if not all_faction_memberships:
        return False, f"{character.name} is not a member of any faction.", None

    # Get current turn for cooldown check
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    can_change, turns_remaining = character.can_change_representation(current_turn)

    # Build membership list with faction details
    all_memberships = []
    represented_faction = None
    represented_leader = None
    represented_members = []

    for fm in all_faction_memberships:
        faction = await Faction.fetch_by_id(conn, fm.faction_id)
        if faction:
            is_represented = character.represented_faction_id == faction.id
            is_leader = faction.leader_character_id == character.id

            membership_info = {
                'faction': faction,
                'joined_turn': fm.joined_turn,
                'is_represented': is_represented,
                'is_leader': is_leader
            }
            all_memberships.append(membership_info)

            # Get details for represented faction
            if is_represented:
                represented_faction = faction
                if faction.leader_character_id:
                    represented_leader = await Character.fetch_by_id(conn, faction.leader_character_id)

                # Fetch members of represented faction
                faction_members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)
                for member in faction_members:
                    char = await Character.fetch_by_id(conn, member.character_id)
                    if char:
                        represented_members.append(char)

    # If no represented faction found but we have memberships, use the first one
    if not represented_faction and all_memberships:
        represented_faction = all_memberships[0]['faction']
        if represented_faction.leader_character_id:
            represented_leader = await Character.fetch_by_id(conn, represented_faction.leader_character_id)

        faction_members = await FactionMember.fetch_by_faction(conn, represented_faction.id, guild_id)
        for member in faction_members:
            char = await Character.fetch_by_id(conn, member.character_id)
            if char:
                represented_members.append(char)

    return True, "", {
        'character': character,
        'faction': represented_faction,  # Backwards compatibility
        'leader': represented_leader,
        'members': represented_members,
        'all_memberships': all_memberships,
        'represented_faction': represented_faction,
        'can_change_representation': can_change,
        'turns_until_change': turns_remaining
    }


async def view_units_for_character(conn: asyncpg.Connection, user_id: int, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch units owned or commanded by player's character, plus faction units from all factions
    where they have COMMAND permission.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - owned_units: List of ACTIVE Unit objects owned
        - commanded_units: List of ACTIVE Unit objects commanded
        - faction_units_by_faction: Dict mapping Faction -> List of ACTIVE Unit objects
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

    # Track unit IDs we've already listed
    listed_unit_ids = {u.id for u in active_owned} | {u.id for u in active_commanded}

    # Check ALL factions where the character has COMMAND permission or is leader
    # Use list of tuples since Faction is not hashable
    faction_units_list = []  # List of (faction, units) tuples

    # Get all factions where character is leader
    all_factions = await Faction.fetch_all(conn, guild_id)
    for faction in all_factions:
        is_leader = faction.leader_character_id == character.id
        has_command = await FactionPermission.has_permission(
            conn, faction.id, character.id, 'COMMAND', guild_id
        )

        if is_leader or has_command:
            # Fetch faction-owned units
            all_faction_units = await Unit.fetch_by_faction_owner(conn, faction.id, guild_id)
            # Filter to active and exclude already-listed units
            faction_units = [
                u for u in all_faction_units
                if u.status == 'ACTIVE' and u.id not in listed_unit_ids
            ]
            if faction_units:
                faction_units_list.append((faction, faction_units))
                # Add to listed to avoid duplicates across factions
                listed_unit_ids.update(u.id for u in faction_units)

    if not active_owned and not active_commanded and not faction_units_list and not disbanded_units:
        return False, f"{character.name} doesn't own or command any units.", None

    return True, "", {
        'character': character,
        'owned_units': active_owned,
        'commanded_units': active_commanded,
        'faction_units_list': faction_units_list,
        'disbanded_units': disbanded_units
    }


async def view_territories_for_character(conn: asyncpg.Connection, user_id: int, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch territories controlled by the player's character, plus faction territories from all
    factions where they have any permission.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - territories: List of Territory objects (character-controlled)
        - faction_territories_by_faction: Dict mapping Faction -> List of Territory objects
        - adjacencies: Dict mapping territory_id to list of adjacent territory IDs
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)

    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    # Fetch territories controlled by this character
    territories = await Territory.fetch_by_controller(conn, character.id, guild_id)

    # Track territory IDs we've already listed
    listed_territory_ids = {t.territory_id for t in territories}

    # Get all permissions for this character
    all_permissions = await FactionPermission.fetch_by_character(conn, character.id, guild_id)
    faction_ids_with_permission = {p.faction_id for p in all_permissions}

    # Check ALL factions where the character has any permission or is leader
    # Use list of tuples since Faction is not hashable
    faction_territories_list = []  # List of (faction, territories) tuples

    all_factions = await Faction.fetch_all(conn, guild_id)
    for faction in all_factions:
        is_leader = faction.leader_character_id == character.id
        has_any_permission = faction.id in faction_ids_with_permission

        if is_leader or has_any_permission:
            # Fetch faction-controlled territories
            all_faction_territories = await Territory.fetch_by_faction_controller(conn, faction.id, guild_id)
            # Exclude already-listed territories
            faction_territories = [
                t for t in all_faction_territories
                if t.territory_id not in listed_territory_ids
            ]
            if faction_territories:
                faction_territories_list.append((faction, faction_territories))
                # Add to listed to avoid duplicates across factions
                listed_territory_ids.update(t.territory_id for t in faction_territories)

    if not territories and not faction_territories_list:
        return False, f"{character.name} doesn't control any territories and has no faction access.", None

    # Fetch adjacencies for all territories
    adjacencies = {}
    for territory in territories:
        adjacent_ids = await TerritoryAdjacency.fetch_adjacent(conn, territory.territory_id, guild_id)
        adjacencies[territory.territory_id] = adjacent_ids
    for faction, faction_territories in faction_territories_list:
        for territory in faction_territories:
            adjacent_ids = await TerritoryAdjacency.fetch_adjacent(conn, territory.territory_id, guild_id)
            adjacencies[territory.territory_id] = adjacent_ids

    return True, "", {
        'character': character,
        'territories': territories,
        'faction_territories_list': faction_territories_list,
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
