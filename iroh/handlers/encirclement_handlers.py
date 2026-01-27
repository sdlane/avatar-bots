"""
Encirclement phase handlers for the wargame system.

A land unit is **encircled** if no path exists over land through friendly/allied/neutral
territories to a territory controlled by its home faction or an ally. Encircled units
cannot have resources spent on them during upkeep and lose organization.
"""
import asyncpg
from typing import List, Set, Optional
from collections import deque
import logging
import json

from db import (
    Unit, Territory, Character, Alliance, WarParticipant, TerritoryAdjacency,
    FactionPermission, Order
)

logger = logging.getLogger(__name__)

# Water terrain types - units cannot traverse these
WATER_TERRAIN_TYPES = ['ocean', 'lake', 'sea', 'water']


async def get_allied_faction_ids(
    conn: asyncpg.Connection,
    faction_id: int,
    guild_id: int
) -> Set[int]:
    """
    Get set of faction IDs allied with the given faction (includes the faction itself).

    Args:
        conn: Database connection
        faction_id: The faction to check alliances for
        guild_id: Guild ID

    Returns:
        Set of faction IDs including self and all active allies
    """
    allied_ids = {faction_id}

    # Fetch all active alliances for this faction
    alliances = await Alliance.fetch_all_active(conn, guild_id)

    for alliance in alliances:
        if alliance.faction_a_id == faction_id:
            allied_ids.add(alliance.faction_b_id)
        elif alliance.faction_b_id == faction_id:
            allied_ids.add(alliance.faction_a_id)

    logger.debug(f"get_allied_faction_ids: faction {faction_id} allied with {allied_ids}")
    return allied_ids


async def get_enemy_faction_ids(
    conn: asyncpg.Connection,
    faction_id: int,
    guild_id: int
) -> Set[int]:
    """
    Get set of faction IDs on the opposite side of any war from the given faction.

    Args:
        conn: Database connection
        faction_id: The faction to check wars for
        guild_id: Guild ID

    Returns:
        Set of enemy faction IDs
    """
    enemy_ids = set()

    # Get all war participations for this faction
    participations = await WarParticipant.fetch_by_faction(conn, faction_id, guild_id)

    for participation in participations:
        # Get all participants in this war
        war_participants = await WarParticipant.fetch_by_war(conn, participation.war_id, guild_id)

        for other in war_participants:
            # If on opposite side, they're an enemy
            if other.faction_id != faction_id and other.side != participation.side:
                enemy_ids.add(other.faction_id)

    logger.debug(f"get_enemy_faction_ids: faction {faction_id} at war with {enemy_ids}")
    return enemy_ids


async def get_territory_controller_faction(
    conn: asyncpg.Connection,
    territory: Territory,
    guild_id: int
) -> Optional[int]:
    """
    Get the faction ID controlling a territory.

    For character controller: looks up character.represented_faction_id
    For faction controller: returns controller_faction_id
    For uncontrolled: returns None

    Args:
        conn: Database connection
        territory: The territory to check
        guild_id: Guild ID

    Returns:
        Faction ID (internal) or None if uncontrolled
    """
    if territory.controller_character_id is not None:
        # Character-controlled: look up their represented faction
        character = await Character.fetch_by_id(conn, territory.controller_character_id)
        if character:
            return character.represented_faction_id
        return None

    if territory.controller_faction_id is not None:
        return territory.controller_faction_id

    return None


async def is_territory_traversable(
    conn: asyncpg.Connection,
    territory: Territory,
    home_faction_id: int,
    allied_ids: Set[int],
    enemy_ids: Set[int],
    guild_id: int
) -> bool:
    """
    Check if a territory can be traversed for encirclement path finding.

    A territory is traversable if:
    - It's NOT ocean/lake terrain
    - It's uncontrolled (controller is None), OR
    - It's controlled by an allied faction, OR
    - It's controlled by a faction NOT at war (neutral)

    A territory is NOT traversable if:
    - It's ocean/lake terrain, OR
    - It's controlled by an enemy faction

    Args:
        conn: Database connection
        territory: The territory to check
        home_faction_id: The unit's home faction ID
        allied_ids: Set of allied faction IDs (including home faction)
        enemy_ids: Set of enemy faction IDs
        guild_id: Guild ID

    Returns:
        True if traversable, False otherwise
    """
    # Water territories are not traversable for land units
    if territory.terrain_type.lower() in WATER_TERRAIN_TYPES:
        return False

    # Get the controlling faction
    controller_faction = await get_territory_controller_faction(conn, territory, guild_id)

    # Uncontrolled territories are traversable
    if controller_faction is None:
        return True

    # Allied territories are traversable
    if controller_faction in allied_ids:
        return True

    # Enemy territories are NOT traversable
    if controller_faction in enemy_ids:
        return False

    # Neutral (not at war) territories are traversable
    return True


async def is_friendly_territory(
    conn: asyncpg.Connection,
    territory: Territory,
    allied_ids: Set[int],
    guild_id: int
) -> bool:
    """
    Check if a territory is controlled by a friendly faction (home or allied).

    Args:
        conn: Database connection
        territory: The territory to check
        allied_ids: Set of allied faction IDs (including home faction)
        guild_id: Guild ID

    Returns:
        True if controlled by an allied faction, False otherwise
    """
    controller_faction = await get_territory_controller_faction(conn, territory, guild_id)

    if controller_faction is None:
        return False

    return controller_faction in allied_ids


async def is_unit_transported(
    conn: asyncpg.Connection,
    unit: Unit,
    guild_id: int
) -> bool:
    """
    Check if a unit is currently being transported (on water via naval transport).

    Checks Order.result_data['transported'] == True for any ongoing movement order.

    Args:
        conn: Database connection
        unit: The unit to check
        guild_id: Guild ID

    Returns:
        True if unit is currently transported, False otherwise
    """
    # Fetch ongoing orders for this unit
    # We need to check if any movement order has result_data['transported'] = True
    # This requires looking at WargameOrder table
    query = """
        SELECT result_data
        FROM WargameOrder
        WHERE guild_id = $1
        AND status = 'ONGOING'
        AND $2 = ANY(unit_ids)
        AND order_type = 'UNIT'
    """
    rows = await conn.fetch(query, guild_id, unit.id)

    for row in rows:
        result_data = json.loads(row['result_data']) if row['result_data'] else None

        if result_data and result_data.get('transported') is True:
            return True

    return False


async def get_unit_home_faction_id(
    conn: asyncpg.Connection,
    unit: Unit,
    guild_id: int
) -> Optional[int]:
    """
    Get the home faction ID for a unit.

    For character-owned units: owner's represented_faction_id
    For faction-owned units: owner_faction_id

    Args:
        conn: Database connection
        unit: The unit to check
        guild_id: Guild ID

    Returns:
        Faction ID (internal) or None if unaffiliated
    """
    if unit.owner_character_id is not None:
        character = await Character.fetch_by_id(conn, unit.owner_character_id)
        if character:
            return character.represented_faction_id
        return None

    if unit.owner_faction_id is not None:
        return unit.owner_faction_id

    return None


async def bfs_can_reach_friendly(
    conn: asyncpg.Connection,
    start_territory_id: str,
    home_faction_id: int,
    allied_ids: Set[int],
    enemy_ids: Set[int],
    guild_id: int,
    convoy_traversable_ids: Optional[Set[str]] = None
) -> bool:
    """
    BFS to check if a path exists from start_territory to any friendly territory.

    The goal is to reach any territory controlled by a faction in allied_ids.
    Can traverse: friendly, allied, uncontrolled, neutral (not at war) land territories.
    Cannot traverse: ocean/lake, enemy territories (unless convoy support).

    With convoy support, territories in convoy_traversable_ids can also be traversed,
    allowing passage through ocean tiles (naval convoy) or certain other territories
    (aerial convoy).

    Args:
        conn: Database connection
        start_territory_id: Starting territory ID
        home_faction_id: The unit's home faction ID
        allied_ids: Set of allied faction IDs (including home faction)
        enemy_ids: Set of enemy faction IDs
        guild_id: Guild ID
        convoy_traversable_ids: Optional set of territory IDs traversable via convoy

    Returns:
        True if a path to friendly territory exists, False if encircled
    """
    # Get the starting territory
    start_territory = await Territory.fetch_by_territory_id(conn, start_territory_id, guild_id)
    if not start_territory:
        logger.warning(f"bfs_can_reach_friendly: start territory {start_territory_id} not found")
        return False

    # If starting territory is friendly, immediately return True
    if await is_friendly_territory(conn, start_territory, allied_ids, guild_id):
        return True

    # BFS
    visited = {start_territory_id}
    queue = deque([start_territory_id])

    while queue:
        current_id = queue.popleft()

        # Get adjacent territories
        adjacent_ids = await TerritoryAdjacency.fetch_adjacent(conn, current_id, guild_id)

        for adj_id in adjacent_ids:
            if adj_id in visited:
                continue

            visited.add(adj_id)

            # Fetch adjacent territory
            adj_territory = await Territory.fetch_by_territory_id(conn, adj_id, guild_id)
            if not adj_territory:
                continue

            # Check if this is a friendly territory (goal reached)
            if await is_friendly_territory(conn, adj_territory, allied_ids, guild_id):
                logger.debug(f"bfs_can_reach_friendly: found path from {start_territory_id} to friendly {adj_id}")
                return True

            # Check if traversable via normal means
            is_traversable = await is_territory_traversable(
                conn, adj_territory, home_faction_id, allied_ids, enemy_ids, guild_id
            )

            # Check if traversable via convoy
            is_convoy = convoy_traversable_ids and adj_id in convoy_traversable_ids

            if is_traversable or is_convoy:
                queue.append(adj_id)
                if is_convoy and not is_traversable:
                    logger.debug(f"bfs_can_reach_friendly: using convoy to traverse {adj_id}")

    # No path found to friendly territory
    logger.debug(f"bfs_can_reach_friendly: no path from {start_territory_id} to friendly territory")
    return False


def unit_has_keyword(unit: Unit, keyword: str) -> bool:
    """
    Check if a unit has a specific keyword (case-insensitive).

    Args:
        unit: The unit to check
        keyword: The keyword to look for

    Returns:
        True if unit has the keyword, False otherwise
    """
    if not unit.keywords:
        return False
    keyword_lower = keyword.lower()
    return any(k.lower() == keyword_lower for k in unit.keywords)


def is_unit_exempt_from_engagement(unit: Unit) -> bool:
    """
    Check if a unit is exempt from engagement and encirclement.

    Units with 'infiltrator', 'aerial', or 'aerial-transport' keywords cannot be engaged or encircled.

    Args:
        unit: The unit to check

    Returns:
        True if unit is exempt, False otherwise
    """
    return (unit_has_keyword(unit, 'infiltrator') or
            unit_has_keyword(unit, 'aerial') or
            unit_has_keyword(unit, 'aerial-transport'))


async def get_naval_convoy_territories(
    conn: asyncpg.Connection,
    guild_id: int,
    allied_ids: Set[int]
) -> Set[str]:
    """
    Get ocean territories traversable via naval convoy.

    Returns territory IDs where:
    - A naval unit occupies it
    - That unit has an active naval_convoy order
    - That unit belongs to a faction in allied_ids

    Args:
        conn: Database connection
        guild_id: Guild ID
        allied_ids: Set of allied faction IDs

    Returns:
        Set of territory IDs traversable via naval convoy
    """
    convoy_territories: Set[str] = set()

    # Fetch all active naval_convoy orders
    convoy_orders = await Order.fetch_active_by_action(conn, guild_id, 'naval_convoy')

    for order in convoy_orders:
        # Get units involved in this convoy order
        for unit_id in order.unit_ids:
            unit = await Unit.fetch_by_id(conn, unit_id)
            if not unit or not unit.is_naval:
                continue

            # Check if unit belongs to an allied faction
            unit_faction_id = await get_unit_home_faction_id(conn, unit, guild_id)
            if unit_faction_id and unit_faction_id in allied_ids:
                # Add the territory where this naval unit is located
                if unit.current_territory_id:
                    convoy_territories.add(unit.current_territory_id)
                    logger.debug(f"Naval convoy at {unit.current_territory_id} by unit {unit.unit_id}")

    return convoy_territories


async def get_aerial_convoy_territories(
    conn: asyncpg.Connection,
    guild_id: int,
    allied_ids: Set[int],
    enemy_ids: Set[int]
) -> Set[str]:
    """
    Get territories traversable via aerial convoy.

    Returns territory IDs where:
    - A unit with 'aerial-transport' keyword occupies it
    - That unit has an active aerial_convoy order
    - That unit belongs to a faction in allied_ids
    - The territory is NOT enemy-controlled

    Args:
        conn: Database connection
        guild_id: Guild ID
        allied_ids: Set of allied faction IDs
        enemy_ids: Set of enemy faction IDs

    Returns:
        Set of territory IDs traversable via aerial convoy
    """
    convoy_territories: Set[str] = set()

    # Fetch all active aerial_convoy orders
    convoy_orders = await Order.fetch_active_by_action(conn, guild_id, 'aerial_convoy')

    for order in convoy_orders:
        # Get units involved in this convoy order
        for unit_id in order.unit_ids:
            unit = await Unit.fetch_by_id(conn, unit_id)
            if not unit:
                continue

            # Check unit has aerial-transport keyword
            if not unit_has_keyword(unit, 'aerial-transport'):
                continue

            # Check if unit belongs to an allied faction
            unit_faction_id = await get_unit_home_faction_id(conn, unit, guild_id)
            if not unit_faction_id or unit_faction_id not in allied_ids:
                continue

            # Check territory is not enemy-controlled
            if unit.current_territory_id:
                territory = await Territory.fetch_by_territory_id(conn, unit.current_territory_id, guild_id)
                if territory:
                    controller_faction = await get_territory_controller_faction(conn, territory, guild_id)
                    # Aerial convoy works in: uncontrolled, allied, neutral (not enemy)
                    if controller_faction is None or controller_faction not in enemy_ids:
                        convoy_territories.add(unit.current_territory_id)
                        logger.debug(f"Aerial convoy at {unit.current_territory_id} by unit {unit.unit_id}")

    return convoy_territories


async def get_convoy_traversable_territories(
    conn: asyncpg.Connection,
    guild_id: int,
    home_faction_id: int,
    allied_ids: Set[int],
    enemy_ids: Set[int]
) -> Set[str]:
    """
    Combine naval and aerial convoy territories.

    Args:
        conn: Database connection
        guild_id: Guild ID
        home_faction_id: The unit's home faction ID
        allied_ids: Set of allied faction IDs
        enemy_ids: Set of enemy faction IDs

    Returns:
        Set of territory IDs traversable via convoy (naval or aerial)
    """
    naval_convoys = await get_naval_convoy_territories(conn, guild_id, allied_ids)
    aerial_convoys = await get_aerial_convoy_territories(conn, guild_id, allied_ids, enemy_ids)

    combined = naval_convoys | aerial_convoys
    logger.debug(f"Convoy traversable territories: naval={naval_convoys}, aerial={aerial_convoys}, combined={combined}")

    return combined


async def get_affected_character_ids_for_unit(
    conn: asyncpg.Connection,
    unit: Unit,
    guild_id: int
) -> List[int]:
    """
    Get character IDs that should be notified about encirclement events for a unit.

    Includes: owner + commander + faction members with COMMAND permission.

    Args:
        conn: Database connection
        unit: The unit
        guild_id: Guild ID

    Returns:
        List of character IDs to notify
    """
    affected_ids = set()

    # Add owner
    if unit.owner_character_id is not None:
        affected_ids.add(unit.owner_character_id)

    # Add commander if different from owner
    if unit.commander_character_id is not None:
        affected_ids.add(unit.commander_character_id)

    # Add faction members with COMMAND permission (if unit has a faction)
    if unit.faction_id is not None:
        command_holders = await FactionPermission.fetch_characters_with_permission(
            conn, unit.faction_id, "COMMAND", guild_id
        )
        affected_ids.update(command_holders)

    return list(affected_ids)


async def check_unit_encircled(
    conn: asyncpg.Connection,
    unit: Unit,
    guild_id: int
) -> bool:
    """
    Check if a single unit is encircled.

    A unit is encircled if:
    - It's a land unit (not naval)
    - It's not currently transported
    - No path exists over land through friendly/allied/neutral territories
      to a territory controlled by its home faction or an ally
    - Convoy support (naval_convoy, aerial_convoy orders) can provide additional
      traversable paths through ocean or other territories

    Args:
        conn: Database connection
        unit: The unit to check
        guild_id: Guild ID

    Returns:
        True if unit is encircled, False otherwise
    """
    # Naval units are never encircled
    if unit.is_naval:
        return False

    # Infiltrator and aerial units are never encircled
    if is_unit_exempt_from_engagement(unit):
        return False

    # Transported units are not encircled (Phase 1)
    if await is_unit_transported(conn, unit, guild_id):
        return False

    # Get unit's home faction
    home_faction_id = await get_unit_home_faction_id(conn, unit, guild_id)

    # Unaffiliated units (no home faction) are always encircled
    if home_faction_id is None:
        logger.debug(f"check_unit_encircled: unit {unit.unit_id} has no home faction - ENCIRCLED")
        return True

    # Unit must have a current territory
    if not unit.current_territory_id:
        logger.warning(f"check_unit_encircled: unit {unit.unit_id} has no current territory")
        return True

    # Get allied and enemy factions
    allied_ids = await get_allied_faction_ids(conn, home_faction_id, guild_id)
    enemy_ids = await get_enemy_faction_ids(conn, home_faction_id, guild_id)

    # Get convoy traversable territories (Phase 2)
    convoy_traversable_ids = await get_convoy_traversable_territories(
        conn, guild_id, home_faction_id, allied_ids, enemy_ids
    )

    # BFS to find path to friendly territory (with convoy support)
    can_reach = await bfs_can_reach_friendly(
        conn, unit.current_territory_id, home_faction_id,
        allied_ids, enemy_ids, guild_id,
        convoy_traversable_ids=convoy_traversable_ids
    )

    if not can_reach:
        logger.info(f"check_unit_encircled: unit {unit.unit_id} at {unit.current_territory_id} is ENCIRCLED")
        return True

    return False
