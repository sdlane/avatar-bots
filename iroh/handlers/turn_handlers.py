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
from orders.victory_point_orders import handle_assign_victory_points_order
from orders.alliance_orders import handle_make_alliance_order

import logging

logger = logging.getLogger(__name__)

OrderHandlerMap: Dict[str, function] = {
    OrderType.LEAVE_FACTION.value: handle_leave_faction_order,
    OrderType.KICK_FROM_FACTION.value: handle_kick_from_faction_order,
    OrderType.JOIN_FACTION.value: handle_join_faction_order,
    OrderType.ASSIGN_COMMANDER.value: handle_assign_commander_order,
    OrderType.ASSIGN_VICTORY_POINTS.value: handle_assign_victory_points_order,
    OrderType.MAKE_ALLIANCE.value: handle_make_alliance_order,
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

async def _collect_character_production(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Collect resources from character production values.

    For each character with non-zero production, add resources to their inventory.
    Generates ONE event per character with non-zero production.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Character production: starting for guild {guild_id}, turn {turn_number}")

    # Fetch all characters in the guild
    characters = await Character.fetch_all(conn, guild_id)

    for character in characters:
        # Check if character has any production
        total_production = (
            character.ore_production + character.lumber_production +
            character.coal_production + character.rations_production +
            character.cloth_production + character.platinum_production
        )

        if total_production == 0:
            continue

        # Fetch or create PlayerResources
        player_resources = await PlayerResources.fetch_by_character(conn, character.id, guild_id)

        if not player_resources:
            # Create new PlayerResources entry
            player_resources = PlayerResources(
                character_id=character.id,
                ore=character.ore_production,
                lumber=character.lumber_production,
                coal=character.coal_production,
                rations=character.rations_production,
                cloth=character.cloth_production,
                platinum=character.platinum_production,
                guild_id=guild_id
            )
        else:
            # Add to existing resources
            player_resources.ore += character.ore_production
            player_resources.lumber += character.lumber_production
            player_resources.coal += character.coal_production
            player_resources.rations += character.rations_production
            player_resources.cloth += character.cloth_production
            player_resources.platinum += character.platinum_production

        # Update database
        await player_resources.upsert(conn)

        resources = {
            'ore': character.ore_production,
            'lumber': character.lumber_production,
            'coal': character.coal_production,
            'rations': character.rations_production,
            'cloth': character.cloth_production,
            'platinum': character.platinum_production
        }

        logger.info(f"Character production: Awarded {resources} to character {character.name} (ID: {character.id})")

        # Create event for this character
        events.append(TurnLog(
            turn_number=turn_number,
            phase='RESOURCE_COLLECTION',
            event_type='CHARACTER_PRODUCTION',
            entity_type='character',
            entity_id=character.id,
            event_data={
                'affected_character_ids': [character.id],
                'character_name': character.name,
                'resources': resources
            },
            guild_id=guild_id
        ))

    logger.info(f"Character production: finished for guild {guild_id}, turn {turn_number}. Processed {len(events)} characters.")
    return events


async def _collect_territory_production(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Collect resources from territory production.

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
    logger.info(f"Territory production: starting for guild {guild_id}, turn {turn_number}")

    # Fetch all territories in the guild
    territories = await Territory.fetch_all(conn, guild_id)

    # Dictionary to aggregate resources per character
    # Structure: {character_id: {ore: amount, lumber: amount, ...}}
    character_resources = {}

    for territory in territories:
        # Skip territories with no controller
        if territory.controller_character_id is None:
            logger.debug(f"Territory production: Territory {territory.territory_id} has no controller, skipping")
            continue

        char_id = territory.controller_character_id

        # Initialize character entry if not exists
        if char_id not in character_resources:
            character_resources[char_id] = {
                'ore': 0,
                'lumber': 0,
                'coal': 0,
                'rations': 0,
                'cloth': 0,
                'platinum': 0
            }

        # Aggregate resources
        character_resources[char_id]['ore'] += territory.ore_production
        character_resources[char_id]['lumber'] += territory.lumber_production
        character_resources[char_id]['coal'] += territory.coal_production
        character_resources[char_id]['rations'] += territory.rations_production
        character_resources[char_id]['cloth'] += territory.cloth_production
        character_resources[char_id]['platinum'] += territory.platinum_production

    # Process each character's aggregated resources
    for char_id, resources in character_resources.items():
        # Fetch character
        character = await Character.fetch_by_id(conn, char_id)
        if not character:
            logger.warning(f"Territory production: Character {char_id} not found, skipping resource allocation")
            continue

        # Check if character has any resources to collect
        total_resources = sum(resources.values())
        if total_resources == 0:
            logger.debug(f"Territory production: Character {char_id} has no resources to collect")
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
                platinum=resources['platinum'],
                guild_id=guild_id
            )
        else:
            # Add to existing resources
            player_resources.ore += resources['ore']
            player_resources.lumber += resources['lumber']
            player_resources.coal += resources['coal']
            player_resources.rations += resources['rations']
            player_resources.cloth += resources['cloth']
            player_resources.platinum += resources['platinum']

        # Update database
        await player_resources.upsert(conn)

        logger.info(f"Territory production: Awarded {resources} to character {character.name} (ID: {char_id})")

        # Create single event for this character with aggregated resources
        events.append(TurnLog(
            turn_number=turn_number,
            phase='RESOURCE_COLLECTION',
            event_type='TERRITORY_PRODUCTION',
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
                    'cloth': resources['cloth'],
                    'platinum': resources['platinum']
                }
            },
            guild_id=guild_id
        ))

    logger.info(f"Territory production: finished for guild {guild_id}, turn {turn_number}. Processed {len(character_resources)} characters.")
    return events


async def execute_resource_collection_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Resource Collection phase.

    1. Character production: Add resources based on character production values
    2. Territory production: Add resources based on controlled territories

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Resource collection phase: starting for guild {guild_id}, turn {turn_number}")

    # Character production first
    char_events = await _collect_character_production(conn, guild_id, turn_number)
    events.extend(char_events)

    # Territory production second
    territory_events = await _collect_territory_production(conn, guild_id, turn_number)
    events.extend(territory_events)

    logger.info(f"Resource collection phase: finished for guild {guild_id}, turn {turn_number}")
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

    # Group units by owner (only active units need upkeep)
    units_by_owner: Dict[int, List[Unit]] = {}
    for unit in all_units:
        if unit.status != 'ACTIVE':
            continue
        owner_id = unit.owner_character_id
        if owner_id not in units_by_owner:
            units_by_owner[owner_id] = []
        units_by_owner[owner_id].append(unit)

    # Process upkeep for each owner
    resource_types = ['ore', 'lumber', 'coal', 'rations', 'cloth', 'platinum']

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
                ore=0, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
                guild_id=guild_id
            )

        # Track total spent and deficits for summary events
        total_spent = {rt: 0 for rt in resource_types}
        total_deficit = {rt: 0 for rt in resource_types}
        units_maintained = 0
        units_with_deficit = 0

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
                    total_deficit[rt] += needed - deducted

            units_maintained += 1

            # If there was a deficit, penalize organization
            if unit_deficit:
                units_with_deficit += 1
                penalty = sum(unit_deficit.values())
                unit.organization -= penalty
                await unit.upsert(conn)

                # Build affected_character_ids - include commander if different from owner
                affected_ids = [owner_id]
                if unit.commander_character_id and unit.commander_character_id != owner_id:
                    affected_ids.append(unit.commander_character_id)

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
                        'owner_character_id': owner_id,
                        'owner_name': owner.name,
                        'affected_character_ids': affected_ids
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

        # Generate total deficit summary event if any deficits occurred
        if units_with_deficit > 0:
            non_zero_deficit = {rt: v for rt, v in total_deficit.items() if v > 0}
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.UPKEEP.value,
                event_type='UPKEEP_TOTAL_DEFICIT',
                entity_type='character',
                entity_id=owner_id,
                event_data={
                    'character_name': owner.name,
                    'total_deficit': non_zero_deficit,
                    'units_affected': units_with_deficit,
                    'affected_character_ids': [owner_id]
                },
                guild_id=guild_id
            ))
            logger.info(f"Upkeep phase: {owner.name} total deficit {non_zero_deficit} affecting {units_with_deficit} units")

    logger.info(f"Upkeep phase: finished upkeep phase for guild {guild_id}, turn {turn_number}")
    return events


async def disband_low_organization_units(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int,
    phase: str
) -> List[TurnLog]:
    """
    Disband all units with organization <= 0 by setting their status to DISBANDED.

    This function is designed to be reusable from multiple phases (ORGANIZATION, COMBAT).

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number
        phase: The phase calling this function (for event logging)

    Returns:
        List of TurnLog events for disbanded units
    """
    events = []

    # Fetch all units and filter for active ones with org <= 0
    all_units = await Unit.fetch_all(conn, guild_id)
    units_to_disband = [u for u in all_units if u.organization <= 0 and u.status == 'ACTIVE']

    for unit in units_to_disband:
        # Set status to DISBANDED
        unit.status = 'DISBANDED'
        await unit.upsert(conn)

        # Build affected_character_ids list
        affected_ids = [unit.owner_character_id]
        if unit.commander_character_id and unit.commander_character_id != unit.owner_character_id:
            affected_ids.append(unit.commander_character_id)

        # Fetch owner name for event
        owner = await Character.fetch_by_id(conn, unit.owner_character_id)
        owner_name = owner.name if owner else 'Unknown'

        # Create UNIT_DISBANDED event
        events.append(TurnLog(
            turn_number=turn_number,
            phase=phase,
            event_type='UNIT_DISBANDED',
            entity_type='unit',
            entity_id=unit.id,
            event_data={
                'unit_id': unit.unit_id,
                'unit_name': unit.name or unit.unit_id,
                'owner_character_id': unit.owner_character_id,
                'owner_name': owner_name,
                'final_organization': unit.organization,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

        logger.info(f"Organization phase: Disbanded unit {unit.unit_id} (org={unit.organization})")

    return events


async def recover_organization_in_friendly_territory(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Increase organization by 1 for units in territory controlled by their faction.

    "Territory controlled by faction" means:
    - territory.controller_character_id is a member of unit.faction_id

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for recovered units
    """
    events = []

    # Fetch all units and filter for active ones with faction and territory
    all_units = await Unit.fetch_all(conn, guild_id)
    active_units = [u for u in all_units if u.status == 'ACTIVE' and u.faction_id and u.current_territory_id is not None]

    for unit in active_units:
        # Skip if already at max organization
        if unit.organization >= unit.max_organization:
            continue

        # Fetch territory
        territory = await Territory.fetch_by_territory_id(conn, unit.current_territory_id, guild_id)
        if not territory or not territory.controller_character_id:
            continue

        # Check if territory controller is in unit's faction
        controller_faction = await FactionMember.fetch_by_character(conn, territory.controller_character_id, guild_id)
        if not controller_faction or controller_faction.faction_id != unit.faction_id:
            continue

        # Increase organization by 1 (capped at max)
        old_org = unit.organization
        unit.organization = min(unit.organization + 1, unit.max_organization)
        await unit.upsert(conn)

        # Build affected_character_ids
        affected_ids = [unit.owner_character_id]
        if unit.commander_character_id and unit.commander_character_id != unit.owner_character_id:
            affected_ids.append(unit.commander_character_id)

        # Create ORG_RECOVERY event
        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.ORGANIZATION.value,
            event_type='ORG_RECOVERY',
            entity_type='unit',
            entity_id=unit.id,
            event_data={
                'unit_id': unit.unit_id,
                'unit_name': unit.name or unit.unit_id,
                'old_organization': old_org,
                'new_organization': unit.organization,
                'territory_id': unit.current_territory_id,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

        logger.info(f"Organization phase: Unit {unit.unit_id} recovered org {old_org} -> {unit.organization}")

    return events


async def execute_organization_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Organization phase.

    1. Disband units with organization <= 0
    2. Recover organization for units in friendly territory

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Organization phase: starting organization phase for guild {guild_id}, turn {turn_number}")

    # Step 1: Disband units with organization <= 0
    disband_events = await disband_low_organization_units(
        conn, guild_id, turn_number, TurnPhase.ORGANIZATION.value
    )
    events.extend(disband_events)

    # Step 2: Recover organization for units in friendly territory
    recovery_events = await recover_organization_in_friendly_territory(
        conn, guild_id, turn_number
    )
    events.extend(recovery_events)

    logger.info(f"Organization phase: finished organization phase for guild {guild_id}, turn {turn_number}. "
                f"Disbanded {len(disband_events)} units, recovered {len(recovery_events)} units.")
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
