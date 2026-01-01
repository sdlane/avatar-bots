from order_types import *
from datetime import datetime
from db import Character, Faction, FactionMember, FactionJoinRequest, Unit
import asyncpg
from typing import Optional, Dict

async def handle_leave_faction_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> Optional[Dict]:
    """
    Handle a single LEAVE_FACTION order.

    Args:
        conn: Database connection
        order: The order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        Event dict if successful, None if failed
    """
    try:
        character = await Character.fetch_by_id(conn, order.character_id)
        if not character:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Character not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return None

        # Get current faction membership
        faction_member = await FactionMember.fetch_by_character(conn, character.id, guild_id)
        if not faction_member:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Character not in a faction'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return None

        faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

        # Remove from faction
        await FactionMember.delete(conn, character.id, guild_id)

        # Update units' faction_id to NULL
        units = await Unit.fetch_by_owner(conn, character.id, guild_id)
        for unit in units:
            if unit.faction_id == faction_member.faction_id:
                unit.faction_id = None
                await unit.upsert(conn)

        # Mark order success
        order.status = OrderStatus.SUCCESS.value
        order.result_data = {
            'faction_name': faction.name if faction else 'Unknown',
            'faction_id': faction.faction_id if faction else None
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        return {
            'phase': TurnPhase.BEGINNING.value,
            'event_type': 'LEAVE_FACTION',
            'entity_type': 'character',
            'entity_id': character.id,
            'event_data': {
                'character_name': character.name,
                'faction_name': faction.name if faction else 'Unknown',
                'order_id': order.order_id
            }
        }

    except Exception as e:
        order.status = OrderStatus.FAILED.value
        order.result_data = {'error': str(e)}
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)
        return None


async def handle_join_faction_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> Optional[Dict]:
    """
    Handle a single JOIN_FACTION order by checking/creating FactionJoinRequest entries.

    This function:
    1. Validates the order (character not already in faction)
    2. Checks if matching request exists from other party
    3. If match exists: executes join, deletes requests, marks order SUCCESS
    4. If no match: creates request, marks order SUCCESS with "waiting" status

    Args:
        conn: Database connection
        order: The JOIN_FACTION order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        Event dict with join status (completed or waiting)
    """
    #try:
    # Extract order data
    character_id = order.character_id
    target_faction_id = order.order_data.get('target_faction_id')
    submitted_by = order.order_data.get('submitted_by')  # 'character' or 'leader'

    # Validate character exists
    character = await Character.fetch_by_id(conn, character_id)
    if not character:
        order.status = OrderStatus.FAILED.value
        order.result_data = {'error': 'Character not found'}
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)
        return None

    # Validate faction exists
    faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
    if not faction:
        order.status = OrderStatus.FAILED.value
        order.result_data = {'error': 'Faction not found'}
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)
        return None

    # Check if character is already a member of a faction
    existing_membership = await FactionMember.fetch_by_character(conn, character.id, guild_id)
    
    if existing_membership:
        order.status = OrderStatus.FAILED.value
        order.result_data = {'error': 'Character already in a faction'}
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)
        return None

    # Check for matching request from other party
    other_party = 'leader' if submitted_by == 'character' else 'character'
    matching_request = await FactionJoinRequest.fetch_matching_request(
        conn, character.id, faction.id, other_party, guild_id
    )

    if matching_request:
        # Both parties have submitted - execute the join

        # Create faction membership
        faction_member = FactionMember(
            character_id=character.id,
            faction_id=faction.id,
            joined_turn=turn_number,
            guild_id=guild_id
        )
        await faction_member.insert(conn)

        # Update units' faction_id
        units = await Unit.fetch_by_owner(conn, character.id, guild_id)
        for unit in units:
            unit.faction_id = faction.id
            await unit.upsert(conn)

        # Delete all requests for this character-faction pair
        await FactionJoinRequest.delete_all_for_character_faction(
            conn, character.id, faction.id, guild_id
        )

        # Mark order as SUCCESS
        order.status = OrderStatus.SUCCESS.value
        order.result_data = {
            'faction_name': faction.name,
            'faction_id': faction.faction_id,
            'joined': True
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        # Return event for completed join
        return {
            'phase': TurnPhase.BEGINNING.value,
            'event_type': 'JOIN_FACTION_COMPLETED',
            'entity_type': 'character',
            'entity_id': character.id,
            'event_data': {
                'character_name': character.name,
                'faction_name': faction.name,
                'order_id': order.order_id,
                'status': 'completed'
            }
        }
    else:
        # No matching request - create a new request
        request = FactionJoinRequest(
            character_id=character.id,
            faction_id=faction.id,
            submitted_by=submitted_by,
            guild_id=guild_id
        )
        await request.insert(conn)

        # Mark order as SUCCESS (request submitted successfully)
        order.status = OrderStatus.SUCCESS.value
        waiting_for = "faction leader" if submitted_by == 'character' else character.name
        order.result_data = {
            'faction_name': faction.name,
            'faction_id': faction.faction_id,
            'joined': False,
            'waiting_for': waiting_for
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        # Return event for pending join request
        return {
            'phase': TurnPhase.BEGINNING.value,
            'event_type': 'JOIN_FACTION_PENDING',
            'entity_type': 'character',
            'entity_id': character.id,
            'event_data': {
                'character_name': character.name,
                'faction_name': faction.name,
                'order_id': order.order_id,
                'status': 'pending',
                'waiting_for': waiting_for
            }
        }

#    except Exception as e:
#        order.status = OrderStatus.FAILED.value
#        order.result_data = {'error': str(e)}
#        order.updated_at = datetime.now()
#        order.updated_turn = turn_number
#        await order.upsert(conn)
#        return None


async def handle_kick_from_faction_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> Optional[Dict]:
    """
    Handle a single KICK_FROM_FACTION order.

    Args:
        conn: Database connection
        order: The order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        Event dict if successful, None if failed
    """
    try:
        # Extract order data
        target_character_id = order.order_data.get('target_character_id')
        faction_id = order.order_data.get('faction_id')

        # Validate target character still exists
        target_character = await Character.fetch_by_id(conn, target_character_id)
        if not target_character:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Target character not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return None

        # Validate faction still exists
        faction = await Faction.fetch_by_id(conn, faction_id)
        if not faction:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Faction not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return None

        # Check target is still in the faction
        target_membership = await FactionMember.fetch_by_character(conn, target_character.id, guild_id)
        if not target_membership or target_membership.faction_id != faction.id:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Target character is no longer in the faction'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return None

        # Remove from faction
        await FactionMember.delete(conn, target_character.id, guild_id)

        # Update units' faction_id to NULL
        units = await Unit.fetch_by_owner(conn, target_character.id, guild_id)
        for unit in units:
            if unit.faction_id == faction.id:
                unit.faction_id = None
                await unit.upsert(conn)

        # Mark order success
        order.status = OrderStatus.SUCCESS.value
        order.result_data = {
            'target_character_name': target_character.name,
            'faction_name': faction.name,
            'faction_id': faction.faction_id
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        return {
            'phase': TurnPhase.BEGINNING.value,
            'event_type': 'KICK_FROM_FACTION',
            'entity_type': 'character',
            'entity_id': target_character.id,
            'event_data': {
                'character_name': target_character.name,
                'faction_name': faction.name,
                'order_id': order.order_id
            }
        }

    except Exception as e:
        order.status = OrderStatus.FAILED.value
        order.result_data = {'error': str(e)}
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)
        return None