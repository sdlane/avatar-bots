"""
Victory point order handlers.
"""
from order_types import OrderType, OrderStatus, TurnPhase
from datetime import datetime
from db import Character, Faction, FactionMember, Territory, TurnLog, Order
import asyncpg
from typing import List


async def handle_assign_victory_points_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a single ASSIGN_VICTORY_POINTS order.

    This order assigns victory points from territories controlled by the submitting
    character to a target faction.

    - On first execution (PENDING): Generate report, change status to ONGOING
    - On subsequent turns (ONGOING): Order persists until cancelled

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
        target_faction_id = order.order_data.get('target_faction_id')

        # Validate target faction still exists
        target_faction = await Faction.fetch_by_faction_id(conn, target_faction_id, guild_id)
        if not target_faction:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Target faction no longer exists'}
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
                    'order_type': 'ASSIGN_VICTORY_POINTS',
                    'order_id': order.order_id,
                    'error': 'Target faction no longer exists',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Get character info
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
                    'order_type': 'ASSIGN_VICTORY_POINTS',
                    'order_id': order.order_id,
                    'error': 'Character not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Calculate VPs this character controls
        territories = await Territory.fetch_by_controller(conn, order.character_id, guild_id)
        total_vps = sum(t.victory_points for t in territories)

        # Build affected character IDs list: submitter + faction leader + all faction members
        affected_character_ids = [order.character_id]

        # Add faction leader
        if target_faction.leader_character_id:
            if target_faction.leader_character_id not in affected_character_ids:
                affected_character_ids.append(target_faction.leader_character_id)

        # Add all faction members
        faction_members = await FactionMember.fetch_by_faction(conn, target_faction.id, guild_id)
        for member in faction_members:
            if member.character_id not in affected_character_ids:
                affected_character_ids.append(member.character_id)

        if order.status == OrderStatus.PENDING.value:
            # First turn - transition to ONGOING and generate report
            order.status = OrderStatus.ONGOING.value
            order.result_data = {
                'vps_controlled': total_vps,
                'target_faction_name': target_faction.name
            }
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)

            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='VP_ASSIGNMENT_STARTED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'character_name': character.name,
                    'target_faction_id': target_faction_id,
                    'target_faction_name': target_faction.name,
                    'order_id': order.order_id,
                    'vps_controlled': total_vps,
                    'affected_character_ids': affected_character_ids
                },
                guild_id=guild_id
            )]

        elif order.status == OrderStatus.ONGOING.value:
            # Subsequent turns - order persists, just update result data
            order.result_data = {
                'vps_controlled': total_vps,
                'target_faction_name': target_faction.name
            }
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)

            # Return event (informational, no actual VP tallying yet - war system not implemented)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='VP_ASSIGNMENT_ACTIVE',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'character_name': character.name,
                    'target_faction_id': target_faction_id,
                    'target_faction_name': target_faction.name,
                    'order_id': order.order_id,
                    'vps_controlled': total_vps,
                    'affected_character_ids': affected_character_ids
                },
                guild_id=guild_id
            )]

        else:
            # Unexpected status - should not happen
            return []

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
                'order_type': 'ASSIGN_VICTORY_POINTS',
                'order_id': order.order_id,
                'error': str(e),
                'affected_character_ids': [order.character_id]
            },
            guild_id=guild_id
        )]
