"""
Order management command handlers.
"""
import asyncpg
from typing import Tuple, List, Optional
from db import Order, Unit, Character, Faction, FactionMember, Territory, TurnLog, Alliance, FactionPermission, UnitType, BuildingType
from order_types import OrderType, ORDER_PHASE_MAP, ORDER_PRIORITY_MAP, OrderStatus, TurnPhase
from datetime import datetime


async def check_unit_order_authorization(
    conn: asyncpg.Connection,
    unit: Unit,
    character_id: int,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Check if a character can issue orders for a unit.

    For character-owned units: must be owner or commander
    For faction-owned units: must be commander OR have COMMAND permission

    Args:
        conn: Database connection
        unit: The unit to check authorization for
        character_id: Internal character ID
        guild_id: Guild ID

    Returns:
        (authorized, error_message)
        - If authorized, returns (True, "")
        - If not authorized, returns (False, "error message")
    """
    # Check if unit is character-owned
    if unit.owner_character_id is not None:
        # Character-owned unit: must be owner or commander
        if unit.owner_character_id == character_id:
            return True, ""
        if unit.commander_character_id == character_id:
            return True, ""
        return False, "You must be the owner or commander of this unit to issue orders."

    # Faction-owned unit
    if unit.owner_faction_id is not None:
        # Commander is always authorized
        if unit.commander_character_id == character_id:
            return True, ""

        # Check if character has COMMAND permission for this faction
        has_permission = await FactionPermission.has_permission(
            conn, unit.owner_faction_id, character_id, "COMMAND", guild_id
        )
        if has_permission:
            return True, ""

        return False, "You are not authorized to issue orders for this faction unit. Ask a GM for clarification."

    # Should not reach here, but handle edge case
    return False, "Unit has no valid owner."


async def submit_join_faction_order(
    conn: asyncpg.Connection,
    character_identifier: str,
    target_faction_id: str,
    guild_id: int,
    submitting_character_id: int
) -> Tuple[bool, str]:
    """
    Submit an order for a character to join a faction.

    Requires BOTH the character wanting to join AND the faction leader to submit orders.
    The order is only executed when both parties have submitted matching orders.

    Args:
        conn: Database connection
        character_identifier: Character identifier (the one wanting to join)
        target_faction_id: Faction ID to join
        guild_id: Guild ID
        submitting_character_id: ID of character submitting this order (for validation)

    Returns:
        (success, message)
    """
    # Validate character exists
    character = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not character:
        return False, f"Character '{character_identifier}' not found."

    # Validate faction exists
    faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
    if not faction:
        return False, f"Faction '{target_faction_id}' not found."

    # Check character not already in this specific faction
    existing_membership = await FactionMember.fetch_membership(conn, faction.id, character.id, guild_id)
    if existing_membership:
        return False, f"{character.name} is already a member of {faction.name}."

    # Validate submitter is either:
    # 1. The character themselves (requesting to join)
    # 2. The faction leader
    # 3. Someone with MEMBERSHIP permission for the faction
    is_character = submitting_character_id == character.id
    is_leader = submitting_character_id == faction.leader_character_id
    has_membership_permission = await FactionPermission.has_permission(
        conn, faction.id, submitting_character_id, "MEMBERSHIP", guild_id
    )

    if not is_character and not is_leader and not has_membership_permission:
        return False, f"You must be either authorized to manage faction membership or the person being added to the faction in order to issue a join faction order."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Determine submitted_by role
    # 'character' = the person joining, 'leader' = faction authorization (leader or MEMBERSHIP permission)
    submitted_by = 'character' if is_character else 'leader'

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.JOIN_FACTION.value,
        unit_ids=[],
        character_id=character.id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.JOIN_FACTION].value,
        priority=ORDER_PRIORITY_MAP[OrderType.JOIN_FACTION],
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': target_faction_id,
            'submitted_by': submitted_by,
            'submitting_character_id': submitting_character_id
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)
    return True, f"Order submitted. Order will be processed at the next beginning phase. The addition to the faction will be completed when both the faction leader and the person being added submit the order."


async def submit_leave_faction_order(
    conn: asyncpg.Connection,
    character: Character,
    guild_id: int,
    faction_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Submit an order for a character to leave a faction.

    Args:
        conn: Database connection
        character: Character object
        guild_id: Guild ID
        faction_id: Optional faction identifier. If not provided, leaves represented faction.

    Returns:
        (success, message)
    """
    # Determine which faction to leave
    if faction_id:
        faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
        if not faction:
            return False, f"Faction '{faction_id}' not found."
        faction_member = await FactionMember.fetch_membership(conn, faction.id, character.id, guild_id)
        if not faction_member:
            return False, f"You are not a member of {faction.name}."
    else:
        # Default to represented faction or any membership
        faction_member = await FactionMember.fetch_by_character(conn, character.id, guild_id)
        if not faction_member:
            return False, f"You are not a member of any faction."
        faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

    # Check character is not faction leader
    if faction.leader_character_id == character.id:
        return False, f"You are the leader of {faction.name}. Get a GM to assign a new leader first using `/set-faction-leader`."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Check no pending leave order for this specific faction
    existing_orders = await Order.fetch_by_character_and_type(
        conn, character.id, guild_id, OrderType.LEAVE_FACTION.value, OrderStatus.PENDING.value
    )

    # Filter to orders for this specific faction
    for existing_order in existing_orders:
        order_faction_id = existing_order.order_data.get('faction_id')
        if order_faction_id == faction.id:
            return False, f"{character.name} already has a pending order to leave {faction.name}."

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order with faction_id in order_data
    order = Order(
        order_id=order_id,
        order_type=OrderType.LEAVE_FACTION.value,
        unit_ids=[],
        character_id=character.id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.LEAVE_FACTION].value,
        priority=ORDER_PRIORITY_MAP[OrderType.LEAVE_FACTION],
        status=OrderStatus.PENDING.value,
        order_data={
            'faction_id': faction.id,
            'faction_name': faction.name
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    return True, f"Order submitted: {character.name} will leave {faction.name} next turn (Order #{order_id})."


async def submit_kick_from_faction_order(
    conn: asyncpg.Connection,
    submitting_character: Character,
    target_character_identifier: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Submit an order to kick a member from a faction.

    Requires MEMBERSHIP permission or being the faction leader.

    Cannot be issued:
    - Within the first 3 turns of the game
    - Within 3 turns of the creation of the faction
    - Within 3 turns of the member joining the faction
    - Against the faction leader themselves

    Args:
        conn: Database connection
        submitting_character: Character submitting the order
        target_character_identifier: Character identifier to kick
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate target character exists
    target_character = await Character.fetch_by_identifier(conn, target_character_identifier, guild_id)
    if not target_character:
        return False, f"Character '{target_character_identifier}' not found."

    # Check submitter is in a faction
    submitter_membership = await FactionMember.fetch_by_character(conn, submitting_character.id, guild_id)
    if not submitter_membership:
        return False, "You are not a member of any faction."

    # Get faction
    faction = await Faction.fetch_by_id(conn, submitter_membership.faction_id)

    # Check submitter is faction leader OR has MEMBERSHIP permission
    is_leader = faction.leader_character_id == submitting_character.id
    has_membership_permission = await FactionPermission.has_permission(
        conn, faction.id, submitting_character.id, "MEMBERSHIP", guild_id
    )
    if not is_leader and not has_membership_permission:
        return False, f"You are not authorized to kick members from {faction.name}. Ask a GM for clarification."

    # Check target is not the submitter themselves
    if target_character.id == submitting_character.id:
        return False, "You cannot kick yourself from the faction."

    # Check target is not the faction leader
    if target_character.id == faction.leader_character_id:
        return False, f"You cannot kick the leader of {faction.name}. Transfer leadership first."

    # Check target is in the same faction
    target_membership = await FactionMember.fetch_by_character(conn, target_character.id, guild_id)
    if not target_membership or target_membership.faction_id != faction.id:
        return False, f"{target_character.name} is not a member of {faction.name}."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] + 1 if wargame_config else 1

    # Check not within first 3 turns of game
    if current_turn < 3:
        return False, f"Kick orders cannot be issued within the first 3 turns of the game. Current turn: {current_turn}."

    # Get faction created_turn
    faction_row = await conn.fetchrow(
        "SELECT created_turn FROM Faction WHERE id = $1;",
        faction.id
    )
    faction_created_turn = faction_row['created_turn'] if faction_row and faction_row['created_turn'] else 0

    # Check not within 3 turns of faction creation
    if current_turn - faction_created_turn < 4:
        turns_remaining = 4 - (current_turn - faction_created_turn)
        return False, f"Kick orders cannot be issued within 3 turns of faction creation. Wait {turns_remaining} more turn(s)."

    # Check not within 3 turns of member joining
    if current_turn - target_membership.joined_turn <= 3:
        turns_remaining = 4 - (current_turn - target_membership.joined_turn)
        return False, f"{target_character.name} joined the faction too recently. Wait {turns_remaining} more turn(s)."

    # Check no pending kick orders for this target
    existing_orders = await Order.fetch_by_type_and_target(
        conn, guild_id, OrderType.KICK_FROM_FACTION.value, OrderStatus.PENDING.value, target_character.id
    )

    if existing_orders:
        return False, f"There is already a pending kick order for {target_character.name}."

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.KICK_FROM_FACTION.value,
        unit_ids=[],
        character_id=submitting_character.id,
        turn_number=current_turn,
        phase=ORDER_PHASE_MAP[OrderType.KICK_FROM_FACTION].value,
        priority=ORDER_PRIORITY_MAP[OrderType.KICK_FROM_FACTION],
        status=OrderStatus.PENDING.value,
        order_data={
            'target_character_id': target_character.id,
            'target_character_name': target_character.name,
            'faction_id': faction.id
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    return True, f"Order submitted: {target_character.name} will be kicked from {faction.name} next turn (Order #{order_id})."


async def submit_transit_order(
    conn: asyncpg.Connection,
    unit_ids: List[str],
    path: List[int],
    guild_id: int,
    character_id: int
) -> Tuple[bool, str]:
    """
    Submit a transit order for one or more units.

    Args:
        conn: Database connection
        unit_ids: List of unit IDs (user-facing)
        path: Full path (list of territory IDs)
        guild_id: Guild ID
        character_id: Character submitting the order (for validation)

    Returns:
        (success, message)
    """
    # Validate path is non-empty
    if not path or len(path) < 2:
        return False, "Path must include at least a starting and destination territory."

    # Fetch all units
    units = []
    for unit_id in unit_ids:
        unit = await Unit.fetch_by_unit_id(conn, unit_id, guild_id)
        if not unit:
            return False, f"Unit '{unit_id}' not found."
        units.append(unit)

    if not units:
        return False, "No units specified."

    # Validate all units are land units (not naval)
    naval_units = [u.unit_id for u in units if u.is_naval]
    if naval_units:
        return False, f"Naval units cannot use transit orders: {', '.join(naval_units)}"

    # Validate authorization for all units
    unauthorized_units = []
    for unit in units:
        authorized, _ = await check_unit_order_authorization(conn, unit, character_id, guild_id)
        if not authorized:
            unauthorized_units.append(unit.unit_id)

    if unauthorized_units:
        return False, f"You are not authorized to issue orders for these units: {', '.join(unauthorized_units)}. Ask a GM for clarification."

    # Validate all units in same starting territory
    starting_territories = set(u.current_territory_id for u in units)
    if len(starting_territories) > 1:
        return False, f"All units must be in the same territory. Units are in: {starting_territories}"

    starting_territory_id = units[0].current_territory_id

    # Validate path starts with current territory
    if path[0] != starting_territory_id:
        return False, f"Path must start with the units' current territory ({starting_territory_id})."

    # Validate path using validate_path helper
    valid, error_msg = await validate_path(conn, path, guild_id)
    if not valid:
        return False, error_msg

    # Check no units have pending/ongoing orders
    unit_internal_ids = [u.id for u in units]
    existing_orders = await Order.fetch_by_units(
        conn, unit_internal_ids, [OrderStatus.PENDING.value, OrderStatus.ONGOING.value], guild_id
    )
    if existing_orders:
        conflicting_units = set()
        for order in existing_orders:
            conflicting_units.update([u.unit_id for u in units if u.id in order.unit_ids])
        return False, f"These units already have pending orders: {', '.join(conflicting_units)}"

    # Find slowest unit (minimum movement stat)
    slowest_movement = min(u.movement for u in units)
    slowest_unit = next(u for u in units if u.movement == slowest_movement)

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Determine if order will be ongoing
    path_length = len(path) - 1  # Number of steps
    will_be_ongoing = path_length > slowest_movement

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.UNIT.value,
        unit_ids=unit_internal_ids,
        character_id=character_id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={'path': path, 'path_index': 0},
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    unit_list = ', '.join([u.unit_id for u in units])
    ongoing_note = " (will take multiple turns)" if will_be_ongoing else ""
    return True, f"Transit order submitted for {unit_list} -> Territory {path[-1]} (Order #{order_id}){ongoing_note}. Slowest unit: {slowest_unit.unit_id} (movement={slowest_movement})."


# Valid unit action types
VALID_LAND_ACTIONS = ['transit', 'transport', 'patrol', 'raid', 'capture', 'siege', 'aerial_convoy', 'aerial_scout']
VALID_NAVAL_ACTIONS = ['naval_transit', 'naval_convoy', 'naval_patrol', 'naval_transport']
VALID_UNIT_ACTIONS = VALID_LAND_ACTIONS + VALID_NAVAL_ACTIONS

# Terrain types considered water (for naval units)
WATER_TERRAIN_TYPES = ['ocean', 'lake', 'sea', 'water']


async def validate_transport_path(
    conn: asyncpg.Connection,
    path: List[str],
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    Validate and extract transport path data for land transport orders.

    Transport paths must follow the format: [land1, water1, water2, ..., land2]
    - Must start with a land territory (coast_territory)
    - Must have a contiguous water section (water_path)
    - Must end with a land territory (disembark_territory)

    Args:
        conn: Database connection
        path: Full path including land start/end and water portion
        guild_id: Guild ID

    Returns:
        (success, error_message, transport_data)
        - transport_data contains: water_path, coast_territory, disembark_territory
    """
    if len(path) < 3:
        return False, "Transport path must have at least 3 territories (land-water-land).", None

    # Classify each territory as land or water
    territory_types = []
    for territory_id in path:
        territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
        if not territory:
            return False, f"Territory '{territory_id}' not found.", None
        is_water = territory.terrain_type.lower() in WATER_TERRAIN_TYPES
        territory_types.append((territory_id, is_water))

    # Path must start with land
    if territory_types[0][1]:  # First territory is water
        return False, f"Transport path must start with a land territory, but '{path[0]}' is water.", None

    # Path must end with land
    if territory_types[-1][1]:  # Last territory is water
        return False, f"Transport path must end with a land territory, but '{path[-1]}' is water.", None

    # Find the water section - it must be contiguous
    water_start = None
    water_end = None
    in_water = False

    for i, (territory_id, is_water) in enumerate(territory_types):
        if is_water and not in_water:
            # Started water section
            water_start = i
            in_water = True
        elif not is_water and in_water:
            # Ended water section
            water_end = i
            in_water = False
            break

    # If we're still in water at the end, something is wrong (but we already checked end is land)
    # This shouldn't happen given the end-is-land check above
    if in_water:
        water_end = len(territory_types)

    # Validate water section exists
    if water_start is None:
        return False, "Transport path must include at least one water territory.", None

    # Extract the water path
    water_path = [t[0] for t in territory_types[water_start:water_end]]

    # Check there's no more water after the first water section ends
    for i in range(water_end, len(territory_types)):
        if territory_types[i][1]:
            return False, f"Transport path water section must be contiguous. Found land at '{territory_types[water_end-1][0]}' followed by water at '{territory_types[i][0]}'.", None

    # The coast territory is the last land territory before water
    coast_territory = territory_types[water_start - 1][0]

    # The disembark territory is the first land territory after water
    disembark_territory = territory_types[water_end][0]

    transport_data = {
        'water_path': water_path,
        'coast_territory': coast_territory,
        'disembark_territory': disembark_territory
    }

    return True, "", transport_data


async def submit_unit_order(
    conn: asyncpg.Connection,
    unit_ids: List[str],
    action: str,
    path: List[str],
    guild_id: int,
    character_id: int,
    speed: Optional[int] = None,
    override: bool = False
) -> Tuple[bool, str, Optional[dict]]:
    """
    Submit a unit order for one or more units.

    Args:
        conn: Database connection
        unit_ids: List of unit IDs (user-facing)
        action: Action type (one of VALID_UNIT_ACTIONS)
        path: Full path (list of territory IDs as strings)
        guild_id: Guild ID
        character_id: Character submitting the order
        speed: Speed parameter for patrol orders only
        override: If True, override existing orders (cancel them and create new)

    Returns:
        (success, message, extra_data)
        - extra_data may contain {'confirmation_needed': True, 'existing_orders': [...]} if orders exist
    """
    # Normalize action to lowercase
    action = action.lower().strip()

    # Validate action is one of the valid types
    if action not in VALID_UNIT_ACTIONS:
        return False, f"Invalid action '{action}'. Valid actions: {', '.join(VALID_UNIT_ACTIONS)}", None

    # Validate path is non-empty
    if not path or len(path) < 2:
        return False, "Path must include at least a starting and destination territory.", None

    # Fetch all units
    units = []
    for unit_id in unit_ids:
        unit = await Unit.fetch_by_unit_id(conn, unit_id, guild_id)
        if not unit:
            return False, f"Unit '{unit_id}' not found.", None
        units.append(unit)

    if not units:
        return False, "No units specified.", None

    # Validate land/naval action matches unit type
    is_naval_action = action in VALID_NAVAL_ACTIONS
    for unit in units:
        if is_naval_action and not unit.is_naval:
            return False, f"Unit '{unit.unit_id}' is a land unit but you specified a naval action '{action}'.", None
        if not is_naval_action and unit.is_naval:
            return False, f"Unit '{unit.unit_id}' is a naval unit but you specified a land action '{action}'.", None

    # Infiltrator, aerial, and aerial-transport units cannot perform patrol, capture, or siege actions
    RESTRICTED_ACTIONS = ['patrol', 'capture', 'siege']
    if action in RESTRICTED_ACTIONS:
        for unit in units:
            if unit.keywords:
                keywords_lower = [k.lower() for k in unit.keywords]
                if 'infiltrator' in keywords_lower or 'aerial' in keywords_lower or 'aerial-transport' in keywords_lower:
                    return False, f"Unit '{unit.unit_id}' has infiltrator/aerial/aerial-transport keyword and cannot perform '{action}' action.", None

    # Validate authorization for all units
    unauthorized_units = []
    for unit in units:
        authorized, _ = await check_unit_order_authorization(conn, unit, character_id, guild_id)
        if not authorized:
            unauthorized_units.append(unit.unit_id)

    if unauthorized_units:
        return False, f"You are not authorized to issue orders for these units: {', '.join(unauthorized_units)}. Ask a GM for clarification.", None

    # Validate all units in same starting territory
    starting_territories = set(u.current_territory_id for u in units)
    if len(starting_territories) > 1:
        return False, f"All units must be in the same territory. Units are in: {starting_territories}", None

    starting_territory_id = units[0].current_territory_id

    # Validate path starts with current territory
    if path[0] != starting_territory_id:
        return False, f"Path must start with the units' current territory ({starting_territory_id}).", None

    # Patrol paths must contain at least two different territories (check before adjacency)
    if action in ['patrol', 'naval_patrol']:
        unique_territories = set(path)
        if len(unique_territories) < 2:
            return False, "Patrol path must contain at least two different territories.", None

    # Validate path using validate_path_with_details helper
    valid, error_msg = await validate_path_with_details(conn, path, guild_id)
    if not valid:
        return False, error_msg, None

    # Validate terrain for naval actions (all territories must be water)
    if is_naval_action:
        for territory_id in path:
            territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
            if territory and territory.terrain_type.lower() not in WATER_TERRAIN_TYPES:
                return False, f"Naval units cannot traverse land territory '{territory_id}' (terrain: {territory.terrain_type}).", None

    # Validate terrain for land actions (no water unless all infiltrators/aerial/aerial-transport)
    if not is_naval_action and action != 'transport':
        all_can_traverse_water = all(
            unit.keywords and any(k.lower() in ('infiltrator', 'aerial', 'aerial-transport') for k in unit.keywords)
            for unit in units
        )
        if not all_can_traverse_water:
            for territory_id in path:
                territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
                if territory and territory.terrain_type.lower() in WATER_TERRAIN_TYPES:
                    return False, f"Land units cannot traverse water territory '{territory_id}'. Use transport orders for water crossing.", None

    # Action-specific validation: Siege requires city terrain at path end
    if action == 'siege':
        final_territory = await Territory.fetch_by_territory_id(conn, path[-1], guild_id)
        if final_territory and final_territory.terrain_type.lower() != 'city':
            return False, f"Siege action requires a city at the destination. Territory '{path[-1]}' is '{final_territory.terrain_type}'.", None

    # Action-specific validation: Land transport path validation
    transport_data = None
    if action == 'transport':
        valid, error_msg, transport_data = await validate_transport_path(conn, path, guild_id)
        if not valid:
            return False, error_msg, None

    # Action-specific validation: Aerial convoy requires aerial-transport keyword
    if action == 'aerial_convoy':
        # All units must have 'aerial-transport' keyword
        for unit in units:
            if not unit.keywords or 'aerial-transport' not in unit.keywords:
                return False, f"Unit '{unit.unit_id}' requires 'aerial-transport' keyword for aerial_convoy.", None

        # Get the character's represented faction to check enemy territories
        character = await Character.fetch_by_id(conn, character_id)
        if character and character.represented_faction_id:
            # Get enemy factions (factions at war)
            from handlers.encirclement_handlers import get_enemy_faction_ids, get_territory_controller_faction
            enemy_ids = await get_enemy_faction_ids(conn, character.represented_faction_id, guild_id)

            # Check current territory is not enemy-controlled
            current_territory = await Territory.fetch_by_territory_id(conn, starting_territory_id, guild_id)
            if current_territory:
                territory_controller = await get_territory_controller_faction(conn, current_territory, guild_id)
                if territory_controller and territory_controller in enemy_ids:
                    return False, "Aerial convoy cannot be used in enemy-controlled territory.", None

    # Action-specific validation: Aerial scout requires aerial or aerial-transport keyword
    if action == 'aerial_scout':
        # All units must have 'aerial' or 'aerial-transport' keyword
        for unit in units:
            if not unit.keywords or not any(k.lower() in ('aerial', 'aerial-transport') for k in unit.keywords):
                return False, f"Unit '{unit.unit_id}' requires 'aerial' or 'aerial-transport' keyword for aerial_scout.", None

        # Path length cannot exceed movement stat (path includes current position)
        slowest_movement = min(u.movement for u in units)
        if len(path) > slowest_movement:
            return False, f"Aerial scout path ({len(path)} territories) exceeds movement stat ({slowest_movement}).", None

    # Validate speed parameter for patrol actions
    if action in ['patrol', 'naval_patrol']:
        if speed is not None and speed < 1:
            return False, "Speed must be at least 1 for patrol orders.", None
    elif speed is not None:
        return False, "Speed parameter is only valid for patrol actions.", None

    # Check existing orders for all units
    unit_internal_ids = [u.id for u in units]
    existing_orders = await Order.fetch_by_units(
        conn, unit_internal_ids, [OrderStatus.PENDING.value, OrderStatus.ONGOING.value], guild_id
    )

    if existing_orders and not override:
        # Collect details about existing orders
        existing_order_details = []
        for order in existing_orders:
            # Find which units in our list are affected
            affected_unit_ids = [u.unit_id for u in units if u.id in order.unit_ids]
            existing_order_details.append({
                'order_id': order.order_id,
                'order_type': order.order_type,
                'status': order.status,
                'affected_units': affected_unit_ids,
                'action': order.order_data.get('action', 'unknown')
            })

        conflicting_units = set()
        for order in existing_orders:
            conflicting_units.update([u.unit_id for u in units if u.id in order.unit_ids])

        return False, f"These units already have pending orders: {', '.join(conflicting_units)}. Use confirmation to override.", {
            'confirmation_needed': True,
            'existing_orders': existing_order_details
        }

    # If override=True and there are existing orders, cancel them
    if existing_orders and override:
        for existing_order in existing_orders:
            existing_order.status = OrderStatus.CANCELLED.value
            existing_order.updated_at = datetime.now()
            existing_order.result_data = {'cancelled_reason': 'overridden_by_new_order'}
            await existing_order.upsert(conn)

    # Find slowest unit (minimum movement stat)
    slowest_movement = min(u.movement for u in units)
    slowest_unit = next(u for u in units if u.movement == slowest_movement)

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Determine if order will be ongoing
    path_length = len(path) - 1  # Number of steps
    will_be_ongoing = path_length > slowest_movement

    # Build order_data
    order_data = {
        'action': action,
        'path': path,
        'path_index': 0
    }
    if speed is not None:
        order_data['speed'] = speed

    # Add transport-specific data for land transport orders
    if transport_data is not None:
        order_data['water_path'] = transport_data['water_path']
        order_data['coast_territory'] = transport_data['coast_territory']
        order_data['disembark_territory'] = transport_data['disembark_territory']

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.UNIT.value,
        unit_ids=unit_internal_ids,
        character_id=character_id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data=order_data,
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    unit_list = ', '.join([u.unit_id for u in units])
    ongoing_note = " (will take multiple turns)" if will_be_ongoing else ""
    override_note = " (previous orders cancelled)" if existing_orders and override else ""
    speed_note = f", speed={speed}" if speed is not None else ""

    return True, f"Unit order submitted: {action} for {unit_list} -> Territory {path[-1]} (Order #{order_id}){ongoing_note}{override_note}. Slowest unit: {slowest_unit.unit_id} (movement={slowest_movement}{speed_note}).", None


async def validate_path_with_details(
    conn: asyncpg.Connection,
    path: List[str],
    guild_id: int
) -> Tuple[bool, str]:
    """
    Validate a path is valid (territories exist and are adjacent).
    Returns detailed error messages for non-adjacent territories.

    Args:
        conn: Database connection
        path: List of territory IDs (as strings)
        guild_id: Guild ID

    Returns:
        (success, error_message)
    """
    if not path:
        return False, "Path is empty."

    # Check all territories exist
    for territory_id in path:
        territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
        if not territory:
            return False, f"Territory '{territory_id}' not found."

    # Check each consecutive pair is adjacent
    for i in range(len(path) - 1):
        territory_a = path[i]
        territory_b = path[i + 1]

        # Check adjacency (order doesn't matter due to canonical ordering in DB)
        is_adjacent = await conn.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM TerritoryAdjacency
                WHERE ((territory_a_id = $1 AND territory_b_id = $2)
                   OR (territory_a_id = $2 AND territory_b_id = $1))
                AND guild_id = $3
            );
        """, territory_a, territory_b, guild_id)

        if not is_adjacent:
            return False, f"Territories '{territory_a}' and '{territory_b}' are not adjacent."

    return True, ""


# Minimum turns before cancellation for specific order types
# Orders not in this dict default to 0 (immediate cancellation allowed)
CANCEL_MINIMUM_TURNS = {
    OrderType.ASSIGN_VICTORY_POINTS.value: 3,
}


async def cancel_order(
    conn: asyncpg.Connection,
    order_id: str,
    guild_id: int,
    character_id: int
) -> Tuple[bool, str]:
    """
    Cancel a pending or ongoing order.

    Some order types have minimum commitment periods before cancellation.

    Args:
        conn: Database connection
        order_id: Order ID to cancel
        guild_id: Guild ID
        character_id: Character requesting cancellation (for validation)

    Returns:
        (success, message)
    """
    # Fetch order
    order = await Order.fetch_by_order_id(conn, order_id, guild_id)
    if not order:
        return False, f"Order '{order_id}' not found."

    # Validate order belongs to character
    if order.character_id != character_id:
        return False, f"Order '{order_id}' does not belong to you."

    # Check status - allow both PENDING and ONGOING
    if order.status not in [OrderStatus.PENDING.value, OrderStatus.ONGOING.value]:
        return False, f"Cannot cancel order '{order_id}' with status '{order.status}'."

    # Get current turn (needed for minimum commitment check and TurnLog)
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Check minimum commitment for ONGOING orders
    # Relaxed by one turn since cancellation takes effect at start of next turn
    if order.status == OrderStatus.ONGOING.value:
        min_turns = CANCEL_MINIMUM_TURNS.get(order.order_type, 0)
        if min_turns > 0:
            # Calculate turns active (including next turn when cancellation takes effect)
            turns_active = current_turn - order.turn_number + 1
            if turns_active < min_turns:
                turns_remaining = min_turns - turns_active
                return False, f"Cannot cancel '{order_id}' yet. Minimum commitment: {min_turns} turns. {turns_remaining} turn(s) remaining."

    # Update status to CANCELLED
    order.status = OrderStatus.CANCELLED.value
    order.updated_at = datetime.now()
    await order.upsert(conn)

    # Create TurnLog entry for VP assignment cancellations
    if order.order_type == OrderType.ASSIGN_VICTORY_POINTS.value:
        # Get character and faction info for the event
        character = await Character.fetch_by_id(conn, character_id)
        target_faction_id = order.order_data.get('target_faction_id')
        target_faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id) if target_faction_id else None

        # Build affected character IDs: submitter + faction leader + all faction members
        affected_character_ids = [character_id]
        if target_faction:
            if target_faction.leader_character_id and target_faction.leader_character_id not in affected_character_ids:
                affected_character_ids.append(target_faction.leader_character_id)
            faction_members = await FactionMember.fetch_by_faction(conn, target_faction.id, guild_id)
            for member in faction_members:
                if member.character_id not in affected_character_ids:
                    affected_character_ids.append(member.character_id)

        # Create and save the TurnLog entry (will appear at beginning of next turn's report)
        turn_log = TurnLog(
            turn_number=current_turn + 1,
            phase=TurnPhase.BEGINNING.value,
            event_type='VP_ASSIGNMENT_CANCELLED',
            entity_type='character',
            entity_id=character_id,
            event_data={
                'character_name': character.name if character else 'Unknown',
                'target_faction_id': target_faction_id,
                'target_faction_name': target_faction.name if target_faction else 'Unknown',
                'order_id': order_id,
                'affected_character_ids': affected_character_ids
            },
            guild_id=guild_id
        )
        await turn_log.insert(conn)

    return True, f"Order '{order_id}' has been cancelled."


async def view_pending_orders(
    conn: asyncpg.Connection,
    character_identifier: str,
    guild_id: int
) -> Tuple[bool, str, Optional[List[dict]]]:
    """
    View all pending/ongoing orders for a character and their units.

    Args:
        conn: Database connection
        character_identifier: Character identifier
        guild_id: Guild ID

    Returns:
        (success, message, orders_list)
    """
    # Fetch character
    character = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not character:
        return False, f"Character '{character_identifier}' not found.", None

    # Fetch pending/ongoing orders for character
    orders = await Order.fetch_by_character(conn, character.id, guild_id)

    if not orders:
        return True, f"No pending orders for {character.name}.", []

    # Convert to dict format for display
    orders_list = []
    for order in orders:
        order_dict = {
            'order_id': order.order_id,
            'order_type': order.order_type,
            'status': order.status,
            'turn_number': order.turn_number,
            'order_data': order.order_data
        }

        # Add unit info for transit orders
        if order.unit_ids:
            units = []
            for unit_id in order.unit_ids:
                unit = await Unit.fetch_by_id(conn, unit_id)
                if unit:
                    units.append(unit.unit_id)
            order_dict['units'] = units

        orders_list.append(order_dict)

    return True, f"Found {len(orders)} pending order(s) for {character.name}.", orders_list


async def submit_resource_transfer_order(
    conn: asyncpg.Connection,
    from_character: Character,
    to_character_identifier: str,
    resources: dict,
    is_ongoing: bool,
    term: Optional[int],
    guild_id: int
) -> Tuple[bool, str]:
    """
    Submit a resource transfer order (one-time or ongoing).

    Args:
        conn: Database connection
        from_character: Character sending resources
        to_character_identifier: Character identifier receiving resources
        resources: Dict with keys: ore, lumber, coal, rations, cloth
        is_ongoing: True for ongoing transfer, False for one-time
        term: Number of turns (ongoing only), None = indefinite
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate recipient character exists
    to_character = await Character.fetch_by_identifier(conn, to_character_identifier, guild_id)
    if not to_character:
        return False, f"Character '{to_character_identifier}' not found."

    # Cannot transfer to self
    if from_character.id == to_character.id:
        return False, "Cannot transfer resources to yourself."

    # Validate resources dict
    resource_types = ['ore', 'lumber', 'coal', 'rations', 'cloth', 'platinum']
    for resource_type in resource_types:
        if resource_type not in resources:
            resources[resource_type] = 0
        if resources[resource_type] < 0:
            return False, f"Resource amounts cannot be negative."

    # Check at least one resource > 0
    total_resources = sum(resources.values())
    if total_resources <= 0:
        return False, "Must transfer at least one resource."

    # Validate term if ongoing
    if is_ongoing and term is not None:
        if term < 2:
            return False, "Term must be at least 2 turns if specified."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order data
    order_data = {
        'to_character_id': to_character.id,
        'ore': resources['ore'],
        'lumber': resources['lumber'],
        'coal': resources['coal'],
        'rations': resources['rations'],
        'cloth': resources['cloth'],
        'platinum': resources['platinum']
    }

    # Add ongoing-specific fields
    if is_ongoing:
        order_data['term'] = term
        order_data['turns_executed'] = 0

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.RESOURCE_TRANSFER.value,
        unit_ids=[],
        character_id=from_character.id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.RESOURCE_TRANSFER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.RESOURCE_TRANSFER],
        status=OrderStatus.ONGOING.value if is_ongoing else OrderStatus.PENDING.value,
        order_data=order_data,
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    # Format response message
    resource_strs = []
    for resource_type in resource_types:
        if resources[resource_type] > 0:
            resource_strs.append(f"{resources[resource_type]} {resource_type}")

    transfer_type = "Ongoing" if is_ongoing else "One-time"
    term_str = f" (for {term} turns)" if is_ongoing and term else " (indefinite)" if is_ongoing else ""

    return True, f"{transfer_type} transfer order submitted: {from_character.name} → {to_character.name}: {', '.join(resource_strs)}{term_str} (Order #{order_id})."


async def submit_cancel_transfer_order(
    conn: asyncpg.Connection,
    character: Character,
    original_order_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Submit an order to cancel an ongoing resource transfer.

    Args:
        conn: Database connection
        character: Character submitting the cancel order
        original_order_id: The order ID to cancel
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate original order exists
    original_order = await Order.fetch_by_order_id(conn, original_order_id, guild_id)
    if not original_order:
        return False, f"Order '{original_order_id}' not found."

    # Validate it's a RESOURCE_TRANSFER order
    if original_order.order_type != OrderType.RESOURCE_TRANSFER.value:
        return False, f"Order '{original_order_id}' is not a RESOURCE_TRANSFER order."

    # Validate it has ONGOING status
    if original_order.status != OrderStatus.ONGOING.value:
        return False, f"Order '{original_order_id}' is not ONGOING. Only ongoing transfers can be cancelled."

    # Validate it belongs to the character
    if original_order.character_id != character.id:
        return False, f"Order '{original_order_id}' does not belong to you."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Validate at least 1 turn has passed since submission
    original_submitted_at = original_order.submitted_at
    original_turn = original_order.turn_number

    # Check if the original order was submitted in a previous turn
    if original_turn >= current_turn:
        return False, f"Cannot cancel order '{original_order_id}' on the same turn it was submitted. Wait until next turn."

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create cancel order
    order = Order(
        order_id=order_id,
        order_type=OrderType.CANCEL_TRANSFER.value,
        unit_ids=[],
        character_id=character.id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.CANCEL_TRANSFER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.CANCEL_TRANSFER],
        status=OrderStatus.PENDING.value,
        order_data={'original_order_id': original_order_id},
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    return True, f"Cancel transfer order submitted for '{original_order_id}' (Order #{order_id}). Cancellation will be processed next turn."


async def submit_assign_commander_order(
    conn: asyncpg.Connection,
    unit_id: str,
    new_commander_identifier: str,
    guild_id: int,
    submitting_character_id: int,
    confirmed: bool = False
) -> Tuple[bool, str, bool]:
    """
    Submit an order to assign a new commander to a unit.

    For character-owned units: only the owner can assign a commander.
    For faction-owned units: requires COMMAND permission.

    Args:
        conn: Database connection
        unit_id: The unit ID to reassign
        new_commander_identifier: Character identifier for new commander
        guild_id: Guild ID
        submitting_character_id: ID of character submitting
        confirmed: If True, skip faction mismatch check (user already confirmed)

    Returns:
        (success, message, needs_confirmation)
        - needs_confirmation=True means faction mismatch detected, show confirmation dialog
    """
    # Fetch unit
    unit = await Unit.fetch_by_unit_id(conn, unit_id, guild_id)
    if not unit:
        return False, f"Unit '{unit_id}' not found.", False

    # Validate authorization - for assign commander, we check ownership/permission
    # (not commander status, since we're changing the commander)
    if unit.owner_character_id is not None:
        # Character-owned unit: must be owner
        if unit.owner_character_id != submitting_character_id:
            return False, "Only the unit owner can assign a commander.", False
    elif unit.owner_faction_id is not None:
        # Faction-owned unit: must have COMMAND permission
        has_permission = await FactionPermission.has_permission(
            conn, unit.owner_faction_id, submitting_character_id, "COMMAND", guild_id
        )
        if not has_permission:
            return False, "You are not authorized to assign commanders for this faction unit. Ask a GM for clarification.", False
    else:
        return False, "Unit has no valid owner.", False

    # Fetch new commander
    new_commander = await Character.fetch_by_identifier(conn, new_commander_identifier, guild_id)
    if not new_commander:
        return False, f"Character '{new_commander_identifier}' not found.", False

    # Validate new commander is different from current
    if unit.commander_character_id == new_commander.id:
        return False, f"{new_commander.name} is already the commander of this unit.", False

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Validate 2-turn cooldown
    if unit.commander_assigned_turn is not None:
        turns_since_assignment = current_turn - unit.commander_assigned_turn
        if turns_since_assignment < 2:
            turns_remaining = 2 - turns_since_assignment
            return False, f"Cannot change commander yet. {turns_remaining} more turn(s) required before reassignment.", False

    # Check faction membership - warn if new commander is in a different faction
    # For character-owned units: compare owner's faction with commander's faction
    # For faction-owned units: compare owning faction with commander's faction
    if unit.owner_character_id is not None:
        owner_membership = await FactionMember.fetch_by_character(conn, unit.owner_character_id, guild_id)
        owner_faction_id = owner_membership.faction_id if owner_membership else None
    else:
        # Faction-owned unit - the owning faction IS the relevant faction
        owner_faction_id = unit.owner_faction_id

    commander_membership = await FactionMember.fetch_by_character(conn, new_commander.id, guild_id)
    commander_faction_id = commander_membership.faction_id if commander_membership else None

    if owner_faction_id != commander_faction_id and not confirmed:
        # Faction mismatch - need confirmation
        if unit.owner_character_id is not None:
            owner = await Character.fetch_by_id(conn, unit.owner_character_id)
            owner_name = owner.name if owner else "Unknown"

            if owner_faction_id is None and commander_faction_id is None:
                faction_msg = "Neither you nor the new commander are in a faction."
            elif owner_faction_id is None:
                faction_msg = f"You are not in a faction, but {new_commander.name} is."
            elif commander_faction_id is None:
                faction_msg = f"{new_commander.name} is not in a faction, but you are."
            else:
                faction_msg = f"You and {new_commander.name} are in different factions."
        else:
            # Faction-owned unit
            owning_faction = await Faction.fetch_by_id(conn, unit.owner_faction_id)
            faction_name = owning_faction.name if owning_faction else "the faction"

            if commander_faction_id is None:
                faction_msg = f"{new_commander.name} is not in any faction, but this unit belongs to {faction_name}."
            else:
                faction_msg = f"{new_commander.name} is not a member of {faction_name}."

        return False, f"Warning: {faction_msg} Once assigned, the commander cannot be changed for 2 turns. Do you want to proceed?", True

    # Check for existing pending ASSIGN_COMMANDER orders for this unit
    existing_orders = await Order.fetch_by_units(
        conn, [unit.id], [OrderStatus.PENDING.value], guild_id
    )
    for existing_order in existing_orders:
        if existing_order.order_type == OrderType.ASSIGN_COMMANDER.value:
            return False, f"There is already a pending commander assignment order for this unit.", False

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.ASSIGN_COMMANDER.value,
        unit_ids=[unit.id],
        character_id=submitting_character_id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.ASSIGN_COMMANDER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.ASSIGN_COMMANDER],
        status=OrderStatus.PENDING.value,
        order_data={
            'unit_id': unit_id,
            'new_commander_id': new_commander.id,
            'new_commander_name': new_commander.name
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    return True, f"Order submitted: {new_commander.name} will be assigned as commander of {unit.name or unit.unit_id} next turn (Order #{order_id}).", False


async def submit_assign_victory_points_order(
    conn: asyncpg.Connection,
    character: Character,
    target_faction_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Submit an order to assign victory points to a faction.

    Creates a PENDING order that will become ONGOING after first turn.
    If the character already has an active VP assignment, it will be superceded.

    Args:
        conn: Database connection
        character: Character submitting the order
        target_faction_id: Faction ID to receive VPs
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate target faction exists
    target_faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
    if not target_faction:
        return False, f"Faction '{target_faction_id}' not found."

    # Check if character already has an active VP assignment order - supercede it
    existing_orders = await Order.fetch_by_character_and_type(
        conn, character.id, guild_id,
        OrderType.ASSIGN_VICTORY_POINTS.value, OrderStatus.ONGOING.value
    )
    pending_orders = await Order.fetch_by_character_and_type(
        conn, character.id, guild_id,
        OrderType.ASSIGN_VICTORY_POINTS.value, OrderStatus.PENDING.value
    )

    superceded_order_id = None
    for old_order in existing_orders + pending_orders:
        old_order.status = OrderStatus.CANCELLED.value
        old_order.updated_at = datetime.now()
        old_order.result_data = {'superceded_by': 'new_order'}
        await old_order.upsert(conn)
        superceded_order_id = old_order.order_id

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create PENDING order (will become ONGOING after first turn)
    order = Order(
        order_id=order_id,
        order_type=OrderType.ASSIGN_VICTORY_POINTS.value,
        unit_ids=[],
        character_id=character.id,
        turn_number=current_turn + 1,
        phase=ORDER_PHASE_MAP[OrderType.ASSIGN_VICTORY_POINTS].value,
        priority=ORDER_PRIORITY_MAP[OrderType.ASSIGN_VICTORY_POINTS],
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': target_faction_id
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    supercede_note = f" (superceded previous order {superceded_order_id})" if superceded_order_id else ""
    return True, f"VP assignment order submitted: Your victory points will be assigned to {target_faction.name} (Order #{order_id}){supercede_note}. This order will remain active until cancelled."


async def submit_make_alliance_order(
    conn: asyncpg.Connection,
    submitting_character: Character,
    target_faction_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Submit an order for a faction leader to propose an alliance with another faction.

    Requires BOTH faction leaders to submit orders for the alliance to activate.

    Args:
        conn: Database connection
        submitting_character: Character submitting the order (must be faction leader)
        target_faction_id: Faction ID to ally with
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Check submitter is in a faction
    faction_member = await FactionMember.fetch_by_character(conn, submitting_character.id, guild_id)
    if not faction_member:
        return False, "You are not a member of any faction."

    # Get submitter's faction
    submitting_faction = await Faction.fetch_by_id(conn, faction_member.faction_id)
    if not submitting_faction:
        return False, "Your faction could not be found."

    # Check submitter is faction leader
    if submitting_faction.leader_character_id != submitting_character.id:
        return False, f"Only the leader of {submitting_faction.name} can propose alliances."

    # Validate target faction exists
    target_faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
    if not target_faction:
        return False, f"Faction '{target_faction_id}' not found."

    # Can't ally with self
    if submitting_faction.id == target_faction.id:
        return False, "Cannot propose an alliance with your own faction."

    # Check for existing active alliance
    existing_alliance = await Alliance.fetch_by_factions(
        conn, submitting_faction.id, target_faction.id, guild_id
    )
    if existing_alliance and existing_alliance.status == 'ACTIVE':
        return False, f"An alliance already exists between {submitting_faction.name} and {target_faction.name}."

    # Check for existing pending order from this faction
    existing_orders = await Order.fetch_by_character_and_type(
        conn, submitting_character.id, guild_id,
        OrderType.MAKE_ALLIANCE.value, OrderStatus.PENDING.value
    )
    # Filter to orders targeting the same faction
    for existing in existing_orders:
        if existing.order_data.get('target_faction_id') == target_faction_id:
            return False, f"You already have a pending alliance order for {target_faction.name}."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.MAKE_ALLIANCE.value,
        unit_ids=[],
        character_id=submitting_character.id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.MAKE_ALLIANCE].value,
        priority=ORDER_PRIORITY_MAP[OrderType.MAKE_ALLIANCE],
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': target_faction_id,
            'target_faction_name': target_faction.name,
            'submitting_faction_id': submitting_faction.faction_id,
            'submitting_faction_name': submitting_faction.name
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    # Check if there's already a pending alliance from the other faction
    if existing_alliance:
        # Determine who's waiting
        if existing_alliance.initiated_by_faction_id == target_faction.id:
            return True, f"Alliance order submitted (Order #{order_id}). {target_faction.name} has already proposed an alliance - it will be activated next turn!"
        else:
            return True, f"Alliance order submitted (Order #{order_id}). You have already proposed this alliance - waiting for {target_faction.name} to accept."

    return True, f"Alliance order submitted: {submitting_faction.name} proposes alliance with {target_faction.name} (Order #{order_id}). The alliance will be activated when {target_faction.name}'s leader also submits an alliance order."


async def submit_dissolve_alliance_order(
    conn: asyncpg.Connection,
    submitting_character: Character,
    target_faction_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Submit an order for a faction leader to dissolve an alliance with another faction.

    Constraints:
    - Cannot be issued within the first 4 turns of the game
    - Cannot be issued within 4 turns of the alliance being activated

    Args:
        conn: Database connection
        submitting_character: Character submitting the order (must be faction leader)
        target_faction_id: Faction ID of the alliance to dissolve
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Check submitter is in a faction
    faction_member = await FactionMember.fetch_by_character(conn, submitting_character.id, guild_id)
    if not faction_member:
        return False, "You are not a member of any faction."

    # Get submitter's faction
    submitting_faction = await Faction.fetch_by_id(conn, faction_member.faction_id)
    if not submitting_faction:
        return False, "Your faction could not be found."

    # Check submitter is faction leader
    if submitting_faction.leader_character_id != submitting_character.id:
        return False, f"Only the leader of {submitting_faction.name} can dissolve alliances."

    # Validate target faction exists
    target_faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
    if not target_faction:
        return False, f"Faction '{target_faction_id}' not found."

    # Can't dissolve alliance with self
    if submitting_faction.id == target_faction.id:
        return False, "Cannot dissolve an alliance with your own faction."

    # Check for existing active alliance
    existing_alliance = await Alliance.fetch_by_factions(
        conn, submitting_faction.id, target_faction.id, guild_id
    )
    if not existing_alliance or existing_alliance.status != 'ACTIVE':
        return False, f"No active alliance exists between {submitting_faction.name} and {target_faction.name}."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Check constraint: Cannot dissolve within first 4 turns of the game
    if current_turn < 4:
        turns_remaining = 4 - current_turn
        return False, f"Cannot dissolve alliances within the first 4 turns of the game. {turns_remaining} turn(s) remaining."

    # Check constraint: Cannot dissolve within 4 turns of alliance being activated
    if existing_alliance.activated_turn is not None:
        turns_since_activation = current_turn - existing_alliance.activated_turn
        if turns_since_activation < 4:
            turns_remaining = 4 - turns_since_activation
            return False, f"Cannot dissolve this alliance yet. The alliance must be at least 4 turns old. {turns_remaining} turn(s) remaining."

    # Check for existing pending order from this character for the same target
    existing_orders = await Order.fetch_by_character_and_type(
        conn, submitting_character.id, guild_id,
        OrderType.DISSOLVE_ALLIANCE.value, OrderStatus.PENDING.value
    )
    # Filter to orders targeting the same faction
    for existing in existing_orders:
        if existing.order_data.get('target_faction_id') == target_faction_id:
            return False, f"You already have a pending order to dissolve the alliance with {target_faction.name}."

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.DISSOLVE_ALLIANCE.value,
        unit_ids=[],
        character_id=submitting_character.id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.DISSOLVE_ALLIANCE].value,
        priority=ORDER_PRIORITY_MAP[OrderType.DISSOLVE_ALLIANCE],
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': target_faction_id,
            'target_faction_name': target_faction.name,
            'submitting_faction_id': submitting_faction.faction_id,
            'submitting_faction_name': submitting_faction.name,
            'alliance_activated_turn': existing_alliance.activated_turn
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    return True, f"Order to dissolve alliance with {target_faction.name} submitted (Order #{order_id}). The alliance will be dissolved next turn."


async def submit_declare_war_order(
    conn: asyncpg.Connection,
    submitting_character: Character,
    target_faction_ids: List[str],
    objective: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Submit an order for a faction leader to declare war on one or more factions.

    Args:
        conn: Database connection
        submitting_character: Character submitting the order (must be faction leader)
        target_faction_ids: List of faction IDs to declare war on
        objective: The objective/reason for the war
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate objective is not empty
    if not objective or not objective.strip():
        return False, "Objective cannot be empty."

    # Validate at least one target
    if not target_faction_ids:
        return False, "Must specify at least one target faction."

    # Check submitter is in a faction
    faction_member = await FactionMember.fetch_by_character(conn, submitting_character.id, guild_id)
    if not faction_member:
        return False, "You are not a member of any faction."

    # Get submitter's faction
    submitting_faction = await Faction.fetch_by_id(conn, faction_member.faction_id)
    if not submitting_faction:
        return False, "Your faction could not be found."

    # Check submitter is faction leader
    if submitting_faction.leader_character_id != submitting_character.id:
        return False, f"Only the leader of {submitting_faction.name} can declare war."

    # Validate all target factions exist and are not self
    target_faction_internal_ids = []
    target_faction_names = []
    for target_id in target_faction_ids:
        target_faction = await Faction.fetch_by_faction_id(conn, target_id, guild_id)
        if not target_faction:
            return False, f"Faction '{target_id}' not found."
        if target_faction.id == submitting_faction.id:
            return False, "Cannot declare war on your own faction."
        target_faction_internal_ids.append(target_faction.id)
        target_faction_names.append(target_faction.name)

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.DECLARE_WAR.value,
        unit_ids=[],
        character_id=submitting_character.id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.DECLARE_WAR].value,
        priority=ORDER_PRIORITY_MAP[OrderType.DECLARE_WAR],
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_ids': target_faction_internal_ids,
            'submitting_faction_id': submitting_faction.id,
            'objective': objective.strip()
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    targets_str = ', '.join(target_faction_names)
    return True, f"War declaration order submitted: {submitting_faction.name} declares war on {targets_str} (Objective: \"{objective}\") (Order #{order_id}). This will be processed next turn."


async def validate_path(
    conn: asyncpg.Connection,
    path: List[int],
    guild_id: int
) -> Tuple[bool, str]:
    """
    Validate a path is valid (territories exist and are adjacent).

    Args:
        conn: Database connection
        path: List of territory IDs
        guild_id: Guild ID

    Returns:
        (success, error_message)
    """
    if not path:
        return False, "Path is empty."

    # Check all territories exist
    for territory_id in path:
        territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
        if not territory:
            return False, f"Territory {territory_id} not found."

    # Check each consecutive pair is adjacent
    for i in range(len(path) - 1):
        territory_a = path[i]
        territory_b = path[i + 1]

        # Check adjacency (order doesn't matter due to canonical ordering in DB)
        is_adjacent = await conn.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM TerritoryAdjacency
                WHERE ((territory_a_id = $1 AND territory_b_id = $2)
                   OR (territory_a_id = $2 AND territory_b_id = $1))
                AND guild_id = $3
            );
        """, territory_a, territory_b, guild_id)

        if not is_adjacent:
            return False, f"Territories {territory_a} and {territory_b} are not adjacent."

    return True, ""


async def submit_mobilization_order(
    conn: asyncpg.Connection,
    unit_type_id: str,
    territory_id: str,
    guild_id: int,
    submitting_character_id: int,
    faction_id: Optional[str] = None,
    unit_name: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Submit a mobilization order to create a new unit.

    Args:
        conn: Database connection
        unit_type_id: The type of unit to create
        territory_id: Territory where unit will be mobilized
        guild_id: Guild ID
        submitting_character_id: Character submitting the order
        faction_id: Optional faction ID if using faction resources
        unit_name: Optional custom name for the unit

    Returns:
        (success, message)
    """
    # Validate unit type exists
    unit_type = await UnitType.fetch_by_type_id(conn, unit_type_id, guild_id)
    if not unit_type:
        return False, f"Unit type '{unit_type_id}' not found."

    # Validate territory exists
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False, f"Territory '{territory_id}' not found."

    # Get submitter's faction membership
    submitter = await Character.fetch_by_id(conn, submitting_character_id)
    if not submitter:
        return False, "Character not found."

    submitter_membership = await FactionMember.fetch_by_character(conn, submitting_character_id, guild_id)
    submitter_faction = None
    submitter_faction_nation = None

    if submitter_membership:
        submitter_faction = await Faction.fetch_by_id(conn, submitter_membership.faction_id)
        if submitter_faction:
            submitter_faction_nation = submitter_faction.nation

    use_faction_resources = False
    target_faction = None

    if faction_id:
        # Using faction resources - need CONSTRUCTION permission
        target_faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
        if not target_faction:
            return False, f"Faction '{faction_id}' not found."

        has_construction = await FactionPermission.has_permission(
            conn, target_faction.id, submitting_character_id, "CONSTRUCTION", guild_id
        )
        if not has_construction:
            return False, f"You do not have CONSTRUCTION permission for {target_faction.name}."

        # Check territory is controlled by faction or a faction member
        territory_accessible = await _is_territory_accessible_for_construction(
            conn, territory, target_faction.id, guild_id
        )
        if not territory_accessible:
            return False, f"Territory '{territory_id}' is not controlled by {target_faction.name} or a member of the faction."

        use_faction_resources = True

    # Validate nation matching rules
    # unit_type.nation must match owner's faction.nation
    if unit_type.nation:
        owner_nation = target_faction.nation if target_faction else submitter_faction_nation
        if owner_nation != unit_type.nation:
            return False, f"Unit type '{unit_type.name}' requires nation '{unit_type.nation}' but your faction is '{owner_nation or 'none'}'."

        # unit_type.nation must match territory.original_nation
        # EXCEPTION: Fifth Nation can build Fifth Nation units in any territory they control
        is_fifth_nation_exception = (owner_nation == "fifth-nation" and unit_type.nation == "fifth-nation")

        if not is_fifth_nation_exception:
            if territory.original_nation != unit_type.nation:
                return False, f"Unit type '{unit_type.name}' can only be built in {unit_type.nation} territories, but territory '{territory_id}' is originally '{territory.original_nation or 'unaffiliated'}'."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.MOBILIZATION.value,
        unit_ids=[],
        character_id=submitting_character_id,
        turn_number=current_turn + 1,
        phase=ORDER_PHASE_MAP[OrderType.MOBILIZATION].value,
        priority=ORDER_PRIORITY_MAP[OrderType.MOBILIZATION],
        status=OrderStatus.PENDING.value,
        order_data={
            'unit_type_id': unit_type_id,
            'unit_type_name': unit_type.name,
            'territory_id': territory_id,
            'faction_id': faction_id,
            'unit_name': unit_name,
            'use_faction_resources': use_faction_resources
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    name_note = f" named '{unit_name}'" if unit_name else ""
    resource_note = f" using {target_faction.name} resources" if target_faction else ""
    return True, f"Mobilization order submitted: {unit_type.name}{name_note} in territory {territory_id}{resource_note} (Order #{order_id})."


async def submit_construction_order(
    conn: asyncpg.Connection,
    building_type_id: str,
    territory_id: str,
    guild_id: int,
    submitting_character_id: int,
    faction_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Submit a construction order to build a new building.

    Args:
        conn: Database connection
        building_type_id: The type of building to construct
        territory_id: Territory where building will be constructed
        guild_id: Guild ID
        submitting_character_id: Character submitting the order
        faction_id: Optional faction ID if using faction resources

    Returns:
        (success, message)
    """
    # Validate building type exists
    building_type = await BuildingType.fetch_by_type_id(conn, building_type_id, guild_id)
    if not building_type:
        return False, f"Building type '{building_type_id}' not found."

    # Validate territory exists
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False, f"Territory '{territory_id}' not found."

    use_faction_resources = False
    target_faction = None

    if faction_id:
        # Using faction resources - need CONSTRUCTION permission
        target_faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
        if not target_faction:
            return False, f"Faction '{faction_id}' not found."

        has_construction = await FactionPermission.has_permission(
            conn, target_faction.id, submitting_character_id, "CONSTRUCTION", guild_id
        )
        if not has_construction:
            return False, f"You do not have CONSTRUCTION permission for {target_faction.name}."

        use_faction_resources = True

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await Order.get_count(conn, guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.CONSTRUCTION.value,
        unit_ids=[],
        character_id=submitting_character_id,
        turn_number=current_turn + 1,
        phase=ORDER_PHASE_MAP[OrderType.CONSTRUCTION].value,
        priority=ORDER_PRIORITY_MAP[OrderType.CONSTRUCTION],
        status=OrderStatus.PENDING.value,
        order_data={
            'building_type_id': building_type_id,
            'building_type_name': building_type.name,
            'territory_id': territory_id,
            'faction_id': faction_id,
            'use_faction_resources': use_faction_resources
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    resource_note = f" using {target_faction.name} resources" if target_faction else ""
    return True, f"Construction order submitted: {building_type.name} in territory {territory_id}{resource_note} (Order #{order_id})."


async def _is_territory_accessible_for_construction(
    conn: asyncpg.Connection,
    territory: Territory,
    faction_id: int,
    guild_id: int
) -> bool:
    """
    Check if territory is controlled by the faction or a member of the faction.

    Args:
        conn: Database connection
        territory: Territory to check
        faction_id: Faction ID (internal)
        guild_id: Guild ID

    Returns:
        True if territory is accessible, False otherwise
    """
    # Check if territory is controlled by the faction directly
    if territory.controller_faction_id == faction_id:
        return True

    # Check if territory is controlled by a character who is a member of the faction
    if territory.controller_character_id:
        member = await FactionMember.fetch_by_character(
            conn, territory.controller_character_id, guild_id
        )
        if member and member.faction_id == faction_id:
            return True

    return False
