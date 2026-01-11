"""
Resource management command handlers.
"""
import asyncpg
from typing import Tuple, Optional, Dict
from db import PlayerResources, Character, Faction, FactionResources


async def modify_resources(conn: asyncpg.Connection, character_identifier: str, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch or create resources for modification.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - resources: PlayerResources object
    """
    # Validate character
    char = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not char:
        return False, f"Character '{character_identifier}' not found.", None

    # Fetch or create resources
    resources = await PlayerResources.fetch_by_character(conn, char.id, guild_id)
    if not resources:
        # Create empty resources entry
        resources = PlayerResources(
            character_id=char.id,
            ore=0,
            lumber=0,
            coal=0,
            rations=0,
            cloth=0,
            platinum=0,
            guild_id=guild_id
        )
        await resources.upsert(conn)

    return True, "", {
        'character': char,
        'resources': resources
    }


async def modify_character_production(
    conn: asyncpg.Connection,
    character_identifier: str,
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch character for production modification.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
    """
    char = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not char:
        return False, f"Character '{character_identifier}' not found.", None

    return True, "", {'character': char}


async def modify_character_vp(
    conn: asyncpg.Connection,
    character_identifier: str,
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    Fetch character for victory points modification.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
    """
    char = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not char:
        return False, f"Character '{character_identifier}' not found.", None

    return True, "", {'character': char}


# ============== Faction Resource Handlers ==============


async def get_faction_resources(
    conn: asyncpg.Connection,
    faction_id: str,
    guild_id: int
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Get a faction's resource stockpile.

    Args:
        conn: Database connection
        faction_id: Faction identifier (user-facing)
        guild_id: Guild ID

    Returns:
        (success, message, resources_dict or None)
    """
    # Validate faction
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found.", None

    # Fetch or create resources
    resources = await FactionResources.fetch_by_faction(conn, faction.id, guild_id)
    if not resources:
        # Create empty resources entry
        resources = FactionResources(
            faction_id=faction.id,
            ore=0,
            lumber=0,
            coal=0,
            rations=0,
            cloth=0,
            platinum=0,
            guild_id=guild_id
        )
        await resources.upsert(conn)

    return True, f"Resources for {faction.name}.", {
        'faction_id': faction_id,
        'faction_name': faction.name,
        'ore': resources.ore,
        'lumber': resources.lumber,
        'coal': resources.coal,
        'rations': resources.rations,
        'cloth': resources.cloth,
        'platinum': resources.platinum
    }


async def modify_faction_resources(
    conn: asyncpg.Connection,
    faction_id: str,
    guild_id: int,
    changes: Dict[str, int]
) -> Tuple[bool, str]:
    """
    Modify a faction's resource stockpile (GM operation).

    Args:
        conn: Database connection
        faction_id: Faction identifier (user-facing)
        guild_id: Guild ID
        changes: Dict with resource changes (can be positive or negative)
                 Keys: ore, lumber, coal, rations, cloth, platinum

    Returns:
        (success, message)
    """
    # Validate faction
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Fetch or create resources
    resources = await FactionResources.fetch_by_faction(conn, faction.id, guild_id)
    if not resources:
        resources = FactionResources(
            faction_id=faction.id,
            ore=0,
            lumber=0,
            coal=0,
            rations=0,
            cloth=0,
            platinum=0,
            guild_id=guild_id
        )

    # Apply changes
    resource_fields = ['ore', 'lumber', 'coal', 'rations', 'cloth', 'platinum']
    changes_made = []

    for field in resource_fields:
        if field in changes and changes[field] != 0:
            old_value = getattr(resources, field)
            new_value = old_value + changes[field]

            # Prevent negative resources
            if new_value < 0:
                return False, f"Cannot reduce {field} below 0. Current: {old_value}, change: {changes[field]}"

            setattr(resources, field, new_value)
            change_str = f"+{changes[field]}" if changes[field] > 0 else str(changes[field])
            changes_made.append(f"{field}: {old_value} → {new_value} ({change_str})")

    if not changes_made:
        return False, "No resource changes specified."

    # Save changes
    await resources.upsert(conn)

    return True, f"Updated {faction.name} resources:\n" + "\n".join(changes_made)


async def get_or_create_faction_resources(
    conn: asyncpg.Connection,
    faction_id: int,
    guild_id: int
) -> FactionResources:
    """
    Helper to get or create faction resources by internal ID.

    Args:
        conn: Database connection
        faction_id: Internal faction ID
        guild_id: Guild ID

    Returns:
        FactionResources object
    """
    resources = await FactionResources.fetch_by_faction(conn, faction_id, guild_id)
    if not resources:
        resources = FactionResources(
            faction_id=faction_id,
            ore=0,
            lumber=0,
            coal=0,
            rations=0,
            cloth=0,
            platinum=0,
            guild_id=guild_id
        )
        await resources.upsert(conn)
    return resources
