"""
Order handlers for unit-related orders.
"""
from order_types import OrderType, OrderStatus, TurnPhase
from datetime import datetime
from db import Character, Unit, FactionMember, TurnLog, Order
import asyncpg
from typing import List


async def handle_assign_commander_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a single ASSIGN_COMMANDER order.

    Validates:
    - Unit exists
    - Submitter is the unit owner
    - New commander exists
    - New commander is different from current commander
    - Owner and new commander are in the same faction

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
        unit_id = order.order_data.get('unit_id')
        new_commander_id = order.order_data.get('new_commander_id')

        # Fetch the unit
        unit = await Unit.fetch_by_unit_id(conn, unit_id, guild_id)
        if not unit:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Unit not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='unit',
                entity_id=None,
                event_data={
                    'order_type': 'ASSIGN_COMMANDER',
                    'order_id': order.order_id,
                    'error': 'Unit not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Validate submitter is the owner
        if unit.owner_character_id != order.character_id:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Only the unit owner can assign a commander'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='unit',
                entity_id=unit.id,
                event_data={
                    'order_type': 'ASSIGN_COMMANDER',
                    'order_id': order.order_id,
                    'error': 'Only the unit owner can assign a commander',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Fetch new commander
        new_commander = await Character.fetch_by_id(conn, new_commander_id)
        if not new_commander:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'New commander not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='unit',
                entity_id=unit.id,
                event_data={
                    'order_type': 'ASSIGN_COMMANDER',
                    'order_id': order.order_id,
                    'error': 'New commander not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Validate new commander is different from current commander
        if unit.commander_character_id == new_commander_id:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'New commander is the same as current commander'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='unit',
                entity_id=unit.id,
                event_data={
                    'order_type': 'ASSIGN_COMMANDER',
                    'order_id': order.order_id,
                    'error': 'New commander is the same as current commander',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Re-check faction membership at execution time
        # Owner and new commander must be in the same faction
        owner = await Character.fetch_by_id(conn, unit.owner_character_id)
        owner_membership = await FactionMember.fetch_by_character(conn, unit.owner_character_id, guild_id)
        commander_membership = await FactionMember.fetch_by_character(conn, new_commander_id, guild_id)

        owner_faction_id = owner_membership.faction_id if owner_membership else None
        commander_faction_id = commander_membership.faction_id if commander_membership else None

        if owner_faction_id != commander_faction_id:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Owner and new commander are no longer in the same faction'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.BEGINNING.value,
                event_type='ORDER_FAILED',
                entity_type='unit',
                entity_id=unit.id,
                event_data={
                    'order_type': 'ASSIGN_COMMANDER',
                    'order_id': order.order_id,
                    'error': 'Owner and new commander are no longer in the same faction',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Store old commander info before update
        old_commander_id = unit.commander_character_id
        old_commander = None
        old_commander_name = None
        if old_commander_id:
            old_commander = await Character.fetch_by_id(conn, old_commander_id)
            old_commander_name = old_commander.name if old_commander else None

        # Update the unit
        unit.commander_character_id = new_commander_id
        unit.commander_assigned_turn = turn_number
        await unit.upsert(conn)

        # Mark order as SUCCESS
        order.status = OrderStatus.SUCCESS.value
        order.result_data = {
            'unit_id': unit.unit_id,
            'old_commander_id': old_commander_id,
            'old_commander_name': old_commander_name,
            'new_commander_id': new_commander_id,
            'new_commander_name': new_commander.name
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        # Build affected_character_ids list
        # Include: owner, new commander (if different from owner), old commander (if exists and different)
        affected_character_ids = [unit.owner_character_id]

        if new_commander_id != unit.owner_character_id:
            affected_character_ids.append(new_commander_id)

        if old_commander_id and old_commander_id != unit.owner_character_id and old_commander_id != new_commander_id:
            affected_character_ids.append(old_commander_id)

        # Return success event
        return [TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.BEGINNING.value,
            event_type='COMMANDER_ASSIGNED',
            entity_type='unit',
            entity_id=unit.id,
            event_data={
                'unit_id': unit.unit_id,
                'unit_name': unit.name or unit.unit_id,
                'old_commander_id': old_commander_id,
                'old_commander_name': old_commander_name,
                'new_commander_id': new_commander_id,
                'new_commander_name': new_commander.name,
                'owner_id': unit.owner_character_id,
                'owner_name': owner.name if owner else 'Unknown',
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
            entity_type='unit',
            entity_id=None,
            event_data={
                'order_type': 'ASSIGN_COMMANDER',
                'order_id': order.order_id,
                'error': str(e),
                'affected_character_ids': [order.character_id]
            },
            guild_id=guild_id
        )]
