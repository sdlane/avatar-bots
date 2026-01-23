"""
Spirit Nexus handlers for BFS pathfinding and industrial damage logic.
"""
import asyncpg
from typing import Optional, Tuple, List
from collections import deque
from db import SpiritNexus, TerritoryAdjacency, TurnLog, BuildingType
import logging

logger = logging.getLogger(__name__)

# Pole swap pairs - if the nearest nexus is one of these, damage the other instead
POLE_SWAP_PAIRS = {
    'south-pole': 'north-pole',
    'north-pole': 'south-pole',
}


async def find_nearest_nexus(
    conn: asyncpg.Connection,
    start_territory_id: str,
    guild_id: int
) -> Tuple[Optional[SpiritNexus], int]:
    """
    Find the nearest spirit nexus to a given territory using BFS.

    Traverses ALL terrain types (including ocean/lake).
    If multiple nexuses are at the same distance, picks alphabetically by identifier.

    Args:
        conn: Database connection
        start_territory_id: The territory to start the search from
        guild_id: Guild ID

    Returns:
        Tuple of (nearest SpiritNexus or None, distance in territories)
    """
    # First check if there's a nexus at the start territory
    nexus_at_start = await SpiritNexus.fetch_by_territory(conn, start_territory_id, guild_id)
    if nexus_at_start:
        return nexus_at_start, 0

    # Get all nexuses in the guild
    all_nexuses = await SpiritNexus.fetch_all(conn, guild_id)
    if not all_nexuses:
        return None, -1

    # Build a set of territory IDs that have nexuses for quick lookup
    nexus_territories = {nexus.territory_id: nexus for nexus in all_nexuses}

    # BFS to find nearest nexus
    visited = {start_territory_id}
    queue = deque([(start_territory_id, 0)])  # (territory_id, distance)

    # Track nexuses found at each distance level
    found_at_distance: List[SpiritNexus] = []
    found_distance = -1

    while queue:
        current_territory, distance = queue.popleft()

        # If we already found nexuses at a closer distance, stop searching
        if found_distance >= 0 and distance > found_distance:
            break

        # Check if current territory has a nexus
        if current_territory in nexus_territories:
            if found_distance < 0:
                found_distance = distance
            if distance == found_distance:
                found_at_distance.append(nexus_territories[current_territory])

        # Get adjacent territories (traverses all terrain types)
        adjacent = await TerritoryAdjacency.fetch_adjacent(conn, current_territory, guild_id)

        for adj_territory in adjacent:
            if adj_territory not in visited:
                visited.add(adj_territory)
                queue.append((adj_territory, distance + 1))

    if not found_at_distance:
        return None, -1

    # If multiple nexuses at same distance, pick alphabetically by identifier
    found_at_distance.sort(key=lambda n: n.identifier)
    return found_at_distance[0], found_distance


def get_pole_swap_target(nexus_identifier: str) -> Optional[str]:
    """
    Get the pole swap target for a nexus identifier.

    Args:
        nexus_identifier: The identifier of the nearest nexus

    Returns:
        The identifier of the nexus to damage instead, or None if no swap needed
    """
    return POLE_SWAP_PAIRS.get(nexus_identifier)


def building_type_is_industrial(building_type: BuildingType) -> bool:
    """
    Check if a building type has the 'industrial' keyword.

    Args:
        building_type: The BuildingType to check

    Returns:
        True if the building type has the industrial keyword
    """
    if not building_type.keywords:
        return False
    return 'industrial' in [k.lower() for k in building_type.keywords]


def building_type_is_spiritual(building_type: BuildingType) -> bool:
    """
    Check if a building type has the 'spiritual' keyword.

    Args:
        building_type: The BuildingType to check

    Returns:
        True if the building type has the spiritual keyword
    """
    if not building_type.keywords:
        return False
    return 'spiritual' in [k.lower() for k in building_type.keywords]


def building_has_keyword(keywords: Optional[List[str]], keyword: str) -> bool:
    """
    Check if a list of keywords contains the specified keyword (case-insensitive).

    Args:
        keywords: List of keywords to check (can be None)
        keyword: The keyword to search for

    Returns:
        True if the keyword is found
    """
    if not keywords:
        return False
    return keyword.lower() in [k.lower() for k in keywords]


async def apply_industrial_damage(
    conn: asyncpg.Connection,
    territory_id: str,
    guild_id: int,
    turn_number: int,
    building_type_name: str,
    building_id: str
) -> Optional[TurnLog]:
    """
    Apply damage to the nearest spirit nexus when an industrial building is constructed.

    Implements the pole swap rule: if nearest nexus is "south-pole", damage "north-pole" instead
    (and vice versa).

    Args:
        conn: Database connection
        territory_id: The territory where the building was constructed
        guild_id: Guild ID
        turn_number: Current turn number
        building_type_name: Name of the building type constructed
        building_id: ID of the newly constructed building

    Returns:
        TurnLog entry for the damage event, or None if no nexus was damaged
    """
    # Find the nearest nexus
    nearest_nexus, distance = await find_nearest_nexus(conn, territory_id, guild_id)

    if nearest_nexus is None:
        logger.debug(f"No spirit nexus found for industrial damage from {territory_id}")
        return None

    # Check for pole swap
    original_nearest_identifier = nearest_nexus.identifier
    was_pole_swapped = False
    swap_target = get_pole_swap_target(nearest_nexus.identifier)

    if swap_target:
        # Need to damage the swap target instead
        target_nexus = await SpiritNexus.fetch_by_identifier(conn, swap_target, guild_id)
        if target_nexus:
            nearest_nexus = target_nexus
            was_pole_swapped = True
            logger.info(f"Pole swap: {original_nearest_identifier} -> {swap_target}")
        else:
            logger.warning(f"Pole swap target {swap_target} not found, damaging {original_nearest_identifier} instead")

    # Record old health and apply damage
    old_health = nearest_nexus.health
    nearest_nexus.health -= 1
    await nearest_nexus.upsert(conn)

    logger.info(
        f"Spirit nexus {nearest_nexus.identifier} damaged: {old_health} -> {nearest_nexus.health} "
        f"(source: {building_type_name} at {territory_id}, distance: {distance})"
    )

    # Create TurnLog entry (GM-only, no affected_character_ids)
    return TurnLog(
        turn_number=turn_number,
        phase='CONSTRUCTION',
        event_type='NEXUS_DAMAGED',
        entity_type='spirit_nexus',
        entity_id=nearest_nexus.id,
        event_data={
            'nexus_identifier': nearest_nexus.identifier,
            'nexus_territory_id': nearest_nexus.territory_id,
            'old_health': old_health,
            'new_health': nearest_nexus.health,
            'damage': 1,
            'source_territory_id': territory_id,
            'source_building_id': building_id,
            'source_building_type': building_type_name,
            'distance_from_source': distance,
            'was_pole_swapped': was_pole_swapped,
            'original_nearest_nexus': original_nearest_identifier if was_pole_swapped else None,
        },
        guild_id=guild_id
    )


async def apply_spiritual_repair(
    conn: asyncpg.Connection,
    territory_id: str,
    guild_id: int,
    turn_number: int,
    building_type_name: str,
    building_id: str
) -> Optional[TurnLog]:
    """
    Apply repair (+1 health) to the nearest spirit nexus when a spiritual building is constructed.

    Implements the pole swap rule: if nearest nexus is "south-pole", repair "north-pole" instead
    (and vice versa).

    Args:
        conn: Database connection
        territory_id: The territory where the building was constructed
        guild_id: Guild ID
        turn_number: Current turn number
        building_type_name: Name of the building type constructed
        building_id: ID of the newly constructed building

    Returns:
        TurnLog entry for the repair event, or None if no nexus was repaired
    """
    # Find the nearest nexus
    nearest_nexus, distance = await find_nearest_nexus(conn, territory_id, guild_id)

    if nearest_nexus is None:
        logger.debug(f"No spirit nexus found for spiritual repair from {territory_id}")
        return None

    # Check for pole swap
    original_nearest_identifier = nearest_nexus.identifier
    was_pole_swapped = False
    swap_target = get_pole_swap_target(nearest_nexus.identifier)

    if swap_target:
        # Need to repair the swap target instead
        target_nexus = await SpiritNexus.fetch_by_identifier(conn, swap_target, guild_id)
        if target_nexus:
            nearest_nexus = target_nexus
            was_pole_swapped = True
            logger.info(f"Pole swap (spiritual repair): {original_nearest_identifier} -> {swap_target}")
        else:
            logger.warning(f"Pole swap target {swap_target} not found, repairing {original_nearest_identifier} instead")

    # Record old health and apply repair
    old_health = nearest_nexus.health
    nearest_nexus.health += 1
    await nearest_nexus.upsert(conn)

    logger.info(
        f"Spirit nexus {nearest_nexus.identifier} repaired: {old_health} -> {nearest_nexus.health} "
        f"(source: {building_type_name} at {territory_id}, distance: {distance})"
    )

    # Create TurnLog entry (GM-only, no affected_character_ids)
    return TurnLog(
        turn_number=turn_number,
        phase='CONSTRUCTION',
        event_type='NEXUS_REPAIRED',
        entity_type='spirit_nexus',
        entity_id=nearest_nexus.id,
        event_data={
            'nexus_identifier': nearest_nexus.identifier,
            'nexus_territory_id': nearest_nexus.territory_id,
            'old_health': old_health,
            'new_health': nearest_nexus.health,
            'repair': 1,
            'source_territory_id': territory_id,
            'source_building_id': building_id,
            'source_building_type': building_type_name,
            'distance_from_source': distance,
            'was_pole_swapped': was_pole_swapped,
            'original_nearest_nexus': original_nearest_identifier if was_pole_swapped else None,
        },
        guild_id=guild_id
    )


async def apply_spiritual_destruction_damage(
    conn: asyncpg.Connection,
    territory_id: str,
    guild_id: int,
    turn_number: int,
    building_name: str,
    building_id: str,
    phase: str = 'ORGANIZATION'
) -> Optional[TurnLog]:
    """
    Apply damage (-2 health) to the nearest spirit nexus when a spiritual building is destroyed.

    Implements the pole swap rule: if nearest nexus is "south-pole", damage "north-pole" instead
    (and vice versa).

    Args:
        conn: Database connection
        territory_id: The territory where the building was destroyed
        guild_id: Guild ID
        turn_number: Current turn number
        building_name: Name of the building that was destroyed
        building_id: ID of the destroyed building
        phase: The turn phase (defaults to ORGANIZATION)

    Returns:
        TurnLog entry for the damage event, or None if no nexus was damaged
    """
    # Find the nearest nexus
    nearest_nexus, distance = await find_nearest_nexus(conn, territory_id, guild_id)

    if nearest_nexus is None:
        logger.debug(f"No spirit nexus found for spiritual destruction damage from {territory_id}")
        return None

    # Check for pole swap
    original_nearest_identifier = nearest_nexus.identifier
    was_pole_swapped = False
    swap_target = get_pole_swap_target(nearest_nexus.identifier)

    if swap_target:
        # Need to damage the swap target instead
        target_nexus = await SpiritNexus.fetch_by_identifier(conn, swap_target, guild_id)
        if target_nexus:
            nearest_nexus = target_nexus
            was_pole_swapped = True
            logger.info(f"Pole swap (spiritual destruction): {original_nearest_identifier} -> {swap_target}")
        else:
            logger.warning(f"Pole swap target {swap_target} not found, damaging {original_nearest_identifier} instead")

    # Record old health and apply damage (2 points for destruction)
    old_health = nearest_nexus.health
    nearest_nexus.health -= 2
    await nearest_nexus.upsert(conn)

    logger.info(
        f"Spirit nexus {nearest_nexus.identifier} damaged (spiritual destruction): {old_health} -> {nearest_nexus.health} "
        f"(source: {building_name} at {territory_id}, distance: {distance})"
    )

    # Create TurnLog entry (GM-only, no affected_character_ids)
    return TurnLog(
        turn_number=turn_number,
        phase=phase,
        event_type='NEXUS_DAMAGED',
        entity_type='spirit_nexus',
        entity_id=nearest_nexus.id,
        event_data={
            'nexus_identifier': nearest_nexus.identifier,
            'nexus_territory_id': nearest_nexus.territory_id,
            'old_health': old_health,
            'new_health': nearest_nexus.health,
            'damage': 2,
            'source_territory_id': territory_id,
            'source_building_id': building_id,
            'source_building_name': building_name,
            'reason': 'spiritual_building_destroyed',
            'distance_from_source': distance,
            'was_pole_swapped': was_pole_swapped,
            'original_nearest_nexus': original_nearest_identifier if was_pole_swapped else None,
        },
        guild_id=guild_id
    )
