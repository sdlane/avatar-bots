"""
Resource management command handlers.
"""
import asyncpg
from typing import Tuple, Optional
from db import PlayerResources, Character


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
