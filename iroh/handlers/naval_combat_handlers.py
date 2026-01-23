"""
Naval combat phase handlers for the wargame system.

Naval combat is triggered when patrolling naval units occupy the same territory
as hostile naval units. Unlike land combat:
- Naval units can fight in multiple territories per turn (damage accumulates)
- Naval units do NOT retreat - they just take organization damage
- All damage is calculated first, then applied simultaneously
- If a naval transport is destroyed, its carried land units are also destroyed
"""
import asyncpg
import json
from typing import List, Optional, Tuple, Dict, Set
from dataclasses import dataclass, field
from collections import defaultdict
import logging

from db import Unit, TurnLog, Faction, FactionPermission, Order, NavalUnitPosition
from order_types import OrderStatus, TurnPhase
from handlers.movement_handlers import (
    are_factions_at_war,
    are_factions_allied,
    unit_has_keyword,
)
from handlers.combat_handlers import get_unit_faction_id

logger = logging.getLogger(__name__)

# Track which submarines engaged in combat this turn (for observation visibility)
_submarines_in_combat_this_turn: Set[int] = set()


def mark_submarine_in_combat(unit_id: int) -> None:
    """Mark a submarine as having engaged in combat this turn."""
    _submarines_in_combat_this_turn.add(unit_id)


def is_submarine_in_combat_this_turn(unit_id: int) -> bool:
    """Check if a submarine engaged in combat this turn."""
    return unit_id in _submarines_in_combat_this_turn


def clear_submarine_combat_tracking() -> None:
    """Clear the submarine combat tracking for a new turn."""
    _submarines_in_combat_this_turn.clear()


@dataclass
class NavalCombatSide:
    """Represents one side in naval combat (can be multiple allied factions)."""
    faction_ids: Set[int] = field(default_factory=set)
    units: List[Unit] = field(default_factory=list)
    total_attack: int = 0
    total_defense: int = 0


async def find_naval_patrol_units(
    conn: asyncpg.Connection,
    guild_id: int
) -> List[Unit]:
    """
    Find all active naval units with active patrol orders.

    Args:
        conn: Database connection
        guild_id: Guild ID

    Returns:
        List of naval units with patrol orders
    """
    # Find all ONGOING or SUCCESS naval_patrol orders from current turn
    rows = await conn.fetch("""
        SELECT DISTINCT unnest(unit_ids) as unit_id
        FROM WargameOrder
        WHERE guild_id = $1
          AND order_type = 'UNIT'
          AND status IN ('SUCCESS', 'ONGOING')
          AND order_data->>'action' = 'naval_patrol'
    """, guild_id)

    patrol_units = []
    for row in rows:
        unit = await Unit.fetch_by_id(conn, row['unit_id'])
        if unit and unit.is_naval and unit.status == 'ACTIVE':
            patrol_units.append(unit)

    logger.debug(f"find_naval_patrol_units: found {len(patrol_units)} patrol units")
    return patrol_units


async def get_naval_unit_occupied_territories(
    conn: asyncpg.Connection,
    unit_id: int,
    guild_id: int
) -> List[str]:
    """
    Get territories a naval unit occupies from NavalUnitPosition table.

    Args:
        conn: Database connection
        unit_id: Unit's internal ID
        guild_id: Guild ID

    Returns:
        List of territory_ids the unit occupies
    """
    return await NavalUnitPosition.fetch_territories_by_unit(conn, unit_id, guild_id)


async def get_all_naval_units_in_territory(
    conn: asyncpg.Connection,
    territory_id: str,
    guild_id: int
) -> List[Unit]:
    """
    Get ALL naval units that occupy a given territory.

    Uses the NavalUnitPosition table to find units.

    Args:
        conn: Database connection
        territory_id: Territory ID to check
        guild_id: Guild ID

    Returns:
        List of active naval Unit objects occupying this territory
    """
    unit_ids = await NavalUnitPosition.fetch_units_in_territory(conn, territory_id, guild_id)
    units = []
    for unit_id in unit_ids:
        unit = await Unit.fetch_by_id(conn, unit_id)
        if unit and unit.is_naval and unit.status == 'ACTIVE':
            units.append(unit)
    return units


async def find_combat_territories_for_patrol(
    conn: asyncpg.Connection,
    patrol_unit: Unit,
    guild_id: int
) -> List[str]:
    """
    Find territories where patrol unit triggers combat (has hostile units present).

    Combat is triggered in a territory if there are ANY hostile naval units present.

    Args:
        conn: Database connection
        patrol_unit: The patrolling naval unit
        guild_id: Guild ID

    Returns:
        List of territory_ids where combat will occur
    """
    patrol_faction_id = await get_unit_faction_id(conn, patrol_unit, guild_id)
    patrol_territories = await get_naval_unit_occupied_territories(conn, patrol_unit.id, guild_id)

    combat_territories = []
    for territory_id in patrol_territories:
        # Get all naval units in this territory
        units_in_territory = await get_all_naval_units_in_territory(conn, territory_id, guild_id)

        # Check if any unit is hostile
        for other_unit in units_in_territory:
            if other_unit.id == patrol_unit.id:
                continue

            other_faction_id = await get_unit_faction_id(conn, other_unit, guild_id)

            # Skip if either faction is None (unaffiliated)
            if patrol_faction_id is None or other_faction_id is None:
                continue

            if await are_factions_at_war(conn, patrol_faction_id, other_faction_id, guild_id):
                combat_territories.append(territory_id)
                break  # One hostile is enough to trigger combat

    logger.debug(f"find_combat_territories_for_patrol: patrol unit {patrol_unit.unit_id} "
                 f"triggers combat in {len(combat_territories)} territories")
    return combat_territories


async def group_units_into_naval_combat_sides(
    conn: asyncpg.Connection,
    units: List[Unit],
    guild_id: int
) -> List[NavalCombatSide]:
    """
    Group units into combat sides based on faction and alliance.

    Allied factions are combined into a single side.

    Args:
        conn: Database connection
        units: List of naval units in the territory
        guild_id: Guild ID

    Returns:
        List of NavalCombatSide objects (one per side)
    """
    # Group units by faction first
    faction_units: Dict[Optional[int], List[Unit]] = defaultdict(list)

    for unit in units:
        faction_id = await get_unit_faction_id(conn, unit, guild_id)
        faction_units[faction_id].append(unit)

    # Build alliance groups - factions that are allied with each other
    faction_ids = [f for f in faction_units.keys() if f is not None]
    alliance_groups: List[Set[int]] = []
    processed: Set[int] = set()

    for faction_id in faction_ids:
        if faction_id in processed:
            continue

        # Start a new group with this faction
        group = {faction_id}
        processed.add(faction_id)

        # Find all factions allied with this one
        for other_faction_id in faction_ids:
            if other_faction_id in processed:
                continue

            # Check if allied with any faction in the current group
            for group_faction_id in list(group):
                if await are_factions_allied(conn, group_faction_id, other_faction_id, guild_id):
                    group.add(other_faction_id)
                    processed.add(other_faction_id)
                    break

        alliance_groups.append(group)

    # Build combat sides from alliance groups
    sides: List[NavalCombatSide] = []

    for group in alliance_groups:
        if not group:
            continue

        side_units: List[Unit] = []

        for faction_id in group:
            side_units.extend(faction_units[faction_id])

        if side_units:
            side = NavalCombatSide(
                faction_ids=group,
                units=side_units,
                total_attack=sum(u.attack for u in side_units),
                total_defense=sum(u.defense for u in side_units)
            )
            sides.append(side)

    return sides


def naval_side_has_spirit_unit(side: NavalCombatSide) -> bool:
    """Check if any unit on a naval combat side has the spirit keyword."""
    return any(unit_has_keyword(u, 'spirit') for u in side.units if u.status == 'ACTIVE')


def should_submarine_engage(
    submarine: Unit,
    our_side: NavalCombatSide,
    enemy_side: NavalCombatSide
) -> bool:
    """
    Determine if a submarine should engage in combat.

    Submarine only engages if its side would deal damage (attack > enemy defense).

    Args:
        submarine: The submarine unit
        our_side: The submarine's side
        enemy_side: The enemy side

    Returns:
        True if submarine should engage, False otherwise
    """
    # Calculate total attack for our side
    return our_side.total_attack > enemy_side.total_defense


def filter_submarines_from_combat(
    sides: List[NavalCombatSide],
    hostile_pairs: List[Tuple[int, int]]
) -> List[NavalCombatSide]:
    """
    Filter out submarines that won't engage from combat sides.

    Submarines only engage if their side would deal damage.
    If a submarine won't engage, it's removed from its side for damage calculation.

    Args:
        sides: List of NavalCombatSide objects
        hostile_pairs: List of hostile (side_index, side_index) pairs

    Returns:
        Modified list of NavalCombatSide objects with non-engaging submarines removed
    """
    # Build a set of submarines that will engage
    engaging_submarines: Set[int] = set()

    for i, j in hostile_pairs:
        side_a, side_b = sides[i], sides[j]

        # Check submarines in side_a
        for unit in side_a.units:
            if unit_has_keyword(unit, 'submarine') and unit.status == 'ACTIVE':
                if should_submarine_engage(unit, side_a, side_b):
                    engaging_submarines.add(unit.id)
                    mark_submarine_in_combat(unit.id)

        # Check submarines in side_b
        for unit in side_b.units:
            if unit_has_keyword(unit, 'submarine') and unit.status == 'ACTIVE':
                if should_submarine_engage(unit, side_b, side_a):
                    engaging_submarines.add(unit.id)
                    mark_submarine_in_combat(unit.id)

    # Create new sides with non-engaging submarines filtered out
    filtered_sides = []
    for side in sides:
        filtered_units = []
        for unit in side.units:
            if unit_has_keyword(unit, 'submarine') and unit.id not in engaging_submarines:
                # This submarine won't engage - skip it
                continue
            filtered_units.append(unit)

        filtered_side = NavalCombatSide(
            faction_ids=side.faction_ids,
            units=filtered_units,
            total_attack=sum(u.attack for u in filtered_units if u.status == 'ACTIVE'),
            total_defense=sum(u.defense for u in filtered_units if u.status == 'ACTIVE')
        )
        filtered_sides.append(filtered_side)

    return filtered_sides


def calculate_naval_combat_damage_for_pairing(
    attacker_side: NavalCombatSide,
    defender_side: NavalCombatSide
) -> Dict[int, int]:
    """
    Calculate org damage for a single attacker vs defender pairing.

    Each unit on defender side loses 2 org if attacker's total attack > defender's total defense.
    If attacker has spirit units, defender takes +1 additional org damage (does not stack).

    Args:
        attacker_side: The attacking side
        defender_side: The defending side

    Returns:
        Dict mapping defender unit IDs to org damage
    """
    damage: Dict[int, int] = {}

    # Normal combat damage: 2 org if attack > defense
    if attacker_side.total_attack > defender_side.total_defense:
        for unit in defender_side.units:
            if unit.status == 'ACTIVE':
                damage[unit.id] = 2

    # Spirit bonus: if attacker has spirit unit, defender takes +1 org (flat, doesn't stack)
    if naval_side_has_spirit_unit(attacker_side):
        for unit in defender_side.units:
            if unit.status == 'ACTIVE':
                damage[unit.id] = damage.get(unit.id, 0) + 1

    return damage


async def get_affected_character_ids_for_naval_units(
    conn: asyncpg.Connection,
    units: List[Unit],
    guild_id: int
) -> List[int]:
    """
    Get character IDs that should be notified about naval combat events.

    Includes: owner + commander + faction members with COMMAND permission.

    Args:
        conn: Database connection
        units: List of naval units
        guild_id: Guild ID

    Returns:
        List of character IDs to notify
    """
    affected_ids = set()

    for unit in units:
        # Add owner
        if unit.owner_character_id is not None:
            affected_ids.add(unit.owner_character_id)

        # Add commander if different from owner
        if unit.commander_character_id is not None:
            affected_ids.add(unit.commander_character_id)

        # Add faction members with COMMAND permission
        faction_id = await get_unit_faction_id(conn, unit, guild_id)
        if faction_id is not None:
            command_holders = await FactionPermission.fetch_characters_with_permission(
                conn, faction_id, "COMMAND", guild_id
            )
            affected_ids.update(command_holders)

    return list(affected_ids)


async def find_all_naval_combat_territories(
    conn: asyncpg.Connection,
    guild_id: int
) -> Set[str]:
    """
    Find all territories where naval combat will occur.

    Naval combat occurs in any territory where:
    - At least one naval unit with patrol order is present, AND
    - At least one hostile naval unit is also present

    Args:
        conn: Database connection
        guild_id: Guild ID

    Returns:
        Set of territory IDs where combat will occur
    """
    all_combat_territories: Set[str] = set()

    # Find all patrol units
    patrol_units = await find_naval_patrol_units(conn, guild_id)

    # For each patrol unit, find territories where they trigger combat
    for patrol_unit in patrol_units:
        combat_territories = await find_combat_territories_for_patrol(conn, patrol_unit, guild_id)
        all_combat_territories.update(combat_territories)

    return all_combat_territories


async def resolve_naval_combat_in_territory(
    conn: asyncpg.Connection,
    territory_id: str,
    guild_id: int,
    damage_accumulator: Dict[int, int]
) -> List[TurnLog]:
    """
    Calculate naval combat damage for a single territory.

    This function calculates damage but does NOT apply it - damage is accumulated
    and applied later for simultaneous resolution.

    Args:
        conn: Database connection
        territory_id: Territory where combat occurs
        guild_id: Guild ID
        damage_accumulator: Dict to accumulate damage per unit_id

    Returns:
        List of TurnLog events for this combat
    """
    events: List[TurnLog] = []

    # Get all naval units in this territory
    all_units = await get_all_naval_units_in_territory(conn, territory_id, guild_id)

    if len(all_units) < 2:
        return events

    # Group units into sides
    sides = await group_units_into_naval_combat_sides(conn, all_units, guild_id)

    if len(sides) < 2:
        return events

    # Determine hostile pairs
    hostile_pairs: List[Tuple[int, int]] = []  # indices into sides list

    for i, side_a in enumerate(sides):
        for j, side_b in enumerate(sides[i + 1:], i + 1):
            # Check if any faction in side_a is at war with any in side_b
            is_hostile = False

            for faction_a in side_a.faction_ids:
                for faction_b in side_b.faction_ids:
                    if await are_factions_at_war(conn, faction_a, faction_b, guild_id):
                        is_hostile = True
                        break
                if is_hostile:
                    break

            if is_hostile:
                hostile_pairs.append((i, j))

    if not hostile_pairs:
        return events

    # Filter submarines that won't engage (submarines only engage if they would deal damage)
    # This also marks engaging submarines for observation visibility
    filtered_sides = filter_submarines_from_combat(sides, hostile_pairs)

    # Generate NAVAL_COMBAT_STARTED event (using original sides for reporting)
    all_participating_units = []
    all_faction_names = []
    all_affected_ids = []

    for side in sides:
        all_participating_units.extend([u.unit_id for u in side.units])
        for faction_id in side.faction_ids:
            faction = await Faction.fetch_by_id(conn, faction_id)
            if faction and faction.name not in all_faction_names:
                all_faction_names.append(faction.name)
        affected_ids = await get_affected_character_ids_for_naval_units(conn, side.units, guild_id)
        for char_id in affected_ids:
            if char_id not in all_affected_ids:
                all_affected_ids.append(char_id)

    events.append(TurnLog(
        turn_number=0,  # Will be set by caller
        phase=TurnPhase.COMBAT.value,
        event_type='NAVAL_COMBAT_STARTED',
        entity_type='territory',
        entity_id=None,
        event_data={
            'territory_id': territory_id,
            'participating_units': all_participating_units,
            'faction_names': all_faction_names,
            'sides_count': len(sides),
            'affected_character_ids': all_affected_ids
        },
        guild_id=guild_id
    ))

    # Use filtered sides for damage calculation (submarines that won't engage are excluded)
    sides = filtered_sides

    # Calculate damage for each hostile pairing
    for i, j in hostile_pairs:
        side_a, side_b = sides[i], sides[j]

        # A attacks B
        damage_to_b = calculate_naval_combat_damage_for_pairing(side_a, side_b)
        for unit_id, dmg in damage_to_b.items():
            damage_accumulator[unit_id] = damage_accumulator.get(unit_id, 0) + dmg

        # B attacks A
        damage_to_a = calculate_naval_combat_damage_for_pairing(side_b, side_a)
        for unit_id, dmg in damage_to_a.items():
            damage_accumulator[unit_id] = damage_accumulator.get(unit_id, 0) + dmg

    return events


async def get_transport_order_carrying_units(
    conn: asyncpg.Connection,
    naval_unit: Unit,
    guild_id: int
) -> List[int]:
    """
    Get the list of carried land unit IDs for a naval transport unit.

    Args:
        conn: Database connection
        naval_unit: The naval transport unit
        guild_id: Guild ID

    Returns:
        List of carried land unit internal IDs
    """
    # Find active transport order for this naval unit
    rows = await conn.fetch("""
        SELECT id, order_id, status, result_data, unit_ids
        FROM WargameOrder
        WHERE guild_id = $1
          AND $2 = ANY(unit_ids)
          AND order_type = 'UNIT'
          AND status IN ('SUCCESS', 'ONGOING')
          AND order_data->>'action' = 'naval_transport'
        ORDER BY id DESC
        LIMIT 1
    """, guild_id, naval_unit.id)

    if not rows:
        return []

    row = rows[0]
    # result_data is stored as JSON string in the database
    result_data_raw = row['result_data']
    if result_data_raw:
        if isinstance(result_data_raw, str):
            result_data = json.loads(result_data_raw)
        else:
            result_data = result_data_raw
    else:
        result_data = {}

    return result_data.get('carrying_units', [])


async def handle_transport_destruction(
    conn: asyncpg.Connection,
    naval_unit: Unit,
    guild_id: int,
    turn_number: int,
    phase: str
) -> List[TurnLog]:
    """
    Handle destruction of transported land units when naval transport is destroyed.

    Called when a naval unit with capacity > 0 is destroyed or disbanded.

    Args:
        conn: Database connection
        naval_unit: The naval transport unit being destroyed
        guild_id: Guild ID
        turn_number: Current turn number
        phase: The phase where this destruction occurs

    Returns:
        List of TurnLog events for cargo destruction
    """
    events: List[TurnLog] = []

    # Check if this unit has transport capacity
    if naval_unit.capacity <= 0:
        return events

    # Get the carrying units
    carrying_unit_ids = await get_transport_order_carrying_units(conn, naval_unit, guild_id)

    if not carrying_unit_ids:
        return events

    # Destroy each carried land unit
    destroyed_unit_names = []
    affected_ids = set()

    for land_unit_id in carrying_unit_ids:
        land_unit = await Unit.fetch_by_id(conn, land_unit_id)
        if not land_unit or land_unit.status != 'ACTIVE':
            continue

        # Set unit status to DISBANDED
        land_unit.status = 'DISBANDED'
        await land_unit.upsert(conn)

        destroyed_unit_names.append(land_unit.name or land_unit.unit_id)

        # Get affected character IDs
        if land_unit.owner_character_id:
            affected_ids.add(land_unit.owner_character_id)
        if land_unit.commander_character_id:
            affected_ids.add(land_unit.commander_character_id)

        # Generate event for each destroyed land unit
        events.append(TurnLog(
            turn_number=turn_number,
            phase=phase,
            event_type='UNIT_DISBANDED',
            entity_type='unit',
            entity_id=land_unit.id,
            event_data={
                'unit_id': land_unit.unit_id,
                'unit_name': land_unit.name or land_unit.unit_id,
                'reason': 'transport_destroyed',
                'transport_unit_id': naval_unit.unit_id,
                'transport_unit_name': naval_unit.name or naval_unit.unit_id,
                'affected_character_ids': list(affected_ids)
            },
            guild_id=guild_id
        ))

        logger.info(f"handle_transport_destruction: land unit {land_unit.unit_id} destroyed "
                    f"with transport {naval_unit.unit_id}")

    # Generate summary event for transport cargo destruction
    if destroyed_unit_names:
        # Add naval unit's affected characters
        nav_affected = await get_affected_character_ids_for_naval_units(conn, [naval_unit], guild_id)
        affected_ids.update(nav_affected)

        events.append(TurnLog(
            turn_number=turn_number,
            phase=phase,
            event_type='TRANSPORT_CARGO_DESTROYED',
            entity_type='unit',
            entity_id=naval_unit.id,
            event_data={
                'transport_unit_id': naval_unit.unit_id,
                'transport_unit_name': naval_unit.name or naval_unit.unit_id,
                'destroyed_land_units': destroyed_unit_names,
                'destroyed_land_unit_count': len(destroyed_unit_names),
                'territory_id': naval_unit.current_territory_id,
                'affected_character_ids': list(affected_ids)
            },
            guild_id=guild_id
        ))

    return events


async def execute_naval_combat_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute naval combat for all patrolling units.

    Algorithm:
    1. Find all territories where naval combat occurs
    2. For each territory, calculate damage (accumulated per unit)
    3. Apply accumulated damage to all units simultaneously
    4. Generate damage events
    5. Check for destroyed transports and handle carried units
    6. Generate combat ended events

    Note: Units are NOT disbanded here - that happens in the Organization phase.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for all naval combat
    """
    events: List[TurnLog] = []
    logger.info(f"Naval combat phase: starting for guild {guild_id}, turn {turn_number}")

    # Clear submarine combat tracking from previous turn
    clear_submarine_combat_tracking()

    # Find all territories where naval combat will occur
    combat_territories = await find_all_naval_combat_territories(conn, guild_id)

    if not combat_territories:
        logger.info(f"Naval combat phase: no combat territories found for guild {guild_id}")
        return events

    logger.info(f"Naval combat phase: found {len(combat_territories)} combat territories")

    # Accumulator for damage per unit across all territories
    damage_accumulator: Dict[int, int] = {}

    # Phase 1: Calculate damage for all combats
    for territory_id in combat_territories:
        combat_events = await resolve_naval_combat_in_territory(
            conn, territory_id, guild_id, damage_accumulator
        )
        # Set turn_number for events
        for event in combat_events:
            event.turn_number = turn_number
        events.extend(combat_events)

    # Phase 2: Apply accumulated damage and generate damage events
    units_to_check_for_transport: List[Unit] = []

    for unit_id, total_damage in damage_accumulator.items():
        unit = await Unit.fetch_by_id(conn, unit_id)
        if not unit or unit.status != 'ACTIVE':
            continue

        old_org = unit.organization
        unit.organization -= total_damage
        await unit.upsert(conn)

        # Track for transport destruction check
        if unit.organization <= 0:
            units_to_check_for_transport.append(unit)

        affected_ids = await get_affected_character_ids_for_naval_units(conn, [unit], guild_id)

        # Get the faction names that attacked this unit
        attacker_faction_names = []
        unit_faction_id = await get_unit_faction_id(conn, unit, guild_id)
        if unit_faction_id:
            # Find all factions at war with this unit's faction
            all_factions = await Faction.fetch_all(conn, guild_id)
            for faction in all_factions:
                if await are_factions_at_war(conn, unit_faction_id, faction.id, guild_id):
                    attacker_faction_names.append(faction.name)

        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.COMBAT.value,
            event_type='NAVAL_COMBAT_DAMAGE',
            entity_type='unit',
            entity_id=unit.id,
            event_data={
                'unit_id': unit.unit_id,
                'unit_name': unit.name or unit.unit_id,
                'damage': total_damage,
                'old_organization': old_org,
                'new_organization': unit.organization,
                'attacker_factions': attacker_faction_names,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

        logger.info(f"Naval combat phase: unit {unit.unit_id} took {total_damage} damage "
                    f"(org {old_org} -> {unit.organization})")

    # Phase 3: Handle transport destruction for units that dropped to 0 or below
    for unit in units_to_check_for_transport:
        transport_events = await handle_transport_destruction(
            conn, unit, guild_id, turn_number, TurnPhase.COMBAT.value
        )
        events.extend(transport_events)

    # Phase 4: Generate NAVAL_COMBAT_ENDED events for each territory
    for territory_id in combat_territories:
        all_units = await get_all_naval_units_in_territory(conn, territory_id, guild_id)
        surviving_units = [u for u in all_units if u.organization > 0]

        affected_ids = await get_affected_character_ids_for_naval_units(conn, all_units, guild_id)

        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.COMBAT.value,
            event_type='NAVAL_COMBAT_ENDED',
            entity_type='territory',
            entity_id=None,
            event_data={
                'territory_id': territory_id,
                'surviving_units': [u.unit_id for u in surviving_units],
                'surviving_count': len(surviving_units),
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

    logger.info(f"Naval combat phase: finished for guild {guild_id}, turn {turn_number}. "
                f"Generated {len(events)} events.")
    return events
