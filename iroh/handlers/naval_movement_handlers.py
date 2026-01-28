"""
Naval movement phase handlers for naval unit positioning.

Naval units occupy a SET of territories rather than a single territory.
This module handles the positioning logic for naval actions:
- Convoy: Occupy all input territories (up to movement stat)
- Patrol: Occupy all input territories (up to movement stat)
- Transit: Sliding window of (movement + 1) territories
- Transport: Wait at first territory, then sliding window after boarding
"""
import asyncpg
from typing import List, Optional, Tuple, Dict, Set
from datetime import datetime
import logging

from db import (
    Order, Unit, Territory, TurnLog, NavalUnitPosition,
    FactionPermission, TerritoryAdjacency
)
from order_types import OrderType, OrderStatus, TurnPhase

logger = logging.getLogger(__name__)

# Water terrain types
WATER_TERRAIN_TYPES = ['ocean', 'lake', 'sea', 'water']

# Naval action types
NAVAL_ACTIONS = ['naval_convoy', 'naval_patrol', 'naval_transit', 'naval_transport']


async def is_water_territory(
    conn: asyncpg.Connection,
    territory_id: str,
    guild_id: int
) -> bool:
    """Check if a territory is a water territory."""
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False
    return territory.terrain_type.lower() in WATER_TERRAIN_TYPES


async def is_land_territory(
    conn: asyncpg.Connection,
    territory_id: str,
    guild_id: int
) -> bool:
    """Check if a territory is a land territory."""
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False
    return territory.terrain_type.lower() not in WATER_TERRAIN_TYPES


async def get_affected_character_ids(
    conn: asyncpg.Connection,
    units: List[Unit],
    guild_id: int
) -> List[int]:
    """
    Get character IDs that should be notified about naval movement events.

    For character-owned units: owner + commander (if different)
    For faction-owned units: all characters with COMMAND privilege
    """
    affected_ids = set()

    for unit in units:
        owner_type = unit.get_owner_type()

        if owner_type == 'character':
            if unit.owner_character_id:
                affected_ids.add(unit.owner_character_id)
            if unit.commander_character_id and unit.commander_character_id != unit.owner_character_id:
                affected_ids.add(unit.commander_character_id)

        elif owner_type == 'faction':
            if unit.owner_faction_id:
                command_holders = await FactionPermission.fetch_characters_with_permission(
                    conn, unit.owner_faction_id, "COMMAND", guild_id
                )
                affected_ids.update(command_holders)
            if unit.commander_character_id:
                affected_ids.add(unit.commander_character_id)

    return list(affected_ids)


def calculate_naval_window_size(
    units: List[Unit],
    action: str
) -> int:
    """
    Calculate the window size (number of territories) for naval positioning.

    For convoy/patrol: Returns movement stat (all territories up to movement)
    For transit: Returns movement stat + 1
    For transport: Returns movement stat (no +1 bonus)

    Args:
        units: List of naval units in the order
        action: Naval action type

    Returns:
        Window size (number of territories the unit group can occupy)
    """
    if not units:
        return 0

    # Base is the slowest unit's movement stat
    slowest_movement = min(unit.movement for unit in units)

    # Apply bonuses based on action
    if action == 'naval_transit':
        return slowest_movement + 1
    else:
        # convoy, patrol, transport - no bonus
        return slowest_movement


def calculate_occupied_territories(
    action: str,
    territory_path: List[str],
    window_size: int,
    window_start_index: int,
    waiting_for_cargo: bool = False
) -> List[str]:
    """
    Calculate which territories a naval unit group currently occupies.

    Args:
        action: Naval action type (naval_convoy, naval_patrol, naval_transit, naval_transport)
        territory_path: Full path of territories for the order
        window_size: Size of the sliding window
        window_start_index: Starting index in path for the window
        waiting_for_cargo: For transport - True if waiting for land unit

    Returns:
        List of territory IDs currently occupied
    """
    if not territory_path:
        return []

    if action in ['naval_convoy', 'naval_patrol']:
        # Convoy/Patrol: Occupy ALL territories in path (up to movement stat)
        return territory_path[:window_size]

    elif action == 'naval_transit':
        # Transit: Sliding window starting at window_start_index
        # At end of path: Only final territory
        end_index = window_start_index + window_size
        if end_index > len(territory_path):
            # Past end - only occupy final territory
            return [territory_path[-1]]
        return territory_path[window_start_index:end_index]

    elif action == 'naval_transport':
        # Transport: Waiting = only first territory, otherwise sliding window
        if waiting_for_cargo:
            return [territory_path[0]]
        # After boarding: sliding window
        end_index = window_start_index + window_size
        if end_index > len(territory_path):
            return [territory_path[-1]]
        return territory_path[window_start_index:end_index]

    return []


async def validate_path_water_only(
    conn: asyncpg.Connection,
    territory_path: List[str],
    guild_id: int
) -> Tuple[bool, str]:
    """
    Validate that all territories in path are water territories.

    Args:
        conn: Database connection
        territory_path: List of territory IDs
        guild_id: Guild ID

    Returns:
        (valid, error_message)
    """
    for territory_id in territory_path:
        if not await is_water_territory(conn, territory_id, guild_id):
            return False, f"Territory {territory_id} is not a water territory"
    return True, ""


async def validate_naval_order_overlap(
    conn: asyncpg.Connection,
    unit_id: int,
    new_territory_set: List[str],
    guild_id: int
) -> Tuple[bool, str]:
    """
    Validate that new naval order territories overlap with previous positions.

    For first order (no previous positions), checks against unit's current_territory_id.

    Args:
        conn: Database connection
        unit_id: Unit's internal ID
        new_territory_set: List of territory IDs in the new order
        guild_id: Guild ID

    Returns:
        (valid, error_message)
    """
    if not new_territory_set:
        return False, "Order has no territories"

    # Get current positions from NavalUnitPosition table
    current_positions = await NavalUnitPosition.fetch_territories_by_unit(conn, unit_id, guild_id)

    if current_positions:
        # Check overlap with current positions
        if set(new_territory_set) & set(current_positions):
            return True, ""
        return False, "New order must overlap with at least one currently occupied territory"

    # No current positions - check against unit's current_territory_id
    unit = await Unit.fetch_by_id(conn, unit_id)
    if not unit:
        return False, f"Unit {unit_id} not found"

    if unit.current_territory_id in new_territory_set:
        return True, ""

    return False, f"First order must include unit's initial territory ({unit.current_territory_id})"


async def validate_transport_coastal(
    conn: asyncpg.Connection,
    first_territory: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Validate that the first territory in a transport path is adjacent to at least one land tile.

    This allows land units to board from a coastal territory.

    Args:
        conn: Database connection
        first_territory: First territory ID in the transport path
        guild_id: Guild ID

    Returns:
        (valid, error_message)
    """
    adjacent = await TerritoryAdjacency.fetch_adjacent(conn, first_territory, guild_id)

    for adj_territory_id in adjacent:
        if await is_land_territory(conn, adj_territory_id, guild_id):
            return True, ""

    return False, f"First territory {first_territory} must be adjacent to at least one land tile for boarding"


def validate_territory_count(
    territory_path: List[str],
    max_territories: int,
    action: str
) -> Tuple[bool, str]:
    """
    Validate that the order doesn't exceed the maximum territory count.

    Only applies to convoy and patrol (which occupy all territories).
    Transit and transport use sliding windows, so path can be longer.

    Args:
        territory_path: List of territory IDs
        max_territories: Maximum allowed (movement stat)
        action: Naval action type

    Returns:
        (valid, error_message)
    """
    if action in ['naval_convoy', 'naval_patrol']:
        if len(territory_path) > max_territories:
            return False, f"Order has {len(territory_path)} territories, max allowed is {max_territories}"
    return True, ""


async def process_naval_convoy(
    conn: asyncpg.Connection,
    order: Order,
    units: List[Unit],
    guild_id: int,
    turn_number: int
) -> Tuple[Order, List[TurnLog]]:
    """
    Process a naval convoy order.

    Convoy: Naval unit occupies all specified territories immediately.
    Positions stay fixed until new order is issued.

    Args:
        conn: Database connection
        order: The naval_convoy order
        units: Naval units in the order
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        (updated_order, events)
    """
    events = []
    order_data = order.order_data
    territory_path = order_data.get('path', [])

    window_size = calculate_naval_window_size(units, 'naval_convoy')
    occupied = calculate_occupied_territories('naval_convoy', territory_path, window_size, 0)

    # Update positions for each unit
    for unit in units:
        await NavalUnitPosition.set_positions(conn, unit.id, occupied, guild_id)
        # Update unit's current_territory_id to first territory (for backwards compatibility)
        unit.current_territory_id = occupied[0] if occupied else unit.current_territory_id
        await unit.upsert(conn)

    # Update order
    order.status = OrderStatus.SUCCESS.value
    order.result_data = {
        'occupied_territories': occupied,
        'path_complete': True
    }
    order.updated_at = datetime.now()
    order.updated_turn = turn_number
    await order.upsert(conn)

    # Generate event
    affected_ids = await get_affected_character_ids(conn, units, guild_id)
    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.MOVEMENT.value,
        event_type='NAVAL_POSITION_SET',
        entity_type='order',
        entity_id=order.id,
        event_data={
            'order_id': order.order_id,
            'units': [u.unit_id for u in units],
            'action': 'naval_convoy',
            'occupied_territories': occupied,
            'affected_character_ids': affected_ids
        },
        guild_id=guild_id
    ))

    logger.info(f"Naval convoy: units {[u.unit_id for u in units]} now occupy {occupied}")
    return order, events


async def process_naval_patrol(
    conn: asyncpg.Connection,
    order: Order,
    units: List[Unit],
    guild_id: int,
    turn_number: int
) -> Tuple[Order, List[TurnLog]]:
    """
    Process a naval patrol order.

    Patrol: Naval unit occupies all specified territories immediately.
    Positions stay fixed until new order is issued (same as convoy).

    Args:
        conn: Database connection
        order: The naval_patrol order
        units: Naval units in the order
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        (updated_order, events)
    """
    events = []
    order_data = order.order_data
    territory_path = order_data.get('path', [])

    window_size = calculate_naval_window_size(units, 'naval_patrol')
    occupied = calculate_occupied_territories('naval_patrol', territory_path, window_size, 0)

    # Update positions for each unit
    for unit in units:
        await NavalUnitPosition.set_positions(conn, unit.id, occupied, guild_id)
        unit.current_territory_id = occupied[0] if occupied else unit.current_territory_id
        await unit.upsert(conn)

    # Update order
    order.status = OrderStatus.SUCCESS.value
    order.result_data = {
        'occupied_territories': occupied,
        'path_complete': True
    }
    order.updated_at = datetime.now()
    order.updated_turn = turn_number
    await order.upsert(conn)

    # Generate event
    affected_ids = await get_affected_character_ids(conn, units, guild_id)
    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.MOVEMENT.value,
        event_type='NAVAL_POSITION_SET',
        entity_type='order',
        entity_id=order.id,
        event_data={
            'order_id': order.order_id,
            'units': [u.unit_id for u in units],
            'action': 'naval_patrol',
            'occupied_territories': occupied,
            'affected_character_ids': affected_ids
        },
        guild_id=guild_id
    ))

    logger.info(f"Naval patrol: units {[u.unit_id for u in units]} now occupy {occupied}")
    return order, events


async def process_naval_transit(
    conn: asyncpg.Connection,
    order: Order,
    units: List[Unit],
    guild_id: int,
    turn_number: int
) -> Tuple[Order, List[TurnLog]]:
    """
    Process a naval transit order.

    Transit: Sliding window of (movement + 1) territories.
    Window advances each turn until reaching end of path.
    At end: Only final territory is occupied.

    Args:
        conn: Database connection
        order: The naval_transit order
        units: Naval units in the order
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        (updated_order, events)
    """
    events = []
    order_data = order.order_data
    territory_path = order_data.get('path', [])

    # Get current window position from result_data (for ongoing orders)
    result_data = order.result_data or {}
    window_start_index = result_data.get('window_start_index', 0)

    window_size = calculate_naval_window_size(units, 'naval_transit')

    # Advance window by window_size for ongoing orders
    if order.status == OrderStatus.ONGOING.value:
        window_start_index += window_size

    occupied = calculate_occupied_territories('naval_transit', territory_path, window_size, window_start_index)

    # Check if path is complete
    path_complete = (window_start_index + window_size >= len(territory_path))

    # Update positions for each unit
    for unit in units:
        await NavalUnitPosition.set_positions(conn, unit.id, occupied, guild_id)
        unit.current_territory_id = occupied[0] if occupied else unit.current_territory_id
        await unit.upsert(conn)

    # Update order
    if path_complete:
        order.status = OrderStatus.SUCCESS.value
    else:
        order.status = OrderStatus.ONGOING.value

    order.result_data = {
        'occupied_territories': occupied,
        'window_start_index': window_start_index,
        'path_complete': path_complete
    }
    order.updated_at = datetime.now()
    order.updated_turn = turn_number
    await order.upsert(conn)

    # Generate event
    affected_ids = await get_affected_character_ids(conn, units, guild_id)
    event_type = 'NAVAL_TRANSIT_COMPLETE' if path_complete else 'NAVAL_TRANSIT_PROGRESS'
    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.MOVEMENT.value,
        event_type=event_type,
        entity_type='order',
        entity_id=order.id,
        event_data={
            'order_id': order.order_id,
            'units': [u.unit_id for u in units],
            'action': 'naval_transit',
            'occupied_territories': occupied,
            'window_start_index': window_start_index,
            'path_complete': path_complete,
            'affected_character_ids': affected_ids
        },
        guild_id=guild_id
    ))

    logger.info(f"Naval transit: units {[u.unit_id for u in units]} at window {window_start_index}, "
                f"occupying {occupied}, complete={path_complete}")
    return order, events


async def process_naval_transport(
    conn: asyncpg.Connection,
    order: Order,
    units: List[Unit],
    guild_id: int,
    turn_number: int
) -> Tuple[Order, List[TurnLog]]:
    """
    Process a naval transport order.

    Transport:
    - While waiting for cargo: Occupy only first territory
    - After cargo boarded: Sliding window of (movement) territories (no +1)
    - Window advances each turn after boarding

    Args:
        conn: Database connection
        order: The naval_transport order
        units: Naval units in the order
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        (updated_order, events)
    """
    events = []
    order_data = order.order_data
    territory_path = order_data.get('path', [])

    # Get current state from result_data
    result_data = order.result_data or {}
    window_start_index = result_data.get('window_start_index', 0)
    waiting_for_cargo = result_data.get('waiting_for_cargo', True)
    carrying_units = result_data.get('carrying_units', [])

    window_size = calculate_naval_window_size(units, 'naval_transport')

    # If we have cargo and this is an ongoing order, advance window
    if not waiting_for_cargo and order.status == OrderStatus.ONGOING.value:
        window_start_index += window_size

    occupied = calculate_occupied_territories(
        'naval_transport', territory_path, window_size,
        window_start_index, waiting_for_cargo
    )

    # Check if path is complete (only if we have cargo)
    path_complete = (not waiting_for_cargo and
                     window_start_index + window_size >= len(territory_path))

    # Update positions for each unit
    for unit in units:
        await NavalUnitPosition.set_positions(conn, unit.id, occupied, guild_id)
        unit.current_territory_id = occupied[0] if occupied else unit.current_territory_id
        await unit.upsert(conn)

    # Update order
    if path_complete:
        order.status = OrderStatus.SUCCESS.value
    else:
        order.status = OrderStatus.ONGOING.value

    order.result_data = {
        'occupied_territories': occupied,
        'window_start_index': window_start_index,
        'path_complete': path_complete,
        'waiting_for_cargo': waiting_for_cargo,
        'carrying_units': carrying_units
    }
    order.updated_at = datetime.now()
    order.updated_turn = turn_number
    await order.upsert(conn)

    # Generate event
    affected_ids = await get_affected_character_ids(conn, units, guild_id)
    if waiting_for_cargo:
        event_type = 'NAVAL_WAITING'
        event_data = {
            'order_id': order.order_id,
            'units': [u.unit_id for u in units],
            'action': 'naval_transport',
            'occupied_territories': occupied,
            'waiting_for_cargo': True,
            'affected_character_ids': affected_ids
        }
    elif path_complete:
        event_type = 'NAVAL_TRANSIT_COMPLETE'
        event_data = {
            'order_id': order.order_id,
            'units': [u.unit_id for u in units],
            'action': 'naval_transport',
            'occupied_territories': occupied,
            'carrying_units': carrying_units,
            'path_complete': True,
            'affected_character_ids': affected_ids
        }
    else:
        event_type = 'NAVAL_TRANSIT_PROGRESS'
        event_data = {
            'order_id': order.order_id,
            'units': [u.unit_id for u in units],
            'action': 'naval_transport',
            'occupied_territories': occupied,
            'carrying_units': carrying_units,
            'window_start_index': window_start_index,
            'path_complete': False,
            'affected_character_ids': affected_ids
        }

    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.MOVEMENT.value,
        event_type=event_type,
        entity_type='order',
        entity_id=order.id,
        event_data=event_data,
        guild_id=guild_id
    ))

    logger.info(f"Naval transport: units {[u.unit_id for u in units]} "
                f"{'waiting' if waiting_for_cargo else f'at window {window_start_index}'}, "
                f"occupying {occupied}")
    return order, events


async def validate_naval_order(
    conn: asyncpg.Connection,
    order: Order,
    units: List[Unit],
    guild_id: int
) -> Tuple[bool, str]:
    """
    Validate a naval order before processing.

    Checks:
    1. All units are naval
    2. All territories in path are water
    3. Path overlaps with previous positions (or initial territory for first order)
    4. For convoy/patrol: territory count <= movement stat
    5. For transport: first territory is adjacent to at least one land tile

    Args:
        conn: Database connection
        order: The naval order to validate
        units: Naval units in the order
        guild_id: Guild ID

    Returns:
        (valid, error_message)
    """
    order_data = order.order_data
    action = order_data.get('action', '')
    territory_path = order_data.get('path', [])

    # Check all units are naval
    for unit in units:
        if not unit.is_naval:
            return False, f"Unit {unit.unit_id} is not a naval unit"

    if not territory_path:
        return False, "Order has no path specified"

    # Check all territories are water
    valid, error = await validate_path_water_only(conn, territory_path, guild_id)
    if not valid:
        return False, error

    # Check overlap with previous positions (for each unit)
    for unit in units:
        valid, error = await validate_naval_order_overlap(conn, unit.id, territory_path, guild_id)
        if not valid:
            return False, f"Unit {unit.unit_id}: {error}"

    # Check territory count for convoy/patrol
    window_size = calculate_naval_window_size(units, action)
    if action in ["naval_patrol", "naval_convoy"]:
        valid, error = validate_territory_count(territory_path, window_size, action)
    if not valid:
        return False, error

    # For transport: validate first territory is adjacent to land
    if action == 'naval_transport':
        valid, error = await validate_transport_coastal(conn, territory_path[0], guild_id)
        if not valid:
            return False, error

    return True, ""


async def execute_naval_movement_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute naval movement for all naval orders.

    This processes naval_convoy, naval_patrol, naval_transit, and naval_transport orders.
    Called at the start of the movement phase, before land unit movement.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events
    """
    events = []
    logger.info(f"Naval movement phase: starting for guild {guild_id}, turn {turn_number}")

    # Fetch all PENDING and ONGOING UNIT orders for MOVEMENT phase with naval actions
    all_orders = await Order.fetch_unresolved_by_phase(conn, guild_id, TurnPhase.MOVEMENT.value)

    # Filter to naval orders
    naval_orders = [
        o for o in all_orders
        if o.order_type == OrderType.UNIT.value and
        o.order_data.get('action', '') in NAVAL_ACTIONS
    ]

    if not naval_orders:
        logger.info(f"Naval movement phase: no naval orders to process for guild {guild_id}")
        return events

    logger.info(f"Naval movement phase: processing {len(naval_orders)} naval orders")

    for order in naval_orders:
        # Get units from order
        units = []
        for unit_id in order.unit_ids:
            unit = await Unit.fetch_by_id(conn, unit_id)
            if unit and unit.is_naval and unit.status == 'ACTIVE':
                units.append(unit)

        if not units:
            # No valid naval units - fail the order
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'No valid naval units in order'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.MOVEMENT.value,
                event_type='ORDER_FAILED',
                entity_type='order',
                entity_id=order.id,
                event_data={
                    'order_id': order.order_id,
                    'error': 'No valid naval units in order',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            ))
            continue

        # Validate order
        valid, error = await validate_naval_order(conn, order, units, guild_id)
        if not valid:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': error}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)

            affected_ids = await get_affected_character_ids(conn, units, guild_id)
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.MOVEMENT.value,
                event_type='ORDER_FAILED',
                entity_type='order',
                entity_id=order.id,
                event_data={
                    'order_id': order.order_id,
                    'error': error,
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))
            continue

        # Process based on action type
        action = order.order_data.get('action', '')

        if action == 'naval_convoy':
            order, order_events = await process_naval_convoy(
                conn, order, units, guild_id, turn_number
            )
            events.extend(order_events)

        elif action == 'naval_patrol':
            order, order_events = await process_naval_patrol(
                conn, order, units, guild_id, turn_number
            )
            events.extend(order_events)

        elif action == 'naval_transit':
            order, order_events = await process_naval_transit(
                conn, order, units, guild_id, turn_number
            )
            events.extend(order_events)

        elif action == 'naval_transport':
            order, order_events = await process_naval_transport(
                conn, order, units, guild_id, turn_number
            )
            events.extend(order_events)

    logger.info(f"Naval movement phase: finished, generated {len(events)} events")
    return events


async def update_naval_transport_cargo(
    conn: asyncpg.Connection,
    naval_order: Order,
    land_unit_ids: List[int],
    guild_id: int
) -> None:
    """
    Update a naval transport order to record that cargo has boarded.

    Called by the land transport boarding logic when land units board a naval transport.

    Args:
        conn: Database connection
        naval_order: The naval_transport order
        land_unit_ids: List of land unit internal IDs that boarded
        guild_id: Guild ID
    """
    result_data = naval_order.result_data or {}
    result_data['waiting_for_cargo'] = False
    carrying_units = result_data.get('carrying_units', [])
    carrying_units.extend(land_unit_ids)
    result_data['carrying_units'] = carrying_units

    naval_order.result_data = result_data
    await naval_order.upsert(conn)

    logger.info(f"Naval transport {naval_order.order_id}: cargo boarded, carrying {carrying_units}")


async def get_naval_units_in_territory(
    conn: asyncpg.Connection,
    territory_id: str,
    guild_id: int
) -> List[Unit]:
    """
    Get all naval units that occupy a given territory.

    Uses the NavalUnitPosition table to find units.

    Args:
        conn: Database connection
        territory_id: Territory ID to check
        guild_id: Guild ID

    Returns:
        List of naval Unit objects occupying this territory
    """
    unit_ids = await NavalUnitPosition.fetch_units_in_territory(conn, territory_id, guild_id)
    units = []
    for unit_id in unit_ids:
        unit = await Unit.fetch_by_id(conn, unit_id)
        if unit and unit.is_naval and unit.status == 'ACTIVE':
            units.append(unit)
    return units


async def initialize_naval_position_from_current(
    conn: asyncpg.Connection,
    unit: Unit,
    guild_id: int
) -> None:
    """
    Initialize a naval unit's position in NavalUnitPosition table from current_territory_id.

    Called when a naval unit has no orders - it should occupy its current territory.

    Args:
        conn: Database connection
        unit: Naval unit to initialize
        guild_id: Guild ID
    """
    if not unit.current_territory_id:
        logger.warning(f"initialize_naval_position_from_current: unit {unit.unit_id} has no current_territory_id")
        return

    # Check if already has positions
    current = await NavalUnitPosition.fetch_territories_by_unit(conn, unit.id, guild_id)
    if current:
        logger.debug(f"initialize_naval_position_from_current: unit {unit.unit_id} already has positions {current}")
        return

    # Set single position at current territory
    await NavalUnitPosition.set_positions(conn, unit.id, [unit.current_territory_id], guild_id)
    logger.info(f"initialize_naval_position_from_current: unit {unit.unit_id} initialized at {unit.current_territory_id}")
