"""
Movement phase handlers for land unit movement.

This module contains helper functions for processing tick-based movement
during the MOVEMENT phase of turn resolution.
"""
import asyncpg
from typing import List, Optional, Tuple, Dict, Set
from datetime import datetime
import logging
from collections import defaultdict

from db import Order, Unit, Territory, TurnLog, FactionPermission, Character, Alliance, WarParticipant, TerritoryAdjacency, Faction, NavalUnitPosition
from order_types import OrderType, OrderStatus, TurnPhase
from orders.movement_state import MovementUnitState, MovementStatus, MovementAction
from handlers.encirclement_handlers import is_unit_exempt_from_engagement

# Import is deferred to avoid circular imports - loaded when needed
# from handlers.naval_movement_handlers import update_naval_transport_cargo

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


async def get_unit_group_faction_id(
    conn: asyncpg.Connection,
    units: List[Unit],
    guild_id: int
) -> Optional[int]:
    """
    Get the faction ID for a unit group based on owner.

    For character-owned units: looks up the owner character's represented_faction_id.
    For faction-owned units: uses owner_faction_id directly.

    Args:
        conn: Database connection
        units: List of units in the group
        guild_id: Guild ID

    Returns:
        The faction ID (internal) representing the unit group, or None if unaffiliated
    """
    if not units:
        logger.debug("get_unit_group_faction_id: no units provided, returning None")
        return None

    # Use the first unit to determine the group's faction
    # (all units in a movement order should have the same owner)
    unit = units[0]
    unit_ids = [u.unit_id for u in units]
    logger.debug(f"get_unit_group_faction_id: checking units {unit_ids}, "
                 f"owner_character_id={unit.owner_character_id}, owner_faction_id={unit.owner_faction_id}")

    if unit.owner_character_id is not None:
        # Character-owned unit: look up the character's represented faction
        character = await Character.fetch_by_id(conn, unit.owner_character_id)
        if character:
            logger.debug(f"get_unit_group_faction_id: character {character.identifier} "
                        f"represented_faction_id={character.represented_faction_id}")
            return character.represented_faction_id
        logger.debug(f"get_unit_group_faction_id: character not found for id {unit.owner_character_id}")
        return None
    elif unit.owner_faction_id is not None:
        # Faction-owned unit: use owner_faction_id directly
        logger.debug(f"get_unit_group_faction_id: faction-owned unit, returning owner_faction_id={unit.owner_faction_id}")
        return unit.owner_faction_id

    logger.debug("get_unit_group_faction_id: no owner found, returning None")
    return None


async def are_factions_at_war(
    conn: asyncpg.Connection,
    faction_a_id: int,
    faction_b_id: int,
    guild_id: int
) -> bool:
    """
    Check if two factions are on opposite sides of any war.

    Args:
        conn: Database connection
        faction_a_id: First faction's internal ID
        faction_b_id: Second faction's internal ID
        guild_id: Guild ID

    Returns:
        True if factions are on opposite sides of any war, False otherwise
    """
    logger.debug(f"are_factions_at_war: checking faction_a_id={faction_a_id}, faction_b_id={faction_b_id}")

    if faction_a_id == faction_b_id:
        logger.debug("are_factions_at_war: same faction, returning False")
        return False

    # Get all war participations for both factions
    a_participations = await WarParticipant.fetch_by_faction(conn, faction_a_id, guild_id)
    b_participations = await WarParticipant.fetch_by_faction(conn, faction_b_id, guild_id)

    logger.debug(f"are_factions_at_war: faction_a participations: {[(p.war_id, p.side) for p in a_participations]}")
    logger.debug(f"are_factions_at_war: faction_b participations: {[(p.war_id, p.side) for p in b_participations]}")

    # Build a dict of war_id -> side for faction_a
    a_wars: Dict[int, str] = {p.war_id: p.side for p in a_participations}

    # Check if faction_b is on the opposite side in any shared war
    for b_part in b_participations:
        if b_part.war_id in a_wars:
            a_side = a_wars[b_part.war_id]
            b_side = b_part.side
            logger.debug(f"are_factions_at_war: shared war {b_part.war_id}, a_side={a_side}, b_side={b_side}")
            if a_side != b_side:
                logger.debug(f"are_factions_at_war: factions on opposite sides of war {b_part.war_id}, returning True")
                return True

    logger.debug("are_factions_at_war: no opposing war participation found, returning False")
    return False


async def are_factions_allied(
    conn: asyncpg.Connection,
    faction_a_id: int,
    faction_b_id: int,
    guild_id: int
) -> bool:
    """
    Check if two factions have an ACTIVE alliance.

    Args:
        conn: Database connection
        faction_a_id: First faction's internal ID
        faction_b_id: Second faction's internal ID
        guild_id: Guild ID

    Returns:
        True if factions have an ACTIVE alliance, False otherwise
    """
    if faction_a_id == faction_b_id:
        return True  # Same faction is considered allied with itself

    alliance = await Alliance.fetch_by_factions(conn, faction_a_id, faction_b_id, guild_id)
    if alliance and alliance.status == "ACTIVE":
        return True

    return False


async def are_unit_groups_hostile(
    conn: asyncpg.Connection,
    units_a: List[Unit],
    units_b: List[Unit],
    territory_id: str,
    action_a: Optional[str],
    action_b: Optional[str],
    guild_id: int
) -> Tuple[bool, Optional[str]]:
    """
    Check if two unit groups are hostile to each other.

    Hostile if:
    1. Factions are on opposite sides of any war, OR
    2. One group is raiding and the other is allied with territory controller

    Args:
        conn: Database connection
        units_a: First unit group
        units_b: Second unit group
        territory_id: Territory where the encounter occurs
        action_a: Movement action for group A (transit, raid, etc.) or None if stationary
        action_b: Movement action for group B (transit, raid, etc.) or None if stationary
        guild_id: Guild ID

    Returns:
        (is_hostile, reason): Tuple of boolean and reason string ("war" or "raid_defense")
    """
    units_a_ids = [u.unit_id for u in units_a]
    units_b_ids = [u.unit_id for u in units_b]
    logger.debug(f"are_unit_groups_hostile: checking units_a={units_a_ids} (action={action_a}) "
                 f"vs units_b={units_b_ids} (action={action_b}) in territory {territory_id}")

    faction_a_id = await get_unit_group_faction_id(conn, units_a, guild_id)
    faction_b_id = await get_unit_group_faction_id(conn, units_b, guild_id)

    logger.debug(f"are_unit_groups_hostile: faction_a_id={faction_a_id}, faction_b_id={faction_b_id}")

    # Same faction or unaffiliated - not hostile
    if faction_a_id == faction_b_id:
        logger.debug("are_unit_groups_hostile: same faction, not hostile")
        return False, None
    if faction_a_id is None or faction_b_id is None:
        logger.debug("are_unit_groups_hostile: one or both factions unaffiliated, not hostile")
        return False, None

    # Check war hostility
    at_war = await are_factions_at_war(conn, faction_a_id, faction_b_id, guild_id)
    if at_war:
        logger.info(f"are_unit_groups_hostile: factions {faction_a_id} and {faction_b_id} are at war - HOSTILE")
        return True, "war"

    # Check raid hostility
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        logger.debug(f"are_unit_groups_hostile: territory {territory_id} not found")
        return False, None

    controller_faction_id = territory.controller_faction_id
    logger.debug(f"are_unit_groups_hostile: territory controller_faction_id={controller_faction_id}")

    if controller_faction_id:
        # If group A is raiding
        if action_a == "raid":
            logger.debug(f"are_unit_groups_hostile: group A is raiding")
            # Hostile to territory controller
            if faction_b_id == controller_faction_id:
                logger.info(f"are_unit_groups_hostile: raider vs territory controller - HOSTILE")
                return True, "raid_defense"
            # Hostile to allies of territory controller
            if await are_factions_allied(conn, faction_b_id, controller_faction_id, guild_id):
                logger.info(f"are_unit_groups_hostile: raider vs ally of controller - HOSTILE")
                return True, "raid_defense"

        # If group B is raiding
        if action_b == "raid":
            logger.debug(f"are_unit_groups_hostile: group B is raiding")
            # Hostile to territory controller
            if faction_a_id == controller_faction_id:
                logger.info(f"are_unit_groups_hostile: raider vs territory controller - HOSTILE")
                return True, "raid_defense"
            # Hostile to allies of territory controller
            if await are_factions_allied(conn, faction_a_id, controller_faction_id, guild_id):
                logger.info(f"are_unit_groups_hostile: raider vs ally of controller - HOSTILE")
                return True, "raid_defense"

    logger.debug("are_unit_groups_hostile: no hostility detected")
    return False, None


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

        # Extract transport-specific data from order_data
        water_path = order_data.get('water_path')
        coast_territory = order_data.get('coast_territory')
        disembark_territory = order_data.get('disembark_territory')

        # Get water_path_index from result_data for ongoing transport orders
        water_path_index = result_data.get('water_path_index', 0)

        # Determine initial status for transport orders
        initial_status = MovementStatus.MOVING
        if action == 'transport' and water_path:
            # Check if this is a resuming transported state
            if result_data.get('transported'):
                initial_status = MovementStatus.TRANSPORTED

        # Build the state
        state = MovementUnitState(
            units=units,
            order=order,
            total_movement_points=total_mp,
            remaining_mp=total_mp,
            status=initial_status,
            current_territory_id=territory_id,
            path_index=path_index,
            action=action,
            speed=speed,
            territories_entered=[],
            blocked_at=None,
            mp_expended_this_turn=0,
            # Transport-specific fields
            water_path=water_path,
            water_path_index=water_path_index,
            coast_territory=coast_territory,
            disembark_territory=disembark_territory
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


async def find_hostiles_in_territory(
    conn: asyncpg.Connection,
    patrol_state: MovementUnitState,
    territory_id: str,
    all_states: List[MovementUnitState],
    moving_unit_ids: Set[int],
    guild_id: int
) -> Tuple[bool, List[Unit], Optional[MovementUnitState], Optional[str]]:
    """
    Find hostile units in a territory for patrol engagement.

    Checks both moving units (other movement states) and stationary units.

    Args:
        conn: Database connection
        patrol_state: The patrol MovementUnitState looking for hostiles
        territory_id: Territory to check for hostiles
        all_states: List of all MovementUnitState objects
        moving_unit_ids: Set of unit internal IDs that are part of movement states
        guild_id: Guild ID

    Returns:
        Tuple of (found, hostile_units, hostile_state_if_moving, reason)
    """
    logger.debug(f"find_hostiles_in_territory: patrol checking territory {territory_id}")

    # Check moving units first (other movement states in target territory)
    for state in all_states:
        if state == patrol_state or state.status != MovementStatus.MOVING:
            continue
        if state.current_territory_id != territory_id:
            continue

        # Skip if all units in the group are exempt from engagement
        if all(is_unit_exempt_from_engagement(u) for u in state.units):
            continue

        is_hostile, reason = await are_unit_groups_hostile(
            conn, patrol_state.units, state.units, territory_id,
            patrol_state.action, state.action, guild_id
        )
        if is_hostile:
            logger.debug(f"find_hostiles_in_territory: found hostile moving units in {territory_id}")
            return True, state.units, state, reason

    # Check stationary units (filter out exempt units)
    all_units = await Unit.fetch_by_territory(conn, territory_id, guild_id)
    stationary = [u for u in all_units
                  if u.id not in moving_unit_ids and u.status == 'ACTIVE'
                  and not is_unit_exempt_from_engagement(u)]

    if stationary:
        # Group by faction and check hostility
        by_faction: Dict[Optional[int], List[Unit]] = defaultdict(list)
        for unit in stationary:
            faction_id = await get_unit_group_faction_id(conn, [unit], guild_id)
            by_faction[faction_id].append(unit)

        for faction_id, faction_units in by_faction.items():
            is_hostile, reason = await are_unit_groups_hostile(
                conn, patrol_state.units, faction_units, territory_id,
                patrol_state.action, None, guild_id
            )
            if is_hostile:
                logger.debug(f"find_hostiles_in_territory: found hostile stationary units in {territory_id}")
                return True, faction_units, None, reason

    logger.debug(f"find_hostiles_in_territory: no hostiles found in {territory_id}")
    return False, [], None, None


async def execute_patrol_engagement(
    conn: asyncpg.Connection,
    patrol_state: MovementUnitState,
    hostile_units: List[Unit],
    hostile_state: Optional[MovementUnitState],
    target_territory: str,
    terrain_cost: int,
    reason: str,
    turn_number: int,
    guild_id: int
) -> List[TurnLog]:
    """
    Execute patrol engagement - move patrol to territory and engage both groups.

    Args:
        conn: Database connection
        patrol_state: The patrol MovementUnitState
        hostile_units: List of hostile units being engaged
        hostile_state: The hostile MovementUnitState if they are moving, None if stationary
        target_territory: Territory where engagement occurs
        terrain_cost: MP cost to enter the territory
        reason: Reason for hostility ("war" or "raid_defense")
        turn_number: Current turn number
        guild_id: Guild ID

    Returns:
        List of TurnLog events for the engagement
    """
    events: List[TurnLog] = []
    old_territory = patrol_state.current_territory_id

    logger.info(f"execute_patrol_engagement: patrol moving from {old_territory} to {target_territory} "
                f"to engage hostiles (reason: {reason})")

    # Move patrol units
    patrol_state.remaining_mp -= terrain_cost
    patrol_state.mp_expended_this_turn += terrain_cost
    patrol_state.current_territory_id = target_territory
    patrol_state.territories_entered.append(target_territory)

    for unit in patrol_state.units:
        unit.current_territory_id = target_territory
        await unit.upsert(conn)

    # Set both groups to ENGAGED
    patrol_state.status = MovementStatus.ENGAGED
    if hostile_state:
        hostile_state.status = MovementStatus.ENGAGED

    # Get faction and character info for events
    patrol_faction_id = await get_unit_group_faction_id(conn, patrol_state.units, guild_id)
    hostile_faction_id = await get_unit_group_faction_id(conn, hostile_units, guild_id)

    patrol_affected_ids = await get_affected_character_ids(conn, patrol_state.units, guild_id)
    hostile_affected_ids = await get_affected_character_ids(conn, hostile_units, guild_id)

    patrol_unit_ids = [u.unit_id for u in patrol_state.units]
    hostile_unit_ids = [u.unit_id for u in hostile_units]

    # Event for patrol (the intercepting unit)
    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.MOVEMENT.value,
        event_type='PATROL_ENGAGEMENT',
        entity_type='order',
        entity_id=patrol_state.order.id,
        event_data={
            'order_id': patrol_state.order.order_id,
            'units': patrol_unit_ids,
            'from_territory': old_territory,
            'to_territory': target_territory,
            'engaged_with': hostile_unit_ids,
            'engaged_faction_id': hostile_faction_id,
            'reason': reason,
            'engaged_by_patrol': False,  # This is the patrol doing the interception
            'affected_character_ids': patrol_affected_ids
        },
        guild_id=guild_id
    ))

    # Event for hostile (the intercepted unit)
    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.MOVEMENT.value,
        event_type='PATROL_ENGAGEMENT',
        entity_type='order' if hostile_state else 'unit',
        entity_id=hostile_state.order.id if hostile_state else (hostile_units[0].id if hostile_units else None),
        event_data={
            'order_id': hostile_state.order.order_id if hostile_state else None,
            'units': hostile_unit_ids,
            'from_territory': old_territory,  # Where the patrol came from
            'to_territory': target_territory,
            'engaged_with': patrol_unit_ids,
            'engaged_faction_id': patrol_faction_id,
            'reason': reason,
            'engaged_by_patrol': True,  # This group was intercepted by patrol
            'affected_character_ids': hostile_affected_ids
        },
        guild_id=guild_id
    ))

    logger.info(f"execute_patrol_engagement: generated {len(events)} events")
    return events


async def process_patrol_engagement(
    conn: asyncpg.Connection,
    states: List[MovementUnitState],
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Process patrol engagement opportunities.

    Before any ticks, between each tick, and after the last tick, patrol units
    check adjacent territories for hostile units. If a hostile is found in an
    adjacent territory and the patrol has enough remaining MP to pay the terrain
    cost, the patrol moves to that territory and both become ENGAGED.

    Processing order: Patrol orders are processed by order.id ascending (oldest first).
    Tiebreaking: When multiple hostiles exist in different adjacent territories,
    first filter to reachable territories (enough MP for terrain cost), then pick
    alphabetically by territory_id.

    Args:
        conn: Database connection
        states: List of MovementUnitState objects
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for patrol engagements
    """
    events: List[TurnLog] = []

    # 1. Filter to patrol states that are still MOVING
    patrol_states = [s for s in states
                     if s.is_patrol() and s.status == MovementStatus.MOVING]

    if not patrol_states:
        logger.debug("process_patrol_engagement: no patrol states to process")
        return events

    # 2. Sort by order.id ascending (oldest first)
    patrol_states.sort(key=lambda s: s.order.id)

    # 3. Build set of unit IDs in movement states
    moving_unit_ids: Set[int] = {u.id for state in states for u in state.units}

    logger.info(f"process_patrol_engagement: processing {len(patrol_states)} patrol states")

    # 4. Process each patrol
    for patrol_state in patrol_states:
        if patrol_state.status != MovementStatus.MOVING:
            continue  # May have been engaged by earlier patrol

        patrol_unit_ids = [u.unit_id for u in patrol_state.units]
        logger.debug(f"process_patrol_engagement: checking patrol {patrol_unit_ids} "
                     f"at {patrol_state.current_territory_id}")

        # Get adjacent territories
        adjacent = await TerritoryAdjacency.fetch_adjacent(
            conn, patrol_state.current_territory_id, guild_id
        )

        if not adjacent:
            logger.debug(f"process_patrol_engagement: no adjacent territories for "
                         f"{patrol_state.current_territory_id}")
            continue

        # Filter to reachable territories and sort alphabetically
        reachable: List[Tuple[str, int]] = []
        for territory_id in adjacent:
            terrain_cost = await get_terrain_cost(conn, territory_id, guild_id)
            if terrain_cost <= patrol_state.remaining_mp:
                reachable.append((territory_id, terrain_cost))

        # Sort alphabetically by territory_id for tiebreaking
        reachable.sort(key=lambda x: x[0])

        logger.debug(f"process_patrol_engagement: reachable territories: {reachable}")

        # Check each reachable territory for hostiles
        for target_territory, terrain_cost in reachable:
            hostile_found, hostile_units, hostile_state, reason = \
                await find_hostiles_in_territory(
                    conn, patrol_state, target_territory,
                    states, moving_unit_ids, guild_id
                )

            if hostile_found:
                engagement_events = await execute_patrol_engagement(
                    conn, patrol_state, hostile_units, hostile_state,
                    target_territory, terrain_cost, reason, turn_number, guild_id
                )
                events.extend(engagement_events)
                break  # Only engage one target per check

    logger.info(f"process_patrol_engagement: finished, generated {len(events)} events")
    return events


async def check_engagement(
    conn: asyncpg.Connection,
    states: List[MovementUnitState],
    turn_number: int,
    guild_id: int
) -> List[TurnLog]:
    """
    Check for engagements between moving units and other units.

    For each state with status=MOVING:
    1. Get all other MovementUnitStates in same territory
    2. Get all stationary units in same territory (not in any movement state)
    3. Check hostility against each
    4. If hostile, set status to ENGAGED and generate event

    Args:
        conn: Database connection
        states: List of MovementUnitState objects
        turn_number: Current turn number
        guild_id: Guild ID

    Returns:
        List of TurnLog events for engagements detected
    """
    logger.info(f"check_engagement: starting engagement check for {len(states)} movement states")
    events: List[TurnLog] = []

    # Build set of unit IDs that are part of movement states
    moving_unit_ids: Set[int] = set()
    for state in states:
        for unit in state.units:
            moving_unit_ids.add(unit.id)
    logger.debug(f"check_engagement: {len(moving_unit_ids)} units are part of movement states")

    # Group states by current territory
    states_by_territory: Dict[str, List[MovementUnitState]] = defaultdict(list)
    for state in states:
        states_by_territory[state.current_territory_id].append(state)

    logger.debug(f"check_engagement: states grouped by territory: "
                 f"{[(t, len(s)) for t, s in states_by_territory.items()]}")

    # Process each territory
    for territory_id, territory_states in states_by_territory.items():
        logger.debug(f"check_engagement: processing territory {territory_id} with {len(territory_states)} states")

        # Get moving states (not already engaged)
        moving_states = [s for s in territory_states if s.status == MovementStatus.MOVING]
        logger.debug(f"check_engagement: {len(moving_states)} states with MOVING status in territory {territory_id}")

        for s in territory_states:
            unit_ids = [u.unit_id for u in s.units]
            logger.debug(f"check_engagement: state for units {unit_ids}, status={s.status}, action={s.action}")

        if not moving_states:
            logger.debug(f"check_engagement: no moving states in territory {territory_id}, skipping")
            continue

        # Check moving vs moving
        logger.debug(f"check_engagement: checking {len(moving_states)} moving states vs each other")
        for i, state_a in enumerate(moving_states):
            if state_a.status != MovementStatus.MOVING:
                continue

            # Skip if all units in group are exempt from engagement
            if all(is_unit_exempt_from_engagement(u) for u in state_a.units):
                continue

            for state_b in moving_states[i+1:]:
                if state_b.status != MovementStatus.MOVING:
                    continue

                # Skip if all units in group are exempt from engagement
                if all(is_unit_exempt_from_engagement(u) for u in state_b.units):
                    continue

                logger.debug(f"check_engagement: checking moving vs moving hostility")
                is_hostile, reason = await are_unit_groups_hostile(
                    conn, state_a.units, state_b.units, territory_id,
                    state_a.action, state_b.action, guild_id
                )

                if is_hostile:
                    logger.info(f"check_engagement: ENGAGEMENT DETECTED (moving vs moving) in {territory_id}, reason={reason}")
                    # Both groups become engaged
                    state_a.status = MovementStatus.ENGAGED
                    state_b.status = MovementStatus.ENGAGED

                    # Generate events for both groups
                    affected_ids_a = await get_affected_character_ids(conn, state_a.units, guild_id)
                    affected_ids_b = await get_affected_character_ids(conn, state_b.units, guild_id)

                    faction_a_id = await get_unit_group_faction_id(conn, state_a.units, guild_id)
                    faction_b_id = await get_unit_group_faction_id(conn, state_b.units, guild_id)

                    # Event for group A
                    events.append(TurnLog(
                        turn_number=turn_number,
                        phase=TurnPhase.MOVEMENT.value,
                        event_type='ENGAGEMENT_DETECTED',
                        entity_type='order',
                        entity_id=state_a.order.id,
                        event_data={
                            'order_id': state_a.order.order_id,
                            'units': [u.unit_id for u in state_a.units],
                            'territory': territory_id,
                            'engaged_with': [u.unit_id for u in state_b.units],
                            'engaged_faction_id': faction_b_id,
                            'reason': reason,
                            'affected_character_ids': affected_ids_a
                        },
                        guild_id=guild_id
                    ))

                    # Event for group B
                    events.append(TurnLog(
                        turn_number=turn_number,
                        phase=TurnPhase.MOVEMENT.value,
                        event_type='ENGAGEMENT_DETECTED',
                        entity_type='order',
                        entity_id=state_b.order.id,
                        event_data={
                            'order_id': state_b.order.order_id,
                            'units': [u.unit_id for u in state_b.units],
                            'territory': territory_id,
                            'engaged_with': [u.unit_id for u in state_a.units],
                            'engaged_faction_id': faction_a_id,
                            'reason': reason,
                            'affected_character_ids': affected_ids_b
                        },
                        guild_id=guild_id
                    ))

        # Check moving vs stationary
        # First, get all units in territory that aren't part of movement states
        logger.debug(f"check_engagement: fetching stationary units in territory {territory_id}")
        all_units_in_territory = await Unit.fetch_by_territory(conn, territory_id, guild_id)
        logger.debug(f"check_engagement: found {len(all_units_in_territory)} total units in territory {territory_id}")

        # Filter out exempt units (infiltrator/aerial) from stationary checks
        stationary_units = [u for u in all_units_in_territory
                           if u.id not in moving_unit_ids and u.status == 'ACTIVE'
                           and not is_unit_exempt_from_engagement(u)]
        logger.debug(f"check_engagement: {len(stationary_units)} stationary ACTIVE non-exempt units in territory {territory_id}")

        if stationary_units:
            for u in stationary_units:
                logger.debug(f"check_engagement: stationary unit {u.unit_id}, "
                            f"owner_char={u.owner_character_id}, owner_faction={u.owner_faction_id}")

        if not stationary_units:
            logger.debug(f"check_engagement: no stationary units in territory {territory_id}")
            continue

        # Group stationary units by faction
        stationary_by_faction: Dict[Optional[int], List[Unit]] = defaultdict(list)
        for unit in stationary_units:
            faction_id = await get_unit_group_faction_id(conn, [unit], guild_id)
            stationary_by_faction[faction_id].append(unit)

        logger.debug(f"check_engagement: stationary units grouped by faction: "
                     f"{[(f, [u.unit_id for u in units]) for f, units in stationary_by_faction.items()]}")

        # Check each moving state against stationary groups
        for state in moving_states:
            if state.status != MovementStatus.MOVING:
                logger.debug(f"check_engagement: skipping state (not MOVING), status={state.status}")
                continue

            # Skip if all units in moving group are exempt from engagement
            if all(is_unit_exempt_from_engagement(u) for u in state.units):
                logger.debug(f"check_engagement: skipping state (all units exempt from engagement)")
                continue

            moving_unit_ids_str = [u.unit_id for u in state.units]
            logger.debug(f"check_engagement: checking moving units {moving_unit_ids_str} vs stationary groups")

            for faction_id, faction_units in stationary_by_faction.items():
                faction_unit_ids = [u.unit_id for u in faction_units]
                logger.debug(f"check_engagement: checking against stationary faction {faction_id}, "
                            f"units {faction_unit_ids}")

                is_hostile, reason = await are_unit_groups_hostile(
                    conn, state.units, faction_units, territory_id,
                    state.action, None,  # Stationary units have no action
                    guild_id
                )

                if is_hostile:
                    logger.info(f"check_engagement: ENGAGEMENT DETECTED (moving vs stationary) in {territory_id}, reason={reason}")
                    # Moving group becomes engaged
                    state.status = MovementStatus.ENGAGED

                    # Get affected character IDs
                    affected_ids_moving = await get_affected_character_ids(conn, state.units, guild_id)
                    affected_ids_stationary = await get_affected_character_ids(conn, faction_units, guild_id)

                    moving_faction_id = await get_unit_group_faction_id(conn, state.units, guild_id)

                    # Event for moving group
                    events.append(TurnLog(
                        turn_number=turn_number,
                        phase=TurnPhase.MOVEMENT.value,
                        event_type='ENGAGEMENT_DETECTED',
                        entity_type='order',
                        entity_id=state.order.id,
                        event_data={
                            'order_id': state.order.order_id,
                            'units': [u.unit_id for u in state.units],
                            'territory': territory_id,
                            'engaged_with': [u.unit_id for u in faction_units],
                            'engaged_faction_id': faction_id,
                            'reason': reason,
                            'affected_character_ids': affected_ids_moving
                        },
                        guild_id=guild_id
                    ))

                    # Event for stationary group (notify owners)
                    events.append(TurnLog(
                        turn_number=turn_number,
                        phase=TurnPhase.MOVEMENT.value,
                        event_type='ENGAGEMENT_DETECTED',
                        entity_type='unit',  # No order for stationary units
                        entity_id=faction_units[0].id if faction_units else None,
                        event_data={
                            'order_id': None,
                            'units': [u.unit_id for u in faction_units],
                            'territory': territory_id,
                            'engaged_with': [u.unit_id for u in state.units],
                            'engaged_faction_id': moving_faction_id,
                            'reason': reason,
                            'affected_character_ids': affected_ids_stationary
                        },
                        guild_id=guild_id
                    ))

                    break  # Only one engagement per moving state

    logger.info(f"check_engagement: finished, generated {len(events)} engagement events")
    return events


def unit_has_keyword(unit: Unit, keyword: str) -> bool:
    """
    Check if a unit has a specific keyword (case-insensitive).

    Args:
        unit: The unit to check
        keyword: The keyword to look for

    Returns:
        True if the unit has the keyword, False otherwise
    """
    if not unit.keywords:
        return False
    keyword_lower = keyword.lower()
    return any(k.lower() == keyword_lower for k in unit.keywords)


async def get_territories_in_range(
    conn: asyncpg.Connection,
    territory_id: str,
    range_distance: int,
    guild_id: int
) -> Dict[int, List[str]]:
    """
    Get all territories within range, organized by distance.

    Args:
        conn: Database connection
        territory_id: Starting territory ID
        range_distance: Maximum distance (1 or 2)
        guild_id: Guild ID

    Returns:
        Dict mapping distance to list of territory IDs.
        {0: [origin], 1: [adjacent], 2: [2-step territories]}
    """
    result: Dict[int, List[str]] = {}

    # Distance 0 is the same territory
    result[0] = [territory_id]

    # Distance 1 is adjacent territories
    adjacent = await TerritoryAdjacency.fetch_adjacent(conn, territory_id, guild_id)
    result[1] = adjacent

    if range_distance >= 2:
        # Distance 2 is territories adjacent to distance-1 territories
        distance_2 = set()
        for adj_territory in adjacent:
            adj_adjacent = await TerritoryAdjacency.fetch_adjacent(conn, adj_territory, guild_id)
            distance_2.update(adj_adjacent)

        # Remove origin and distance-1 territories
        distance_2.discard(territory_id)
        distance_2 -= set(adjacent)
        result[2] = list(distance_2)

    return result


async def recipient_should_see_observation(
    conn: asyncpg.Connection,
    recipient_character_id: int,
    observed: Unit,
    guild_id: int
) -> bool:
    """
    Check if a recipient should receive an observation event for observed unit.

    Returns False (skip event) if recipient:
    - Owns the observed unit (owner_character_id == recipient)
    - Commands the observed unit (commander_character_id == recipient)
    - For faction-owned observed unit: recipient has COMMAND permission for that faction

    Returns True otherwise.

    Args:
        conn: Database connection
        recipient_character_id: The character who would receive the event
        observed: The unit being observed
        guild_id: Guild ID

    Returns:
        True if the recipient should see the observation, False otherwise
    """
    # Character-owned unit checks
    if observed.owner_character_id == recipient_character_id:
        return False
    if observed.commander_character_id == recipient_character_id:
        return False

    # Faction-owned unit check
    if observed.owner_faction_id:
        has_command = await FactionPermission.has_permission(
            conn, observed.owner_faction_id, recipient_character_id, "COMMAND", guild_id
        )
        if has_command:
            return False

    return True


async def get_observation_recipients(
    conn: asyncpg.Connection,
    observer: Unit,
    guild_id: int
) -> List[int]:
    """
    Get character IDs that should receive observation events from this observer.

    Character-owned: owner + commander (if different)
    Faction-owned: all characters with COMMAND permission

    Args:
        conn: Database connection
        observer: The observing unit
        guild_id: Guild ID

    Returns:
        List of character IDs to notify
    """
    if observer.owner_character_id is not None:
        # Character-owned unit
        recipients = [observer.owner_character_id]
        if observer.commander_character_id and observer.commander_character_id != observer.owner_character_id:
            recipients.append(observer.commander_character_id)
        return recipients
    elif observer.owner_faction_id is not None:
        # Faction-owned unit
        return await FactionPermission.fetch_characters_with_permission(
            conn, observer.owner_faction_id, "COMMAND", guild_id
        )
    return []


async def generate_observation_reports(
    conn: asyncpg.Connection,
    states: List[MovementUnitState],
    guild_id: int,
    turn_number: int,
    tick: Optional[int] = None,
    observation_tracker: Optional[Dict[Tuple[int, int], int]] = None
) -> Tuple[List[TurnLog], Dict[Tuple[int, int], int]]:
    """
    Generate observation events for all units seeing other units.

    Units observe other units at:
    - Distance 0 (same territory)
    - Distance 1 (adjacent territory)
    - Distance 2 (for scouts only)

    Infiltrators cannot be observed by anyone.

    Args:
        conn: Database connection
        states: List of MovementUnitState objects (for moving unit positions)
        guild_id: Guild ID
        turn_number: Current turn number
        tick: Current tick number (for deduplication tracking)
        observation_tracker: Dict tracking (recipient_char_id, observed_unit_id) -> tick

    Returns:
        (events, updated_tracker): Tuple of events and updated tracker dict
    """
    if observation_tracker is None:
        observation_tracker = {}

    events: List[TurnLog] = []

    # Get all active units in guild
    all_units = await Unit.fetch_all(conn, guild_id)
    active_units = [u for u in all_units if u.status == 'ACTIVE' and u.current_territory_id]

    # Build unit_id -> MovementUnitState mapping for moving units
    # This lets us use current tick positions instead of database positions
    moving_unit_positions: Dict[str, str] = {}
    for state in states:
        for unit in state.units:
            moving_unit_positions[unit.unit_id] = state.current_territory_id

    def get_unit_current_territory(unit: Unit) -> str:
        """Get unit's current territory (from movement state if moving, else from db)."""
        if unit.unit_id in moving_unit_positions:
            return moving_unit_positions[unit.unit_id]
        return unit.current_territory_id

    # Build territory -> units mapping (using current tick positions)
    units_by_territory: Dict[str, List[Unit]] = defaultdict(list)
    for unit in active_units:
        current_territory = get_unit_current_territory(unit)
        if current_territory:
            units_by_territory[current_territory].append(unit)

    # Process each potential observer
    for observer in active_units:
        # Get observer's current position
        observer_territory = get_unit_current_territory(observer)
        if not observer_territory:
            continue

        # Determine observation range
        is_scout = unit_has_keyword(observer, 'scout')
        observation_range = 2 if is_scout else 1

        # Get territories in range (includes distance 0 = same territory)
        territories_in_range = await get_territories_in_range(
            conn, observer_territory, observation_range, guild_id
        )

        # Get recipient character IDs for this observer
        recipient_ids = await get_observation_recipients(conn, observer, guild_id)

        if not recipient_ids:
            continue

        # Check each territory in range
        for distance, territory_list in territories_in_range.items():
            for territory_id in territory_list:
                for observed in units_by_territory.get(territory_id, []):
                    # Skip self
                    if observed.id == observer.id:
                        continue

                    # Skip infiltrators (invisible to everyone)
                    if unit_has_keyword(observed, 'infiltrator'):
                        continue

                    # Get observed unit's faction info
                    observed_faction_id = await get_unit_group_faction_id(conn, [observed], guild_id)
                    observed_faction = None
                    if observed_faction_id:
                        observed_faction = await Faction.fetch_by_id(conn, observed_faction_id)

                    # Create ONE event per recipient character
                    for recipient_id in recipient_ids:
                        # Skip if recipient owns/commands the observed unit
                        if not await recipient_should_see_observation(conn, recipient_id, observed, guild_id):
                            continue

                        # Track observation per (recipient, observed_unit)
                        key = (recipient_id, observed.id)
                        observation_tracker[key] = tick if tick is not None else 0

                        events.append(TurnLog(
                            turn_number=turn_number,
                            phase=TurnPhase.MOVEMENT.value,
                            event_type='UNIT_OBSERVED',
                            entity_type='unit',
                            entity_id=observed.id,
                            event_data={
                                'observer_unit_id': observer.unit_id,
                                'observer_territory': observer_territory,
                                'observed_unit_id': observed.unit_id,
                                'observed_unit_type': observed.unit_type,
                                'observed_faction_id': observed_faction.faction_id if observed_faction else None,
                                'observed_faction_name': observed_faction.name if observed_faction else 'Unaffiliated',
                                'observed_territory': territory_id,
                                'distance': distance,
                                'tick': tick,
                                'affected_character_ids': [recipient_id]
                            },
                            guild_id=guild_id
                        ))

    return events, observation_tracker


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

    # Add transport-specific data for land transport orders
    if state.is_transport():
        order.result_data['water_path_index'] = state.water_path_index
        order.result_data['transported'] = state.status == MovementStatus.TRANSPORTED

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


# ============================================================================
# Transport Helper Functions
# ============================================================================

# Water terrain types (for transport validation)
WATER_TERRAIN_TYPES = ['ocean', 'lake', 'sea', 'water']


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


async def get_naval_transport_capacity(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int
) -> int:
    """
    Get total capacity of naval units in a naval_transport order.

    Args:
        conn: Database connection
        order: The naval transport order
        guild_id: Guild ID

    Returns:
        Total capacity (sum of all naval unit capacities)
    """
    total_capacity = 0
    for unit_id in order.unit_ids:
        unit = await Unit.fetch_by_id(conn, unit_id)
        if unit and unit.is_naval and unit.status == 'ACTIVE':
            # Capacity is stored on the unit (default to 0 if not set)
            total_capacity += getattr(unit, 'capacity', 0) or 0
    return total_capacity


async def get_land_unit_group_size(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int
) -> int:
    """
    Get total size of land units in a transport order.

    Args:
        conn: Database connection
        order: The land transport order
        guild_id: Guild ID

    Returns:
        Total size (sum of all land unit sizes)
    """
    total_size = 0
    for unit_id in order.unit_ids:
        unit = await Unit.fetch_by_id(conn, unit_id)
        if unit and not unit.is_naval and unit.status == 'ACTIVE':
            # Size is stored on the unit (default to 1 if not set)
            total_size += getattr(unit, 'size', 1) or 1
    return total_size


def get_unit_group_direct_faction_id(units: List[Unit]) -> Optional[int]:
    """
    Get the direct faction_id from units (for transport matching).

    This checks the unit's faction_id field directly, not the owner's faction.

    Args:
        units: List of units in the group

    Returns:
        The faction_id of the first unit that has one, or None
    """
    for unit in units:
        if unit.faction_id:
            return unit.faction_id
    return None


async def find_matching_naval_transport(
    conn: asyncpg.Connection,
    land_state: MovementUnitState,
    naval_states: List[MovementUnitState],
    guild_id: int
) -> Optional[MovementUnitState]:
    """
    Find a naval transport order that matches a land unit's transport requirements.

    Matching conditions:
    1. Naval's water path == land's water_path (exact match)
    2. Naval unit is not engaged
    3. Naval capacity >= land unit size
    4. Naval and land are same faction OR allied factions

    Args:
        conn: Database connection
        land_state: The land transport MovementUnitState
        naval_states: List of naval_transport MovementUnitStates to check
        guild_id: Guild ID

    Returns:
        Matching naval MovementUnitState, or None if no match found
    """
    if not land_state.water_path:
        logger.debug(f"find_matching_naval_transport: land state has no water_path")
        return None

    land_water_path = land_state.water_path
    land_size = await get_land_unit_group_size(conn, land_state.order, guild_id)
    # Use direct faction_id from unit for transport matching
    land_faction_id = get_unit_group_direct_faction_id(land_state.units)

    logger.debug(f"find_matching_naval_transport: looking for match for land units {[u.unit_id for u in land_state.units]}, "
                 f"water_path={land_water_path}, size={land_size}, faction={land_faction_id}")

    for naval_state in naval_states:
        # Skip if naval is engaged
        if naval_state.status == MovementStatus.ENGAGED:
            logger.debug(f"find_matching_naval_transport: skipping naval {naval_state.order.order_id} - engaged")
            continue

        # Get naval's water path from order_data (the full path for naval_transport is all water)
        naval_path = naval_state.order.order_data.get('path', [])

        # Check path match
        if naval_path != land_water_path:
            logger.debug(f"find_matching_naval_transport: naval {naval_state.order.order_id} path mismatch: "
                         f"{naval_path} != {land_water_path}")
            continue

        # Check capacity
        naval_capacity = await get_naval_transport_capacity(conn, naval_state.order, guild_id)
        if naval_capacity < land_size:
            logger.debug(f"find_matching_naval_transport: naval {naval_state.order.order_id} insufficient capacity: "
                         f"{naval_capacity} < {land_size}")
            continue

        # Check faction/alliance using direct faction_id from units
        naval_faction_id = get_unit_group_direct_faction_id(naval_state.units)

        if land_faction_id is None or naval_faction_id is None:
            logger.debug(f"find_matching_naval_transport: naval {naval_state.order.order_id} - one faction is None")
            continue

        if land_faction_id != naval_faction_id:
            # Check if allied
            allied = await are_factions_allied(conn, land_faction_id, naval_faction_id, guild_id)
            if not allied:
                logger.debug(f"find_matching_naval_transport: naval {naval_state.order.order_id} - not same faction or allied")
                continue

        logger.info(f"find_matching_naval_transport: found match - naval {naval_state.order.order_id}")
        return naval_state

    logger.debug(f"find_matching_naval_transport: no matching naval transport found")
    return None


async def process_transport_disembarkation(
    conn: asyncpg.Connection,
    land_states: List[MovementUnitState],
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Process disembarkation for transported land units at the end of their water path.

    At the beginning of the movement phase, transported land units that are at
    the last water territory in their water_path disembark to their disembark_territory.
    Disembarkation is FREE (no MP cost).

    Args:
        conn: Database connection
        land_states: List of land MovementUnitStates (including transported ones)
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for disembarkations
    """
    events: List[TurnLog] = []

    for state in land_states:
        # Only process transported land units
        if state.status != MovementStatus.TRANSPORTED:
            continue

        # Check if at end of water path
        if not state.is_at_water_path_end():
            continue

        # Check adjacency to disembark territory
        if not state.disembark_territory:
            logger.warning(f"process_transport_disembarkation: transported unit has no disembark_territory")
            continue

        current_water = state.current_territory_id
        adjacent = await TerritoryAdjacency.fetch_adjacent(conn, current_water, guild_id)

        if state.disembark_territory not in adjacent:
            logger.warning(f"process_transport_disembarkation: disembark territory {state.disembark_territory} "
                           f"is not adjacent to current water territory {current_water}")
            continue

        # Disembark - move land unit to disembark territory (FREE - no MP cost)
        old_territory = state.current_territory_id
        state.current_territory_id = state.disembark_territory
        state.territories_entered.append(state.disembark_territory)
        state.status = MovementStatus.MOVING  # Can continue moving on land
        state.transport_naval_order_id = None  # Unlink from naval

        # Update path_index to match the disembark position in the full path
        full_path = state.get_path()
        try:
            state.path_index = full_path.index(state.disembark_territory)
        except ValueError:
            # Disembark territory should be in the path
            logger.warning(f"process_transport_disembarkation: disembark territory not in path")

        # Update unit positions in database
        for unit in state.units:
            unit.current_territory_id = state.disembark_territory
            await unit.upsert(conn)

        # Generate event
        affected_ids = await get_affected_character_ids(conn, state.units, guild_id)

        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.MOVEMENT.value,
            event_type='TRANSPORT_DISEMBARK',
            entity_type='order',
            entity_id=state.order.id,
            event_data={
                'order_id': state.order.order_id,
                'units': [u.unit_id for u in state.units],
                'from_territory': old_territory,
                'to_territory': state.disembark_territory,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

        logger.info(f"process_transport_disembarkation: units {[u.unit_id for u in state.units]} "
                    f"disembarked from {old_territory} to {state.disembark_territory}")

    return events


async def process_transport_boarding(
    conn: asyncpg.Connection,
    land_states: List[MovementUnitState],
    naval_states: List[MovementUnitState],
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Process boarding for land units at their coast territory.

    At the beginning of the movement phase, land units with transport orders
    that are at their coast_territory attempt to board matching naval transports.

    Processing order: Land orders are processed by order.id ascending (oldest first).

    Args:
        conn: Database connection
        land_states: List of land transport MovementUnitStates
        naval_states: List of naval_transport MovementUnitStates
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for boarding attempts
    """
    events: List[TurnLog] = []

    # Filter to land transport states that are MOVING and at their coast territory
    transport_states = [s for s in land_states
                        if s.is_transport() and s.status == MovementStatus.MOVING]

    # Sort by order.id (oldest first)
    transport_states.sort(key=lambda s: s.order.id)

    logger.info(f"process_transport_boarding: processing {len(transport_states)} land transport states")

    for land_state in transport_states:
        # Skip if not at coast territory
        coast = land_state.coast_territory
        if not coast or land_state.current_territory_id != coast:
            logger.debug(f"process_transport_boarding: land units {[u.unit_id for u in land_state.units]} "
                         f"not at coast territory {coast}, currently at {land_state.current_territory_id}")
            continue

        # Skip if already engaged
        if land_state.status == MovementStatus.ENGAGED:
            logger.debug(f"process_transport_boarding: land units engaged, skipping")
            continue

        # Check adjacency to first water territory
        if not land_state.water_path:
            logger.warning(f"process_transport_boarding: land state has no water_path")
            continue

        first_water = land_state.water_path[0]
        adjacent = await TerritoryAdjacency.fetch_adjacent(conn, coast, guild_id)

        if first_water not in adjacent:
            logger.warning(f"process_transport_boarding: first water {first_water} not adjacent to coast {coast}")
            land_state.status = MovementStatus.WAITING_FOR_TRANSPORT
            affected_ids = await get_affected_character_ids(conn, land_state.units, guild_id)
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.MOVEMENT.value,
                event_type='TRANSPORT_WAITING',
                entity_type='order',
                entity_id=land_state.order.id,
                event_data={
                    'order_id': land_state.order.order_id,
                    'units': [u.unit_id for u in land_state.units],
                    'territory': coast,
                    'reason': 'water_not_adjacent',
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))
            continue

        # Find matching naval transport
        naval_state = await find_matching_naval_transport(conn, land_state, naval_states, guild_id)

        if not naval_state:
            # No match found - wait
            land_state.status = MovementStatus.WAITING_FOR_TRANSPORT
            affected_ids = await get_affected_character_ids(conn, land_state.units, guild_id)
            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.MOVEMENT.value,
                event_type='TRANSPORT_WAITING',
                entity_type='order',
                entity_id=land_state.order.id,
                event_data={
                    'order_id': land_state.order.order_id,
                    'units': [u.unit_id for u in land_state.units],
                    'territory': coast,
                    'reason': 'no_matching_naval',
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))
            logger.debug(f"process_transport_boarding: no matching naval transport for land units")
            continue

        # Board - move land unit to first water territory
        old_territory = land_state.current_territory_id
        land_state.current_territory_id = first_water
        land_state.territories_entered.append(first_water)
        land_state.water_path_index = 0
        land_state.status = MovementStatus.TRANSPORTED
        land_state.transport_naval_order_id = naval_state.order.id

        # Link naval to land
        naval_state.transported_land_order_ids.append(land_state.order.id)

        # Update unit positions in database
        for unit in land_state.units:
            unit.current_territory_id = first_water
            await unit.upsert(conn)

        # Update naval transport order to mark cargo has boarded
        # This updates the naval order's result_data to no longer wait
        from handlers.naval_movement_handlers import update_naval_transport_cargo
        land_unit_ids = [u.id for u in land_state.units]
        await update_naval_transport_cargo(conn, naval_state.order, land_unit_ids, guild_id)

        # Generate boarding event
        affected_ids = await get_affected_character_ids(conn, land_state.units, guild_id)
        naval_unit_ids = [u.unit_id for u in naval_state.units]

        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.MOVEMENT.value,
            event_type='TRANSPORT_BOARDING',
            entity_type='order',
            entity_id=land_state.order.id,
            event_data={
                'order_id': land_state.order.order_id,
                'units': [u.unit_id for u in land_state.units],
                'naval_units': naval_unit_ids,
                'naval_order_id': naval_state.order.order_id,
                'from_territory': old_territory,
                'to_territory': first_water,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

        logger.info(f"process_transport_boarding: units {[u.unit_id for u in land_state.units]} "
                    f"boarded naval {naval_unit_ids} at {first_water}")

    return events


async def process_transport_movement_tick(
    conn: asyncpg.Connection,
    land_states: List[MovementUnitState],
    naval_states: List[MovementUnitState],
    tick: int,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Move transported land units through water one step per tick.

    Transport speed = slowest naval unit movement + 1 bonus
    Land units move through water territories independently (naval units don't move).

    Args:
        conn: Database connection
        land_states: List of all land MovementUnitStates
        naval_states: List of naval_transport MovementUnitStates
        tick: Current tick number
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for transport movement
    """
    events: List[TurnLog] = []

    # Build map of naval order ID to naval state
    naval_by_order_id = {s.order.id: s for s in naval_states}

    for land_state in land_states:
        # Only process transported land units
        if land_state.status != MovementStatus.TRANSPORTED:
            continue

        # Get the linked naval transport
        naval_order_id = land_state.transport_naval_order_id
        if not naval_order_id or naval_order_id not in naval_by_order_id:
            logger.warning(f"process_transport_movement_tick: transported land has invalid naval_order_id")
            continue

        naval_state = naval_by_order_id[naval_order_id]

        # Calculate transport MP (slowest naval + 1 bonus)
        transport_mp = naval_state.total_movement_points  # Already includes naval's base movement

        # Check if this unit moves at this tick
        if transport_mp < tick:
            continue

        # Check if at end of water path
        if land_state.is_at_water_path_end():
            continue

        # Get next water territory
        next_water = land_state.get_water_path_next_territory()
        if not next_water:
            continue

        # Move to next water territory (no terrain cost for water transport)
        old_territory = land_state.current_territory_id
        land_state.current_territory_id = next_water
        land_state.water_path_index += 1
        land_state.territories_entered.append(next_water)

        # Update unit positions in database
        for unit in land_state.units:
            unit.current_territory_id = next_water
            await unit.upsert(conn)

        # Generate progress event
        affected_ids = await get_affected_character_ids(conn, land_state.units, guild_id)

        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.MOVEMENT.value,
            event_type='TRANSPORT_PROGRESS',
            entity_type='order',
            entity_id=land_state.order.id,
            event_data={
                'order_id': land_state.order.order_id,
                'units': [u.unit_id for u in land_state.units],
                'from_territory': old_territory,
                'to_territory': next_water,
                'water_path_index': land_state.water_path_index,
                'water_path_length': len(land_state.water_path) if land_state.water_path else 0,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

        logger.debug(f"process_transport_movement_tick: units {[u.unit_id for u in land_state.units]} "
                     f"moved from {old_territory} to {next_water}")

    return events


async def build_naval_transport_states(
    conn: asyncpg.Connection,
    naval_orders: List[Order],
    guild_id: int
) -> Tuple[List[MovementUnitState], List[TurnLog]]:
    """
    Build MovementUnitState objects for naval transport orders.

    Naval transport orders don't actually move in the movement phase (naval movement
    not yet implemented), but we need their state for matching with land transports.

    Args:
        conn: Database connection
        naval_orders: List of naval_transport orders
        guild_id: Guild ID

    Returns:
        (valid_states, failed_events)
    """
    states = []
    failed_events = []

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
            await order.upsert(conn)
            failed_events.append(TurnLog(
                turn_number=order.turn_number,
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

        # All units should be in the same territory (first water territory of path)
        territories = set(u.current_territory_id for u in units)
        if len(territories) > 1:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Naval units not co-located'}
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
                    'error': 'Naval units not co-located',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            ))
            continue

        territory_id = units[0].current_territory_id

        # Extract order data
        order_data = order.order_data
        action = order_data.get('action', 'naval_transport')
        path = order_data.get('path', [])

        if not path:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'No path specified'}
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
                    'error': 'No path specified',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            ))
            continue

        # Calculate movement points (for determining transport speed)
        total_mp = calculate_movement_points(units, action)

        # Build the state
        state = MovementUnitState(
            units=units,
            order=order,
            total_movement_points=total_mp,
            remaining_mp=total_mp,
            status=MovementStatus.WAITING_FOR_CARGO,  # Naval waits for land units
            current_territory_id=territory_id,
            path_index=0,
            action=action,
            speed=None,
            territories_entered=[],
            blocked_at=None,
            mp_expended_this_turn=0
        )

        states.append(state)

    return states, failed_events
