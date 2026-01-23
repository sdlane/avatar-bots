"""
Building management command handlers.
"""
import asyncpg
from typing import Optional, Tuple
from db import Building, BuildingType, Territory


async def create_building(
    conn: asyncpg.Connection,
    building_id: str,
    building_type_id: str,
    territory_id: str,
    guild_id: int,
    name: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Create a new building.

    Returns:
        (success, message)
    """
    # Check if building already exists
    existing = await Building.fetch_by_building_id(conn, building_id, guild_id)
    if existing:
        return False, f"Building '{building_id}' already exists."

    # Validate building type exists
    building_type = await BuildingType.fetch_by_type_id(conn, building_type_id, guild_id)
    if not building_type:
        return False, f"Building type '{building_type_id}' not found."

    # Validate territory exists
    territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
    if not territory:
        return False, f"Territory '{territory_id}' not found."

    # Check for duplicate building type in territory
    existing_buildings = await Building.fetch_by_territory(conn, territory_id, guild_id)
    for existing in existing_buildings:
        if existing.building_type == building_type_id:
            return False, f"Territory already has a building of type '{building_type_id}'."

    # Create building with upkeep and keywords from building type
    building = Building(
        building_id=building_id,
        name=name,
        building_type=building_type_id,
        territory_id=territory_id,
        durability=10,
        status="ACTIVE",
        upkeep_ore=building_type.upkeep_ore,
        upkeep_lumber=building_type.upkeep_lumber,
        upkeep_coal=building_type.upkeep_coal,
        upkeep_rations=building_type.upkeep_rations,
        upkeep_cloth=building_type.upkeep_cloth,
        upkeep_platinum=building_type.upkeep_platinum,
        keywords=building_type.keywords.copy() if building_type.keywords else [],
        guild_id=guild_id
    )

    # Verify building data
    valid, error_msg = building.verify()
    if not valid:
        return False, f"Invalid building data: {error_msg}"

    await building.upsert(conn)

    display_name = name or building_id
    return True, f"Building '{display_name}' ({building_type.name}) created in territory '{territory.name or territory_id}'."


async def edit_building(
    conn: asyncpg.Connection,
    building_id: str,
    guild_id: int,
    name: Optional[str] = None,
    durability: Optional[int] = None,
    status: Optional[str] = None,
    keywords: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Edit an existing building.

    Returns:
        (success, message)
    """
    building = await Building.fetch_by_building_id(conn, building_id, guild_id)
    if not building:
        return False, f"Building '{building_id}' not found."

    # Track changes
    changes = []

    if name is not None:
        building.name = name
        changes.append(f"name -> '{name}'")

    if durability is not None:
        if durability < 0:
            return False, "Durability cannot be negative."
        building.durability = durability
        changes.append(f"durability -> {durability}")

    if status is not None:
        valid_statuses = ["ACTIVE", "DESTROYED"]
        if status not in valid_statuses:
            return False, f"Status must be one of: {', '.join(valid_statuses)}"
        building.status = status
        changes.append(f"status -> {status}")

    if keywords is not None:
        if keywords.strip():
            building.keywords = [k.strip() for k in keywords.split(',') if k.strip()]
        else:
            building.keywords = []
        changes.append(f"keywords -> {building.keywords}")

    if not changes:
        return False, "No changes specified."

    await building.upsert(conn)

    display_name = building.name or building_id
    return True, f"Building '{display_name}' updated: {', '.join(changes)}"


async def delete_building(conn: asyncpg.Connection, building_id: str, guild_id: int) -> Tuple[bool, str]:
    """Delete a building."""
    building = await Building.fetch_by_building_id(conn, building_id, guild_id)
    if not building:
        return False, f"Building '{building_id}' not found."

    display_name = building.name or building_id
    await Building.delete(conn, building_id, guild_id)

    return True, f"Building '{display_name}' has been deleted."
