"""
Order management command handlers.
"""
import asyncpg
from typing import Tuple, List, Optional
from db import Order, Unit, Character, Faction, FactionMember, Territory
from order_types import OrderType, ORDER_PHASE_MAP, ORDER_PRIORITY_MAP, OrderStatus
from datetime import datetime


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

    # Check character not already in this faction
    existing_membership = await FactionMember.fetch_by_character(conn, character.id, guild_id)
    if existing_membership and existing_membership.faction_id == faction.id:
        return False, f"{character.name} is already a member of {faction.name}."

    # Validate submitter is either the character themselves or the faction leader
    is_character = submitting_character_id == character.id
    is_leader = submitting_character_id == faction.leader_character_id

    if not is_character and not is_leader:
        return False, f"You must be either the leader of the faction or the person being added to the faction in order to issue a join faction order."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Generate order ID
    order_count = await conn.fetchval('SELECT COUNT(*) FROM "Order" WHERE guild_id = $1;', guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Determine submitted_by role
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
    guild_id: int
) -> Tuple[bool, str]:
    """
    Submit an order for a character to leave their faction.

    Args:
        conn: Database connection
        character_identifier: Character identifier
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Check character is in a faction
    faction_member = await FactionMember.fetch_by_character(conn, character.id, guild_id)
    if not faction_member:
        return False, f"You are not a member of any faction."

    # Get faction name
    faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

    # Check character is not faction leader
    if faction.leader_character_id == character.id:
        return False, f"You are the leader of {faction.name}. Get a GM to a new leader first using `/set-faction-leader`."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Check no pending faction order for current turn
    existing_orders = await conn.fetch("""
        SELECT order_id FROM "Order"
        WHERE character_id = $1 AND guild_id = $2
        AND status = $3
        AND order_type = $4;
    """, character.id, guild_id, OrderStatus.PENDING.value, OrderType.LEAVE_FACTION.value)

    if existing_orders:
        return False, f"{character.name} already has a pending faction order."


    # Generate order ID
    order_count = await conn.fetchval('SELECT COUNT(*) FROM "Order" WHERE guild_id = $1;', guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.LEAVE_FACTION.value,
        unit_ids=[],
        character_id=character.id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.LEAVE_FACTION].value,
        priority=ORDER_PRIORITY_MAP[OrderType.LEAVE_FACTION],
        status=OrderStatus.PENDING.value,
        order_data={},
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    return True, f"Order submitted: {character.name} will leave {faction.name} next turn (Order #{order_id})."


async def submit_kick_from_faction_order(
    conn: asyncpg.Connection,
    leader_character: Character,
    target_character_identifier: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Submit an order for a faction leader to kick a member from their faction.

    Cannot be issued:
    - Within the first 3 turns of the game
    - Within 3 turns of the creation of the faction
    - Within 3 turns of the member joining the faction
    - Against the faction leader themselves

    Args:
        conn: Database connection
        leader_character: Character submitting the order (must be faction leader)
        target_character_identifier: Character identifier to kick
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate target character exists
    target_character = await Character.fetch_by_identifier(conn, target_character_identifier, guild_id)
    if not target_character:
        return False, f"Character '{target_character_identifier}' not found."

    # Check leader is in a faction
    leader_membership = await FactionMember.fetch_by_character(conn, leader_character.id, guild_id)
    if not leader_membership:
        return False, "You are not a member of any faction."

    # Get faction
    faction = await Faction.fetch_by_id(conn, leader_membership.faction_id)

    # Check leader is the faction leader
    if faction.leader_character_id != leader_character.id:
        return False, f"You must be the leader of {faction.name} to kick members."

    # Check target is not the leader themselves
    if target_character.id == leader_character.id:
        return False, "You cannot kick yourself from the faction."

    # Check target is in the same faction
    target_membership = await FactionMember.fetch_by_character(conn, target_character.id, guild_id)
    if not target_membership or target_membership.faction_id != faction.id:
        return False, f"{target_character.name} is not a member of {faction.name}."

    # Get current turn from WargameConfig
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

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
    if current_turn - faction_created_turn < 3:
        turns_remaining = 3 - (current_turn - faction_created_turn)
        return False, f"Kick orders cannot be issued within 3 turns of faction creation. Wait {turns_remaining} more turn(s)."

    # Check not within 3 turns of member joining
    if current_turn - target_membership.joined_turn < 3:
        turns_remaining = 3 - (current_turn - target_membership.joined_turn)
        return False, f"{target_character.name} joined the faction too recently. Wait {turns_remaining} more turn(s)."

    # Check no pending kick orders for this target
    existing_orders = await conn.fetch("""
        SELECT order_id FROM "Order"
        WHERE guild_id = $1
        AND status = $2
        AND order_type = $3
        AND order_data->>'target_character_id' = $4;
    """, guild_id, OrderStatus.PENDING.value, OrderType.KICK_FROM_FACTION.value, str(target_character.id))

    if existing_orders:
        return False, f"There is already a pending kick order for {target_character.name}."

    # Generate order ID
    order_count = await conn.fetchval('SELECT COUNT(*) FROM "Order" WHERE guild_id = $1;', guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.KICK_FROM_FACTION.value,
        unit_ids=[],
        character_id=leader_character.id,
        turn_number=current_turn + 1,  # Execute next turn
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

    # Validate all units are owned or commanded by the character
    unauthorized_units = [u.unit_id for u in units
                         if u.owner_character_id != character_id and u.commander_character_id != character_id]
    if unauthorized_units:
        return False, f"You don't own or command these units: {', '.join(unauthorized_units)}"

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
        conn, unit_internal_ids, [OrderStatus.PENDING, OrderStatus.ONGOING], guild_id
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
    order_count = await conn.fetchval('SELECT COUNT(*) FROM "Order" WHERE guild_id = $1;', guild_id)
    order_id = f"ORD-{order_count + 1:04d}"

    # Determine if order will be ongoing
    path_length = len(path) - 1  # Number of steps
    will_be_ongoing = path_length > slowest_movement

    # Create order
    order = Order(
        order_id=order_id,
        order_type=OrderType.TRANSIT.value,
        unit_ids=unit_internal_ids,
        character_id=character_id,
        turn_number=current_turn + 1,  # Execute next turn
        phase=ORDER_PHASE_MAP[OrderType.TRANSIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.TRANSIT],
        status=OrderStatus.PENDING,
        order_data={'path': path, 'path_index': 0},
        submitted_at=datetime.now(),
        guild_id=guild_id
    )

    await order.upsert(conn)

    unit_list = ', '.join([u.unit_id for u in units])
    ongoing_note = " (will take multiple turns)" if will_be_ongoing else ""
    return True, f"Transit order submitted for {unit_list} -> Territory {path[-1]} (Order #{order_id}){ongoing_note}. Slowest unit: {slowest_unit.unit_id} (movement={slowest_movement})."


async def cancel_order(
    conn: asyncpg.Connection,
    order_id: str,
    guild_id: int,
    character_id: int
) -> Tuple[bool, str]:
    """
    Cancel a pending order.

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

    # Validate status is PENDING (cannot cancel ONGOING orders)
    if order.status != OrderStatus.PENDING.value:
        return False, f"Cannot cancel order '{order_id}' with status '{order.status}'. Only PENDING orders can be cancelled."

    # Update status to CANCELLED
    order.status = OrderStatus.CANCELLED.value
    order.updated_at = datetime.now()
    await order.upsert(conn)

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
