"""
Alliance order handlers for turn resolution.
"""
from order_types import OrderType, OrderStatus, TurnPhase
from datetime import datetime
from db import Character, Faction, FactionMember, Alliance, TurnLog
import asyncpg
from typing import List


async def handle_make_alliance_order(
    conn: asyncpg.Connection,
    order,  # Order type from db
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a MAKE_ALLIANCE order.

    This function checks if a matching alliance request exists from the other faction.
    If both faction leaders have submitted orders, the alliance is activated.
    If only one has submitted, a pending alliance is created/updated.

    Args:
        conn: Database connection
        order: The MAKE_ALLIANCE order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    try:
        # Extract order data
        target_faction_id = order.order_data.get('target_faction_id')
        submitting_faction_id = order.order_data.get('submitting_faction_id')

        # Validate submitting character still exists and is still a faction leader
        character = await Character.fetch_by_id(conn, order.character_id)
        if not character:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Character not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [_create_failed_event(order, guild_id, turn_number, 'Character not found')]

        # Validate submitting faction still exists
        submitting_faction = await Faction.fetch_by_faction_id(conn, submitting_faction_id, guild_id)
        if not submitting_faction:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Submitting faction not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [_create_failed_event(order, guild_id, turn_number, 'Submitting faction not found')]

        # Validate character is still faction leader
        if submitting_faction.leader_character_id != character.id:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Character is no longer faction leader'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [_create_failed_event(order, guild_id, turn_number, 'Character is no longer faction leader')]

        # Validate target faction still exists
        target_faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
        if not target_faction:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Target faction not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [_create_failed_event(order, guild_id, turn_number, 'Target faction not found')]

        # Check for existing alliance between the two factions
        existing_alliance = await Alliance.fetch_by_factions(
            conn, submitting_faction.id, target_faction.id, guild_id
        )

        # Determine canonical ordering for status interpretation
        # faction_a_id is always < faction_b_id
        # PENDING_FACTION_A means "waiting for faction A to respond" (faction B initiated)
        # PENDING_FACTION_B means "waiting for faction B to respond" (faction A initiated)
        if submitting_faction.id < target_faction.id:
            submitting_is_faction_a = True
            pending_for_submitter = "PENDING_FACTION_A"  # Status when waiting for me (A) to respond
            pending_for_target = "PENDING_FACTION_B"  # Status when I (A) propose, waiting for B
        else:
            submitting_is_faction_a = False
            pending_for_submitter = "PENDING_FACTION_B"  # Status when waiting for me (B) to respond
            pending_for_target = "PENDING_FACTION_A"  # Status when I (B) propose, waiting for A

        if existing_alliance:
            if existing_alliance.status == "ACTIVE":
                # Already allied
                order.status = OrderStatus.FAILED.value
                order.result_data = {'error': 'Alliance already exists'}
                order.updated_at = datetime.now()
                order.updated_turn = turn_number
                await order.upsert(conn)
                return [_create_failed_event(order, guild_id, turn_number,
                    f'Alliance already exists between {submitting_faction.name} and {target_faction.name}')]

            elif existing_alliance.status == pending_for_submitter:
                # The other faction already proposed - activate the alliance!
                existing_alliance.status = "ACTIVE"
                existing_alliance.activated_at = datetime.now()
                await existing_alliance.upsert(conn)

                # Mark order as success
                order.status = OrderStatus.SUCCESS.value
                order.result_data = {
                    'alliance_formed': True,
                    'target_faction_name': target_faction.name,
                    'submitting_faction_name': submitting_faction.name
                }
                order.updated_at = datetime.now()
                order.updated_turn = turn_number
                await order.upsert(conn)

                # Get affected character IDs (both faction leaders + all members)
                affected_character_ids = await _get_affected_character_ids(
                    conn, submitting_faction, target_faction, guild_id
                )

                return [TurnLog(
                    turn_number=turn_number,
                    phase=TurnPhase.BEGINNING.value,
                    event_type='ALLIANCE_FORMED',
                    entity_type='faction',
                    entity_id=submitting_faction.id,
                    event_data={
                        'faction_a_name': submitting_faction.name if submitting_is_faction_a else target_faction.name,
                        'faction_b_name': target_faction.name if submitting_is_faction_a else submitting_faction.name,
                        'faction_a_id': submitting_faction.faction_id if submitting_is_faction_a else target_faction.faction_id,
                        'faction_b_id': target_faction.faction_id if submitting_is_faction_a else submitting_faction.faction_id,
                        'order_id': order.order_id,
                        'affected_character_ids': affected_character_ids
                    },
                    guild_id=guild_id
                )]

            elif existing_alliance.status == pending_for_target:
                # We already proposed, duplicate order
                order.status = OrderStatus.FAILED.value
                order.result_data = {'error': 'Alliance already proposed by your faction'}
                order.updated_at = datetime.now()
                order.updated_turn = turn_number
                await order.upsert(conn)
                return [_create_failed_event(order, guild_id, turn_number,
                    f'Alliance already proposed by {submitting_faction.name}. Waiting for {target_faction.name} to accept.')]

        else:
            # No existing alliance - create a new pending one
            # Canonical ordering: faction_a_id < faction_b_id
            faction_a_id = min(submitting_faction.id, target_faction.id)
            faction_b_id = max(submitting_faction.id, target_faction.id)

            new_alliance = Alliance(
                faction_a_id=faction_a_id,
                faction_b_id=faction_b_id,
                status=pending_for_target,  # Status indicates we're waiting for the other faction
                initiated_by_faction_id=submitting_faction.id,
                created_at=datetime.now(),
                guild_id=guild_id
            )
            await new_alliance.insert(conn)

            # Mark order as success
            order.status = OrderStatus.SUCCESS.value
            order.result_data = {
                'alliance_formed': False,
                'waiting_for': target_faction.name,
                'target_faction_name': target_faction.name,
                'submitting_faction_name': submitting_faction.name
            }
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)

            # Get affected character IDs (both faction leaders + all members)
            affected_character_ids = await _get_affected_character_ids(
                conn, submitting_faction, target_faction, guild_id
            )

            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ALLIANCE_PENDING',
                entity_type='faction',
                entity_id=submitting_faction.id,
                event_data={
                    'faction_a_name': submitting_faction.name if submitting_is_faction_a else target_faction.name,
                    'faction_b_name': target_faction.name if submitting_is_faction_a else submitting_faction.name,
                    'faction_a_id': submitting_faction.faction_id if submitting_is_faction_a else target_faction.faction_id,
                    'faction_b_id': target_faction.faction_id if submitting_is_faction_a else submitting_faction.faction_id,
                    'waiting_for_faction_name': target_faction.name,
                    'initiated_by_faction_name': submitting_faction.name,
                    'order_id': order.order_id,
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
        return [_create_failed_event(order, guild_id, turn_number, str(e))]


async def _get_affected_character_ids(
    conn: asyncpg.Connection,
    faction_a: Faction,
    faction_b: Faction,
    guild_id: int
) -> List[int]:
    """
    Get all character IDs affected by an alliance event.
    Includes both faction leaders and all members of both factions.
    """
    affected_ids = []

    # Add faction leaders
    if faction_a.leader_character_id:
        affected_ids.append(faction_a.leader_character_id)
    if faction_b.leader_character_id and faction_b.leader_character_id not in affected_ids:
        affected_ids.append(faction_b.leader_character_id)

    # Add all members of faction A
    faction_a_members = await FactionMember.fetch_by_faction(conn, faction_a.id, guild_id)
    for member in faction_a_members:
        if member.character_id not in affected_ids:
            affected_ids.append(member.character_id)

    # Add all members of faction B
    faction_b_members = await FactionMember.fetch_by_faction(conn, faction_b.id, guild_id)
    for member in faction_b_members:
        if member.character_id not in affected_ids:
            affected_ids.append(member.character_id)

    return affected_ids


def _create_failed_event(order, guild_id: int, turn_number: int, error: str) -> TurnLog:
    """Create a standard ORDER_FAILED event."""
    return TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.BEGINNING.value,
        event_type='ORDER_FAILED',
        entity_type='character',
        entity_id=order.character_id,
        event_data={
            'order_type': 'MAKE_ALLIANCE',
            'order_id': order.order_id,
            'error': error,
            'affected_character_ids': [order.character_id]
        },
        guild_id=guild_id
    )
