"""
Movement phase handlers for land unit movement.

This module contains helper functions for processing tick-based movement
during the MOVEMENT phase of turn resolution.
"""
import asyncpg
from typing import List, Optional, Tuple
from datetime import datetime
import logging

from db import Order, Unit, Territory, TurnLog, FactionPermission
from order_types import OrderType, OrderStatus, TurnPhase
from orders.movement_state import MovementUnitState, MovementStatus, MovementAction

logger = logging.getLogger(__name__)

# Terrain movement costs
TERRAIN_COSTS = {
    'mountains': 3,
    'mountain': 3,
    'desert': 2,
    # Default terrain cost is 1
}
DEFAULT_TERRAIN_COST = 1


async def get_terrain_cost(conn: asyncpg.Connection, territory_id: str, guild_id: int) -> int:
    """
    Get the movement cost for entering a territory based on terrain type.

    Args:
        conn: Database connection
        territory_id: ID of the territory to check
        guild_id: Guild ID

    Returns:
        Movement point cost (mountains=3, desert=2, default=1)
    """
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        logger.warning(f"Territory {territory_id} not found, using default cost")
        return DEFAULT_TERRAIN_COST

    terrain_type = territory.terrain_type.lower()
    return TERRAIN_COSTS.get(terrain_type, DEFAULT_TERRAIN_COST)


def calculate_movement_points(units: List[Unit], action: str) -> int:
    """
    Calculate total movement points for a unit group.

    Uses the slowest unit's movement stat as base, then applies
    action bonuses (+1 for transit and transport).

    Args:
        units: List of units moving together
        action: Movement action type

    Returns:
        Total movement points available
    """
    if not units:
        return 0

    # Base MP is the slowest unit's movement stat
    base_mp = min(unit.movement for unit in units)

    # Apply +1 bonus for transit and transport actions
    bonus = 1 if action in MovementAction.BONUS_ACTIONS else 0

    return base_mp + bonus


async def get_affected_character_ids(conn: asyncpg.Connection, units: List[Unit], guild_id: int) -> List[int]:
    """
    Get character IDs that should be notified about movement events.

    For character-owned units: owner + commander (if different)
    For faction-owned units: all characters with COMMAND privilege

    Args:
        conn: Database connection
        units: List of units in the movement order
        guild_id: Guild ID

    Returns:
        List of character IDs to notify
    """
    affected_ids = set()

    for unit in units:
        owner_type = unit.get_owner_type()

        if owner_type == 'character':
            # Add owner
            if unit.owner_character_id:
                affected_ids.add(unit.owner_character_id)
            # Add commander if different
            if unit.commander_character_id and unit.commander_character_id != unit.owner_character_id:
                affected_ids.add(unit.commander_character_id)

        elif owner_type == 'faction':
            # Add all characters with COMMAND permission for this faction
            if unit.owner_faction_id:
                command_holders = await FactionPermission.fetch_characters_with_permission(
                    conn, unit.owner_faction_id, "COMMAND", guild_id
                )
                affected_ids.update(command_holders)
            # Also add commander if set
            if unit.commander_character_id:
                affected_ids.add(unit.commander_character_id)

    return list(affected_ids)


async def validate_units_colocation(
    conn: asyncpg.Connection,
    unit_ids: List[int],
    guild_id: int
) -> Tuple[bool, str, Optional[str]]:
    """
    Validate that all units in an order are in the same territory.

    Args:
        conn: Database connection
        unit_ids: List of unit internal IDs
        guild_id: Guild ID

    Returns:
        (valid, error_message, territory_id)
    """
    if not unit_ids:
        return False, "No units specified in order", None

    territories = set()
    for unit_id in unit_ids:
        unit = await Unit.fetch_by_id(conn, unit_id)
        if not unit:
            return False, f"Unit ID {unit_id} not found", None
        if unit.is_naval:
            return False, f"Naval unit {unit.unit_id} cannot use land movement orders", None
        if not unit.current_territory_id:
            return False, f"Unit {unit.unit_id} has no current territory", None
        territories.add(unit.current_territory_id)

    if len(territories) > 1:
        return False, f"Units are not co-located: found in territories {territories}", None

    return True, "", territories.pop()


async def build_movement_states(
    conn: asyncpg.Connection,
    orders: List[Order],
    guild_id: int
) -> Tuple[List[MovementUnitState], List[TurnLog]]:
    """
    Build MovementUnitState objects for each order.

    Also validates orders and returns failed events for invalid orders.

    Args:
        conn: Database connection
        orders: List of UNIT orders for the movement phase
        guild_id: Guild ID

    Returns:
        (valid_states, failed_events)
    """
    states = []
    failed_events = []

    for order in orders:
        # Get units from order
        units = []
        for unit_id in order.unit_ids:
            unit = await Unit.fetch_by_id(conn, unit_id)
            if unit and not unit.is_naval and unit.status == 'ACTIVE':
                units.append(unit)

        if not units:
            # All units invalid or naval - fail the order
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'No valid land units in order'}
            order.updated_at = datetime.now()
            await order.upsert(conn)
            failed_events.append(TurnLog(
                turn_number=order.turn_number,
                phase=TurnPhase.MOVEMENT.value,
                event_type='ORDER_FAILED',
                entity_type='order',
                entity_id=order.id,
                event_data={
                    'order_id': order.order_id,
                    'error': 'No valid land units in order',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            ))
            continue

        # Validate co-location
        valid, error, territory_id = await validate_units_colocation(
            conn, order.unit_ids, guild_id
        )

        if not valid:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': error}
            order.updated_at = datetime.now()
            await order.upsert(conn)

            affected_ids = await get_affected_character_ids(conn, units, guild_id)
            failed_events.append(TurnLog(
                turn_number=order.turn_number,
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

        # Extract order data
        order_data = order.order_data
        action = order_data.get('action', 'transit')
        path = order_data.get('path', [])
        speed = order_data.get('speed')

        # Get path_index from result_data (for ongoing orders) or order_data
        result_data = order.result_data or {}
        path_index = result_data.get('path_index', order_data.get('path_index', 0))

        if not path or len(path) < 2:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Invalid path - must have at least 2 territories'}
            order.updated_at = datetime.now()
            await order.upsert(conn)

            affected_ids = await get_affected_character_ids(conn, units, guild_id)
            failed_events.append(TurnLog(
                turn_number=order.turn_number,
                phase=TurnPhase.MOVEMENT.value,
                event_type='ORDER_FAILED',
                entity_type='order',
                entity_id=order.id,
                event_data={
                    'order_id': order.order_id,
                    'error': 'Invalid path - must have at least 2 territories',
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))
            continue

        # Calculate movement points
        total_mp = calculate_movement_points(units, action)

        # Build the state
        state = MovementUnitState(
            units=units,
            order=order,
            total_movement_points=total_mp,
            remaining_mp=total_mp,
            status=MovementStatus.MOVING,
            current_territory_id=territory_id,
            path_index=path_index,
            action=action,
            speed=speed,
            territories_entered=[],
            blocked_at=None,
            mp_expended_this_turn=0
        )

        states.append(state)

    return states, failed_events


async def try_move_unit_group(
    conn: asyncpg.Connection,
    state: MovementUnitState,
    guild_id: int
) -> Tuple[bool, Optional[int]]:
    """
    Attempt to move a unit group one step along its path.

    Args:
        conn: Database connection
        state: MovementUnitState to update
        guild_id: Guild ID

    Returns:
        (moved, terrain_cost) - whether move succeeded and the cost if applicable
    """
    # Check if still moving
    if state.status != MovementStatus.MOVING:
        return False, None

    # For patrol orders, check speed limit
    if state.is_patrol() and not state.can_continue_patrol():
        return False, None

    # Get next territory
    next_territory = state.get_next_territory()
    if not next_territory:
        # At end of path
        if state.is_patrol():
            # Reset to beginning of path for patrol
            state.path_index = 0
            next_territory = state.get_next_territory()
            if not next_territory:
                state.status = MovementStatus.PATH_COMPLETE
                return False, None
        else:
            state.status = MovementStatus.PATH_COMPLETE
            return False, None

    # Get terrain cost
    terrain_cost = await get_terrain_cost(conn, next_territory, guild_id)

    # Check if we have enough MP
    if terrain_cost > state.remaining_mp:
        state.status = MovementStatus.OUT_OF_MP
        state.blocked_at = next_territory
        return False, terrain_cost

    # For patrol with speed limit, check if this move would exceed speed
    if state.is_patrol() and state.speed is not None:
        if state.mp_expended_this_turn + terrain_cost > state.speed:
            # Don't move, but don't mark as OUT_OF_MP - patrol just stops for the turn
            return False, terrain_cost

    # Execute the move
    state.remaining_mp -= terrain_cost
    state.mp_expended_this_turn += terrain_cost
    state.path_index += 1
    state.current_territory_id = next_territory
    state.territories_entered.append(next_territory)

    # Update all units' positions
    for unit in state.units:
        unit.current_territory_id = next_territory
        await unit.upsert(conn)

    logger.debug(f"Moved units to {next_territory}, cost {terrain_cost}, remaining MP {state.remaining_mp}")
    return True, terrain_cost


async def process_movement_tick(
    conn: asyncpg.Connection,
    states: List[MovementUnitState],
    tick: int,
    guild_id: int
) -> List[TurnLog]:
    """
    Process one tick of movement for all states.

    Args:
        conn: Database connection
        states: List of MovementUnitState objects
        tick: Current tick number (counting down from max)
        guild_id: Guild ID

    Returns:
        List of events generated during this tick
    """
    events = []

    for state in states:
        # Skip if not moving
        if state.status != MovementStatus.MOVING:
            continue

        # Skip if unit doesn't move at this tick
        if state.total_movement_points < tick:
            continue

        # For patrol orders, check speed limit before each move
        if state.is_patrol() and not state.can_continue_patrol():
            continue

        # Try to move
        moved, terrain_cost = await try_move_unit_group(conn, state, guild_id)

        # If blocked by terrain cost, generate event
        if not moved and state.status == MovementStatus.OUT_OF_MP and state.blocked_at:
            affected_ids = await get_affected_character_ids(conn, state.units, guild_id)
            events.append(TurnLog(
                turn_number=state.order.turn_number,
                phase=TurnPhase.MOVEMENT.value,
                event_type='MOVEMENT_BLOCKED',
                entity_type='order',
                entity_id=state.order.id,
                event_data={
                    'order_id': state.order.order_id,
                    'units': [u.unit_id for u in state.units],
                    'blocked_at': state.blocked_at,
                    'terrain_cost': terrain_cost,
                    'remaining_mp': state.remaining_mp,
                    'current_territory': state.current_territory_id,
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))

    return events


async def process_patrol_engagement(
    conn: asyncpg.Connection,
    states: List[MovementUnitState],
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Process patrol engagement opportunities.

    PLACEHOLDER - Will be implemented with combat phase.

    Args:
        conn: Database connection
        states: List of MovementUnitState objects
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of events (empty for now)
    """
    # Placeholder for patrol engagement logic
    return []


async def check_engagement(
    conn: asyncpg.Connection,
    states: List[MovementUnitState],
    guild_id: int
) -> None:
    """
    Check for engagements between moving units and other units.

    PLACEHOLDER - Will be implemented with combat phase.

    Args:
        conn: Database connection
        states: List of MovementUnitState objects
        guild_id: Guild ID
    """
    # Placeholder for engagement logic
    pass


async def generate_observation_reports(
    conn: asyncpg.Connection,
    states: List[MovementUnitState],
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Generate observation reports for units seeing other units move.

    PLACEHOLDER - Will be implemented with observation system.

    Args:
        conn: Database connection
        states: List of MovementUnitState objects
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of events (empty for now)
    """
    # Placeholder for observation reports
    return []


async def finalize_movement_order(
    conn: asyncpg.Connection,
    state: MovementUnitState,
    turn_number: int,
    guild_id: int
) -> TurnLog:
    """
    Finalize a movement order after all ticks are processed.

    Updates order status and result_data, generates appropriate event.

    Args:
        conn: Database connection
        state: MovementUnitState to finalize
        turn_number: Current turn number
        guild_id: Guild ID

    Returns:
        TurnLog event for this order
    """
    order = state.order
    steps_taken = len(state.territories_entered)
    path = state.get_path()

    # Determine if path is complete
    is_complete = state.is_path_complete()

    # For patrol orders, they stay ONGOING indefinitely
    if state.is_patrol():
        order.status = OrderStatus.ONGOING.value
        is_complete = False  # Patrol never completes
    elif is_complete:
        order.status = OrderStatus.SUCCESS.value
    else:
        order.status = OrderStatus.ONGOING.value

    # Update result_data
    order.result_data = {
        'final_territory': state.current_territory_id,
        'path_index': state.path_index,
        'steps_taken': steps_taken,
        'status': state.status,
        'blocked': state.blocked_at is not None,
        'completed': is_complete and not state.is_patrol()
    }
    order.updated_at = datetime.now()
    order.updated_turn = turn_number
    await order.upsert(conn)

    # Generate event
    affected_ids = await get_affected_character_ids(conn, state.units, guild_id)
    unit_ids = [u.unit_id for u in state.units]

    if is_complete and not state.is_patrol():
        # TRANSIT_COMPLETE
        return TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.MOVEMENT.value,
            event_type='TRANSIT_COMPLETE',
            entity_type='order',
            entity_id=order.id,
            event_data={
                'order_id': order.order_id,
                'units': unit_ids,
                'final_territory': state.current_territory_id,
                'total_steps': steps_taken,
                'action': state.action,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        )
    else:
        # TRANSIT_PROGRESS
        return TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.MOVEMENT.value,
            event_type='TRANSIT_PROGRESS',
            entity_type='order',
            entity_id=order.id,
            event_data={
                'order_id': order.order_id,
                'units': unit_ids,
                'current_territory': state.current_territory_id,
                'path_index': state.path_index,
                'total_steps': len(path) - 1,
                'steps_taken': steps_taken,
                'action': state.action,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        )
