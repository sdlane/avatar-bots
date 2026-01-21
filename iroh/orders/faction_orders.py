from order_types import *
from datetime import datetime
from db import Character, Faction, FactionMember, FactionJoinRequest, Unit, TurnLog, War, WarParticipant, Alliance
import asyncpg
from typing import Optional, Dict, List, Union

async def handle_leave_faction_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a single LEAVE_FACTION order.
    Supports multi-faction membership - only removes from the specific faction specified in order_data.

    Args:
        conn: Database connection
        order: The order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    try:
        character = await Character.fetch_by_id(conn, order.character_id)
        if not character:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Character not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'order_type': 'LEAVE_FACTION',
                    'order_id': order.order_id,
                    'error': 'Character not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Get faction from order_data (new) or fall back to fetch_by_character (legacy)
        faction_id_from_order = order.order_data.get('faction_id')
        if faction_id_from_order:
            faction = await Faction.fetch_by_id(conn, faction_id_from_order)
            faction_member = await FactionMember.fetch_membership(conn, faction_id_from_order, character.id, guild_id) if faction else None
        else:
            # Legacy support: get character's represented/primary faction
            faction_member = await FactionMember.fetch_by_character(conn, character.id, guild_id)
            faction = await Faction.fetch_by_id(conn, faction_member.faction_id) if faction_member else None

        if not faction_member or not faction:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Character not in the specified faction'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='character',
                entity_id=character.id,
                event_data={
                    'order_type': 'LEAVE_FACTION',
                    'order_id': order.order_id,
                    'error': 'Character not in the specified faction',
                    'affected_character_ids': [character.id]
                },
                guild_id=guild_id
            )]

        # Get all faction members BEFORE the character leaves
        faction_members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)

        # Check if leaving the represented faction (or no representation set)
        is_represented_faction = character.represented_faction_id == faction.id
        has_no_representation = character.represented_faction_id is None

        # Remove from this specific faction
        await FactionMember.delete(conn, character.id, guild_id, faction_id=faction.id)

        # Handle representation and units if leaving represented faction OR no representation set
        new_represented_faction = None
        if is_represented_faction or has_no_representation:
            # Get remaining memberships
            remaining_memberships = await FactionMember.fetch_all_by_character(conn, character.id, guild_id)

            if remaining_memberships:
                # Auto-assign to most recent membership (highest joined_turn)
                new_represented_faction = await Faction.fetch_by_id(conn, remaining_memberships[0].faction_id)
                character.represented_faction_id = remaining_memberships[0].faction_id
                # Note: Auto-assignment does NOT reset cooldown
                await character.upsert(conn)

                # Update owned units to new represented faction
                units = await Unit.fetch_by_owner(conn, character.id, guild_id)
                for unit in units:
                    if unit.faction_id == faction.id:
                        unit.faction_id = character.represented_faction_id
                        await unit.upsert(conn)
            else:
                # No more memberships - clear representation
                character.represented_faction_id = None
                await character.upsert(conn)

                # Update owned units to have no faction
                units = await Unit.fetch_by_owner(conn, character.id, guild_id)
                for unit in units:
                    if unit.faction_id == faction.id:
                        unit.faction_id = None
                        await unit.upsert(conn)

        # Mark order success
        order.status = OrderStatus.SUCCESS.value
        order.result_data = {
            'faction_name': faction.name if faction else 'Unknown',
            'faction_id': faction.faction_id if faction else None,
            'new_represented_faction': new_represented_faction.name if new_represented_faction else None
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        # Collect all affected character IDs (the leaving character + all faction members)
        affected_character_ids = [character.id]
        for member in faction_members:
            if member.character_id != character.id:
                affected_character_ids.append(member.character_id)

        # Build event data
        event_data = {
            'character_name': character.name,
            'faction_name': faction.name if faction else 'Unknown',
            'order_id': order.order_id,
            'affected_character_ids': affected_character_ids
        }
        if new_represented_faction:
            event_data['new_represented_faction'] = new_represented_faction.name

        # Return single event with all affected character IDs
        return [TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.BEGINNING.value,
            event_type='LEAVE_FACTION',
            entity_type='character',
            entity_id=character.id,
            event_data=event_data,
            guild_id=guild_id
        )]

    except Exception as e:
        order.status = OrderStatus.FAILED.value
        order.result_data = {'error': str(e)}
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)
        return [TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.BEGINNING.value,
            event_type='ORDER_FAILED',
            entity_type='character',
            entity_id=order.character_id,
            event_data={
                'order_type': 'LEAVE_FACTION',
                'order_id': order.order_id,
                'error': str(e),
                'affected_character_ids': [order.character_id]
            },
            guild_id=guild_id
        )]


async def handle_join_faction_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
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
        List of TurnLog objects
    """
    try:
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
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'order_type': 'JOIN_FACTION',
                    'order_id': order.order_id,
                    'error': 'Character not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Validate faction exists
        faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
        if not faction:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Faction not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='character',
                entity_id=character.id,
                event_data={
                    'order_type': 'JOIN_FACTION',
                    'order_id': order.order_id,
                    'error': 'Faction not found',
                    'affected_character_ids': [character.id]
                },
                guild_id=guild_id
            )]

        # Check if character is already a member of THIS SPECIFIC faction
        existing_membership = await FactionMember.fetch_membership(conn, faction.id, character.id, guild_id)

        if existing_membership:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Character already in this faction'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='character',
                entity_id=character.id,
                event_data={
                    'order_type': 'JOIN_FACTION',
                    'order_id': order.order_id,
                    'error': 'Character already in this faction',
                    'affected_character_ids': [character.id]
                },
                guild_id=guild_id
            )]

        # Check if this is the character's first faction (for auto-representation)
        all_memberships = await FactionMember.fetch_all_by_character(conn, character.id, guild_id)
        is_first_faction = len(all_memberships) == 0

        # Check for matching request from other party
        other_party = 'leader' if submitted_by == 'character' else 'character'
        matching_request = await FactionJoinRequest.fetch_matching_request(
            conn, character.id, faction.id, other_party, guild_id
        )

        if matching_request:
            # Both parties have submitted - execute the join

            # Get all existing faction members BEFORE adding the new member
            faction_members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)

            # Create faction membership
            faction_member = FactionMember(
                character_id=character.id,
                faction_id=faction.id,
                joined_turn=turn_number,
                guild_id=guild_id
            )
            await faction_member.insert(conn)

            # If first faction, auto-set as represented faction
            if is_first_faction:
                character.represented_faction_id = faction.id
                await character.upsert(conn)

            # Only update units if this is now the represented faction
            if character.represented_faction_id == faction.id:
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

            # Collect all affected character IDs (the joining character + all existing members)
            affected_character_ids = [character.id]
            for member in faction_members:
                affected_character_ids.append(member.character_id)

            # Return single event with all affected character IDs
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='JOIN_FACTION_COMPLETED',
                entity_type='character',
                entity_id=character.id,
                event_data={
                    'character_name': character.name,
                    'faction_name': faction.name,
                    'order_id': order.order_id,
                    'status': 'completed',
                    'affected_character_ids': affected_character_ids
                },
                guild_id=guild_id
            )]
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

            # Get faction leader to notify them as well
            affected_character_ids = [character.id]
            if faction.leader_character_id:
                affected_character_ids.append(faction.leader_character_id)

            # Return event for pending join request (for both the submitter and faction leader)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='JOIN_FACTION_PENDING',
                entity_type='character',
                entity_id=character.id,
                event_data={
                    'character_name': character.name,
                    'faction_name': faction.name,
                    'order_id': order.order_id,
                    'status': 'pending',
                    'waiting_for': waiting_for,
                    'affected_character_ids': affected_character_ids
                },
                guild_id=guild_id
            )]

    except Exception as e:
        order.status = OrderStatus.FAILED.value
        order.result_data = {'error': str(e)}
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)
        return [TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.BEGINNING.value,
            event_type='ORDER_FAILED',
            entity_type='character',
            entity_id=order.character_id,
            event_data={
                'order_type': 'JOIN_FACTION',
                'order_id': order.order_id,
                'error': str(e),
                'affected_character_ids': [order.character_id]
            },
            guild_id=guild_id
        )]


async def handle_kick_from_faction_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a single KICK_FROM_FACTION order.

    Args:
        conn: Database connection
        order: The order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
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
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'order_type': 'KICK_FROM_FACTION',
                    'order_id': order.order_id,
                    'error': 'Target character not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Validate faction still exists
        faction = await Faction.fetch_by_id(conn, faction_id)
        if not faction:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Faction not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'order_type': 'KICK_FROM_FACTION',
                    'order_id': order.order_id,
                    'error': 'Faction not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Check target is still in the faction (specific membership check)
        target_membership = await FactionMember.fetch_membership(conn, faction.id, target_character.id, guild_id)
        if not target_membership:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Target character is no longer in the faction'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'order_type': 'KICK_FROM_FACTION',
                    'order_id': order.order_id,
                    'error': 'Target character is no longer in the faction',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Get all faction members BEFORE removing the target
        faction_members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)

        # Check if being kicked from represented faction (or no representation set)
        is_represented_faction = target_character.represented_faction_id == faction.id
        has_no_representation = target_character.represented_faction_id is None

        # Remove from faction (only this specific faction)
        await FactionMember.delete(conn, target_character.id, guild_id, faction_id=faction.id)

        # Handle representation and units if kicked from represented faction OR no representation set
        new_represented_faction = None
        if is_represented_faction or has_no_representation:
            # Get remaining memberships
            remaining_memberships = await FactionMember.fetch_all_by_character(conn, target_character.id, guild_id)

            if remaining_memberships:
                # Auto-assign to most recent membership (highest joined_turn)
                new_represented_faction = await Faction.fetch_by_id(conn, remaining_memberships[0].faction_id)
                target_character.represented_faction_id = remaining_memberships[0].faction_id
                # IMPORTANT: Being kicked resets the cooldown
                target_character.representation_changed_turn = turn_number
                await target_character.upsert(conn)

                # Update owned units to new represented faction
                units = await Unit.fetch_by_owner(conn, target_character.id, guild_id)
                for unit in units:
                    if unit.faction_id == faction.id:
                        unit.faction_id = target_character.represented_faction_id
                        await unit.upsert(conn)
            else:
                # No more memberships - clear representation
                target_character.represented_faction_id = None
                # Reset cooldown even when going factionless
                target_character.representation_changed_turn = turn_number
                await target_character.upsert(conn)

                # Update owned units to have no faction
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
            'faction_id': faction.faction_id,
            'new_represented_faction': new_represented_faction.name if new_represented_faction else None
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        # Collect all affected character IDs (the kicked character + all remaining faction members)
        affected_character_ids = [target_character.id]
        for member in faction_members:
            if member.character_id != target_character.id:
                affected_character_ids.append(member.character_id)

        # Build event data
        event_data = {
            'character_name': target_character.name,
            'faction_name': faction.name,
            'order_id': order.order_id,
            'affected_character_ids': affected_character_ids
        }
        if new_represented_faction:
            event_data['new_represented_faction'] = new_represented_faction.name

        # Return single event with all affected character IDs
        return [TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.BEGINNING.value,
            event_type='KICK_FROM_FACTION',
            entity_type='character',
            entity_id=target_character.id,
            event_data=event_data,
            guild_id=guild_id
        )]

    except Exception as e:
        order.status = OrderStatus.FAILED.value
        order.result_data = {'error': str(e)}
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)
        return [TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.BEGINNING.value,
            event_type='ORDER_FAILED',
            entity_type='character',
            entity_id=order.character_id,
            event_data={
                'order_type': 'KICK_FROM_FACTION',
                'order_id': order.order_id,
                'error': str(e),
                'affected_character_ids': [order.character_id]
            },
            guild_id=guild_id
        )]


async def handle_declare_war_order(
    conn: asyncpg.Connection,
    order,  # Order type from db
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a DECLARE_WAR order.

    This function:
    1. Validates the submitter is still a faction leader
    2. Checks for existing war with same objective (case-insensitive)
    3. If found: Joins existing war on opposite side from targets
    4. If not found: Creates new war with declaring faction on SIDE_A, targets on SIDE_B
    5. Handles allied faction drag-in (allies of both sides join targets' side)
    6. Checks for first-war production bonus eligibility

    Args:
        conn: Database connection
        order: The DECLARE_WAR order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    events = []

    try:
        # Extract order data
        target_faction_ids = order.order_data.get('target_faction_ids', [])
        submitting_faction_id = order.order_data.get('submitting_faction_id')
        objective = order.order_data.get('objective', '')

        # Validate submitting character still exists
        character = await Character.fetch_by_id(conn, order.character_id)
        if not character:
            return await _fail_declare_war_order(conn, order, guild_id, turn_number, 'Character not found')

        # Validate submitting faction still exists
        submitting_faction = await Faction.fetch_by_id(conn, submitting_faction_id)
        if not submitting_faction:
            return await _fail_declare_war_order(conn, order, guild_id, turn_number, 'Submitting faction not found')

        # Validate character is still faction leader
        if submitting_faction.leader_character_id != character.id:
            return await _fail_declare_war_order(conn, order, guild_id, turn_number, 'Character is no longer faction leader')

        # Validate all target factions still exist
        target_factions = []
        for target_id in target_faction_ids:
            target_faction = await Faction.fetch_by_id(conn, target_id)
            if not target_faction:
                return await _fail_declare_war_order(conn, order, guild_id, turn_number, f'Target faction {target_id} not found')
            if target_faction.id == submitting_faction.id:
                return await _fail_declare_war_order(conn, order, guild_id, turn_number, 'Cannot declare war on your own faction')
            target_factions.append(target_faction)

        if not target_factions:
            return await _fail_declare_war_order(conn, order, guild_id, turn_number, 'No valid target factions specified')

        # Check for existing war with same objective
        existing_war = await War.fetch_by_objective(conn, objective, guild_id)

        if existing_war:
            # Join existing war
            events.extend(await _join_existing_war(
                conn, order, existing_war, submitting_faction, target_factions,
                guild_id, turn_number
            ))
        else:
            # Create new war
            events.extend(await _create_new_war(
                conn, order, submitting_faction, target_factions, objective,
                guild_id, turn_number
            ))

        # Check for first-war bonus eligibility
        first_war_bonus = False
        if not submitting_faction.has_declared_war:
            submitting_faction.has_declared_war = True
            await submitting_faction.upsert(conn)
            first_war_bonus = True

            # Get all faction members for bonus notification
            faction_members = await FactionMember.fetch_by_faction(conn, submitting_faction.id, guild_id)
            affected_ids = [submitting_faction.leader_character_id] if submitting_faction.leader_character_id else []
            for member in faction_members:
                if member.character_id not in affected_ids:
                    affected_ids.append(member.character_id)

            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='WAR_PRODUCTION_BONUS',
                entity_type='faction',
                entity_id=submitting_faction.id,
                event_data={
                    'faction_name': submitting_faction.name,
                    'faction_id': submitting_faction.faction_id,
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))

        # Mark order as success
        order.status = OrderStatus.SUCCESS.value
        order.result_data = {
            'objective': objective,
            'target_factions': [f.name for f in target_factions],
            'first_war_bonus': first_war_bonus
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        return events

    except Exception as e:
        return await _fail_declare_war_order(conn, order, guild_id, turn_number, str(e))


async def _fail_declare_war_order(
    conn: asyncpg.Connection,
    order,
    guild_id: int,
    turn_number: int,
    error: str
) -> List[TurnLog]:
    """Mark a DECLARE_WAR order as failed and return failure event."""
    order.status = OrderStatus.FAILED.value
    order.result_data = {'error': error}
    order.updated_at = datetime.now()
    order.updated_turn = turn_number
    await order.upsert(conn)
    return [TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.BEGINNING.value,
        event_type='ORDER_FAILED',
        entity_type='character',
        entity_id=order.character_id,
        event_data={
            'order_type': 'DECLARE_WAR',
            'order_id': order.order_id,
            'error': error,
            'affected_character_ids': [order.character_id]
        },
        guild_id=guild_id
    )]


async def _join_existing_war(
    conn: asyncpg.Connection,
    order,
    war: War,
    submitting_faction: Faction,
    target_factions: List[Faction],
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """Handle joining an existing war based on targets."""
    events = []

    # Check if submitting faction is already in this war
    existing_participant = await WarParticipant.fetch_by_war_and_faction(
        conn, war.id, submitting_faction.id, guild_id
    )
    if existing_participant:
        # Already in war - this is still valid, they're confirming their participation
        # But we won't add them again
        our_side = existing_participant.side
    else:
        # Determine which side to join based on targets
        # If any target is on SIDE_A, we join SIDE_B. If any target is on SIDE_B, we join SIDE_A.
        target_side = None
        for target in target_factions:
            target_participant = await WarParticipant.fetch_by_war_and_faction(
                conn, war.id, target.id, guild_id
            )
            if target_participant:
                target_side = target_participant.side
                break

        if target_side is None:
            # None of our targets are in the war - add targets to SIDE_B, us to SIDE_A
            our_side = "SIDE_A"
            their_side = "SIDE_B"
        else:
            # Join opposite side from targets
            our_side = "SIDE_B" if target_side == "SIDE_A" else "SIDE_A"
            their_side = target_side

        # Add submitting faction to war
        participant = WarParticipant(
            war_id=war.id,
            faction_id=submitting_faction.id,
            side=our_side,
            joined_turn=turn_number,
            is_original_declarer=True,
            guild_id=guild_id
        )
        await participant.insert(conn)

        # Add any targets not already in the war
        for target in target_factions:
            target_participant = await WarParticipant.fetch_by_war_and_faction(
                conn, war.id, target.id, guild_id
            )
            if not target_participant:
                new_participant = WarParticipant(
                    war_id=war.id,
                    faction_id=target.id,
                    side=their_side,
                    joined_turn=turn_number,
                    is_original_declarer=False,
                    guild_id=guild_id
                )
                await new_participant.insert(conn)

    # Get all affected character IDs
    affected_ids = await _get_war_affected_character_ids(conn, war.id, guild_id)

    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.BEGINNING.value,
        event_type='WAR_JOINED',
        entity_type='faction',
        entity_id=submitting_faction.id,
        event_data={
            'war_id': war.war_id,
            'objective': war.objective,
            'joining_faction_name': submitting_faction.name,
            'joining_faction_id': submitting_faction.faction_id,
            'side': our_side,
            'target_factions': [f.name for f in target_factions],
            'order_id': order.order_id,
            'affected_character_ids': affected_ids
        },
        guild_id=guild_id
    ))

    # Handle allied faction drag-in
    drag_in_events = await _handle_allied_drag_in(
        conn, war, submitting_faction, target_factions, guild_id, turn_number
    )
    events.extend(drag_in_events)

    return events


async def _create_new_war(
    conn: asyncpg.Connection,
    order,
    submitting_faction: Faction,
    target_factions: List[Faction],
    objective: str,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """Create a new war with the submitting faction on SIDE_A and targets on SIDE_B."""
    events = []

    # Generate war_id
    war_id = await War.generate_next_war_id(conn, guild_id)

    # Create war
    war = War(
        war_id=war_id,
        objective=objective,
        declared_turn=turn_number,
        created_at=datetime.now(),
        guild_id=guild_id
    )
    await war.insert(conn)

    # Add submitting faction to SIDE_A
    submitting_participant = WarParticipant(
        war_id=war.id,
        faction_id=submitting_faction.id,
        side="SIDE_A",
        joined_turn=turn_number,
        is_original_declarer=True,
        guild_id=guild_id
    )
    await submitting_participant.insert(conn)

    # Add target factions to SIDE_B
    for target in target_factions:
        target_participant = WarParticipant(
            war_id=war.id,
            faction_id=target.id,
            side="SIDE_B",
            joined_turn=turn_number,
            is_original_declarer=False,
            guild_id=guild_id
        )
        await target_participant.insert(conn)

    # Get all affected character IDs
    affected_ids = await _get_war_affected_character_ids(conn, war.id, guild_id)

    events.append(TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.BEGINNING.value,
        event_type='WAR_DECLARED',
        entity_type='faction',
        entity_id=submitting_faction.id,
        event_data={
            'war_id': war.war_id,
            'objective': objective,
            'declaring_faction_name': submitting_faction.name,
            'declaring_faction_id': submitting_faction.faction_id,
            'target_faction_names': [f.name for f in target_factions],
            'target_faction_ids': [f.faction_id for f in target_factions],
            'order_id': order.order_id,
            'affected_character_ids': affected_ids
        },
        guild_id=guild_id
    ))

    # Handle allied faction drag-in
    drag_in_events = await _handle_allied_drag_in(
        conn, war, submitting_faction, target_factions, guild_id, turn_number
    )
    events.extend(drag_in_events)

    return events


async def _handle_allied_drag_in(
    conn: asyncpg.Connection,
    war: War,
    submitting_faction: Faction,
    target_factions: List[Faction],
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle dragging in allied factions that are allied with both sides.
    Such factions join on the targets' side (SIDE_B).
    """
    events = []

    # Get all active alliances involving the submitting faction
    submitting_alliances = await Alliance.fetch_by_faction(conn, submitting_faction.id, guild_id)
    submitting_ally_ids = set()
    for alliance in submitting_alliances:
        if alliance.status == "ACTIVE":
            other_id = alliance.faction_b_id if alliance.faction_a_id == submitting_faction.id else alliance.faction_a_id
            submitting_ally_ids.add(other_id)

    # Get all active alliances involving target factions
    target_ally_ids = set()
    for target in target_factions:
        target_alliances = await Alliance.fetch_by_faction(conn, target.id, guild_id)
        for alliance in target_alliances:
            if alliance.status == "ACTIVE":
                other_id = alliance.faction_b_id if alliance.faction_a_id == target.id else alliance.faction_a_id
                target_ally_ids.add(other_id)

    # Find factions allied with both sides (excluding submitting and target factions)
    all_faction_ids = {submitting_faction.id} | {t.id for t in target_factions}
    caught_in_middle = submitting_ally_ids & target_ally_ids - all_faction_ids

    for faction_id in caught_in_middle:
        # Check if already in war
        existing = await WarParticipant.fetch_by_war_and_faction(conn, war.id, faction_id, guild_id)
        if existing:
            continue

        # Add to SIDE_B (targets' side)
        participant = WarParticipant(
            war_id=war.id,
            faction_id=faction_id,
            side="SIDE_B",
            joined_turn=turn_number,
            is_original_declarer=False,
            guild_id=guild_id
        )
        await participant.insert(conn)

        # Get faction info for event
        dragged_faction = await Faction.fetch_by_id(conn, faction_id)
        if dragged_faction:
            # Get affected character IDs for this faction
            faction_members = await FactionMember.fetch_by_faction(conn, faction_id, guild_id)
            affected_ids = [dragged_faction.leader_character_id] if dragged_faction.leader_character_id else []
            for member in faction_members:
                if member.character_id not in affected_ids:
                    affected_ids.append(member.character_id)

            events.append(TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='WAR_ALLY_DRAGGED_IN',
                entity_type='faction',
                entity_id=faction_id,
                event_data={
                    'war_id': war.war_id,
                    'objective': war.objective,
                    'dragged_faction_name': dragged_faction.name,
                    'dragged_faction_id': dragged_faction.faction_id,
                    'side': 'SIDE_B',
                    'reason': 'Allied with both declaring and target factions',
                    'affected_character_ids': affected_ids
                },
                guild_id=guild_id
            ))

    return events


async def _get_war_affected_character_ids(
    conn: asyncpg.Connection,
    war_id: int,
    guild_id: int
) -> List[int]:
    """Get all character IDs affected by a war event (all faction members on all sides)."""
    affected_ids = []

    participants = await WarParticipant.fetch_by_war(conn, war_id, guild_id)
    for participant in participants:
        faction = await Faction.fetch_by_id(conn, participant.faction_id)
        if faction:
            if faction.leader_character_id and faction.leader_character_id not in affected_ids:
                affected_ids.append(faction.leader_character_id)

            faction_members = await FactionMember.fetch_by_faction(conn, participant.faction_id, guild_id)
            for member in faction_members:
                if member.character_id not in affected_ids:
                    affected_ids.append(member.character_id)

    return affected_ids