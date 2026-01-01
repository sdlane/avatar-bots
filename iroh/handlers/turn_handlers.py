"""
Turn resolution handlers for the wargame system.
"""
import asyncpg
from typing import Tuple, List, Dict, Optional
from datetime import datetime
from db import (
    Order, Unit, Character, Faction, FactionMember, Territory,
    PlayerResources, WargameConfig, TurnLog, FactionJoinRequest
)
from order_types import *
from orders import *

import logging

logger = logging.getLogger(__name__)

OrderHandlerMap: Dict[str, function] = {
    OrderType.LEAVE_FACTION.value: handle_leave_faction_order,
    OrderType.KICK_FROM_FACTION.value: handle_kick_from_faction_order,
    OrderType.JOIN_FACTION.value: handle_join_faction_order,
}

async def resolve_turn(
    conn: asyncpg.Connection,
    guild_id: int
) -> Tuple[bool, str, List[Dict]]:
    """
    Execute turn resolution for a guild.

    Executes all five phases in order:
    1. Beginning (faction joins/leaves)
    2. Movement (placeholder)
    3. Combat (placeholder)
    4. Resource Collection (placeholder)
    5. Resource Transfer (placeholder)
    6. Encirclement (placeholder)
    7. Upkeep (placeholder)
    8. Organization (placeholder)
    9. Construction (placeholder)

    Args:
        conn: Database connection
        guild_id: Guild ID

    Returns:
        (success, message, all_events)
    """
    # Fetch wargame config
    config = await WargameConfig.fetch(conn, guild_id)
    if not config:
        return False, "Wargame not configured for this guild.", []

    turn_number = config.current_turn + 1
    all_events = []

    #try:
    # Execute phases in order
    beginning_events = await execute_beginning_phase(conn, guild_id, turn_number)
    all_events.extend(beginning_events)

    movement_events = await execute_movement_phase(conn, guild_id, turn_number)
    all_events.extend(movement_events)

    resource_events = await execute_resource_collection_phase(conn, guild_id, turn_number)
    all_events.extend(resource_events)

    transfer_events = await execute_resource_transfer_phase(conn, guild_id, turn_number)
    all_events.extend(transfer_events)

    upkeep_events = await execute_upkeep_phase(conn, guild_id, turn_number)
    all_events.extend(upkeep_events)

    # Update config
    config.current_turn = turn_number
    config.last_turn_time = datetime.now()
    await config.upsert(conn)

    # Write all events to TurnLog
    for event in all_events:
        turn_log = TurnLog(
            turn_number=turn_number,
            phase=event['phase'],
            event_type=event['event_type'],
            entity_type=event.get('entity_type'),
            entity_id=event.get('entity_id'),
            event_data=event.get('event_data', {}),
            guild_id=guild_id
        )
        await turn_log.insert(conn)

    return True, f"Turn {turn_number} resolved successfully.", all_events

    #except Exception as e:
        #return False, f"Error resolving turn: {str(e)}", []

async def execute_beginning_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[Dict]:
    """
    Execute the Beginning phase: faction leaves and joins.

    Fetches all PENDING/ONGOING orders for this phase, sorted by priority,
    and calls handlers for order.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of event dicts for TurnLog
    """
    events = []

    # Fetch all orders for this phase (already sorted by priority, submitted_at)
    all_orders = await Order.fetch_unresolved_by_phase(
        conn, guild_id, TurnPhase.BEGINNING.value 
    )

    # Process orders
    for order in all_orders:
        if order.order_type in OrderHandlerMap:
            event = await OrderHandlerMap[order.order_type](conn, order, guild_id, turn_number)
            if event:
                events.append(event)
        else:
            # Mark order as failed - no handler found for this order type
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': f'No handler found for order type: {order.order_type}'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)

    return events


async def execute_movement_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[Dict]:
    """
    Execute the Movement phase: transit orders with tick-based movement.

    Movement happens in ticks from highest movement stat down to 1.
    Units move when tick <= their movement stat.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of event dicts for TurnLog
    """
    events = []
    return events


async def execute_combat_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[Dict]:
    """
    Execute the Combat phase

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of event dicts for TurnLog
    """
    events = []
    return events

async def execute_resource_collection_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[Dict]:
    """
    Execute the Resource Collection phase.

    For each territory, give production to the person controlling the territory.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of event dicts for TurnLog
    """
    events = []

    # Placeholder for now

    return events


async def execute_resource_transfer_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[Dict]:
    """
    Execute the Resource Transfer phase.

    Placeholder for future implementation.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of event dicts for TurnLog
    """
    return []


async def execute_encirclement_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[Dict]:
    """
    Execute the Encirclement phase

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of event dicts for TurnLog
    """
    events = []
    return events

async def execute_upkeep_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[Dict]:
    """
    Execute the Upkeep phase.

    For each unit:
    - Deduct upkeep from owner's resources
    - If insufficient resources, deduct what's available
    - Reduce organization by 1 for EACH missing resource unit
    - If organization <= 0, mark unit for dissolution

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of event dicts for TurnLog
    """
    events = []

    return events


async def execute_organization_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[Dict]:
    """
    Execute the Organization phase

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of event dicts for TurnLog
    """
    events = []
    return events



async def execute_construction_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[Dict]:
    """
    Execute the Construction phase

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of event dicts for TurnLog
    """
    events = []
    return events

async def get_turn_status(
    conn: asyncpg.Connection,
    guild_id: int
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Get current turn status and pending orders count.

    Args:
        conn: Database connection
        guild_id: Guild ID

    Returns:
        (success, message, status_dict)
    """
    # Fetch config
    config = await WargameConfig.fetch(conn, guild_id)
    if not config:
        return False, "Wargame not configured for this guild.", None

    # Count pending orders by phase
    pending_counts = {}
    for phase in TurnPhase:
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM "Order"
            WHERE guild_id = $1
            AND status IN ($2, $3)
            AND phase = $4;
        """, guild_id, OrderStatus.PENDING, OrderStatus.ONGOING, phase.value)
        pending_counts[phase.value] = count

    status_dict = {
        'current_turn': config.current_turn,
        'last_turn_time': config.last_turn_time.isoformat() if config.last_turn_time else None,
        'turn_resolution_enabled': config.turn_resolution_enabled,
        'pending_orders': pending_counts,
        'total_pending': sum(pending_counts.values())
    }

    return True, "Turn status retrieved.", status_dict
