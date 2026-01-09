"""
Resource transfer order handlers.
"""
from order_types import OrderType, OrderStatus, TurnPhase
from datetime import datetime
from db import Character, PlayerResources, TurnLog, Order
import asyncpg
from typing import List


async def handle_cancel_transfer_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a single CANCEL_TRANSFER order.

    Args:
        conn: Database connection
        order: The cancel order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    try:
        # Extract order data
        original_order_id = order.order_data.get('original_order_id')

        # Fetch the original transfer order
        original_order = await Order.fetch_by_order_id(conn, original_order_id, guild_id)

        if not original_order:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Original order not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.RESOURCE_TRANSFER.value,
                event_type='RESOURCE_TRANSFER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'order_type': 'CANCEL_TRANSFER',
                    'order_id': order.order_id,
                    'reason': 'Original order not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Validate it's a RESOURCE_TRANSFER order
        if original_order.order_type != OrderType.RESOURCE_TRANSFER.value:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Original order is not a RESOURCE_TRANSFER'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.RESOURCE_TRANSFER.value,
                event_type='RESOURCE_TRANSFER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'order_type': 'CANCEL_TRANSFER',
                    'order_id': order.order_id,
                    'reason': 'Original order is not a RESOURCE_TRANSFER',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Validate it has ONGOING status
        if original_order.status != OrderStatus.ONGOING.value:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Original order is not ONGOING'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.RESOURCE_TRANSFER.value,
                event_type='RESOURCE_TRANSFER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'order_type': 'CANCEL_TRANSFER',
                    'order_id': order.order_id,
                    'reason': 'Original order is not ONGOING',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Validate it belongs to the character
        if original_order.character_id != order.character_id:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Cannot cancel another character\'s order'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.RESOURCE_TRANSFER.value,
                event_type='RESOURCE_TRANSFER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'order_type': 'CANCEL_TRANSFER',
                    'order_id': order.order_id,
                    'reason': 'Cannot cancel another character\'s order',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Get character names for event
        from_character = await Character.fetch_by_id(conn, original_order.character_id)
        to_character_id = original_order.order_data.get('to_character_id')
        to_character = await Character.fetch_by_id(conn, to_character_id)

        # Cancel the original order
        original_order.status = OrderStatus.CANCELLED.value
        original_order.updated_at = datetime.now()
        original_order.updated_turn = turn_number
        await original_order.upsert(conn)

        # Mark cancel order as SUCCESS
        order.status = OrderStatus.SUCCESS.value
        order.result_data = {
            'original_order_id': original_order_id,
            'cancelled': True
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        # Generate TRANSFER_CANCELLED event
        affected_character_ids = [original_order.character_id]
        if to_character:
            affected_character_ids.append(to_character.id)

        return [TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.RESOURCE_TRANSFER.value,
            event_type='TRANSFER_CANCELLED',
            entity_type='character',
            entity_id=original_order.character_id,
            event_data={
                'from_character_name': from_character.name if from_character else 'Unknown',
                'to_character_name': to_character.name if to_character else 'Unknown',
                'order_id': order.order_id,
                'original_order_id': original_order_id,
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
            phase=TurnPhase.RESOURCE_TRANSFER.value,
            event_type='RESOURCE_TRANSFER_FAILED',
            entity_type='character',
            entity_id=order.character_id,
            event_data={
                'order_type': 'CANCEL_TRANSFER',
                'order_id': order.order_id,
                'reason': str(e),
                'affected_character_ids': [order.character_id]
            },
            guild_id=guild_id
        )]


async def handle_resource_transfer_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a single RESOURCE_TRANSFER order (one-time or ongoing).

    Args:
        conn: Database connection
        order: The transfer order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    try:
        # Extract order data
        to_character_id = order.order_data.get('to_character_id')
        requested_resources = {
            'ore': order.order_data.get('ore', 0),
            'lumber': order.order_data.get('lumber', 0),
            'coal': order.order_data.get('coal', 0),
            'rations': order.order_data.get('rations', 0),
            'cloth': order.order_data.get('cloth', 0),
            'platinum': order.order_data.get('platinum', 0)
        }
        term = order.order_data.get('term')
        turns_executed = order.order_data.get('turns_executed', 0)

        # Validate sender character exists
        from_character = await Character.fetch_by_id(conn, order.character_id)
        if not from_character:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Sender character not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.RESOURCE_TRANSFER.value,
                event_type='RESOURCE_TRANSFER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'from_character_name': 'Unknown',
                    'to_character_name': 'Unknown',
                    'order_id': order.order_id,
                    'reason': 'Sender character not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Validate recipient exists
        to_character = await Character.fetch_by_id(conn, to_character_id)
        if not to_character:
            order.status = OrderStatus.FAILED.value
            order.result_data = {'error': 'Recipient character not found'}
            order.updated_at = datetime.now()
            order.updated_turn = turn_number
            await order.upsert(conn)
            return [TurnLog(
                turn_number=turn_number,
                phase=TurnPhase.RESOURCE_TRANSFER.value,
                event_type='RESOURCE_TRANSFER_FAILED',
                entity_type='character',
                entity_id=order.character_id,
                event_data={
                    'from_character_name': from_character.name,
                    'to_character_name': 'Unknown',
                    'order_id': order.order_id,
                    'reason': 'Recipient character not found',
                    'affected_character_ids': [order.character_id]
                },
                guild_id=guild_id
            )]

        # Fetch PlayerResources for both characters
        sender_resources = await PlayerResources.fetch_by_character(conn, from_character.id, guild_id)
        recipient_resources = await PlayerResources.fetch_by_character(conn, to_character.id, guild_id)

        # Create PlayerResources if they don't exist
        if not sender_resources:
            sender_resources = PlayerResources(character_id=from_character.id, guild_id=guild_id)
            await sender_resources.upsert(conn)

        if not recipient_resources:
            recipient_resources = PlayerResources(character_id=to_character.id, guild_id=guild_id)
            await recipient_resources.upsert(conn)

        # Calculate what can be transferred (min of requested and available)
        transferred_resources = {}
        for resource_type in ['ore', 'lumber', 'coal', 'rations', 'cloth', 'platinum']:
            requested = requested_resources.get(resource_type, 0)
            available = getattr(sender_resources, resource_type)
            transferred = min(requested, available)
            transferred_resources[resource_type] = transferred

        # Check if any resources were transferred
        total_transferred = sum(transferred_resources.values())
        total_requested = sum(requested_resources.values())

        # Transfer resources
        for resource_type, amount in transferred_resources.items():
            if amount > 0:
                # Subtract from sender
                current_sender = getattr(sender_resources, resource_type)
                setattr(sender_resources, resource_type, current_sender - amount)

                # Add to recipient
                current_recipient = getattr(recipient_resources, resource_type)
                setattr(recipient_resources, resource_type, current_recipient + amount)

        # Update PlayerResources
        await sender_resources.upsert(conn)
        await recipient_resources.upsert(conn)

        # Determine outcome and status
        affected_character_ids = [from_character.id, to_character.id]

        if order.status == OrderStatus.PENDING.value:
            # One-time transfer
            if total_transferred == total_requested and total_transferred > 0:
                # Full transfer: mark SUCCESS
                order.status = OrderStatus.SUCCESS.value
                order.result_data = {
                    'transferred_resources': transferred_resources,
                    'success': True
                }
                order.updated_at = datetime.now()
                order.updated_turn = turn_number
                await order.upsert(conn)

                return [TurnLog(
                    turn_number=turn_number,
                    phase=TurnPhase.RESOURCE_TRANSFER.value,
                    event_type='RESOURCE_TRANSFER_SUCCESS',
                    entity_type='character',
                    entity_id=from_character.id,
                    event_data={
                        'from_character_name': from_character.name,
                        'to_character_name': to_character.name,
                        'transferred_resources': transferred_resources,
                        'order_id': order.order_id,
                        'is_ongoing': False,
                        'affected_character_ids': affected_character_ids
                    },
                    guild_id=guild_id
                )]
            else:
                # Partial or no transfer: mark FAILED
                order.status = OrderStatus.FAILED.value
                order.result_data = {
                    'requested_resources': requested_resources,
                    'transferred_resources': transferred_resources,
                    'partial': True
                }
                order.updated_at = datetime.now()
                order.updated_turn = turn_number
                await order.upsert(conn)

                if total_transferred == 0:
                    # No resources transferred
                    return [TurnLog(
                        turn_number=turn_number,
                        phase=TurnPhase.RESOURCE_TRANSFER.value,
                        event_type='RESOURCE_TRANSFER_FAILED',
                        entity_type='character',
                        entity_id=from_character.id,
                        event_data={
                            'from_character_name': from_character.name,
                            'to_character_name': to_character.name,
                            'order_id': order.order_id,
                            'reason': 'No resources available',
                            'is_ongoing': False,
                            'affected_character_ids': affected_character_ids
                        },
                        guild_id=guild_id
                    )]
                else:
                    # Partial transfer
                    return [TurnLog(
                        turn_number=turn_number,
                        phase=TurnPhase.RESOURCE_TRANSFER.value,
                        event_type='RESOURCE_TRANSFER_PARTIAL',
                        entity_type='character',
                        entity_id=from_character.id,
                        event_data={
                            'from_character_name': from_character.name,
                            'to_character_name': to_character.name,
                            'requested_resources': requested_resources,
                            'transferred_resources': transferred_resources,
                            'order_id': order.order_id,
                            'is_ongoing': False,
                            'affected_character_ids': affected_character_ids
                        },
                        guild_id=guild_id
                    )]

        elif order.status == OrderStatus.ONGOING.value:
            # Ongoing transfer
            # Increment turns_executed
            turns_executed += 1
            order.order_data['turns_executed'] = turns_executed

            # Calculate turns remaining (None if indefinite)
            turns_remaining = None
            term_completed = False
            if term is not None:
                turns_remaining = term - turns_executed
                if turns_remaining <= 0:
                    turns_remaining = 0
                    term_completed = True

            # Check term expiration
            if term_completed:
                # Term expired: mark SUCCESS
                order.status = OrderStatus.SUCCESS.value
                order.result_data = {
                    'transferred_resources': transferred_resources,
                    'term_completed': True,
                    'turns_executed': turns_executed
                }
                order.updated_at = datetime.now()
                order.updated_turn = turn_number
                await order.upsert(conn)
            else:
                # Continue ONGOING
                order.result_data = {
                    'transferred_resources': transferred_resources,
                    'turns_executed': turns_executed
                }
                order.updated_at = datetime.now()
                order.updated_turn = turn_number
                await order.upsert(conn)

            # Generate appropriate event
            if total_transferred == total_requested and total_transferred > 0:
                # Full transfer
                return [TurnLog(
                    turn_number=turn_number,
                    phase=TurnPhase.RESOURCE_TRANSFER.value,
                    event_type='RESOURCE_TRANSFER_SUCCESS',
                    entity_type='character',
                    entity_id=from_character.id,
                    event_data={
                        'from_character_name': from_character.name,
                        'to_character_name': to_character.name,
                        'transferred_resources': transferred_resources,
                        'order_id': order.order_id,
                        'is_ongoing': True,
                        'term': term,
                        'turns_remaining': turns_remaining,
                        'term_completed': term_completed,
                        'affected_character_ids': affected_character_ids
                    },
                    guild_id=guild_id
                )]
            else:
                # Partial or no transfer
                return [TurnLog(
                    turn_number=turn_number,
                    phase=TurnPhase.RESOURCE_TRANSFER.value,
                    event_type='RESOURCE_TRANSFER_PARTIAL',
                    entity_type='character',
                    entity_id=from_character.id,
                    event_data={
                        'from_character_name': from_character.name,
                        'to_character_name': to_character.name,
                        'requested_resources': requested_resources,
                        'transferred_resources': transferred_resources,
                        'order_id': order.order_id,
                        'is_ongoing': True,
                        'term': term,
                        'turns_remaining': turns_remaining,
                        'term_completed': term_completed,
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
            phase=TurnPhase.RESOURCE_TRANSFER.value,
            event_type='RESOURCE_TRANSFER_FAILED',
            entity_type='character',
            entity_id=order.character_id,
            event_data={
                'from_character_name': 'Unknown',
                'to_character_name': 'Unknown',
                'order_id': order.order_id,
                'reason': str(e),
                'affected_character_ids': [order.character_id]
            },
            guild_id=guild_id
        )]
