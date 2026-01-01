"""
Faction management command handlers.
"""
import asyncpg
from typing import Optional, Tuple
from db import Faction, FactionMember, Character, Unit, WargameConfig


async def create_faction(conn: asyncpg.Connection, faction_id: str, name: str, guild_id: int, leader_identifier: Optional[str] = None) -> Tuple[bool, str]:
    """
    Create a new faction.

    Args:
        conn: Database connection
        faction_id: Unique faction identifier
        name: Display name for faction
        guild_id: Guild ID
        leader_identifier: Optional character identifier for leader

    Returns:
        (success, message)
    """
    # Check if faction already exists
    existing = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if existing:
        return False, f"A faction with ID '{faction_id}' already exists."

    # Validate leader if provided
    leader_character_id = None
    if leader_identifier:
        leader_char = await Character.fetch_by_identifier(conn, leader_identifier, guild_id)
        if not leader_char:
            return False, f"Character '{leader_identifier}' not found. Create the character first using hawky."
        leader_character_id = leader_char.id

    # Get current turn for created_turn
    config = await WargameConfig.fetch(conn, guild_id)
    current_turn = config.current_turn if config else 0

    # Create faction
    faction = Faction(
        faction_id=faction_id,
        name=name,
        leader_character_id=leader_character_id,
        created_turn=current_turn,
        guild_id=guild_id
    )

    await faction.upsert(conn)

    # Add leader as member if specified
    if leader_character_id:
        # Fetch the newly created faction to get its internal ID
        faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)

        faction_member = FactionMember(
            faction_id=faction.id,
            character_id=leader_character_id,
            joined_turn=current_turn,
            guild_id=guild_id
        )
        await faction_member.insert(conn)

    if leader_identifier:
        return True, f"Faction '{name}' created successfully with leader {leader_identifier}."
    else:
        return True, f"Faction '{name}' created successfully."


async def delete_faction(conn: asyncpg.Connection, faction_id: str, guild_id: int) -> Tuple[bool, str]:
    """
    Delete a faction.

    Args:
        conn: Database connection
        faction_id: Faction identifier to delete
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Check if faction exists
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Check if faction has units
    units = await Unit.fetch_by_faction(conn, faction.id, guild_id)
    if units:
        return False, f"Cannot delete faction '{faction_id}' - it has {len(units)} units. Delete or reassign the units first."

    # Delete faction (CASCADE will delete FactionMember entries)
    await Faction.delete(conn, faction_id, guild_id)

    return True, f"Faction '{faction.name}' has been deleted."


async def set_faction_leader(conn: asyncpg.Connection, faction_id: str, leader_identifier: str, guild_id: int) -> Tuple[bool, str]:
    """
    Change the leader of a faction.

    Args:
        conn: Database connection
        faction_id: Faction identifier
        leader_identifier: Character identifier for new leader (or 'none' to remove)
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Check if faction exists
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Handle removing leader
    if leader_identifier.lower() == 'none':
        faction.leader_character_id = None
        await faction.upsert(conn)
        return True, f"Removed leader from faction '{faction.name}'."

    # Validate new leader
    leader_char = await Character.fetch_by_identifier(conn, leader_identifier, guild_id)
    if not leader_char:
        return False, f"Character '{leader_identifier}' not found."

    # Check if leader is a member of the faction
    faction_member = await FactionMember.fetch_by_character(conn, leader_char.id, guild_id)
    if not faction_member or faction_member.faction_id != faction.id:
        return False, f"{leader_char.name} is not a member of {faction.name}. Add them as a member first."

    # Update leader
    faction.leader_character_id = leader_char.id
    await faction.upsert(conn)

    return True, f"{leader_char.name} is now the leader of {faction.name}."


async def add_faction_member(conn: asyncpg.Connection, faction_id: str, character_identifier: str, guild_id: int) -> Tuple[bool, str]:
    """
    Add a member to a faction.

    Args:
        conn: Database connection
        faction_id: Faction identifier
        character_identifier: Character identifier to add
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Check if faction exists
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Validate character
    char = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not char:
        return False, f"Character '{character_identifier}' not found."

    # Check if already in a faction
    existing_membership = await FactionMember.fetch_by_character(conn, char.id, guild_id)
    if existing_membership:
        existing_faction = await Faction.fetch_by_id(conn, existing_membership.faction_id)
        return False, f"{char.name} is already a member of {existing_faction.name}. Remove them first."

    # Get current turn
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Add member
    faction_member = FactionMember(
        faction_id=faction.id,
        character_id=char.id,
        joined_turn=current_turn,
        guild_id=guild_id
    )
    await faction_member.insert(conn)

    return True, f"{char.name} has joined {faction.name}."


async def remove_faction_member(conn: asyncpg.Connection, character_identifier: str, guild_id: int) -> Tuple[bool, str]:
    """
    Remove a member from their faction.

    Args:
        conn: Database connection
        character_identifier: Character identifier to remove
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate character
    char = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not char:
        return False, f"Character '{character_identifier}' not found."

    # Check if in a faction
    faction_member = await FactionMember.fetch_by_character(conn, char.id, guild_id)
    if not faction_member:
        return False, f"{char.name} is not a member of any faction."

    # Get faction name
    faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

    # Check if character is the leader
    if faction.leader_character_id == char.id:
        return False, f"{char.name} is the leader of {faction.name}. Assign a new leader first using `/set-faction-leader`."

    # Remove member
    await FactionMember.delete(conn, char.id, guild_id)

    return True, f"{char.name} has left {faction.name}."
