"""
Alliance management handlers.
"""
import asyncpg
from typing import Tuple, List, Optional
from db import Alliance, Faction, FactionMember, Character
from datetime import datetime


VALID_ALLIANCE_STATUSES = ['PENDING_FACTION_A', 'PENDING_FACTION_B', 'ACTIVE']


async def view_alliances(
    conn: asyncpg.Connection,
    guild_id: int,
    is_admin: bool,
    faction_leader_of_id: Optional[int]
) -> Tuple[bool, str, List[dict]]:
    """
    View alliances with permission-based filtering.

    - Public: ACTIVE alliances only
    - Faction leader: Also see PENDING involving their faction
    - Admin: See all alliances

    Args:
        conn: Database connection
        guild_id: Guild ID
        is_admin: Whether the user has manage_guild permission
        faction_leader_of_id: Internal faction ID if user is a faction leader, else None

    Returns:
        (success, message, alliances_list)
    """
    if is_admin:
        # Admin sees everything
        alliances = await Alliance.fetch_all(conn, guild_id)
    elif faction_leader_of_id:
        # Faction leader sees ACTIVE + pending involving their faction
        all_alliances = await Alliance.fetch_all(conn, guild_id)
        alliances = []
        for alliance in all_alliances:
            if alliance.status == 'ACTIVE':
                alliances.append(alliance)
            elif alliance.faction_a_id == faction_leader_of_id or alliance.faction_b_id == faction_leader_of_id:
                alliances.append(alliance)
    else:
        # Public sees only ACTIVE
        alliances = await Alliance.fetch_all_active(conn, guild_id)

    if not alliances:
        return True, "No alliances found.", []

    # Convert to dict format with faction names
    alliances_list = []
    for alliance in alliances:
        faction_a = await Faction.fetch_by_id(conn, alliance.faction_a_id)
        faction_b = await Faction.fetch_by_id(conn, alliance.faction_b_id)

        alliance_dict = {
            'faction_a_id': faction_a.faction_id if faction_a else 'Unknown',
            'faction_a_name': faction_a.name if faction_a else 'Unknown',
            'faction_b_id': faction_b.faction_id if faction_b else 'Unknown',
            'faction_b_name': faction_b.name if faction_b else 'Unknown',
            'status': alliance.status,
            'created_at': alliance.created_at.isoformat() if alliance.created_at else None,
            'activated_at': alliance.activated_at.isoformat() if alliance.activated_at else None
        }

        # Add who initiated for pending alliances (admin/leader view)
        if alliance.status != 'ACTIVE' and (is_admin or faction_leader_of_id):
            initiated_faction = await Faction.fetch_by_id(conn, alliance.initiated_by_faction_id)
            alliance_dict['initiated_by'] = initiated_faction.name if initiated_faction else 'Unknown'

            # Determine who is being waited on
            if alliance.status == 'PENDING_FACTION_A':
                # Faction B initiated, waiting for Faction A
                waiting_for = faction_a.name if faction_a else 'Unknown'
            else:
                # Faction A initiated, waiting for Faction B
                waiting_for = faction_b.name if faction_b else 'Unknown'
            alliance_dict['waiting_for'] = waiting_for

        alliances_list.append(alliance_dict)

    return True, f"Found {len(alliances)} alliance(s).", alliances_list


async def add_alliance(
    conn: asyncpg.Connection,
    faction_a_id: str,
    faction_b_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Admin command to directly create an ACTIVE alliance between two factions.

    Args:
        conn: Database connection
        faction_a_id: First faction's user-facing ID
        faction_b_id: Second faction's user-facing ID
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate faction A exists
    faction_a = await Faction.fetch_by_faction_id(conn, faction_a_id, guild_id)
    if not faction_a:
        return False, f"Faction '{faction_a_id}' not found."

    # Validate faction B exists
    faction_b = await Faction.fetch_by_faction_id(conn, faction_b_id, guild_id)
    if not faction_b:
        return False, f"Faction '{faction_b_id}' not found."

    # Can't ally with self
    if faction_a.id == faction_b.id:
        return False, "Cannot create an alliance between a faction and itself."

    # Check for existing alliance
    existing = await Alliance.fetch_by_factions(conn, faction_a.id, faction_b.id, guild_id)
    if existing and existing.status == 'ACTIVE':
        return False, f"Alliance already exists between {faction_a.name} and {faction_b.name}."

    # Canonical ordering
    fa_id = min(faction_a.id, faction_b.id)
    fb_id = max(faction_a.id, faction_b.id)

    if existing:
        # Update existing pending to active
        existing.status = 'ACTIVE'
        existing.activated_at = datetime.now()
        await existing.upsert(conn)
    else:
        # Create new active alliance
        alliance = Alliance(
            faction_a_id=fa_id,
            faction_b_id=fb_id,
            status='ACTIVE',
            initiated_by_faction_id=fa_id,  # Admin-created, use faction A as initiator
            created_at=datetime.now(),
            activated_at=datetime.now(),
            guild_id=guild_id
        )
        await alliance.insert(conn)

    return True, f"Alliance created between {faction_a.name} and {faction_b.name}."


async def edit_alliance(
    conn: asyncpg.Connection,
    faction_a_id: str,
    faction_b_id: str,
    status: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Admin command to directly set alliance status.

    Args:
        conn: Database connection
        faction_a_id: First faction's user-facing ID
        faction_b_id: Second faction's user-facing ID
        status: New status (PENDING_FACTION_A, PENDING_FACTION_B, or ACTIVE)
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate status
    if status not in VALID_ALLIANCE_STATUSES:
        return False, f"Invalid status '{status}'. Valid statuses: {', '.join(VALID_ALLIANCE_STATUSES)}"

    # Validate faction A exists
    faction_a = await Faction.fetch_by_faction_id(conn, faction_a_id, guild_id)
    if not faction_a:
        return False, f"Faction '{faction_a_id}' not found."

    # Validate faction B exists
    faction_b = await Faction.fetch_by_faction_id(conn, faction_b_id, guild_id)
    if not faction_b:
        return False, f"Faction '{faction_b_id}' not found."

    # Check alliance exists
    existing = await Alliance.fetch_by_factions(conn, faction_a.id, faction_b.id, guild_id)
    if not existing:
        return False, f"No alliance exists between {faction_a.name} and {faction_b.name}."

    old_status = existing.status

    # Update status
    existing.status = status
    if status == 'ACTIVE' and not existing.activated_at:
        existing.activated_at = datetime.now()
    elif status != 'ACTIVE':
        existing.activated_at = None

    await existing.upsert(conn)

    return True, f"Alliance between {faction_a.name} and {faction_b.name} updated: {old_status} -> {status}"


async def delete_alliance(
    conn: asyncpg.Connection,
    faction_a_id: str,
    faction_b_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Admin command to delete an alliance between two factions.

    Args:
        conn: Database connection
        faction_a_id: First faction's user-facing ID
        faction_b_id: Second faction's user-facing ID
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate faction A exists
    faction_a = await Faction.fetch_by_faction_id(conn, faction_a_id, guild_id)
    if not faction_a:
        return False, f"Faction '{faction_a_id}' not found."

    # Validate faction B exists
    faction_b = await Faction.fetch_by_faction_id(conn, faction_b_id, guild_id)
    if not faction_b:
        return False, f"Faction '{faction_b_id}' not found."

    # Try to delete
    deleted = await Alliance.delete(conn, faction_a.id, faction_b.id, guild_id)

    if deleted:
        return True, f"Alliance between {faction_a.name} and {faction_b.name} has been deleted."
    else:
        return False, f"No alliance exists between {faction_a.name} and {faction_b.name}."
