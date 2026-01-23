"""
Combat phase handlers for land unit combat.

This module contains helper functions for processing combat during the COMBAT phase
of turn resolution.
"""
import asyncpg
from typing import List, Optional, Tuple, Dict, Set
from dataclasses import dataclass, field
from collections import defaultdict
import logging

from db import Unit, Territory, TurnLog, Building, Order, Faction, FactionPermission, Character
from order_types import OrderStatus, TurnPhase
from handlers.movement_handlers import (
    are_factions_at_war,
    are_factions_allied,
    get_unit_group_faction_id,
    get_affected_character_ids,
    get_territories_in_range,
    unit_has_keyword,
)
from handlers.encirclement_handlers import is_unit_exempt_from_engagement

logger = logging.getLogger(__name__)

# Maximum combat rounds to prevent infinite loops
MAX_COMBAT_ROUNDS = 10


@dataclass
class CombatSide:
    """Represents one side in combat (can be multiple allied factions)."""
    faction_ids: Set[int] = field(default_factory=set)
    units: List[Unit] = field(default_factory=list)
    total_attack: int = 0
    total_defense: int = 0
    has_capture_action: bool = False
    has_raid_action: bool = False


@dataclass
class CombatResult:
    """Result of a single combat round."""
    org_damage: Dict[int, int] = field(default_factory=dict)  # unit_id -> damage
    disbanded_unit_ids: List[int] = field(default_factory=list)
    retreating_side_faction_ids: Set[int] = field(default_factory=set)
    combat_over: bool = False
    victor_side: Optional[CombatSide] = None


async def get_unit_faction_id(conn: asyncpg.Connection, unit: Unit, guild_id: int) -> Optional[int]:
    """
    Get the faction ID for a single unit.

    Uses the unit's faction_id field if set, otherwise looks up the owner's
    represented_faction_id for character-owned units.

    Args:
        conn: Database connection
        unit: The unit to check
        guild_id: Guild ID

    Returns:
        The faction's internal ID, or None if unaffiliated
    """
    # First check direct faction_id on the unit
    if unit.faction_id:
        return unit.faction_id

    # For character-owned units, check the owner's represented faction
    if unit.owner_character_id:
        character = await Character.fetch_by_id(conn, unit.owner_character_id)
        if character:
            return character.represented_faction_id

    # For faction-owned units, use the owner faction
    if unit.owner_faction_id:
        return unit.owner_faction_id

    return None


async def get_unit_order_action(conn: asyncpg.Connection, unit: Unit, guild_id: int) -> Optional[str]:
    """
    Get the action from the unit's most recent movement order.

    Checks order result_data for the action (capture, raid, etc.).

    Args:
        conn: Database connection
        unit: The unit to check
        guild_id: Guild ID

    Returns:
        The action string or None if no relevant order
    """
    # Find orders that include this unit
    rows = await conn.fetch("""
        SELECT order_data, result_data
        FROM WargameOrder
        WHERE guild_id = $1
          AND $2 = ANY(unit_ids)
          AND phase = 'MOVEMENT'
          AND status IN ('SUCCESS', 'ONGOING')
        ORDER BY id DESC
        LIMIT 1
    """, guild_id, unit.id)

    if not rows:
        return None

    row = rows[0]
    import json
    order_data = json.loads(row['order_data']) if row['order_data'] else {}
    return order_data.get('action')


async def get_unit_movement_path(conn: asyncpg.Connection, unit: Unit, guild_id: int) -> Optional[List[str]]:
    """
    Get the movement path from the unit's most recent movement order result_data.

    Args:
        conn: Database connection
        unit: The unit to check
        guild_id: Guild ID

    Returns:
        The path list or None if no relevant order
    """
    rows = await conn.fetch("""
        SELECT order_data, result_data
        FROM WargameOrder
        WHERE guild_id = $1
          AND $2 = ANY(unit_ids)
          AND phase = 'MOVEMENT'
          AND status IN ('SUCCESS', 'ONGOING')
        ORDER BY id DESC
        LIMIT 1
    """, guild_id, unit.id)

    if not rows:
        return None

    row = rows[0]
    import json
    order_data = json.loads(row['order_data']) if row['order_data'] else {}
    return order_data.get('path')


def detect_action_conflicts(action_a: Optional[str], action_b: Optional[str]) -> bool:
    """
    Check if two actions are mutually exclusive (triggering combat between neutral factions).

    Conflicts:
    - Both have 'capture'
    - One has 'raid', other has 'capture'
    - Both have 'raid'

    Args:
        action_a: First unit's action
        action_b: Second unit's action

    Returns:
        True if actions conflict, False otherwise
    """
    if not action_a or not action_b:
        return False

    conflict_pairs = [
        ('capture', 'capture'),
        ('capture', 'raid'),
        ('raid', 'capture'),
        ('raid', 'raid'),
    ]

    return (action_a, action_b) in conflict_pairs


async def are_factions_hostile_for_combat(
    conn: asyncpg.Connection,
    faction_a_id: Optional[int],
    faction_b_id: Optional[int],
    guild_id: int,
    action_a: Optional[str] = None,
    action_b: Optional[str] = None,
    units_a: Optional[List[Unit]] = None,
    units_b: Optional[List[Unit]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Check if two factions are hostile for combat purposes.

    Hostile if:
    1. Factions are on opposite sides of an active war, OR
    2. Neutral factions with conflicting actions (capture vs capture, raid, etc.), OR
    3. One side has 'hostile' keyword and the other is not allied

    Args:
        conn: Database connection
        faction_a_id: First faction's internal ID (or None if unaffiliated)
        faction_b_id: Second faction's internal ID (or None if unaffiliated)
        guild_id: Guild ID
        action_a: Action for faction A's units (optional)
        action_b: Action for faction B's units (optional)
        units_a: Units from side A (optional, for hostile keyword check)
        units_b: Units from side B (optional, for hostile keyword check)

    Returns:
        (is_hostile, reason): Tuple of boolean and reason string ("war", "action_conflict", or "hostile_keyword")
    """
    if faction_a_id == faction_b_id and faction_a_id is not None:
        return False, None

    # Alliance check first (only if both have factions) - allied factions are never hostile
    if faction_a_id is not None and faction_b_id is not None:
        if await are_factions_allied(conn, faction_a_id, faction_b_id, guild_id):
            return False, None

    # HOSTILE keyword check - engages non-allied factions AND unaffiliated units
    if units_a and any(unit_has_keyword(u, 'hostile') for u in units_a):
        return True, "hostile_keyword"
    if units_b and any(unit_has_keyword(u, 'hostile') for u in units_b):
        return True, "hostile_keyword"

    # If either faction is None (unaffiliated), not hostile (unless hostile keyword above)
    if faction_a_id is None or faction_b_id is None:
        return False, None

    # Check war status
    at_war = await are_factions_at_war(conn, faction_a_id, faction_b_id, guild_id)
    if at_war:
        return True, "war"

    # Check for action conflicts between neutral factions
    if detect_action_conflicts(action_a, action_b):
        return True, "action_conflict"

    return False, None


async def find_combat_territories(
    conn: asyncpg.Connection,
    guild_id: int
) -> List[str]:
    """
    Find all territories where hostile units are co-located.

    Args:
        conn: Database connection
        guild_id: Guild ID

    Returns:
        List of territory IDs with potential combat
    """
    combat_territories = []

    # Get all territories with active units
    rows = await conn.fetch("""
        SELECT DISTINCT current_territory_id
        FROM Unit
        WHERE guild_id = $1
          AND status = 'ACTIVE'
          AND current_territory_id IS NOT NULL
          AND is_naval = FALSE
    """, guild_id)

    territory_ids = [row['current_territory_id'] for row in rows]

    for territory_id in territory_ids:
        # Get all active land units in this territory
        units = await Unit.fetch_by_territory(conn, territory_id, guild_id)
        active_land_units = [u for u in units if u.status == 'ACTIVE' and not u.is_naval]
        # Filter out infiltrator/aerial units (exempt from combat)
        active_land_units = [u for u in active_land_units if not is_unit_exempt_from_engagement(u)]

        if len(active_land_units) < 2:
            continue

        # Group units by faction
        faction_units: Dict[Optional[int], List[Unit]] = defaultdict(list)
        faction_actions: Dict[Optional[int], Optional[str]] = {}

        for unit in active_land_units:
            faction_id = await get_unit_faction_id(conn, unit, guild_id)
            faction_units[faction_id].append(unit)

            # Get the unit's action for this faction
            if faction_id not in faction_actions:
                action = await get_unit_order_action(conn, unit, guild_id)
                faction_actions[faction_id] = action

        # Check for hostilities between any faction pairs
        faction_ids = list(faction_units.keys())
        has_hostility = False

        for i, faction_a in enumerate(faction_ids):
            for faction_b in faction_ids[i+1:]:
                is_hostile, _ = await are_factions_hostile_for_combat(
                    conn, faction_a, faction_b, guild_id,
                    faction_actions.get(faction_a),
                    faction_actions.get(faction_b),
                    faction_units.get(faction_a, []),
                    faction_units.get(faction_b, [])
                )
                if is_hostile:
                    has_hostility = True
                    break
            if has_hostility:
                break

        if has_hostility:
            combat_territories.append(territory_id)

    return combat_territories


async def group_units_into_sides(
    conn: asyncpg.Connection,
    units: List[Unit],
    guild_id: int
) -> List[CombatSide]:
    """
    Group units into combat sides based on faction and alliance.

    Allied factions are combined into a single side.

    Args:
        conn: Database connection
        units: List of units in the territory
        guild_id: Guild ID

    Returns:
        List of CombatSide objects (one per side)
    """
    # Group units by faction first
    faction_units: Dict[Optional[int], List[Unit]] = defaultdict(list)
    faction_actions: Dict[Optional[int], Optional[str]] = {}

    for unit in units:
        faction_id = await get_unit_faction_id(conn, unit, guild_id)
        faction_units[faction_id].append(unit)

        # Get action for this faction's units
        if faction_id not in faction_actions:
            action = await get_unit_order_action(conn, unit, guild_id)
            faction_actions[faction_id] = action

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

    # Handle unaffiliated units (None faction) - each as its own side
    if None in faction_units:
        for unit in faction_units[None]:
            side = CombatSide(
                faction_ids=set(),
                units=[unit],
                total_attack=unit.attack,
                total_defense=unit.defense,
                has_capture_action=faction_actions.get(None) == 'capture',
                has_raid_action=faction_actions.get(None) == 'raid'
            )
            alliance_groups.append(set())  # Placeholder

    # Build combat sides from alliance groups
    sides: List[CombatSide] = []

    for group in alliance_groups:
        if not group:
            continue  # Skip empty groups

        side_units: List[Unit] = []
        has_capture = False
        has_raid = False

        for faction_id in group:
            side_units.extend(faction_units[faction_id])
            action = faction_actions.get(faction_id)
            if action == 'capture':
                has_capture = True
            if action == 'raid':
                has_raid = True

        if side_units:
            side = CombatSide(
                faction_ids=group,
                units=side_units,
                total_attack=sum(u.attack for u in side_units),
                total_defense=sum(u.defense for u in side_units),
                has_capture_action=has_capture,
                has_raid_action=has_raid
            )
            sides.append(side)

    return sides


def calculate_side_stats(side: CombatSide) -> Tuple[int, int]:
    """
    Calculate total attack and defense for a combat side.

    Args:
        side: CombatSide to calculate stats for

    Returns:
        (total_attack, total_defense)
    """
    return side.total_attack, side.total_defense


def recalculate_side_stats(side: CombatSide) -> None:
    """
    Recalculate total attack and defense for a combat side after unit changes.

    Modifies the side in place.

    Args:
        side: CombatSide to recalculate
    """
    active_units = [u for u in side.units if u.status == 'ACTIVE' and u.organization > 0]
    side.units = active_units
    side.total_attack = sum(u.attack for u in active_units)
    side.total_defense = sum(u.defense for u in active_units)


def side_has_immobile_unit(side: CombatSide) -> bool:
    """Check if any unit on a side has the immobile keyword."""
    return any(unit_has_keyword(u, 'immobile') for u in side.units if u.status == 'ACTIVE')


def side_has_spirit_unit(side: CombatSide) -> bool:
    """Check if any unit on a side has the spirit keyword."""
    return any(unit_has_keyword(u, 'spirit') for u in side.units if u.status == 'ACTIVE')


def calculate_org_damage_for_pairing(
    attacker_side: CombatSide,
    defender_side: CombatSide
) -> Dict[int, int]:
    """
    Calculate organization damage for a single attacker vs defender pairing.

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
    if side_has_spirit_unit(attacker_side):
        for unit in defender_side.units:
            if unit.status == 'ACTIVE':
                damage[unit.id] = damage.get(unit.id, 0) + 1

    return damage


def determine_retreating_side_for_pairing(
    side_a: CombatSide,
    side_b: CombatSide,
    territory_controller_faction_id: Optional[int]
) -> Optional[CombatSide]:
    """
    Determine which side retreats in a pairwise confrontation.

    If either side has immobile units, neither can retreat - fight to the death.
    Otherwise, side with lower attack retreats. Ties go to territory controller (stays).

    Args:
        side_a: First combat side
        side_b: Second combat side
        territory_controller_faction_id: Faction ID of territory controller (or None)

    Returns:
        The retreating CombatSide, or None if neither retreats
    """
    # If either side has immobile units, neither can retreat - fight to the death
    if side_has_immobile_unit(side_a) or side_has_immobile_unit(side_b):
        return None

    if side_a.total_attack < side_b.total_attack:
        return side_a
    elif side_b.total_attack < side_a.total_attack:
        return side_b
    else:
        # Tie - territory controller stays
        if territory_controller_faction_id:
            if territory_controller_faction_id in side_a.faction_ids:
                return side_b  # side_a is controller, side_b retreats
            elif territory_controller_faction_id in side_b.faction_ids:
                return side_a  # side_b is controller, side_a retreats
        # No controller or neither is controller - no retreat on tie
        return None


async def find_retreat_destination(
    conn: asyncpg.Connection,
    unit: Unit,
    territory_id: str,
    guild_id: int,
    hostile_faction_ids: Set[int]
) -> Optional[str]:
    """
    Find retreat destination for a unit.

    Priority:
    1. Original movement path (backtrack)
    2. Path toward faction capital
    3. Any adjacent non-hostile territory

    Args:
        conn: Database connection
        unit: The retreating unit
        territory_id: Current territory
        guild_id: Guild ID
        hostile_faction_ids: Set of faction IDs hostile to this unit

    Returns:
        Territory ID to retreat to, or None if no retreat possible
    """
    from db import TerritoryAdjacency

    # Try to get movement path from unit's order
    movement_path = await get_unit_movement_path(conn, unit, guild_id)

    if movement_path and territory_id in movement_path:
        # Find the previous territory in the path
        idx = movement_path.index(territory_id)
        if idx > 0:
            prev_territory = movement_path[idx - 1]
            # Check if previous territory is safe
            prev_units = await Unit.fetch_by_territory(conn, prev_territory, guild_id)
            hostile_in_prev = False
            for u in prev_units:
                if u.status == 'ACTIVE':
                    u_faction = await get_unit_faction_id(conn, u, guild_id)
                    if u_faction in hostile_faction_ids:
                        hostile_in_prev = True
                        break
            if not hostile_in_prev:
                return prev_territory

    # Get unit's faction for finding capital
    unit_faction_id = await get_unit_faction_id(conn, unit, guild_id)

    # Get adjacent territories
    adjacent = await TerritoryAdjacency.fetch_adjacent(conn, territory_id, guild_id)

    # Filter to non-hostile, non-water territories
    safe_destinations = []
    for adj_territory_id in adjacent:
        territory = await Territory.fetch_by_territory_id(conn, adj_territory_id, guild_id)
        if not territory:
            continue

        # Skip water territories
        if territory.terrain_type.lower() in ['ocean', 'lake', 'sea', 'water']:
            continue

        # Check for hostile units
        adj_units = await Unit.fetch_by_territory(conn, adj_territory_id, guild_id)
        has_hostile = False
        for u in adj_units:
            if u.status == 'ACTIVE':
                u_faction = await get_unit_faction_id(conn, u, guild_id)
                if u_faction in hostile_faction_ids:
                    has_hostile = True
                    break

        if not has_hostile:
            # Prioritize friendly-controlled territories
            is_friendly = False
            if unit_faction_id:
                if territory.controller_faction_id == unit_faction_id:
                    is_friendly = True
                elif territory.controller_faction_id:
                    is_friendly = await are_factions_allied(
                        conn, unit_faction_id, territory.controller_faction_id, guild_id
                    )

            safe_destinations.append((adj_territory_id, is_friendly))

    # Prefer friendly territories, then alphabetically
    safe_destinations.sort(key=lambda x: (not x[1], x[0]))

    if safe_destinations:
        return safe_destinations[0][0]

    return None


async def execute_retreat(
    conn: asyncpg.Connection,
    side: CombatSide,
    territory_id: str,
    guild_id: int,
    turn_number: int,
    hostile_faction_ids: Set[int]
) -> Tuple[List[TurnLog], bool]:
    """
    Execute retreat for a combat side.

    All units in the side retreat to an adjacent territory if possible.

    Args:
        conn: Database connection
        side: The retreating CombatSide
        territory_id: Current territory
        guild_id: Guild ID
        turn_number: Current turn number
        hostile_faction_ids: Set of hostile faction IDs

    Returns:
        (events, retreat_successful): Tuple of events and whether retreat succeeded
    """
    events: List[TurnLog] = []

    if not side.units:
        return events, True

    # Find retreat destination (use first unit's path as reference)
    retreat_destination = await find_retreat_destination(
        conn, side.units[0], territory_id, guild_id, hostile_faction_ids
    )

    if not retreat_destination:
        logger.info(f"execute_retreat: no retreat destination found for side with factions {side.faction_ids}")
        return events, False

    # Move all units to retreat destination
    retreated_unit_ids = []
    for unit in side.units:
        if unit.status == 'ACTIVE' and unit.organization > 0:
            unit.current_territory_id = retreat_destination
            await unit.upsert(conn)
            retreated_unit_ids.append(unit.unit_id)

    if retreated_unit_ids:
        # Get affected character IDs
        affected_ids = await get_affected_character_ids(conn, side.units, guild_id)

        # Get faction names for event
        faction_names = []
        for faction_id in side.faction_ids:
            faction = await Faction.fetch_by_id(conn, faction_id)
            if faction:
                faction_names.append(faction.name)

        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.COMBAT.value,
            event_type='COMBAT_RETREAT',
            entity_type='unit',
            entity_id=side.units[0].id if side.units else None,
            event_data={
                'units': retreated_unit_ids,
                'from_territory': territory_id,
                'to_territory': retreat_destination,
                'faction_names': faction_names,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

        logger.info(f"execute_retreat: {len(retreated_unit_ids)} units retreated from "
                    f"{territory_id} to {retreat_destination}")

    return events, True


async def resolve_territory_capture(
    conn: asyncpg.Connection,
    territory_id: str,
    remaining_sides: List[CombatSide],
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Resolve territory capture after combat.

    Only rural territories (not cities) can be captured in combat phase.
    Only units with explicit 'capture' action can capture.

    Args:
        conn: Database connection
        territory_id: Territory to potentially capture
        remaining_sides: Combat sides still present after combat
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for capture and building damage
    """
    events: List[TurnLog] = []

    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return events

    # Check if city - cities are NOT captured in combat phase
    if territory.terrain_type.lower() == 'city':
        logger.info(f"resolve_territory_capture: {territory_id} is a city, skipping capture")
        return events

    # Find sides with capture action that have remaining units
    capture_candidates = []
    for side in remaining_sides:
        if not side.has_capture_action:
            continue
        if not side.units:
            continue

        # Get the owner (character or faction) of the capturing units
        # Use the first unit's owner as the representative owner for this side
        representative_unit = side.units[0]

        capture_candidates.append({
            'side': side,
            'unit': representative_unit,
            'total_attack': side.total_attack,
            'unit_count': len(side.units),
            'total_defense': side.total_defense,
            'min_unit_id': min(u.id for u in side.units)
        })

    if not capture_candidates:
        logger.info(f"resolve_territory_capture: no capture candidates for {territory_id}")
        return events

    # If only one candidate, they capture
    # If multiple, use tiebreaker: attack > unit count > defense > lowest unit id
    capture_candidates.sort(key=lambda x: (
        -x['total_attack'],
        -x['unit_count'],
        -x['total_defense'],
        x['min_unit_id']
    ))

    winner = capture_candidates[0]
    winning_unit = winner['unit']

    # Determine new controller (character or faction based on unit ownership)
    old_controller_char = territory.controller_character_id
    old_controller_faction = territory.controller_faction_id

    if winning_unit.owner_character_id:
        territory.controller_character_id = winning_unit.owner_character_id
        territory.controller_faction_id = None
        new_controller_type = 'character'
        new_controller_id = winning_unit.owner_character_id
    else:
        territory.controller_faction_id = winning_unit.owner_faction_id
        territory.controller_character_id = None
        new_controller_type = 'faction'
        new_controller_id = winning_unit.owner_faction_id

    await territory.upsert(conn)

    # Get affected character IDs
    affected_ids = await get_affected_character_ids(conn, winner['side'].units, guild_id)

    # Add old controller to affected
    if old_controller_char and old_controller_char not in affected_ids:
        affected_ids.append(old_controller_char)
    if old_controller_faction:
        old_faction_chars = await FactionPermission.fetch_characters_with_permission(
            conn, old_controller_faction, "COMMAND", guild_id
        )
        for char_id in old_faction_chars:
            if char_id not in affected_ids:
                affected_ids.append(char_id)

    # Get new controller name
    if new_controller_type == 'character':
        controller = await Character.fetch_by_id(conn, new_controller_id)
        new_controller_name = controller.name if controller else 'Unknown'
    else:
        faction = await Faction.fetch_by_id(conn, new_controller_id)
        new_controller_name = faction.name if faction else 'Unknown'

    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.COMBAT.value,
        event_type='TERRITORY_CAPTURED',
        entity_type='territory',
        entity_id=territory.id,
        event_data={
            'territory_id': territory_id,
            'territory_name': territory.name or territory_id,
            'new_controller_type': new_controller_type,
            'new_controller_id': new_controller_id,
            'new_controller_name': new_controller_name,
            'capturing_units': [u.unit_id for u in winner['side'].units],
            'affected_character_ids': affected_ids
        },
        guild_id=guild_id
    ))

    logger.info(f"resolve_territory_capture: {territory_id} captured by "
                f"{new_controller_type} {new_controller_id}")

    # Damage all buildings in territory
    buildings = await Building.fetch_by_territory(conn, territory_id, guild_id)
    for building in buildings:
        if building.status != 'ACTIVE':
            continue

        old_durability = building.durability
        building.durability -= 1
        await building.upsert(conn)

        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.COMBAT.value,
            event_type='BUILDING_COMBAT_DAMAGE',
            entity_type='building',
            entity_id=building.id,
            event_data={
                'building_id': building.building_id,
                'building_name': building.name or building.building_id,
                'territory_id': territory_id,
                'old_durability': old_durability,
                'new_durability': building.durability,
                'damage_reason': 'territory_capture',
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        ))

    return events


async def resolve_combat_in_territory(
    conn: asyncpg.Connection,
    territory_id: str,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Resolve combat in a single territory.

    Combat continues in rounds until:
    - Only one side remains
    - All hostiles have retreated
    - Max rounds reached (safety limit)

    Args:
        conn: Database connection
        territory_id: Territory where combat occurs
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for this combat
    """
    events: List[TurnLog] = []

    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        logger.warning(f"resolve_combat_in_territory: territory {territory_id} not found")
        return events

    # Get all active land units in territory
    all_units = await Unit.fetch_by_territory(conn, territory_id, guild_id)
    active_land_units = [u for u in all_units if u.status == 'ACTIVE' and not u.is_naval]
    # Filter out infiltrator/aerial units (exempt from combat)
    active_land_units = [u for u in active_land_units if not is_unit_exempt_from_engagement(u)]

    if len(active_land_units) < 2:
        return events

    # Group units into sides
    sides = await group_units_into_sides(conn, active_land_units, guild_id)

    if len(sides) < 2:
        return events

    # Determine hostile pairs
    hostile_pairs: List[Tuple[int, int]] = []  # indices into sides list
    action_conflict_pairs: List[Tuple[int, int]] = []  # pairs fighting due to action conflicts

    for i, side_a in enumerate(sides):
        for j, side_b in enumerate(sides[i+1:], i+1):
            # Check if sides are hostile (considering hostile keyword at side level first)
            # Then check faction-level hostility for any faction pair
            is_hostile = False
            is_action_conflict = False

            # Check hostile keyword at side level (works even for unaffiliated units)
            if any(unit_has_keyword(u, 'hostile') for u in side_a.units if u.status == 'ACTIVE'):
                # Side A has hostile keyword - check if sides are allied
                sides_are_allied = False
                for faction_a in side_a.faction_ids:
                    for faction_b in side_b.faction_ids:
                        if await are_factions_allied(conn, faction_a, faction_b, guild_id):
                            sides_are_allied = True
                            break
                    if sides_are_allied:
                        break
                if not sides_are_allied:
                    is_hostile = True

            if not is_hostile and any(unit_has_keyword(u, 'hostile') for u in side_b.units if u.status == 'ACTIVE'):
                # Side B has hostile keyword - check if sides are allied
                sides_are_allied = False
                for faction_a in side_a.faction_ids:
                    for faction_b in side_b.faction_ids:
                        if await are_factions_allied(conn, faction_a, faction_b, guild_id):
                            sides_are_allied = True
                            break
                    if sides_are_allied:
                        break
                if not sides_are_allied:
                    is_hostile = True

            # If not hostile via keyword, check faction-pair hostility
            if not is_hostile:
                for faction_a in side_a.faction_ids:
                    for faction_b in side_b.faction_ids:
                        hostile, reason = await are_factions_hostile_for_combat(
                            conn, faction_a, faction_b, guild_id,
                            'capture' if side_a.has_capture_action else ('raid' if side_a.has_raid_action else None),
                            'capture' if side_b.has_capture_action else ('raid' if side_b.has_raid_action else None),
                            side_a.units, side_b.units
                        )
                        if hostile:
                            is_hostile = True
                            if reason == "action_conflict":
                                is_action_conflict = True
                            break
                    if is_hostile:
                        break

            if is_hostile:
                hostile_pairs.append((i, j))
                if is_action_conflict:
                    action_conflict_pairs.append((i, j))

    if not hostile_pairs:
        return events

    # Generate COMBAT_STARTED event
    all_participating_units = []
    all_faction_names = []
    all_affected_ids = []

    for side in sides:
        all_participating_units.extend([u.unit_id for u in side.units])
        for faction_id in side.faction_ids:
            faction = await Faction.fetch_by_id(conn, faction_id)
            if faction and faction.name not in all_faction_names:
                all_faction_names.append(faction.name)
        affected_ids = await get_affected_character_ids(conn, side.units, guild_id)
        for char_id in affected_ids:
            if char_id not in all_affected_ids:
                all_affected_ids.append(char_id)

    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.COMBAT.value,
        event_type='COMBAT_STARTED',
        entity_type='territory',
        entity_id=territory.id,
        event_data={
            'territory_id': territory_id,
            'territory_name': territory.name or territory_id,
            'participating_units': all_participating_units,
            'faction_names': all_faction_names,
            'sides_count': len(sides),
            'affected_character_ids': all_affected_ids
        },
        guild_id=guild_id
    ))

    # Generate ACTION_CONFLICT events for neutral factions fighting
    for i, j in action_conflict_pairs:
        side_a, side_b = sides[i], sides[j]

        for faction_a in side_a.faction_ids:
            for faction_b in side_b.faction_ids:
                faction_a_obj = await Faction.fetch_by_id(conn, faction_a)
                faction_b_obj = await Faction.fetch_by_id(conn, faction_b)

                events.append(TurnLog(
                    turn_number=turn_number,
                    phase=TurnPhase.COMBAT.value,
                    event_type='COMBAT_ACTION_CONFLICT',
                    entity_type='territory',
                    entity_id=territory.id,
                    event_data={
                        'territory_id': territory_id,
                        'faction_a_name': faction_a_obj.name if faction_a_obj else 'Unknown',
                        'faction_b_name': faction_b_obj.name if faction_b_obj else 'Unknown',
                        'action_a': 'capture' if side_a.has_capture_action else 'raid',
                        'action_b': 'capture' if side_b.has_capture_action else 'raid',
                        'recommendation': 'Consider coordinating actions with other factions in future turns to avoid unintended combat.',
                        'affected_character_ids': all_affected_ids
                    },
                    guild_id=guild_id
                ))

    # Combat loop
    combat_round = 0
    while combat_round < MAX_COMBAT_ROUNDS:
        combat_round += 1
        logger.info(f"resolve_combat_in_territory: round {combat_round} in {territory_id}")

        # Recalculate stats for all sides
        for side in sides:
            recalculate_side_stats(side)

        # Remove empty sides
        sides = [s for s in sides if s.units]

        # Check if combat is over
        if len(sides) < 2:
            break

        # Rebuild hostile pairs with remaining sides
        current_hostile_pairs = []
        for i, side_a in enumerate(sides):
            for j, side_b in enumerate(sides[i+1:], i+1):
                is_hostile = False

                # Check hostile keyword at side level first
                if any(unit_has_keyword(u, 'hostile') for u in side_a.units if u.status == 'ACTIVE'):
                    sides_are_allied = False
                    for faction_a in side_a.faction_ids:
                        for faction_b in side_b.faction_ids:
                            if await are_factions_allied(conn, faction_a, faction_b, guild_id):
                                sides_are_allied = True
                                break
                        if sides_are_allied:
                            break
                    if not sides_are_allied:
                        is_hostile = True

                if not is_hostile and any(unit_has_keyword(u, 'hostile') for u in side_b.units if u.status == 'ACTIVE'):
                    sides_are_allied = False
                    for faction_a in side_a.faction_ids:
                        for faction_b in side_b.faction_ids:
                            if await are_factions_allied(conn, faction_a, faction_b, guild_id):
                                sides_are_allied = True
                                break
                        if sides_are_allied:
                            break
                    if not sides_are_allied:
                        is_hostile = True

                # If not hostile via keyword, check faction-pair hostility
                if not is_hostile:
                    for faction_a in side_a.faction_ids:
                        for faction_b in side_b.faction_ids:
                            hostile, _ = await are_factions_hostile_for_combat(
                                conn, faction_a, faction_b, guild_id,
                                'capture' if side_a.has_capture_action else ('raid' if side_a.has_raid_action else None),
                                'capture' if side_b.has_capture_action else ('raid' if side_b.has_raid_action else None),
                                side_a.units, side_b.units
                            )
                            if hostile:
                                is_hostile = True
                                break
                        if is_hostile:
                            break

                if is_hostile:
                    current_hostile_pairs.append((i, j))

        if not current_hostile_pairs:
            break

        # Phase 1: Calculate all org damage for all hostile pairings
        cumulative_damage: Dict[int, int] = defaultdict(int)  # unit_id -> total damage

        for i, j in current_hostile_pairs:
            side_a, side_b = sides[i], sides[j]

            # A attacks B
            damage_to_b = calculate_org_damage_for_pairing(side_a, side_b)
            for unit_id, dmg in damage_to_b.items():
                cumulative_damage[unit_id] += dmg

            # B attacks A
            damage_to_a = calculate_org_damage_for_pairing(side_b, side_a)
            for unit_id, dmg in damage_to_a.items():
                cumulative_damage[unit_id] += dmg

        # Phase 2: Apply all damage simultaneously
        for unit_id, total_damage in cumulative_damage.items():
            # Find the unit
            for side in sides:
                for unit in side.units:
                    if unit.id == unit_id:
                        old_org = unit.organization
                        unit.organization -= total_damage
                        await unit.upsert(conn)

                        affected_ids = await get_affected_character_ids(conn, [unit], guild_id)
                        events.append(TurnLog(
                            turn_number=turn_number,
                            phase=TurnPhase.COMBAT.value,
                            event_type='COMBAT_ORG_DAMAGE',
                            entity_type='unit',
                            entity_id=unit.id,
                            event_data={
                                'unit_id': unit.unit_id,
                                'unit_name': unit.name or unit.unit_id,
                                'territory_id': territory_id,
                                'damage': total_damage,
                                'old_organization': old_org,
                                'new_organization': unit.organization,
                                'affected_character_ids': affected_ids
                            },
                            guild_id=guild_id
                        ))
                        break

        # Phase 3: Check for disbandment (org <= 0)
        for side in sides:
            for unit in list(side.units):  # Copy list to allow modification
                if unit.organization <= 0:
                    unit.status = 'DISBANDED'
                    await unit.upsert(conn)

                    affected_ids = await get_affected_character_ids(conn, [unit], guild_id)
                    events.append(TurnLog(
                        turn_number=turn_number,
                        phase=TurnPhase.COMBAT.value,
                        event_type='COMBAT_UNIT_DISBANDED',
                        entity_type='unit',
                        entity_id=unit.id,
                        event_data={
                            'unit_id': unit.unit_id,
                            'unit_name': unit.name or unit.unit_id,
                            'territory_id': territory_id,
                            'final_organization': unit.organization,
                            'affected_character_ids': affected_ids
                        },
                        guild_id=guild_id
                    ))

                    logger.info(f"resolve_combat_in_territory: unit {unit.unit_id} disbanded")

        # Recalculate after disbandment
        for side in sides:
            recalculate_side_stats(side)

        sides = [s for s in sides if s.units]

        if len(sides) < 2:
            break

        # Phase 4: Determine retreat
        # Build set of all hostile faction IDs for retreat destination checking
        all_hostile_faction_ids: Set[int] = set()
        for side in sides:
            all_hostile_faction_ids.update(side.faction_ids)

        # Determine which sides must retreat
        # A side retreats if it has lower attack in ANY of its pairings
        sides_to_retreat: Set[int] = set()  # indices

        current_hostile_pairs = []
        for i, side_a in enumerate(sides):
            for j, side_b in enumerate(sides[i+1:], i+1):
                is_hostile = False

                # Check hostile keyword at side level first
                if any(unit_has_keyword(u, 'hostile') for u in side_a.units if u.status == 'ACTIVE'):
                    sides_are_allied = False
                    for faction_a in side_a.faction_ids:
                        for faction_b in side_b.faction_ids:
                            if await are_factions_allied(conn, faction_a, faction_b, guild_id):
                                sides_are_allied = True
                                break
                        if sides_are_allied:
                            break
                    if not sides_are_allied:
                        is_hostile = True

                if not is_hostile and any(unit_has_keyword(u, 'hostile') for u in side_b.units if u.status == 'ACTIVE'):
                    sides_are_allied = False
                    for faction_a in side_a.faction_ids:
                        for faction_b in side_b.faction_ids:
                            if await are_factions_allied(conn, faction_a, faction_b, guild_id):
                                sides_are_allied = True
                                break
                        if sides_are_allied:
                            break
                    if not sides_are_allied:
                        is_hostile = True

                # If not hostile via keyword, check faction-pair hostility
                if not is_hostile:
                    for faction_a in side_a.faction_ids:
                        for faction_b in side_b.faction_ids:
                            hostile, _ = await are_factions_hostile_for_combat(
                                conn, faction_a, faction_b, guild_id,
                                'capture' if side_a.has_capture_action else ('raid' if side_a.has_raid_action else None),
                                'capture' if side_b.has_capture_action else ('raid' if side_b.has_raid_action else None),
                                side_a.units, side_b.units
                            )
                            if hostile:
                                is_hostile = True
                                break
                        if is_hostile:
                            break

                if is_hostile:
                    current_hostile_pairs.append((i, j))

        for i, j in current_hostile_pairs:
            side_a, side_b = sides[i], sides[j]

            retreating_side = determine_retreating_side_for_pairing(
                side_a, side_b, territory.controller_faction_id
            )

            if retreating_side:
                if retreating_side == side_a:
                    sides_to_retreat.add(i)
                else:
                    sides_to_retreat.add(j)

        # Execute retreats
        retreat_failed = False
        for side_idx in sides_to_retreat:
            side = sides[side_idx]

            # Get hostile faction IDs for this side's retreat
            hostile_for_this_side = set()
            for other_side in sides:
                if other_side == side:
                    continue
                # Check hostile keyword first
                if any(unit_has_keyword(u, 'hostile') for u in side.units if u.status == 'ACTIVE') or \
                   any(unit_has_keyword(u, 'hostile') for u in other_side.units if u.status == 'ACTIVE'):
                    hostile_for_this_side.update(other_side.faction_ids)
                    continue
                # Then check faction-pair hostility
                for faction_a in side.faction_ids:
                    for faction_b in other_side.faction_ids:
                        hostile, _ = await are_factions_hostile_for_combat(
                            conn, faction_a, faction_b, guild_id,
                            units_a=side.units, units_b=other_side.units
                        )
                        if hostile:
                            hostile_for_this_side.update(other_side.faction_ids)

            retreat_events, success = await execute_retreat(
                conn, side, territory_id, guild_id, turn_number, hostile_for_this_side
            )
            events.extend(retreat_events)

            if not success:
                retreat_failed = True

        # Remove retreated sides
        sides = [s for i, s in enumerate(sides) if i not in sides_to_retreat]

        # If retreat failed and no disbandment happened, combat continues
        # (this should eventually lead to max rounds or all units disbanded)

    # Check for max rounds
    if combat_round >= MAX_COMBAT_ROUNDS:
        events.append(TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.COMBAT.value,
            event_type='COMBAT_MAX_ROUNDS',
            entity_type='territory',
            entity_id=territory.id,
            event_data={
                'territory_id': territory_id,
                'territory_name': territory.name or territory_id,
                'rounds': combat_round,
                'warning': f'Combat terminated after {MAX_COMBAT_ROUNDS} rounds (safety limit). Some units may still be engaged.',
                'affected_character_ids': all_affected_ids
            },
            guild_id=guild_id
        ))
        logger.warning(f"resolve_combat_in_territory: max rounds reached in {territory_id}")

    # Determine victor and generate COMBAT_ENDED event
    remaining_sides = [s for s in sides if s.units]

    victor_faction_names = []
    if len(remaining_sides) == 1:
        for faction_id in remaining_sides[0].faction_ids:
            faction = await Faction.fetch_by_id(conn, faction_id)
            if faction:
                victor_faction_names.append(faction.name)

    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.COMBAT.value,
        event_type='COMBAT_ENDED',
        entity_type='territory',
        entity_id=territory.id,
        event_data={
            'territory_id': territory_id,
            'territory_name': territory.name or territory_id,
            'rounds': combat_round,
            'victor_factions': victor_faction_names,
            'remaining_units': [u.unit_id for s in remaining_sides for u in s.units],
            'affected_character_ids': all_affected_ids
        },
        guild_id=guild_id
    ))

    # Resolve territory capture
    capture_events = await resolve_territory_capture(
        conn, territory_id, remaining_sides, guild_id, turn_number
    )
    events.extend(capture_events)

    return events


async def execute_combat_phase(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Execute the Combat phase.

    Finds all territories with hostile units and resolves combat in each.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog events for all combat
    """
    events: List[TurnLog] = []
    logger.info(f"Combat phase: starting combat phase for guild {guild_id}, turn {turn_number}")

    # Find territories with combat
    combat_territories = await find_combat_territories(conn, guild_id)

    logger.info(f"Combat phase: found {len(combat_territories)} territories with potential combat")

    # Resolve combat in each territory
    for territory_id in combat_territories:
        territory_events = await resolve_combat_in_territory(
            conn, territory_id, guild_id, turn_number
        )
        events.extend(territory_events)

    logger.info(f"Combat phase: finished combat phase for guild {guild_id}, turn {turn_number}. "
                f"Generated {len(events)} events.")
    return events
