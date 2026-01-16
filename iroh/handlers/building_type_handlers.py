"""
Building type management command handlers.
"""
import asyncpg
from typing import Optional, Tuple
from db import BuildingType


async def create_building_type(conn: asyncpg.Connection, type_id: str, name: str, guild_id: int) -> Tuple[bool, str, Optional[dict]]:
    """
    Check if building type can be created and return data for modal.

    Returns:
        (success, message, data) where data contains type_id, name for modal
    """
    # Check if building type already exists
    existing = await BuildingType.fetch_by_type_id(conn, type_id, guild_id)
    if existing:
        return False, f"Building type '{type_id}' already exists.", None

    return True, "", {'type_id': type_id, 'name': name}


async def edit_building_type(conn: asyncpg.Connection, type_id: str, guild_id: int) -> Tuple[bool, str, Optional[BuildingType]]:
    """
    Fetch building type for editing.

    Returns:
        (success, message, building_type)
    """
    building_type = await BuildingType.fetch_by_type_id(conn, type_id, guild_id)

    if not building_type:
        return False, f"Building type '{type_id}' not found.", None

    return True, "", building_type


async def delete_building_type(conn: asyncpg.Connection, type_id: str, guild_id: int) -> Tuple[bool, str]:
    """Delete a building type."""
    building_type = await BuildingType.fetch_by_type_id(conn, type_id, guild_id)

    if not building_type:
        return False, f"Building type '{type_id}' not found."

    # NOTE: When buildings are implemented, add check here for buildings using this type

    # Delete building type
    await BuildingType.delete(conn, type_id, guild_id)

    return True, f"Building type '{building_type.name}' has been deleted."
