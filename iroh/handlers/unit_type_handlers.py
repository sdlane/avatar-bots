"""
Unit type management command handlers.
"""
import asyncpg
from typing import Optional, Tuple
from db import UnitType


async def create_unit_type(conn: asyncpg.Connection, type_id: str, name: str, guild_id: int, nation: Optional[str] = None) -> Tuple[bool, str, Optional[dict]]:
    """
    Check if unit type can be created and return data for modal.

    Returns:
        (success, message, data) where data contains type_id, name, nation for modal
    """
    # Check if unit type already exists
    existing = await UnitType.fetch_by_type_id(conn, type_id, nation, guild_id)
    if existing:
        if nation:
            return False, f"Unit type '{type_id}' for nation '{nation}' already exists.", None
        else:
            return False, f"Unit type '{type_id}' already exists.", None

    return True, "", {'type_id': type_id, 'name': name, 'nation': nation}


async def edit_unit_type(conn: asyncpg.Connection, type_id: str, guild_id: int, nation: Optional[str] = None) -> Tuple[bool, str, Optional[UnitType]]:
    """
    Fetch unit type for editing.

    Returns:
        (success, message, unit_type)
    """
    unit_type = await UnitType.fetch_by_type_id(conn, type_id, nation, guild_id)

    if not unit_type:
        if nation:
            return False, f"Unit type '{type_id}' for nation '{nation}' not found.", None
        else:
            return False, f"Unit type '{type_id}' not found.", None

    return True, "", unit_type


async def delete_unit_type(conn: asyncpg.Connection, type_id: str, guild_id: int, nation: Optional[str] = None) -> Tuple[bool, str]:
    """Delete a unit type."""
    unit_type = await UnitType.fetch_by_type_id(conn, type_id, nation, guild_id)

    if not unit_type:
        if nation:
            return False, f"Unit type '{type_id}' for nation '{nation}' not found."
        else:
            return False, f"Unit type '{type_id}' not found."

    # Check if any units use this type
    units = await conn.fetch(
        "SELECT * FROM Unit WHERE unit_type = $1 AND guild_id = $2;",
        type_id,
        guild_id
    )

    if units:
        return False, f"Cannot delete unit type '{type_id}' - {len(units)} units are using it. Delete those units first."

    # Delete unit type
    await UnitType.delete(conn, type_id, nation, guild_id)

    return True, f"Unit type '{unit_type.name}' has been deleted."
