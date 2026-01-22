"""
Turn resolution handlers for the wargame system.
"""
import asyncpg
from typing import Tuple, List, Dict, Optional, Set
from datetime import datetime
from db import (
    Order, Unit, Character, Faction, FactionMember, Territory,
    PlayerResources, WargameConfig, TurnLog, FactionJoinRequest, War, WarParticipant,
    FactionResources, FactionPermission, Building
)
from order_types import *
from orders import *
from orders.resource_transfer_orders import (
    handle_cancel_transfer_order,
    handle_resource_transfer_order
)
from orders.victory_point_orders import handle_assign_victory_points_order
from orders.alliance_orders import handle_make_alliance_order, handle_dissolve_alliance_order
from orders.faction_orders import handle_declare_war_order
from orders.construction_orders import handle_mobilization_order, handle_construction_order
from handlers.movement_handlers import (
    build_movement_states,
    build_naval_transport_states,
    process_movement_tick,
    process_patrol_engagement,
    check_engagement,
    generate_observation_reports,
    finalize_movement_order,
    process_transport_boarding,
    process_transport_disembarkation,
    process_transport_movement_tick,
)
from handlers.naval_movement_handlers import (
    execute_naval_movement_phase,
)
from handlers.combat_handlers import execute_combat_phase as _execute_combat_phase
from handlers.encirclement_handlers import (
    check_unit_encircled,
    get_unit_home_faction_id,
    get_affected_character_ids_for_unit,
)
from orders.movement_state import MovementStatus


def deduplicate_observation_events(obs_events: List[TurnLog]) -> List[TurnLog]:
    """
    Deduplicate observation events - keep only one event per (recipient, observed_unit) pair.

    When multiple observer units belonging to the same character see the same target,
    we only want to report it once to that character.

    Args:
        obs_events: List of UNIT_OBSERVED TurnLog events

    Returns:
        Deduplicated list of events
    """
    final_obs_events = {}
    for event in obs_events:
        recipient_id = event.event_data['affected_character_ids'][0]
        observed_unit_id = event.event_data['observed_unit_id']
        tick = event.event_data.get('tick', 0) or 0
        key = (recipient_id, observed_unit_id)

        # Keep the event with the highest tick (most recent observation)
        if key not in final_obs_events or tick >= final_obs_events[key].event_data.get('tick', 0):
            final_obs_events[key] = event

    return list(final_obs_events.values())

import logging

logger = logging.getLogger(__name__)

OrderHandlerMap: Dict[str, function] = {
    OrderType.LEAVE_FACTION.value: handle_leave_faction_order,
    OrderType.KICK_FROM_FACTION.value: handle_kick_from_faction_order,
    OrderType.JOIN_FACTION.value: handle_join_faction_order,
    OrderType.ASSIGN_COMMANDER.value: handle_assign_commander_order,
    OrderType.ASSIGN_VICTORY_POINTS.value: handle_assign_victory_points_order,
    OrderType.MAKE_ALLIANCE.value: handle_make_alliance_order,
    OrderType.DISSOLVE_ALLIANCE.value: handle_dissolve_alliance_order,
    OrderType.DECLARE_WAR.value: handle_declare_war_order,
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

    encirclement_events, encircled_unit_ids = await execute_encirclement_phase(conn, guild_id, turn_number)
    all_events.extend(encirclement_events)

    upkeep_events = await execute_upkeep_phase(conn, guild_id, turn_number, encircled_unit_ids)
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

    Algorithm:
    1. SETUP - Fetch UNIT orders, separate land and naval transport orders, build states
    2. PRE-TICK - Process transport disembarkation, then boarding
    3. PRE-TICK - Check initial engagement
    4. TICK LOOP - For each tick from max_mp down to 1:
       a. Process patrol engagement
       b. Process transport movement (transported land units move through water)
       c. Process regular land movement (skip TRANSPORTED units)
       d. Check engagement (skip TRANSPORTED units)
       e. Generate observation reports
    5. POST-LOOP - Final engagement, observation reports
    6. FINALIZE - Update orders, generate events

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Movement phase: starting movement phase for guild {guild_id}, turn {turn_number}")

    # 0. NAVAL MOVEMENT - Process naval positioning first (before land movement)
    naval_events = await execute_naval_movement_phase(conn, guild_id, turn_number)
    events.extend(naval_events)
    logger.info(f"Movement phase: naval movement generated {len(naval_events)} events")

    # 1. SETUP - Fetch PENDING/ONGOING UNIT orders for MOVEMENT phase
    all_orders = await Order.fetch_unresolved_by_phase(
        conn, guild_id, TurnPhase.MOVEMENT.value
    )

    # Filter to UNIT type orders only
    unit_orders = [o for o in all_orders if o.order_type == OrderType.UNIT.value]

    if not unit_orders:
        logger.info(f"Movement phase: no unit orders to process for guild {guild_id}")
        # Still generate observation reports for stationary units
        obs_events, _ = await generate_observation_reports(conn, [], guild_id, turn_number, tick=0)
        events.extend(deduplicate_observation_events(obs_events))
        logger.info(f"Movement phase: finished movement phase for guild {guild_id}, turn {turn_number}")
        return events

    # Separate land orders from naval orders
    # Naval actions start with 'naval_' - they should not go through land movement processing
    land_orders = [o for o in unit_orders if not o.order_data.get('action', '').startswith('naval_')]
    naval_transport_orders = [o for o in unit_orders if o.order_data.get('action') == 'naval_transport']
    # Note: Other naval actions (naval_transit, naval_patrol, etc.) are currently not processed
    # in the movement phase - naval movement is not yet implemented

    logger.info(f"Movement phase: processing {len(land_orders)} land orders, "
                f"{len(naval_transport_orders)} naval transport orders for guild {guild_id}")

    # Build land movement states (validates orders, fails invalid ones)
    land_states, failed_events = await build_movement_states(conn, land_orders, guild_id)
    events.extend(failed_events)

    # Build naval transport states
    naval_states, naval_failed_events = await build_naval_transport_states(conn, naval_transport_orders, guild_id)
    events.extend(naval_failed_events)

    # Combine for max_ticks calculation
    all_states = land_states + naval_states

    if not land_states and not naval_states:
        logger.info(f"Movement phase: no valid movement states after validation")
        # Still generate observation reports for stationary units
        obs_events, _ = await generate_observation_reports(conn, [], guild_id, turn_number, tick=0)
        events.extend(deduplicate_observation_events(obs_events))
        logger.info(f"Movement phase: finished movement phase for guild {guild_id}, turn {turn_number}")
        return events

    # Sort land states by total_movement_points DESC, then order.id ASC (oldest first for ties)
    land_states.sort(key=lambda s: (-s.total_movement_points, s.order.id))

    # 2. PRE-TICK - Process transport disembarkation first (for units already transported)
    disembark_events = await process_transport_disembarkation(conn, land_states, guild_id, turn_number)
    events.extend(disembark_events)
    logger.info(f"Movement phase: processed {len(disembark_events)} disembarkations")

    # 2. PRE-TICK - Process transport boarding
    boarding_events = await process_transport_boarding(conn, land_states, naval_states, guild_id, turn_number)
    events.extend(boarding_events)
    logger.info(f"Movement phase: processed {len(boarding_events)} boarding events")

    # 3. PRE-TICK - Check initial engagement - units starting in same territory as hostiles can't move
    # Only check non-transported land units
    non_transported_states = [s for s in land_states if s.status != MovementStatus.TRANSPORTED]
    initial_engagement_events = await check_engagement(conn, non_transported_states, turn_number, guild_id)
    events.extend(initial_engagement_events)
    logger.info(f"Movement phase: initial engagement check found {len(initial_engagement_events)} engagements")

    # Calculate max_ticks as the highest total_movement_points
    if all_states:
        max_ticks = max(s.total_movement_points for s in all_states)
    else:
        max_ticks = 0
    logger.info(f"Movement phase: max_ticks={max_ticks}, processing {len(land_states)} land states, "
                f"{len(naval_states)} naval states")

    # Initialize observation tracker for deduplication
    # Tracks (recipient_char_id, observed_unit_id) -> tick
    observation_tracker = {}
    all_obs_events = []

    # 4. TICK LOOP - From max_ticks down to 1
    for tick in range(max_ticks, 0, -1):
        logger.debug(f"Movement phase: tick {tick}")

        # a. Process patrol engagement
        non_transported_states = [s for s in land_states if s.status != MovementStatus.TRANSPORTED]
        patrol_events = await process_patrol_engagement(conn, non_transported_states, guild_id, turn_number)
        events.extend(patrol_events)

        # b. Process transport movement (transported land units move through water)
        transport_tick_events = await process_transport_movement_tick(
            conn, land_states, naval_states, tick, guild_id, turn_number
        )
        events.extend(transport_tick_events)

        # c. Process regular land movement (skip TRANSPORTED units)
        non_transported_states = [s for s in land_states if s.status != MovementStatus.TRANSPORTED]
        tick_events = await process_movement_tick(conn, non_transported_states, tick, guild_id)
        events.extend(tick_events)

        # d. Check engagement (skip TRANSPORTED units - they're on water)
        non_transported_states = [s for s in land_states if s.status != MovementStatus.TRANSPORTED]
        engagement_events = await check_engagement(conn, non_transported_states, turn_number, guild_id)
        events.extend(engagement_events)

        # e. Generate observation reports (include all states for observation)
        obs_events, observation_tracker = await generate_observation_reports(
            conn, land_states, guild_id, turn_number, tick, observation_tracker
        )
        all_obs_events.extend(obs_events)

    # 5. POST-LOOP - Run engagement and observation one more time
    non_transported_states = [s for s in land_states if s.status != MovementStatus.TRANSPORTED]
    patrol_events = await process_patrol_engagement(conn, non_transported_states, guild_id, turn_number)
    events.extend(patrol_events)
    engagement_events = await check_engagement(conn, non_transported_states, turn_number, guild_id)
    events.extend(engagement_events)
    obs_events, observation_tracker = await generate_observation_reports(
        conn, land_states, guild_id, turn_number, 0, observation_tracker
    )
    all_obs_events.extend(obs_events)

    # Deduplicate observation events - keep only one per (recipient, observed_unit)
    events.extend(deduplicate_observation_events(all_obs_events))

    # 6. FINALIZE - Update orders and generate completion events
    for state in land_states:
        final_event = await finalize_movement_order(conn, state, turn_number, guild_id)
        events.append(final_event)

    # Also finalize naval transport orders
    for state in naval_states:
        final_event = await finalize_movement_order(conn, state, turn_number, guild_id)
        events.append(final_event)

    logger.info(f"Movement phase: finished movement phase for guild {guild_id}, turn {turn_number}. "
                f"Generated {len(events)} events.")
    return events


async def execute_combat_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Combat phase.

    Delegates to combat_handlers.execute_combat_phase for actual implementation.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    return await _execute_combat_phase(conn, guild_id, turn_number)

async def _collect_character_production(
    conn: asyncpg.Connection,
    guild_id: int,
    character_resources: dict
) -> None:
    """
    Collect resources from character production values into the character_resources dict.

    For each character with non-zero production, add resources to their inventory
    and accumulate in character_resources dict for later event creation.

    Args:
        conn: Database connection
        guild_id: Guild ID
        character_resources: Dict to accumulate {character_id: {'name': str, 'resources': dict}}
    """
    logger.info(f"Character production: starting for guild {guild_id}")

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

        # Initialize character entry if not exists
        if character.id not in character_resources:
            character_resources[character.id] = {
                'name': character.name,
                'resources': {
                    'ore': 0, 'lumber': 0, 'coal': 0,
                    'rations': 0, 'cloth': 0, 'platinum': 0
                }
            }

        # Accumulate resources
        character_resources[character.id]['resources']['ore'] += character.ore_production
        character_resources[character.id]['resources']['lumber'] += character.lumber_production
        character_resources[character.id]['resources']['coal'] += character.coal_production
        character_resources[character.id]['resources']['rations'] += character.rations_production
        character_resources[character.id]['resources']['cloth'] += character.cloth_production
        character_resources[character.id]['resources']['platinum'] += character.platinum_production

        logger.info(f"Character production: Added production for character {character.name} (ID: {character.id})")

    logger.info(f"Character production: finished for guild {guild_id}")


async def _collect_territory_production(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int,
    character_resources: dict
) -> List[TurnLog]:
    """
    Collect resources from territory production.

    For each territory, give production to the character or faction controlling it.
    Character resources are accumulated into the shared character_resources dict.
    Returns events only for faction territory production.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number
        character_resources: Dict to accumulate {character_id: {'name': str, 'resources': dict}}

    Returns:
        List of TurnLog objects (faction events only)
    """
    events = []
    logger.info(f"Territory production: starting for guild {guild_id}, turn {turn_number}")

    # Fetch all territories in the guild
    territories = await Territory.fetch_all(conn, guild_id)

    # Dictionary to aggregate territory resources per character (for DB update)
    territory_char_resources = {}

    # Dictionary to aggregate resources per faction
    # Structure: {faction_id: {ore: amount, lumber: amount, ...}}
    faction_resources = {}

    for territory in territories:
        # Check controller type using helper method
        owner_type = territory.get_owner_type()

        if owner_type is None:
            logger.debug(f"Territory production: Territory {territory.territory_id} has no controller, skipping")
            continue

        if owner_type == 'character':
            char_id = territory.controller_character_id

            # Initialize character entry if not exists
            if char_id not in territory_char_resources:
                territory_char_resources[char_id] = {
                    'ore': 0,
                    'lumber': 0,
                    'coal': 0,
                    'rations': 0,
                    'cloth': 0,
                    'platinum': 0
                }

            # Aggregate resources
            territory_char_resources[char_id]['ore'] += territory.ore_production
            territory_char_resources[char_id]['lumber'] += territory.lumber_production
            territory_char_resources[char_id]['coal'] += territory.coal_production
            territory_char_resources[char_id]['rations'] += territory.rations_production
            territory_char_resources[char_id]['cloth'] += territory.cloth_production
            territory_char_resources[char_id]['platinum'] += territory.platinum_production

        elif owner_type == 'faction':
            faction_id = territory.controller_faction_id

            # Initialize faction entry if not exists
            if faction_id not in faction_resources:
                faction_resources[faction_id] = {
                    'ore': 0,
                    'lumber': 0,
                    'coal': 0,
                    'rations': 0,
                    'cloth': 0,
                    'platinum': 0
                }

            # Aggregate resources
            faction_resources[faction_id]['ore'] += territory.ore_production
            faction_resources[faction_id]['lumber'] += territory.lumber_production
            faction_resources[faction_id]['coal'] += territory.coal_production
            faction_resources[faction_id]['rations'] += territory.rations_production
            faction_resources[faction_id]['cloth'] += territory.cloth_production
            faction_resources[faction_id]['platinum'] += territory.platinum_production

    # Process each character's aggregated territory resources
    for char_id, resources in territory_char_resources.items():
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

        # Accumulate into shared character_resources dict for combined event creation
        if char_id not in character_resources:
            character_resources[char_id] = {
                'name': character.name,
                'resources': {
                    'ore': 0, 'lumber': 0, 'coal': 0,
                    'rations': 0, 'cloth': 0, 'platinum': 0
                }
            }

        character_resources[char_id]['resources']['ore'] += resources['ore']
        character_resources[char_id]['resources']['lumber'] += resources['lumber']
        character_resources[char_id]['resources']['coal'] += resources['coal']
        character_resources[char_id]['resources']['rations'] += resources['rations']
        character_resources[char_id]['resources']['cloth'] += resources['cloth']
        character_resources[char_id]['resources']['platinum'] += resources['platinum']

    # Process each faction's aggregated resources
    for faction_id, resources in faction_resources.items():
        # Fetch faction
        faction = await Faction.fetch_by_id(conn, faction_id)
        if not faction:
            logger.warning(f"Territory production: Faction {faction_id} not found, skipping resource allocation")
            continue

        # Check if faction has any resources to collect
        total_resources = sum(resources.values())
        if total_resources == 0:
            logger.debug(f"Territory production: Faction {faction_id} has no resources to collect")
            continue

        # Fetch or create FactionResources
        faction_res = await FactionResources.fetch_by_faction(conn, faction_id, guild_id)

        if not faction_res:
            # Create new FactionResources entry
            faction_res = FactionResources(
                faction_id=faction_id,
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
            faction_res.ore += resources['ore']
            faction_res.lumber += resources['lumber']
            faction_res.coal += resources['coal']
            faction_res.rations += resources['rations']
            faction_res.cloth += resources['cloth']
            faction_res.platinum += resources['platinum']

        # Update database
        await faction_res.upsert(conn)

        logger.info(f"Territory production: Awarded {resources} to faction {faction.name} (ID: {faction_id})")

        # Get affected character IDs - faction leader and those with FINANCIAL permission see resource events
        affected_char_ids = await FactionPermission.fetch_characters_with_permission(
            conn, faction_id, "FINANCIAL", guild_id
        )
        # Also include faction leader
        if faction.leader_character_id and faction.leader_character_id not in affected_char_ids:
            affected_char_ids.append(faction.leader_character_id)

        # Create single event for this faction with aggregated resources
        events.append(TurnLog(
            turn_number=turn_number,
            phase='RESOURCE_COLLECTION',
            event_type='FACTION_TERRITORY_PRODUCTION',
            entity_type='faction',
            entity_id=faction_id,
            event_data={
                'affected_character_ids': affected_char_ids,
                'faction_id': faction.faction_id,
                'faction_name': faction.name,
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

    logger.info(f"Territory production: finished for guild {guild_id}, turn {turn_number}. "
                f"Processed {len(character_resources)} characters and {len(faction_resources)} factions.")
    return events


async def _apply_first_war_production_bonus(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int,
    character_resources: dict
) -> Dict[int, dict]:
    """
    Apply the first-war production bonus to factions that declared their first war this turn.

    Doubles all production for all members of the faction. Updates the database and
    accumulates bonus resources into the character_resources dict for consolidated reporting.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number
        character_resources: Dict to accumulate {character_id: {'name': str, 'resources': dict}}

    Returns:
        Dict mapping character_id to bonus info: {char_id: {'faction_name': str, 'bonus': dict}}
    """
    bonus_info = {}
    logger.info(f"First-war bonus: checking for bonuses for guild {guild_id}, turn {turn_number}")

    # Find all DECLARE_WAR orders from this turn that have first_war_bonus=True
    all_orders = await Order.fetch_by_type_and_turn(
        conn, guild_id, OrderType.DECLARE_WAR.value, turn_number
    )

    bonus_faction_ids = set()
    for order in all_orders:
        if order.status == OrderStatus.SUCCESS.value and order.result_data:
            if order.result_data.get('first_war_bonus'):
                submitting_faction_id = order.order_data.get('submitting_faction_id')
                if submitting_faction_id:
                    bonus_faction_ids.add(submitting_faction_id)

    if not bonus_faction_ids:
        logger.info(f"First-war bonus: no bonuses to apply for guild {guild_id}, turn {turn_number}")
        return bonus_info

    # For each faction with bonus, double all faction members' production
    for faction_id in bonus_faction_ids:
        faction = await Faction.fetch_by_id(conn, faction_id)
        if not faction:
            continue

        members = await FactionMember.fetch_by_faction(conn, faction_id, guild_id)

        for member in members:
            character = await Character.fetch_by_id(conn, member.character_id)
            if not character:
                continue

            # Get current resources (after normal production was added)
            player_resources = await PlayerResources.fetch_by_character(conn, member.character_id, guild_id)
            if not player_resources:
                continue

            # Calculate bonus from personal production values
            bonus = {
                'ore': character.ore_production,
                'lumber': character.lumber_production,
                'coal': character.coal_production,
                'rations': character.rations_production,
                'cloth': character.cloth_production,
                'platinum': character.platinum_production
            }

            # Also include territory production for territories this character controls directly
            territories = await Territory.fetch_by_controller(conn, character.id, guild_id)
            for territory in territories:
                bonus['ore'] += territory.ore_production
                bonus['lumber'] += territory.lumber_production
                bonus['coal'] += territory.coal_production
                bonus['rations'] += territory.rations_production
                bonus['cloth'] += territory.cloth_production
                bonus['platinum'] += territory.platinum_production

            # Add bonus resources to database
            player_resources.ore += bonus['ore']
            player_resources.lumber += bonus['lumber']
            player_resources.coal += bonus['coal']
            player_resources.rations += bonus['rations']
            player_resources.cloth += bonus['cloth']
            player_resources.platinum += bonus['platinum']
            await player_resources.upsert(conn)

            total_bonus = sum(bonus.values())
            if total_bonus > 0:
                logger.info(f"First-war bonus: Doubled production for {character.name}: {bonus}")

                # Accumulate bonus into character_resources for consolidated event creation
                if character.id not in character_resources:
                    character_resources[character.id] = {
                        'name': character.name,
                        'resources': {
                            'ore': 0, 'lumber': 0, 'coal': 0,
                            'rations': 0, 'cloth': 0, 'platinum': 0
                        }
                    }

                character_resources[character.id]['resources']['ore'] += bonus['ore']
                character_resources[character.id]['resources']['lumber'] += bonus['lumber']
                character_resources[character.id]['resources']['coal'] += bonus['coal']
                character_resources[character.id]['resources']['rations'] += bonus['rations']
                character_resources[character.id]['resources']['cloth'] += bonus['cloth']
                character_resources[character.id]['resources']['platinum'] += bonus['platinum']

                # Track bonus info for this character
                bonus_info[character.id] = {
                    'faction_name': faction.name,
                    'bonus': bonus
                }

        logger.info(f"First-war bonus: Applied double production to faction {faction.name}")

    return bonus_info


async def execute_resource_collection_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Resource Collection phase.

    1. Character production: Add resources based on character production values
    2. Territory production: Add resources based on controlled territories
    3. First-war bonus: Double production for factions that declared their first war this turn

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Resource collection phase: starting for guild {guild_id}, turn {turn_number}")

    # Shared dict to accumulate all character resources from both production sources
    # Structure: {character_id: {'name': str, 'resources': {ore: int, ...}}}
    character_resources = {}

    # Character production - accumulates into character_resources
    await _collect_character_production(conn, guild_id, character_resources)

    # Territory production - accumulates character resources into shared dict, returns faction events
    faction_events = await _collect_territory_production(conn, guild_id, turn_number, character_resources)

    # Apply first-war production bonus (doubles production for those who qualify)
    # This also accumulates bonus into character_resources and returns bonus info per character
    war_bonus_info = await _apply_first_war_production_bonus(conn, guild_id, turn_number, character_resources)

    # Create combined events for each character (one event per character with all resources)
    for char_id, data in character_resources.items():
        total = sum(data['resources'].values())
        if total == 0:
            continue

        event_data = {
            'affected_character_ids': [char_id],
            'character_name': data['name'],
            'resources': data['resources']
        }

        # Include war bonus info if this character received the bonus
        if char_id in war_bonus_info:
            event_data['war_bonus'] = war_bonus_info[char_id]

        events.append(TurnLog(
            turn_number=turn_number,
            phase='RESOURCE_COLLECTION',
            event_type='CHARACTER_PRODUCTION',
            entity_type='character',
            entity_id=char_id,
            event_data=event_data,
            guild_id=guild_id
        ))

    # Add faction territory production events
    events.extend(faction_events)

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
) -> Tuple[List[TurnLog], Set[int]]:
    """
    Execute the Encirclement phase.

    A land unit is encircled if no path exists over land through friendly/allied/neutral
    territories to a territory controlled by its home faction or an ally.

    Encircled units:
    - Cannot have resources spent on them during upkeep
    - Lose organization during upkeep (penalty = count of resource types in upkeep)

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        Tuple of (List of TurnLog objects, Set of encircled unit internal IDs)
    """
    events = []
    encircled_unit_ids: Set[int] = set()
    logger.info(f"Encirclement phase: starting encirclement phase for guild {guild_id}, turn {turn_number}")

    # Fetch all units in the guild
    all_units = await Unit.fetch_all(conn, guild_id)

    # Filter to active land units only
    land_units = [u for u in all_units if not u.is_naval and u.status == 'ACTIVE']

    logger.info(f"Encirclement phase: checking {len(land_units)} active land units")

    for unit in land_units:
        # Check if unit is encircled
        is_encircled = await check_unit_encircled(conn, unit, guild_id)

        if is_encircled:
            encircled_unit_ids.add(unit.id)

            # Get home faction for event data
            home_faction_id = await get_unit_home_faction_id(conn, unit, guild_id)

            # Get affected character IDs for notifications
            affected_ids = await get_affected_character_ids_for_unit(conn, unit, guild_id)

            # Generate UNIT_ENCIRCLED event
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.ENCIRCLEMENT.value,
                event_type='UNIT_ENCIRCLED',
                entity_type='unit',
                entity_id=unit.id,
                event_data={
                    'unit_id': unit.unit_id,
                    'unit_name': unit.name or unit.unit_id,
                    'territory_id': unit.current_territory_id,
                    'home_faction_id': home_faction_id,
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))

            logger.info(f"Encirclement phase: unit {unit.unit_id} at {unit.current_territory_id} is ENCIRCLED")

    logger.info(f"Encirclement phase: finished encirclement phase for guild {guild_id}, turn {turn_number}. "
                f"{len(encircled_unit_ids)} units encircled.")
    return events, encircled_unit_ids


async def execute_faction_spending(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute faction spending deductions BEFORE unit upkeep.

    For each faction with non-zero spending:
    - Deduct spending amounts from faction resources
    - If insufficient resources, deduct what's available
    - Generate FACTION_SPENDING event
    - Generate FACTION_SPENDING_PARTIAL if any resource was insufficient

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events
    """
    events = []
    logger.info(f"Faction spending: starting faction spending for guild {guild_id}, turn {turn_number}")

    # Fetch all factions
    factions = await Faction.fetch_all(conn, guild_id)
    if not factions:
        logger.info(f"Faction spending: no factions found for guild {guild_id}")
        return events

    resource_types = ['ore', 'lumber', 'coal', 'rations', 'cloth', 'platinum']

    for faction in factions:
        # Check if faction has any spending configured
        spending = {
            'ore': faction.ore_spending,
            'lumber': faction.lumber_spending,
            'coal': faction.coal_spending,
            'rations': faction.rations_spending,
            'cloth': faction.cloth_spending,
            'platinum': faction.platinum_spending
        }

        total_spending = sum(spending.values())
        if total_spending == 0:
            continue

        # Fetch faction resources
        resources = await FactionResources.fetch_by_faction(conn, faction.id, guild_id)
        if not resources:
            resources = FactionResources(
                faction_id=faction.id,
                ore=0, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
                guild_id=guild_id
            )

        # Deduct spending from resources
        amounts_spent = {}
        shortfall = {}

        for rt in resource_types:
            needed = spending[rt]
            if needed == 0:
                continue

            available = getattr(resources, rt)
            deducted = min(needed, available)
            setattr(resources, rt, available - deducted)

            if deducted > 0:
                amounts_spent[rt] = deducted

            if deducted < needed:
                shortfall[rt] = needed - deducted

        # Save updated resources
        await resources.upsert(conn)

        # Get affected character IDs (those with FINANCIAL permission)
        affected_ids = []
        permissions = await FactionPermission.fetch_by_faction(conn, faction.id, guild_id)
        for perm in permissions:
            if perm.permission_type == 'FINANCIAL' and perm.character_id not in affected_ids:
                affected_ids.append(perm.character_id)

        # Generate FACTION_SPENDING event if any resources were spent
        if amounts_spent:
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.UPKEEP.value,
                event_type='FACTION_SPENDING',
                entity_type='faction',
                entity_id=faction.id,
                event_data={
                    'faction_id': faction.faction_id,
                    'faction_name': faction.name,
                    'amounts_spent': amounts_spent,
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))
            logger.info(f"Faction spending: {faction.name} spent {amounts_spent}")

        # Generate FACTION_SPENDING_PARTIAL event if there was any shortfall
        if shortfall:
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.UPKEEP.value,
                event_type='FACTION_SPENDING_PARTIAL',
                entity_type='faction',
                entity_id=faction.id,
                event_data={
                    'faction_id': faction.faction_id,
                    'faction_name': faction.name,
                    'shortfall': shortfall,
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))
            logger.info(f"Faction spending: {faction.name} shortfall {shortfall}")

    logger.info(f"Faction spending: finished faction spending for guild {guild_id}, turn {turn_number}")
    return events


async def execute_building_upkeep(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute building upkeep. Buildings are processed:
    - Lowest durability first
    - Then by territory_id (ascending)
    - Then by id (oldest first)

    Durability penalty = count of different resource TYPES missing (not amounts).

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events
    """
    events = []
    logger.info(f"Building upkeep: starting for guild {guild_id}, turn {turn_number}")

    # Fetch all active buildings sorted for upkeep processing
    buildings = await Building.fetch_active_for_upkeep(conn, guild_id)
    if not buildings:
        logger.info(f"Building upkeep: no active buildings found for guild {guild_id}")
        return events

    resource_types = ['ore', 'lumber', 'coal', 'rations', 'cloth', 'platinum']

    for building in buildings:
        # Skip buildings with no upkeep
        total_upkeep = (
            building.upkeep_ore + building.upkeep_lumber + building.upkeep_coal +
            building.upkeep_rations + building.upkeep_cloth + building.upkeep_platinum
        )
        if total_upkeep == 0:
            continue

        # Find the territory to determine controller
        territory = await Territory.fetch_by_territory_id(conn, building.territory_id, guild_id)
        if not territory:
            logger.warning(f"Building upkeep: territory {building.territory_id} not found for building {building.building_id}")
            # Building in nonexistent territory - all upkeep is deficit
            deficit_types = []
            for rt in resource_types:
                if getattr(building, f'upkeep_{rt}') > 0:
                    deficit_types.append(rt)

            if deficit_types:
                durability_penalty = len(deficit_types)
                building.durability -= durability_penalty
                await building.upsert(conn)

                events.append(TurnLog(
                    turn_number=turn_number,
                    phase=TurnPhase.UPKEEP.value,
                    event_type='BUILDING_UPKEEP_DEFICIT',
                    entity_type='building',
                    entity_id=building.id,
                    event_data={
                        'building_id': building.building_id,
                        'building_name': building.name,
                        'territory_id': building.territory_id,
                        'deficit_types': deficit_types,
                        'durability_penalty': durability_penalty,
                        'new_durability': building.durability,
                        'affected_character_ids': []
                    },
                    guild_id=guild_id
                ))
            continue

        # Determine controller (character or faction)
        owner_type = territory.get_owner_type()
        resources = None
        affected_character_ids = []

        if owner_type == 'character':
            controller_id = territory.controller_character_id
            resources = await PlayerResources.fetch_by_character(conn, controller_id, guild_id)
            if not resources:
                resources = PlayerResources(
                    character_id=controller_id,
                    ore=0, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
                    guild_id=guild_id
                )
            affected_character_ids = [controller_id]

        elif owner_type == 'faction':
            faction_id = territory.controller_faction_id
            resources = await FactionResources.fetch_by_faction(conn, faction_id, guild_id)
            if not resources:
                resources = FactionResources(
                    faction_id=faction_id,
                    ore=0, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
                    guild_id=guild_id
                )
            # Get characters with FINANCIAL permission for notifications
            affected_character_ids = await FactionPermission.fetch_characters_with_permission(
                conn, faction_id, "FINANCIAL", guild_id
            )

        else:
            # Uncontrolled territory - all upkeep is deficit
            deficit_types = []
            for rt in resource_types:
                if getattr(building, f'upkeep_{rt}') > 0:
                    deficit_types.append(rt)

            if deficit_types:
                durability_penalty = len(deficit_types)
                building.durability -= durability_penalty
                await building.upsert(conn)

                events.append(TurnLog(
                    turn_number=turn_number,
                    phase=TurnPhase.UPKEEP.value,
                    event_type='BUILDING_UPKEEP_DEFICIT',
                    entity_type='building',
                    entity_id=building.id,
                    event_data={
                        'building_id': building.building_id,
                        'building_name': building.name,
                        'territory_id': building.territory_id,
                        'deficit_types': deficit_types,
                        'durability_penalty': durability_penalty,
                        'new_durability': building.durability,
                        'affected_character_ids': []
                    },
                    guild_id=guild_id
                ))
            continue

        # Process upkeep payment
        resources_paid = {}
        deficit_types = []

        for rt in resource_types:
            needed = getattr(building, f'upkeep_{rt}')
            if needed == 0:
                continue

            available = getattr(resources, rt)
            deducted = min(needed, available)
            setattr(resources, rt, available - deducted)

            if deducted > 0:
                resources_paid[rt] = deducted

            if deducted < needed:
                deficit_types.append(rt)

        # Save updated resources
        await resources.upsert(conn)

        # Generate appropriate event
        if deficit_types:
            durability_penalty = len(deficit_types)
            building.durability -= durability_penalty
            await building.upsert(conn)

            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.UPKEEP.value,
                event_type='BUILDING_UPKEEP_DEFICIT',
                entity_type='building',
                entity_id=building.id,
                event_data={
                    'building_id': building.building_id,
                    'building_name': building.name,
                    'territory_id': building.territory_id,
                    'resources_paid': resources_paid,
                    'deficit_types': deficit_types,
                    'durability_penalty': durability_penalty,
                    'new_durability': building.durability,
                    'affected_character_ids': affected_character_ids
                },
                guild_id=guild_id
            ))
            logger.info(f"Building upkeep: {building.building_id} deficit types {deficit_types}, durability -{durability_penalty} -> {building.durability}")

        elif resources_paid:
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.UPKEEP.value,
                event_type='BUILDING_UPKEEP_PAID',
                entity_type='building',
                entity_id=building.id,
                event_data={
                    'building_id': building.building_id,
                    'building_name': building.name,
                    'territory_id': building.territory_id,
                    'resources_paid': resources_paid,
                    'affected_character_ids': affected_character_ids
                },
                guild_id=guild_id
            ))
            logger.info(f"Building upkeep: {building.building_id} paid {resources_paid}")

    logger.info(f"Building upkeep: finished for guild {guild_id}, turn {turn_number}")
    return events


async def execute_upkeep_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int,
    encircled_unit_ids: Optional[Set[int]] = None
) -> List[TurnLog]:
    """
    Execute the Upkeep phase.

    For each unit (character-owned or faction-owned):
    - If encircled: skip resource deduction, reduce organization by count of upkeep resource types
    - Otherwise: deduct upkeep from owner's resources (PlayerResources or FactionResources)
    - If insufficient resources, deduct what's available
    - Reduce organization by 1 for EACH missing resource TYPE
    - If organization <= 0, do nothing special (handled later)

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number
        encircled_unit_ids: Optional set of unit IDs that are encircled (skip upkeep, penalize org)

    Returns:
        List of TurnLog objects
    """
    if encircled_unit_ids is None:
        encircled_unit_ids = set()
    events = []
    logger.info(f"Upkeep phase: starting upkeep phase for guild {guild_id}, turn {turn_number}")

    # Process faction spending first, before unit upkeep
    spending_events = await execute_faction_spending(conn, guild_id, turn_number)
    events.extend(spending_events)

    # Process building upkeep before unit upkeep
    building_events = await execute_building_upkeep(conn, guild_id, turn_number)
    events.extend(building_events)

    # Fetch all units for the guild
    all_units = await Unit.fetch_all(conn, guild_id)
    if not all_units:
        logger.info(f"Upkeep phase: no units found for guild {guild_id}")
        logger.info(f"Upkeep phase: finished upkeep phase for guild {guild_id}, turn {turn_number}")
        return events

    # Group units by owner type and ID (only active units need upkeep)
    # Oldest units first (by id) to ensure oldest get upkeep priority
    units_by_character: Dict[int, List[Unit]] = {}
    units_by_faction: Dict[int, List[Unit]] = {}

    for unit in sorted(all_units, key=lambda u: u.id):
        if unit.status != 'ACTIVE':
            continue

        owner_type = unit.get_owner_type()
        if owner_type == 'character':
            owner_id = unit.owner_character_id
            if owner_id not in units_by_character:
                units_by_character[owner_id] = []
            units_by_character[owner_id].append(unit)
        elif owner_type == 'faction':
            owner_id = unit.owner_faction_id
            if owner_id not in units_by_faction:
                units_by_faction[owner_id] = []
            units_by_faction[owner_id].append(unit)

    resource_types = ['ore', 'lumber', 'coal', 'rations', 'cloth', 'platinum']

    # Process upkeep for character-owned units
    for owner_id, units in units_by_character.items():
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
            # Check if unit is encircled - skip normal upkeep and apply encirclement penalty
            if unit.id in encircled_unit_ids:
                # Calculate org penalty = count of resource TYPES in upkeep (not amounts)
                resource_types_needed = []
                for rt in resource_types:
                    if getattr(unit, f'upkeep_{rt}') > 0:
                        resource_types_needed.append(rt)

                penalty = len(resource_types_needed)
                if penalty > 0:
                    unit.organization -= penalty
                    await unit.upsert(conn)

                    affected_ids = [owner_id]
                    if unit.commander_character_id and unit.commander_character_id != owner_id:
                        affected_ids.append(unit.commander_character_id)

                    events.append(TurnLog(
                        turn_number=turn_number,
                        phase=TurnPhase.UPKEEP.value,
                        event_type='UPKEEP_ENCIRCLED',
                        entity_type='unit',
                        entity_id=unit.id,
                        event_data={
                            'unit_id': unit.unit_id,
                            'unit_name': unit.name or unit.unit_id,
                            'organization_penalty': penalty,
                            'new_organization': unit.organization,
                            'resource_types_needed': resource_types_needed,
                            'owner_character_id': owner_id,
                            'owner_name': owner.name,
                            'affected_character_ids': affected_ids
                        },
                        guild_id=guild_id
                    ))
                    logger.info(f"Upkeep phase: encircled unit {unit.unit_id} lost {penalty} org (no resources spent)")

                # Skip normal upkeep processing for encircled units
                continue

            unit_deficit = {}

            for rt in resource_types:
                needed = getattr(unit, f'upkeep_{rt}')
                available = getattr(resources, rt)
                deducted = min(needed, available)

                setattr(resources, rt, available - deducted)
                total_spent[rt] += deducted

                if deducted < needed:
                    unit_deficit[rt] = needed - deducted
                    total_deficit[rt] += needed - deducted

            units_maintained += 1

            if unit_deficit:
                units_with_deficit += 1
                penalty = len(unit_deficit)  # Count of different resource TYPES missing (1 per type)
                unit.organization -= penalty
                await unit.upsert(conn)

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

        await resources.upsert(conn)

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

    # Process upkeep for faction-owned units
    for faction_id, units in units_by_faction.items():
        faction = await Faction.fetch_by_id(conn, faction_id)
        if not faction:
            logger.warning(f"Upkeep phase: owner faction {faction_id} not found, skipping units")
            continue

        # Fetch or create faction resources
        resources = await FactionResources.fetch_by_faction(conn, faction_id, guild_id)
        if not resources:
            resources = FactionResources(
                faction_id=faction_id,
                ore=0, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
                guild_id=guild_id
            )

        # Get COMMAND permission holders for affected_character_ids
        command_holders = await FactionPermission.fetch_characters_with_permission(
            conn, faction_id, "COMMAND", guild_id
        )

        total_spent = {rt: 0 for rt in resource_types}
        total_deficit = {rt: 0 for rt in resource_types}
        units_maintained = 0
        units_with_deficit = 0

        for unit in units:
            # Check if unit is encircled - skip normal upkeep and apply encirclement penalty
            if unit.id in encircled_unit_ids:
                # Calculate org penalty = count of resource TYPES in upkeep (not amounts)
                resource_types_needed = []
                for rt in resource_types:
                    if getattr(unit, f'upkeep_{rt}') > 0:
                        resource_types_needed.append(rt)

                penalty = len(resource_types_needed)
                if penalty > 0:
                    unit.organization -= penalty
                    await unit.upsert(conn)

                    # For faction units, affected includes COMMAND holders and commander
                    affected_ids = list(command_holders)
                    if unit.commander_character_id and unit.commander_character_id not in affected_ids:
                        affected_ids.append(unit.commander_character_id)

                    events.append(TurnLog(
                        turn_number=turn_number,
                        phase=TurnPhase.UPKEEP.value,
                        event_type='FACTION_UPKEEP_ENCIRCLED',
                        entity_type='unit',
                        entity_id=unit.id,
                        event_data={
                            'unit_id': unit.unit_id,
                            'unit_name': unit.name or unit.unit_id,
                            'organization_penalty': penalty,
                            'new_organization': unit.organization,
                            'resource_types_needed': resource_types_needed,
                            'owner_faction_id': faction.faction_id,
                            'owner_faction_name': faction.name,
                            'affected_character_ids': affected_ids
                        },
                        guild_id=guild_id
                    ))
                    logger.info(f"Upkeep phase: encircled faction unit {unit.unit_id} lost {penalty} org (no resources spent)")

                # Skip normal upkeep processing for encircled units
                continue

            unit_deficit = {}

            for rt in resource_types:
                needed = getattr(unit, f'upkeep_{rt}')
                available = getattr(resources, rt)
                deducted = min(needed, available)

                setattr(resources, rt, available - deducted)
                total_spent[rt] += deducted

                if deducted < needed:
                    unit_deficit[rt] = needed - deducted
                    total_deficit[rt] += needed - deducted

            units_maintained += 1

            if unit_deficit:
                units_with_deficit += 1
                penalty = len(unit_deficit)  # Count of different resource TYPES missing (1 per type)
                unit.organization -= penalty
                await unit.upsert(conn)

                # For faction units, affected includes COMMAND holders and commander
                affected_ids = list(command_holders)
                if unit.commander_character_id and unit.commander_character_id not in affected_ids:
                    affected_ids.append(unit.commander_character_id)

                events.append(TurnLog(
                    turn_number=turn_number,
                    phase=TurnPhase.UPKEEP.value,
                    event_type='FACTION_UPKEEP_DEFICIT',
                    entity_type='unit',
                    entity_id=unit.id,
                    event_data={
                        'unit_id': unit.unit_id,
                        'unit_name': unit.name or unit.unit_id,
                        'resources_deficit': unit_deficit,
                        'organization_penalty': penalty,
                        'new_organization': unit.organization,
                        'owner_faction_id': faction.faction_id,
                        'owner_faction_name': faction.name,
                        'affected_character_ids': affected_ids
                    },
                    guild_id=guild_id
                ))
                logger.info(f"Upkeep phase: faction unit {unit.unit_id} deficit {unit_deficit}, org -{penalty} -> {unit.organization}")

        await resources.upsert(conn)

        if any(total_spent[rt] > 0 for rt in resource_types):
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.UPKEEP.value,
                event_type='FACTION_UPKEEP_SUMMARY',
                entity_type='faction',
                entity_id=faction_id,
                event_data={
                    'faction_id': faction.faction_id,
                    'faction_name': faction.name,
                    'resources_spent': total_spent,
                    'units_maintained': units_maintained,
                    'affected_character_ids': command_holders
                },
                guild_id=guild_id
            ))
            logger.info(f"Upkeep phase: faction {faction.name} spent {total_spent} on {units_maintained} units")

        if units_with_deficit > 0:
            non_zero_deficit = {rt: v for rt, v in total_deficit.items() if v > 0}
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.UPKEEP.value,
                event_type='FACTION_UPKEEP_TOTAL_DEFICIT',
                entity_type='faction',
                entity_id=faction_id,
                event_data={
                    'faction_id': faction.faction_id,
                    'faction_name': faction.name,
                    'total_deficit': non_zero_deficit,
                    'units_affected': units_with_deficit,
                    'affected_character_ids': command_holders
                },
                guild_id=guild_id
            ))
            logger.info(f"Upkeep phase: faction {faction.name} total deficit {non_zero_deficit} affecting {units_with_deficit} units")

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


async def destroy_low_durability_buildings(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Destroy all buildings with durability <= 0 by setting status to DESTROYED.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for destroyed buildings
    """
    events = []

    # Fetch all active buildings and filter for those with durability <= 0
    all_buildings = await Building.fetch_all(conn, guild_id)
    buildings_to_destroy = [b for b in all_buildings if b.durability <= 0 and b.status == 'ACTIVE']

    for building in buildings_to_destroy:
        # Set status to DESTROYED
        building.status = 'DESTROYED'
        await building.upsert(conn)

        # Find the territory to get affected character IDs
        affected_ids = []
        territory = await Territory.fetch_by_territory_id(conn, building.territory_id, guild_id)
        if territory:
            owner_type = territory.get_owner_type()
            if owner_type == 'character':
                affected_ids = [territory.controller_character_id]
            elif owner_type == 'faction':
                affected_ids = await FactionPermission.fetch_characters_with_permission(
                    conn, territory.controller_faction_id, "FINANCIAL", guild_id
                )

        # Create BUILDING_DESTROYED event
        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.ORGANIZATION.value,
            event_type='BUILDING_DESTROYED',
            entity_type='building',
            entity_id=building.id,
            event_data={
                'building_id': building.building_id,
                'building_name': building.name,
                'territory_id': building.territory_id,
                'final_durability': building.durability,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

        logger.info(f"Organization phase: Destroyed building {building.building_id} (durability={building.durability})")

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
    2. Destroy buildings with durability <= 0
    3. Recover organization for units in friendly territory

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

    # Step 2: Destroy buildings with durability <= 0
    building_destroy_events = await destroy_low_durability_buildings(
        conn, guild_id, turn_number
    )
    events.extend(building_destroy_events)

    # Step 3: Recover organization for units in friendly territory
    recovery_events = await recover_organization_in_friendly_territory(
        conn, guild_id, turn_number
    )
    events.extend(recovery_events)

    logger.info(f"Organization phase: finished organization phase for guild {guild_id}, turn {turn_number}. "
                f"Disbanded {len(disband_events)} units, destroyed {len(building_destroy_events)} buildings, "
                f"recovered {len(recovery_events)} units.")
    return events



async def execute_construction_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Construction phase - processes MOBILIZATION and CONSTRUCTION orders.

    Orders are processed in FIFO order by submitted_at timestamp.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []
    logger.info(f"Construction phase: starting construction phase for guild {guild_id}, turn {turn_number}")

    # Fetch all unresolved orders for the construction phase
    all_orders = await Order.fetch_unresolved_by_phase(
        conn, guild_id, TurnPhase.CONSTRUCTION.value
    )

    # Sort by submitted_at for FIFO processing (both order types have same priority)
    all_orders.sort(key=lambda o: o.submitted_at or datetime.min)

    logger.info(f"Construction phase: processing {len(all_orders)} orders")

    for order in all_orders:
        if order.order_type == OrderType.MOBILIZATION.value:
            order_events = await handle_mobilization_order(conn, order, guild_id, turn_number)
            events.extend(order_events)
        elif order.order_type == OrderType.CONSTRUCTION.value:
            order_events = await handle_construction_order(conn, order, guild_id, turn_number)
            events.extend(order_events)

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
