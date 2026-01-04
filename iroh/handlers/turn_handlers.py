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
from orders.resource_transfer_orders import (
    handle_cancel_transfer_order,
    handle_resource_transfer_order
)

import logging

logger = logging.getLogger(__name__)

OrderHandlerMap: Dict[str, function] = {
    OrderType.LEAVE_FACTION.value: handle_leave_faction_order,
    OrderType.KICK_FROM_FACTION.value: handle_kick_from_faction_order,
    OrderType.JOIN_FACTION.value: handle_join_faction_order,
    OrderType.CANCEL_TRANSFER.value: handle_cancel_transfer_order,
    OrderType.RESOURCE_TRANSFER.value: handle_resource_transfer_order,
}

async def resolve_turn(
    conn: asyncpg.Connection,
    guild_id: int
) -> Tuple[bool, str, List[TurnLog]]:
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

    combat_events = await execute_combat_phase(conn, guild_id, turn_number)
    all_events.extend(combat_events)

    resource_events = await execute_resource_collection_phase(conn, guild_id, turn_number)
    all_events.extend(resource_events)

    transfer_events = await execute_resource_transfer_phase(conn, guild_id, turn_number)
    all_events.extend(transfer_events)

    encirclement_events = await execute_encirclement_phase(conn, guild_id, turn_number)
    all_events.extend(encirclement_events)

    upkeep_events = await execute_upkeep_phase(conn, guild_id, turn_number)
    all_events.extend(upkeep_events)

    organization_events = await execute_organization_phase(conn, guild_id, turn_number)
    all_events.extend(organization_events)

    construction_events = await execute_construction_phase(conn, guild_id, turn_number)
    all_events.extend(construction_events)

    # Update config
    config.current_turn = turn_number
    config.last_turn_time = datetime.now()
    await config.upsert(conn)
    logger.info(f"Turn resolution: updated config to turn {turn_number} for guild {guild_id}")

    # Write all events to TurnLog
    for event in all_events:
        await event.insert(conn)

    logger.info(f"Turn resolution: wrote {len(all_events)} events to TurnLog for guild {guild_id}, turn {turn_number}")
    logger.info(f"Turn resolution: turn {turn_number} resolved successfully for guild {guild_id}")

    return True, f"Turn {turn_number} resolved successfully.", all_events

    #except Exception as e:
        #return False, f"Error resolving turn: {str(e)}", []

async def execute_beginning_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Beginning phase: faction leaves and joins.

    Fetches all PENDING/ONGOING orders for this phase, sorted by priority,
    and calls handlers for order.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Beginning phase: starting beginning phase for guild {guild_id}, turn {turn_number}")

    # Fetch all orders for this phase (already sorted by priority, submitted_at)
    all_orders = await Order.fetch_unresolved_by_phase(
        conn, guild_id, TurnPhase.BEGINNING.value 
    )

    # Process orders
    for order in all_orders:
        if order.order_type in OrderHandlerMap:
            logger.info(f"Beginning phase: starting to process {order.order_type} order (ID: {order.id}) for guild {guild_id}, turn {turn_number}")
            result_events = await OrderHandlerMap[order.order_type](conn, order, guild_id, turn_number)
            # Handler returns a list of event dicts (may be empty)
            if result_events:
                events.extend(result_events)
            logger.info(f"Beginning phase: processed {order.order_type} order (ID: {order.id}) for guild {guild_id}, turn {turn_number}")
        else:
            # Mark order as failed - no handler found for this order type
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': f'No handler found for order type: {order.order_type}'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            logger.warning(f"Beginning phase: no handler found for order type '{order.order_type}' (order ID: {order.id}) in guild {guild_id}, turn {turn_number}")
    
    logger.info(f"Beginning phase: finished beginning phase for guild {guild_id}, turn {turn_number}")
    return events


async def execute_movement_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Movement phase: transit orders with tick-based movement.

    Movement happens in ticks from highest movement stat down to 1.
    Units move when tick <= their movement stat.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Movement phase: starting movement phase for guild {guild_id}, turn {turn_number}")

    # Placeholder for now

    logger.info(f"Movement phase: finished movement phase for guild {guild_id}, turn {turn_number}")
    return events


async def execute_combat_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Combat phase

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Combat phase: starting combat phase for guild {guild_id}, turn {turn_number}")

    # Placeholder for now

    logger.info(f"Combat phase: finished combat phase for guild {guild_id}, turn {turn_number}")
    return events

async def execute_resource_collection_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Resource Collection phase.

    For each territory, give production to the character controlling the territory.
    Aggregates resources per character and generates ONE event per character.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Resource collection phase: starting for guild {guild_id}, turn {turn_number}")

    # Fetch all territories in the guild
    territories = await Territory.fetch_all(conn, guild_id)

    # Dictionary to aggregate resources per character
    # Structure: {character_id: {ore: amount, lumber: amount, ...}}
    character_resources = {}

    for territory in territories:
        # Skip territories with no controller
        if territory.controller_character_id is None:
            logger.debug(f"Resource collection: Territory {territory.territory_id} has no controller, skipping")
            continue

        char_id = territory.controller_character_id

        # Initialize character entry if not exists
        if char_id not in character_resources:
            character_resources[char_id] = {
                'ore': 0,
                'lumber': 0,
                'coal': 0,
                'rations': 0,
                'cloth': 0
            }

        # Aggregate resources
        character_resources[char_id]['ore'] += territory.ore_production
        character_resources[char_id]['lumber'] += territory.lumber_production
        character_resources[char_id]['coal'] += territory.coal_production
        character_resources[char_id]['rations'] += territory.rations_production
        character_resources[char_id]['cloth'] += territory.cloth_production

    # Process each character's aggregated resources
    for char_id, resources in character_resources.items():
        # Fetch character
        character = await Character.fetch_by_id(conn, char_id)
        if not character:
            logger.warning(f"Resource collection: Character {char_id} not found, skipping resource allocation")
            continue

        # Check if character has any resources to collect
        total_resources = sum(resources.values())
        if total_resources == 0:
            logger.debug(f"Resource collection: Character {char_id} has no resources to collect")
            continue

        # Fetch or create PlayerResources
        player_resources = await PlayerResources.fetch_by_character(conn, char_id, guild_id)

        if not player_resources:
            # Create new PlayerResources entry
            player_resources = PlayerResources(
                character_id=char_id,
                ore=resources['ore'],
                lumber=resources['lumber'],
                coal=resources['coal'],
                rations=resources['rations'],
                cloth=resources['cloth'],
                guild_id=guild_id
            )
        else:
            # Add to existing resources
            player_resources.ore += resources['ore']
            player_resources.lumber += resources['lumber']
            player_resources.coal += resources['coal']
            player_resources.rations += resources['rations']
            player_resources.cloth += resources['cloth']

        # Update database
        await player_resources.upsert(conn)

        logger.info(f"Resource collection: Awarded {resources} to character {character.name} (ID: {char_id})")

        # Create single event for this character with aggregated resources
        events.append(TurnLog(
            turn_number=turn_number,
            phase='RESOURCE_COLLECTION',
            event_type='RESOURCE_COLLECTION',
            entity_type='character',
            entity_id=char_id,
            event_data={
                'affected_character_ids': [char_id],
                'character_name': character.name,
                'resources': {
                    'ore': resources['ore'],
                    'lumber': resources['lumber'],
                    'coal': resources['coal'],
                    'rations': resources['rations'],
                    'cloth': resources['cloth']
                }
            },
            guild_id=guild_id
        ))

    logger.info(f"Resource collection phase: finished for guild {guild_id}, turn {turn_number}. Processed {len(character_resources)} characters.")
    return events


async def execute_resource_transfer_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Resource Transfer phase.

    Processes resource transfer orders in priority sequence:
    1. CANCEL_TRANSFER orders (priority 0)
    2. PENDING RESOURCE_TRANSFER orders (priority 1) - one-time transfers
    3. ONGOING RESOURCE_TRANSFER orders (priority 1) - recurring transfers

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Resource transfer phase: starting for guild {guild_id}, turn {turn_number}")

    # Process CANCEL orders first (priority 0)
    cancel_orders = await Order.fetch_by_phase_status_and_type(
        conn, guild_id, TurnPhase.RESOURCE_TRANSFER.value,
        [OrderStatus.PENDING.value], OrderType.CANCEL_TRANSFER.value
    )
    for order in cancel_orders:
        result_events = await handle_cancel_transfer_order(conn, order, guild_id, turn_number)
        if result_events:
            events.extend(result_events)

    # Process PENDING resource transfers (priority 1) - these are one-time
    pending_transfers = await Order.fetch_by_phase_status_and_type(
        conn, guild_id, TurnPhase.RESOURCE_TRANSFER.value,
        [OrderStatus.PENDING.value], OrderType.RESOURCE_TRANSFER.value
    )
    for order in pending_transfers:
        result_events = await handle_resource_transfer_order(conn, order, guild_id, turn_number)
        if result_events:
            events.extend(result_events)

    # Process ONGOING resource transfers (priority 1) - these are recurring
    ongoing_transfers = await Order.fetch_by_phase_status_and_type(
        conn, guild_id, TurnPhase.RESOURCE_TRANSFER.value,
        [OrderStatus.ONGOING.value], OrderType.RESOURCE_TRANSFER.value
    )
    for order in ongoing_transfers:
        result_events = await handle_resource_transfer_order(conn, order, guild_id, turn_number)
        if result_events:
            events.extend(result_events)

    logger.info(f"Resource transfer phase: finished for guild {guild_id}, turn {turn_number}")
    return events


async def execute_encirclement_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Encirclement phase

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Encirclement phase: starting encirclement phase for guild {guild_id}, turn {turn_number}")

    # Placeholder for now

    logger.info(f"Encirclement phase: finished encirclement phase for guild {guild_id}, turn {turn_number}")
    return events

async def execute_upkeep_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Upkeep phase.

    For each unit:
    - Deduct upkeep from owner's resources
    - If insufficient resources, deduct what's available
    - Reduce organization by 1 for EACH missing resource unit
    - If organization <= 0, do nothing special (handled later)

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Upkeep phase: starting upkeep phase for guild {guild_id}, turn {turn_number}")

    # Fetch all units for the guild
    all_units = await Unit.fetch_all(conn, guild_id)
    if not all_units:
        logger.info(f"Upkeep phase: no units found for guild {guild_id}")
        logger.info(f"Upkeep phase: finished upkeep phase for guild {guild_id}, turn {turn_number}")
        return events

    # Group units by owner
    units_by_owner: Dict[int, List[Unit]] = {}
    for unit in all_units:
        owner_id = unit.owner_character_id
        if owner_id not in units_by_owner:
            units_by_owner[owner_id] = []
        units_by_owner[owner_id].append(unit)

    # Process upkeep for each owner
    resource_types = ['ore', 'lumber', 'coal', 'rations', 'cloth']

    for owner_id, units in units_by_owner.items():
        # Fetch owner character for name
        owner = await Character.fetch_by_id(conn, owner_id)
        if not owner:
            logger.warning(f"Upkeep phase: owner character {owner_id} not found, skipping units")
            continue

        # Fetch or create player resources
        resources = await PlayerResources.fetch_by_character(conn, owner_id, guild_id)
        if not resources:
            resources = PlayerResources(
                character_id=owner_id,
                ore=0, lumber=0, coal=0, rations=0, cloth=0,
                guild_id=guild_id
            )

        # Track total spent for summary event
        total_spent = {rt: 0 for rt in resource_types}
        units_maintained = 0

        for unit in units:
            unit_deficit = {}

            for rt in resource_types:
                needed = getattr(unit, f'upkeep_{rt}')
                available = getattr(resources, rt)
                deducted = min(needed, available)

                # Deduct from resources
                setattr(resources, rt, available - deducted)
                total_spent[rt] += deducted

                # Track deficit
                if deducted < needed:
                    unit_deficit[rt] = needed - deducted

            units_maintained += 1

            # If there was a deficit, penalize organization
            if unit_deficit:
                penalty = sum(unit_deficit.values())
                unit.organization -= penalty
                await unit.upsert(conn)

                events.append(TurnLog(
                    turn_number=turn_number,
                    phase=TurnPhase.UPKEEP.value,
                    event_type='UPKEEP_DEFICIT',
                    entity_type='unit',
                    entity_id=unit.id,
                    event_data={
                        'unit_id': unit.unit_id,
                        'unit_name': unit.name or unit.unit_id,
                        'resources_deficit': unit_deficit,
                        'organization_penalty': penalty,
                        'new_organization': unit.organization,
                        'affected_character_ids': [owner_id]
                    },
                    guild_id=guild_id
                ))
                logger.info(f"Upkeep phase: unit {unit.unit_id} deficit {unit_deficit}, org -{penalty} -> {unit.organization}")

        # Save updated resources
        await resources.upsert(conn)

        # Generate summary event if any resources were spent
        if any(total_spent[rt] > 0 for rt in resource_types):
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.UPKEEP.value,
                event_type='UPKEEP_SUMMARY',
                entity_type='character',
                entity_id=owner_id,
                event_data={
                    'character_name': owner.name,
                    'resources_spent': total_spent,
                    'units_maintained': units_maintained,
                    'affected_character_ids': [owner_id]
                },
                guild_id=guild_id
            ))
            logger.info(f"Upkeep phase: {owner.name} spent {total_spent} on {units_maintained} units")

    logger.info(f"Upkeep phase: finished upkeep phase for guild {guild_id}, turn {turn_number}")
    return events


async def execute_organization_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Organization phase

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Organization phase: starting organization phase for guild {guild_id}, turn {turn_number}")

    # Placeholder for now

    logger.info(f"Organization phase: finished organization phase for guild {guild_id}, turn {turn_number}")
    return events



async def execute_construction_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Construction phase

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Construction phase: starting construction phase for guild {guild_id}, turn {turn_number}")

    # Placeholder for now

    logger.info(f"Construction phase: finished construction phase for guild {guild_id}, turn {turn_number}")
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
        count = await Order.count_by_phase_and_status(
            conn, guild_id, phase.value, [OrderStatus.PENDING.value, OrderStatus.ONGOING.value]
        )
        pending_counts[phase.value] = count

    status_dict = {
        'current_turn': config.current_turn,
        'last_turn_time': config.last_turn_time.isoformat() if config.last_turn_time else None,
        'turn_resolution_enabled': config.turn_resolution_enabled,
        'pending_orders': pending_counts,
        'total_pending': sum(pending_counts.values())
    }

    return True, "Turn status retrieved.", status_dict
