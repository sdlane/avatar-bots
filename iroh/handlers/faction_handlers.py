"""
Faction management command handlers.
"""
import asyncpg
from typing import Optional, Tuple, List, Dict, Any
from db import (
    Faction, FactionMember, Character, Unit, WargameConfig, War, WarParticipant,
    FactionPermission, VALID_PERMISSION_TYPES
)


# ============== Permission Management Handlers ==============


async def sync_leader_permissions(
    conn: asyncpg.Connection,
    faction_id: int,
    new_leader_character_id: int,
    old_leader_character_id: Optional[int],
    guild_id: int
) -> Tuple[bool, str]:
    """
    Sync permissions when faction leader changes.
    Revokes all permissions from old leader, grants all to new leader.

    Args:
        conn: Database connection
        faction_id: Internal faction ID
        new_leader_character_id: Internal character ID of new leader
        old_leader_character_id: Internal character ID of old leader (or None)
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Revoke all permissions from old leader if there was one
    if old_leader_character_id is not None:
        await FactionPermission.delete_all_for_character_in_faction(
            conn, old_leader_character_id, faction_id, guild_id
        )

    # Grant all permissions to new leader
    for perm_type in VALID_PERMISSION_TYPES:
        permission = FactionPermission(
            faction_id=faction_id,
            character_id=new_leader_character_id,
            permission_type=perm_type,
            guild_id=guild_id
        )
        await permission.upsert(conn)

    return True, "Leader permissions synced."


async def grant_faction_permission(
    conn: asyncpg.Connection,
    faction_id: str,
    character_identifier: str,
    permission_type: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Grant a permission to a character for a faction.
    Validates that the character is a faction member.

    Args:
        conn: Database connection
        faction_id: Faction identifier (user-facing)
        character_identifier: Character identifier
        permission_type: One of VALID_PERMISSION_TYPES
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate permission type
    if permission_type not in VALID_PERMISSION_TYPES:
        return False, f"Invalid permission type '{permission_type}'. Must be one of: {', '.join(VALID_PERMISSION_TYPES)}"

    # Validate faction
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Validate character
    char = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not char:
        return False, f"Character '{character_identifier}' not found."

    # Check if character is a member of the faction
    membership = await FactionMember.fetch_membership(conn, faction.id, char.id, guild_id)
    if not membership:
        return False, f"{char.name} is not a member of {faction.name}. Only faction members can hold permissions."

    # Check if already has the permission
    has_perm = await FactionPermission.has_permission(conn, faction.id, char.id, permission_type, guild_id)
    if has_perm:
        return False, f"{char.name} already has {permission_type} permission for {faction.name}."

    # Grant permission
    permission = FactionPermission(
        faction_id=faction.id,
        character_id=char.id,
        permission_type=permission_type,
        guild_id=guild_id
    )
    await permission.upsert(conn)

    return True, f"Granted {permission_type} permission to {char.name} for {faction.name}."


async def revoke_faction_permission(
    conn: asyncpg.Connection,
    faction_id: str,
    character_identifier: str,
    permission_type: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Revoke a permission from a character for a faction.

    Args:
        conn: Database connection
        faction_id: Faction identifier (user-facing)
        character_identifier: Character identifier
        permission_type: One of VALID_PERMISSION_TYPES
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate permission type
    if permission_type not in VALID_PERMISSION_TYPES:
        return False, f"Invalid permission type '{permission_type}'. Must be one of: {', '.join(VALID_PERMISSION_TYPES)}"

    # Validate faction
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Validate character
    char = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not char:
        return False, f"Character '{character_identifier}' not found."

    # Check if has the permission
    has_perm = await FactionPermission.has_permission(conn, faction.id, char.id, permission_type, guild_id)
    if not has_perm:
        return False, f"{char.name} does not have {permission_type} permission for {faction.name}."

    # Revoke permission
    permission = FactionPermission(
        faction_id=faction.id,
        character_id=char.id,
        permission_type=permission_type,
        guild_id=guild_id
    )
    await permission.delete(conn)

    return True, f"Revoked {permission_type} permission from {char.name} for {faction.name}."


async def get_faction_permissions(
    conn: asyncpg.Connection,
    faction_id: str,
    guild_id: int
) -> Tuple[bool, str, Optional[List[Dict[str, Any]]]]:
    """
    Get all permissions for a faction.

    Args:
        conn: Database connection
        faction_id: Faction identifier (user-facing)
        guild_id: Guild ID

    Returns:
        (success, message, list of permission dicts or None)
    """
    # Validate faction
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found.", None

    # Fetch all permissions
    permissions = await FactionPermission.fetch_by_faction(conn, faction.id, guild_id)

    if not permissions:
        return True, f"No permissions set for {faction.name}.", []

    # Build result with character names
    result = []
    char_cache = {}  # Cache character lookups

    for perm in permissions:
        if perm.character_id not in char_cache:
            char = await Character.fetch_by_id(conn, perm.character_id)
            char_cache[perm.character_id] = char

        char = char_cache[perm.character_id]
        result.append({
            'character_identifier': char.identifier if char else 'unknown',
            'character_name': char.name if char else 'Unknown',
            'permission_type': perm.permission_type
        })

    return True, f"Found {len(permissions)} permission(s) for {faction.name}.", result


# ============== Faction Management Handlers ==============


async def create_faction(conn: asyncpg.Connection, faction_id: str, name: str, guild_id: int, leader_identifier: Optional[str] = None, nation: Optional[str] = None) -> Tuple[bool, str]:
    """
    Create a new faction.

    Args:
        conn: Database connection
        faction_id: Unique faction identifier
        name: Display name for faction
        guild_id: Guild ID
        leader_identifier: Optional character identifier for leader
        nation: Optional nation identifier (e.g., 'fire-nation', 'earth-kingdom')

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
        guild_id=guild_id,
        nation=nation
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

        # Grant all permissions to the leader
        await sync_leader_permissions(conn, faction.id, leader_character_id, None, guild_id)

    if leader_identifier:
        return True, f"Faction '{name}' created successfully with leader {leader_identifier}."
    else:
        return True, f"Faction '{name}' created successfully."


async def set_faction_nation(conn: asyncpg.Connection, faction_id: str, nation: str, guild_id: int) -> Tuple[bool, str]:
    """
    Set or update a faction's nation.

    Args:
        conn: Database connection
        faction_id: Faction identifier
        nation: Nation identifier (e.g., 'fire-nation', 'earth-kingdom')
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Check if faction exists
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    old_nation = faction.nation
    faction.nation = nation
    await faction.upsert(conn)

    if old_nation:
        return True, f"Updated nation for '{faction.name}' from '{old_nation}' to '{nation}'."
    else:
        return True, f"Set nation for '{faction.name}' to '{nation}'."


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

    old_leader_id = faction.leader_character_id

    # Handle removing leader
    if leader_identifier.lower() == 'none':
        # Revoke permissions from old leader
        if old_leader_id is not None:
            await FactionPermission.delete_all_for_character_in_faction(
                conn, old_leader_id, faction.id, guild_id
            )
        faction.leader_character_id = None
        await faction.upsert(conn)
        return True, f"Removed leader from faction '{faction.name}'."

    # Validate new leader
    leader_char = await Character.fetch_by_identifier(conn, leader_identifier, guild_id)
    if not leader_char:
        return False, f"Character '{leader_identifier}' not found."

    # Check if leader is a member of the faction
    faction_member = await FactionMember.fetch_membership(conn, faction.id, leader_char.id, guild_id)
    if not faction_member:
        return False, f"{leader_char.name} is not a member of {faction.name}. Add them as a member first."

    # Update leader
    faction.leader_character_id = leader_char.id
    await faction.upsert(conn)

    # Sync permissions: revoke from old leader, grant to new leader
    await sync_leader_permissions(conn, faction.id, leader_char.id, old_leader_id, guild_id)

    return True, f"{leader_char.name} is now the leader of {faction.name}."


async def add_faction_member(conn: asyncpg.Connection, faction_id: str, character_identifier: str, guild_id: int) -> Tuple[bool, str]:
    """
    Add a member to a faction.
    Characters can be members of multiple factions.
    On first faction join, the faction is automatically set as the character's represented faction.

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

    # Check if already a member of THIS faction
    existing_membership = await FactionMember.fetch_membership(conn, faction.id, char.id, guild_id)
    if existing_membership:
        return False, f"{char.name} is already a member of {faction.name}."

    # Get current turn
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Check if this is the character's first faction
    all_memberships = await FactionMember.fetch_all_by_character(conn, char.id, guild_id)
    is_first_faction = len(all_memberships) == 0

    # Add member
    faction_member = FactionMember(
        faction_id=faction.id,
        character_id=char.id,
        joined_turn=current_turn,
        guild_id=guild_id
    )
    await faction_member.insert(conn)

    # If first faction, auto-set as represented faction
    if is_first_faction:
        char.represented_faction_id = faction.id
        await char.upsert(conn)
        return True, f"{char.name} has joined {faction.name} (now representing this faction)."

    return True, f"{char.name} has joined {faction.name}."


async def remove_faction_member(conn: asyncpg.Connection, character_identifier: str, guild_id: int, faction_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Remove a member from a faction.

    Args:
        conn: Database connection
        character_identifier: Character identifier to remove
        guild_id: Guild ID
        faction_id: Optional faction identifier. If not provided, removes from represented faction.

    Returns:
        (success, message)
    """
    # Validate character
    char = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not char:
        return False, f"Character '{character_identifier}' not found."

    # Determine which faction to leave
    if faction_id:
        faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
        if not faction:
            return False, f"Faction '{faction_id}' not found."
        faction_member = await FactionMember.fetch_membership(conn, faction.id, char.id, guild_id)
        if not faction_member:
            return False, f"{char.name} is not a member of {faction.name}."
    else:
        # Default to represented faction or any membership
        faction_member = await FactionMember.fetch_by_character(conn, char.id, guild_id)
        if not faction_member:
            return False, f"{char.name} is not a member of any faction."
        faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

    # Check if character is the leader of this faction
    if faction.leader_character_id == char.id:
        return False, f"{char.name} is the leader of {faction.name}. Assign a new leader first using `/set-faction-leader`."

    # Check if leaving the represented faction
    is_represented_faction = char.represented_faction_id == faction.id

    # Revoke all permissions for this character in this faction
    await FactionPermission.delete_all_for_character_in_faction(
        conn, char.id, faction.id, guild_id
    )

    # Remove member from this specific faction
    await FactionMember.delete(conn, char.id, guild_id, faction_id=faction.id)

    # Handle representation change if leaving represented faction
    if is_represented_faction:
        # Get remaining memberships
        remaining_memberships = await FactionMember.fetch_all_by_character(conn, char.id, guild_id)

        if remaining_memberships:
            # Auto-assign to most recent membership (highest joined_turn)
            new_represented_faction = await Faction.fetch_by_id(conn, remaining_memberships[0].faction_id)
            char.represented_faction_id = remaining_memberships[0].faction_id
            # Note: Auto-assignment does NOT reset cooldown
            await char.upsert(conn)

            # Update owned units to new represented faction
            from db import Unit
            units = await Unit.fetch_by_owner(conn, char.id, guild_id)
            for unit in units:
                if unit.faction_id == faction.id:
                    unit.faction_id = char.represented_faction_id
                    await unit.upsert(conn)

            return True, f"{char.name} has left {faction.name}. Now representing {new_represented_faction.name}."
        else:
            # No more memberships - clear representation
            char.represented_faction_id = None
            await char.upsert(conn)

            # Update owned units to have no faction
            from db import Unit
            units = await Unit.fetch_by_owner(conn, char.id, guild_id)
            for unit in units:
                if unit.faction_id == faction.id:
                    unit.faction_id = None
                    await unit.upsert(conn)

            return True, f"{char.name} has left {faction.name}. No longer representing any faction."

    return True, f"{char.name} has left {faction.name}."


# ============== War Management Handlers ==============


async def view_wars(
    conn: asyncpg.Connection,
    guild_id: int
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    View all wars in the guild.

    Args:
        conn: Database connection
        guild_id: Guild ID

    Returns:
        (success, message, list of war dicts)
    """
    wars = await War.fetch_all(conn, guild_id)

    if not wars:
        return True, "No active wars.", []

    war_data = []
    for war in wars:
        participants = await WarParticipant.fetch_by_war(conn, war.id, guild_id)

        side_a = []
        side_b = []
        for p in participants:
            faction = await Faction.fetch_by_id(conn, p.faction_id)
            if faction:
                faction_info = {
                    'faction_id': faction.faction_id,
                    'name': faction.name,
                    'is_original_declarer': p.is_original_declarer,
                    'joined_turn': p.joined_turn
                }
                if p.side == "SIDE_A":
                    side_a.append(faction_info)
                else:
                    side_b.append(faction_info)

        war_data.append({
            'war_id': war.war_id,
            'objective': war.objective,
            'declared_turn': war.declared_turn,
            'side_a': side_a,
            'side_b': side_b
        })

    return True, f"Found {len(wars)} war(s).", war_data


async def edit_war(
    conn: asyncpg.Connection,
    war_id: str,
    objective: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Edit a war's objective.

    Args:
        conn: Database connection
        war_id: War ID to edit
        objective: New objective text
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    war = await War.fetch_by_id(conn, war_id, guild_id)
    if not war:
        return False, f"War '{war_id}' not found."

    old_objective = war.objective
    war.objective = objective
    await war.upsert(conn)

    return True, f"War '{war_id}' objective updated from '{old_objective}' to '{objective}'."


async def add_war_participant(
    conn: asyncpg.Connection,
    war_id: str,
    faction_id: str,
    side: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Add a faction to a war on a specified side.

    Args:
        conn: Database connection
        war_id: War ID
        faction_id: Faction ID to add
        side: "SIDE_A" or "SIDE_B"
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate side
    if side not in ("SIDE_A", "SIDE_B"):
        return False, f"Invalid side '{side}'. Must be 'SIDE_A' or 'SIDE_B'."

    # Validate war
    war = await War.fetch_by_id(conn, war_id, guild_id)
    if not war:
        return False, f"War '{war_id}' not found."

    # Validate faction
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Check if already in war
    existing = await WarParticipant.fetch_by_war_and_faction(conn, war.id, faction.id, guild_id)
    if existing:
        return False, f"Faction '{faction.name}' is already in war '{war_id}' on {existing.side}."

    # Get current turn
    config = await WargameConfig.fetch(conn, guild_id)
    current_turn = config.current_turn if config else 0

    # Add participant
    participant = WarParticipant(
        war_id=war.id,
        faction_id=faction.id,
        side=side,
        joined_turn=current_turn,
        is_original_declarer=False,
        guild_id=guild_id
    )
    await participant.insert(conn)

    return True, f"Faction '{faction.name}' added to war '{war_id}' on {side}."


async def remove_war_participant(
    conn: asyncpg.Connection,
    war_id: str,
    faction_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Remove a faction from a war.

    Args:
        conn: Database connection
        war_id: War ID
        faction_id: Faction ID to remove
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate war
    war = await War.fetch_by_id(conn, war_id, guild_id)
    if not war:
        return False, f"War '{war_id}' not found."

    # Validate faction
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Check if in war
    existing = await WarParticipant.fetch_by_war_and_faction(conn, war.id, faction.id, guild_id)
    if not existing:
        return False, f"Faction '{faction.name}' is not in war '{war_id}'."

    # Remove participant
    await WarParticipant.delete(conn, war.id, faction.id, guild_id)

    return True, f"Faction '{faction.name}' removed from war '{war_id}'."


async def delete_war(
    conn: asyncpg.Connection,
    war_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Delete a war and all its participants.

    Args:
        conn: Database connection
        war_id: War ID to delete
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate war
    war = await War.fetch_by_id(conn, war_id, guild_id)
    if not war:
        return False, f"War '{war_id}' not found."

    objective = war.objective

    # Delete war (CASCADE will delete WarParticipant entries)
    deleted = await War.delete(conn, war_id, guild_id)

    if deleted:
        return True, f"War '{war_id}' (objective: '{objective}') has been deleted."
    else:
        return False, f"Failed to delete war '{war_id}'."


# ============== Faction Spending Handlers ==============


async def edit_faction_spending(
    conn: asyncpg.Connection,
    faction_id: str,
    guild_id: int,
    spending: Dict[str, int]
) -> Tuple[bool, str]:
    """
    Edit a faction's per-turn spending configuration.
    Only updates fields that are present in the spending dict.

    Args:
        conn: Database connection
        faction_id: Faction identifier (user-facing)
        guild_id: Guild ID
        spending: Dict with spending values to update (only provided keys are changed)
                  Keys: ore, lumber, coal, rations, cloth, platinum

    Returns:
        (success, message)
    """
    # Validate faction exists
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found."

    # Validate all provided spending values are non-negative
    for rt, value in spending.items():
        if value < 0:
            return False, f"Spending for {rt} must be >= 0."

    # Update only the provided faction spending fields
    if 'ore' in spending:
        faction.ore_spending = spending['ore']
    if 'lumber' in spending:
        faction.lumber_spending = spending['lumber']
    if 'coal' in spending:
        faction.coal_spending = spending['coal']
    if 'rations' in spending:
        faction.rations_spending = spending['rations']
    if 'cloth' in spending:
        faction.cloth_spending = spending['cloth']
    if 'platinum' in spending:
        faction.platinum_spending = spending['platinum']

    await faction.upsert(conn)

    # Build summary of changes
    if spending:
        changes = [f"{rt}: {value}" for rt, value in spending.items()]
        return True, f"Updated spending for {faction.name}: {', '.join(changes)}"
    else:
        return True, f"No changes made to spending for {faction.name}."


async def get_faction_spending(
    conn: asyncpg.Connection,
    faction_id: str,
    guild_id: int,
    character_id: Optional[int] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Get a faction's spending configuration.

    Args:
        conn: Database connection
        faction_id: Faction identifier (user-facing)
        guild_id: Guild ID
        character_id: Optional - if provided, verify they are a member of the faction

    Returns:
        (success, message, spending_dict or None)
    """
    # Validate faction exists
    faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
    if not faction:
        return False, f"Faction '{faction_id}' not found.", None

    # If character_id provided, verify they are a member
    if character_id is not None:
        membership = await FactionMember.fetch_by_character(conn, character_id, guild_id)
        if not membership or membership.faction_id != faction.id:
            return False, f"You are not a member of {faction.name}.", None

    # Return spending data
    spending_data = {
        'faction_id': faction.faction_id,
        'faction_name': faction.name,
        'ore': faction.ore_spending,
        'lumber': faction.lumber_spending,
        'coal': faction.coal_spending,
        'rations': faction.rations_spending,
        'cloth': faction.cloth_spending,
        'platinum': faction.platinum_spending
    }

    return True, f"Spending for {faction.name}.", spending_data


# ============== Representation Management Handlers ==============


async def set_character_representation(
    conn: asyncpg.Connection,
    character_id: int,
    target_faction_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Change which faction a character publicly represents.
    Enforces 3-turn cooldown.

    Args:
        conn: Database connection
        character_id: Internal character ID
        target_faction_id: Faction identifier to represent
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate character
    char = await Character.fetch_by_id(conn, character_id)
    if not char:
        return False, "Character not found."

    # Validate target faction
    faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
    if not faction:
        return False, f"Faction '{target_faction_id}' not found."

    # Check if character is a member of target faction
    membership = await FactionMember.fetch_membership(conn, faction.id, char.id, guild_id)
    if not membership:
        return False, f"You are not a member of {faction.name}. Join the faction first."

    # Check if already representing this faction
    if char.represented_faction_id == faction.id:
        return False, f"You are already representing {faction.name}."

    # Get current turn
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    # Check cooldown
    can_change, turns_remaining = char.can_change_representation(current_turn)
    if not can_change:
        return False, f"Cannot change representation yet. {turns_remaining} turn(s) remaining until cooldown expires."

    # Get old faction name for message
    old_faction_name = None
    if char.represented_faction_id:
        old_faction = await Faction.fetch_by_id(conn, char.represented_faction_id)
        old_faction_name = old_faction.name if old_faction else None

    # Update representation
    char.represented_faction_id = faction.id
    char.representation_changed_turn = current_turn
    await char.upsert(conn)

    # Update owned units' faction_id to new represented faction
    from db import Unit
    units = await Unit.fetch_by_owner(conn, char.id, guild_id)
    updated_count = 0
    for unit in units:
        if unit.faction_id != faction.id:
            unit.faction_id = faction.id
            await unit.upsert(conn)
            updated_count += 1

    if old_faction_name:
        msg = f"Now representing {faction.name} (was {old_faction_name})."
    else:
        msg = f"Now representing {faction.name}."

    if updated_count > 0:
        msg += f" Updated {updated_count} unit(s) to {faction.name}."

    return True, msg


async def admin_set_character_representation(
    conn: asyncpg.Connection,
    character_identifier: str,
    target_faction_id: str,
    guild_id: int
) -> Tuple[bool, str]:
    """
    Admin command to set a character's representation, bypassing cooldown.

    Args:
        conn: Database connection
        character_identifier: Character identifier
        target_faction_id: Faction identifier to represent
        guild_id: Guild ID

    Returns:
        (success, message)
    """
    # Validate character
    char = await Character.fetch_by_identifier(conn, character_identifier, guild_id)
    if not char:
        return False, f"Character '{character_identifier}' not found."

    # Validate target faction
    faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
    if not faction:
        return False, f"Faction '{target_faction_id}' not found."

    # Check if character is a member of target faction
    membership = await FactionMember.fetch_membership(conn, faction.id, char.id, guild_id)
    if not membership:
        return False, f"{char.name} is not a member of {faction.name}."

    # Get old faction name for message
    old_faction_name = None
    if char.represented_faction_id:
        old_faction = await Faction.fetch_by_id(conn, char.represented_faction_id)
        old_faction_name = old_faction.name if old_faction else None

    # Update representation (no cooldown check, no cooldown reset)
    char.represented_faction_id = faction.id
    # Don't set representation_changed_turn - admin bypass doesn't start cooldown
    await char.upsert(conn)

    # Update owned units' faction_id to new represented faction
    from db import Unit
    units = await Unit.fetch_by_owner(conn, char.id, guild_id)
    updated_count = 0
    for unit in units:
        if unit.faction_id != faction.id:
            unit.faction_id = faction.id
            await unit.upsert(conn)
            updated_count += 1

    if old_faction_name:
        msg = f"{char.name} now representing {faction.name} (was {old_faction_name}). [Admin override]"
    else:
        msg = f"{char.name} now representing {faction.name}. [Admin override]"

    if updated_count > 0:
        msg += f" Updated {updated_count} unit(s)."

    return True, msg


async def get_character_memberships(
    conn: asyncpg.Connection,
    character_id: int,
    guild_id: int
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Get all faction memberships for a character.

    Args:
        conn: Database connection
        character_id: Internal character ID
        guild_id: Guild ID

    Returns:
        (success, message, membership_data or None)
    """
    # Validate character
    char = await Character.fetch_by_id(conn, character_id)
    if not char:
        return False, "Character not found.", None

    # Get all memberships
    memberships = await FactionMember.fetch_all_by_character(conn, char.id, guild_id)

    if not memberships:
        return True, f"{char.name} is not a member of any faction.", {
            'character_name': char.name,
            'represented_faction': None,
            'memberships': [],
            'can_change_representation': True,
            'turns_until_change': 0
        }

    # Get current turn for cooldown check
    wargame_config = await conn.fetchrow(
        "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
        guild_id
    )
    current_turn = wargame_config['current_turn'] if wargame_config else 0

    can_change, turns_remaining = char.can_change_representation(current_turn)

    # Build membership list
    membership_list = []
    represented_faction_info = None

    for membership in memberships:
        faction = await Faction.fetch_by_id(conn, membership.faction_id)
        if faction:
            is_represented = char.represented_faction_id == faction.id
            is_leader = faction.leader_character_id == char.id
            faction_info = {
                'faction_id': faction.faction_id,
                'faction_name': faction.name,
                'joined_turn': membership.joined_turn,
                'is_represented': is_represented,
                'is_leader': is_leader
            }
            membership_list.append(faction_info)

            if is_represented:
                represented_faction_info = faction_info

    return True, f"Found {len(memberships)} faction membership(s).", {
        'character_name': char.name,
        'represented_faction': represented_faction_info,
        'memberships': membership_list,
        'can_change_representation': can_change,
        'turns_until_change': turns_remaining
    }
