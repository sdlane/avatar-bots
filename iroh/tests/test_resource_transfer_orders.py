"""
Pytest tests for resource transfer order handlers.
Tests verify RESOURCE_TRANSFER and CANCEL_TRANSFER order processing.

Run with: pytest tests/test_resource_transfer_orders.py -v
"""
import pytest
from orders.resource_transfer_orders import (
    handle_cancel_transfer_order,
    handle_resource_transfer_order
)
from db import Character, PlayerResources, Order
from order_types import OrderStatus, TurnPhase, OrderType
from tests.conftest import TEST_GUILD_ID
from datetime import datetime


# ============================================================================
# Tests for handle_cancel_transfer_order
# ============================================================================

@pytest.mark.asyncio
async def test_handle_cancel_transfer_order_success(db_conn, test_server):
    """Test successfully cancelling an ongoing transfer."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-char", name="Sender",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-char", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-char", name="Recipient",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-char", TEST_GUILD_ID)

    # Setup: Create ongoing transfer order
    transfer_order = Order(
        order_id="TRANSFER-001",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=1,
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 100,
            'lumber': 50,
            'coal': 0,
            'rations': 0,
            'cloth': 0,
            'term': None,
            'turns_executed': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await transfer_order.upsert(db_conn)

    # Setup: Create cancel order
    cancel_order = Order(
        order_id="CANCEL-001",
        order_type=OrderType.CANCEL_TRANSFER.value,
        character_id=sender.id,
        turn_number=2,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={'original_order_id': 'TRANSFER-001'},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await cancel_order.upsert(db_conn)

    # Execute
    events = await handle_cancel_transfer_order(db_conn, cancel_order, TEST_GUILD_ID, 2)

    # Verify cancel order status
    cancel_order = await Order.fetch_by_order_id(db_conn, "CANCEL-001", TEST_GUILD_ID)
    assert cancel_order.status == OrderStatus.SUCCESS.value
    assert cancel_order.result_data['cancelled'] == True

    # Verify original order was cancelled
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-001", TEST_GUILD_ID)
    assert transfer_order.status == OrderStatus.CANCELLED.value

    # Verify event generated
    assert len(events) == 1
    assert events[0].event_type == 'TRANSFER_CANCELLED'
    assert sender.id in events[0].event_data['affected_character_ids']
    assert recipient.id in events[0].event_data['affected_character_ids']

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_cancel_transfer_order_not_found(db_conn, test_server):
    """Test cancelling a non-existent order."""
    # Setup: Create character
    sender = Character(
        identifier="sender-char2", name="Sender2",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-char2", TEST_GUILD_ID)

    # Setup: Create cancel order for non-existent transfer
    cancel_order = Order(
        order_id="CANCEL-002",
        order_type=OrderType.CANCEL_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={'original_order_id': 'NON-EXISTENT'},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await cancel_order.upsert(db_conn)

    # Execute
    events = await handle_cancel_transfer_order(db_conn, cancel_order, TEST_GUILD_ID, 1)

    # Verify cancel order failed
    cancel_order = await Order.fetch_by_order_id(db_conn, "CANCEL-002", TEST_GUILD_ID)
    assert cancel_order.status == OrderStatus.FAILED.value
    assert 'not found' in cancel_order.result_data['error'].lower()

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == 'RESOURCE_TRANSFER_FAILED'

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_cancel_transfer_order_not_ongoing(db_conn, test_server):
    """Test cancelling an order that is not ONGOING."""
    # Setup: Create character
    sender = Character(
        identifier="sender-char3", name="Sender3",
        user_id=100000000000000004, channel_id=900000000000000004,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-char3", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-char3", name="Recipient3",
        user_id=100000000000000005, channel_id=900000000000000005,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-char3", TEST_GUILD_ID)

    # Setup: Create PENDING transfer order (not ONGOING)
    transfer_order = Order(
        order_id="TRANSFER-003",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 100,
            'lumber': 0,
            'coal': 0,
            'rations': 0,
            'cloth': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await transfer_order.upsert(db_conn)

    # Setup: Create cancel order
    cancel_order = Order(
        order_id="CANCEL-003",
        order_type=OrderType.CANCEL_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={'original_order_id': 'TRANSFER-003'},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await cancel_order.upsert(db_conn)

    # Execute
    events = await handle_cancel_transfer_order(db_conn, cancel_order, TEST_GUILD_ID, 1)

    # Verify cancel order failed
    cancel_order = await Order.fetch_by_order_id(db_conn, "CANCEL-003", TEST_GUILD_ID)
    assert cancel_order.status == OrderStatus.FAILED.value
    assert 'not ONGOING' in cancel_order.result_data['error']

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# Tests for handle_resource_transfer_order - PENDING (one-time)
# ============================================================================

@pytest.mark.asyncio
async def test_handle_resource_transfer_pending_full_transfer(db_conn, test_server):
    """Test one-time transfer with full resources available."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-pending1", name="SenderPending1",
        user_id=100000000000000010, channel_id=900000000000000010,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-pending1", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-pending1", name="RecipientPending1",
        user_id=100000000000000011, channel_id=900000000000000011,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-pending1", TEST_GUILD_ID)

    # Setup: Give sender resources
    sender_resources = PlayerResources(
        character_id=sender.id,
        ore=100,
        lumber=50,
        coal=25,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await sender_resources.upsert(db_conn)

    # Setup: Create recipient resources
    recipient_resources = PlayerResources(
        character_id=recipient.id,
        ore=10,
        lumber=10,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await recipient_resources.upsert(db_conn)

    # Setup: Create PENDING transfer order
    transfer_order = Order(
        order_id="TRANSFER-PENDING-001",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 50,
            'lumber': 25,
            'coal': 10,
            'rations': 0,
            'cloth': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await transfer_order.upsert(db_conn)

    # Execute
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 1)

    # Verify order status
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-PENDING-001", TEST_GUILD_ID)
    assert transfer_order.status == OrderStatus.SUCCESS.value

    # Verify resources transferred
    sender_resources = await PlayerResources.fetch_by_character(db_conn, sender.id, TEST_GUILD_ID)
    assert sender_resources.ore == 50  # 100 - 50
    assert sender_resources.lumber == 25  # 50 - 25
    assert sender_resources.coal == 15  # 25 - 10

    recipient_resources = await PlayerResources.fetch_by_character(db_conn, recipient.id, TEST_GUILD_ID)
    assert recipient_resources.ore == 60  # 10 + 50
    assert recipient_resources.lumber == 35  # 10 + 25
    assert recipient_resources.coal == 10  # 0 + 10

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == 'RESOURCE_TRANSFER_SUCCESS'

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_resource_transfer_pending_partial_transfer(db_conn, test_server):
    """Test one-time transfer with insufficient resources (partial)."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-pending2", name="SenderPending2",
        user_id=100000000000000012, channel_id=900000000000000012,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-pending2", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-pending2", name="RecipientPending2",
        user_id=100000000000000013, channel_id=900000000000000013,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-pending2", TEST_GUILD_ID)

    # Setup: Give sender insufficient resources
    sender_resources = PlayerResources(
        character_id=sender.id,
        ore=30,  # Requested 100
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await sender_resources.upsert(db_conn)

    recipient_resources = PlayerResources(
        character_id=recipient.id,
        ore=0,
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await recipient_resources.upsert(db_conn)

    # Setup: Create PENDING transfer order
    transfer_order = Order(
        order_id="TRANSFER-PENDING-002",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 100,
            'lumber': 0,
            'coal': 0,
            'rations': 0,
            'cloth': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await transfer_order.upsert(db_conn)

    # Execute
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 1)

    # Verify order status
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-PENDING-002", TEST_GUILD_ID)
    assert transfer_order.status == OrderStatus.FAILED.value

    # Verify partial transfer occurred
    sender_resources = await PlayerResources.fetch_by_character(db_conn, sender.id, TEST_GUILD_ID)
    assert sender_resources.ore == 0  # Transferred all 30

    recipient_resources = await PlayerResources.fetch_by_character(db_conn, recipient.id, TEST_GUILD_ID)
    assert recipient_resources.ore == 30  # Received 30

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == 'RESOURCE_TRANSFER_PARTIAL'

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_resource_transfer_pending_no_resources(db_conn, test_server):
    """Test one-time transfer with no resources available."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-pending3", name="SenderPending3",
        user_id=100000000000000014, channel_id=900000000000000014,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-pending3", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-pending3", name="RecipientPending3",
        user_id=100000000000000015, channel_id=900000000000000015,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-pending3", TEST_GUILD_ID)

    # Setup: Give sender no resources
    sender_resources = PlayerResources(
        character_id=sender.id,
        ore=0,
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await sender_resources.upsert(db_conn)

    # Setup: Create PENDING transfer order
    transfer_order = Order(
        order_id="TRANSFER-PENDING-003",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 100,
            'lumber': 0,
            'coal': 0,
            'rations': 0,
            'cloth': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await transfer_order.upsert(db_conn)

    # Execute
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 1)

    # Verify order status
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-PENDING-003", TEST_GUILD_ID)
    assert transfer_order.status == OrderStatus.FAILED.value

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == 'RESOURCE_TRANSFER_FAILED'
    assert 'No resources available' in events[0].event_data['reason']

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# Tests for handle_resource_transfer_order - ONGOING (recurring)
# ============================================================================

@pytest.mark.asyncio
async def test_handle_resource_transfer_ongoing_full_transfer(db_conn, test_server):
    """Test ongoing transfer with full resources available."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-ongoing1", name="SenderOngoing1",
        user_id=100000000000000020, channel_id=900000000000000020,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-ongoing1", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-ongoing1", name="RecipientOngoing1",
        user_id=100000000000000021, channel_id=900000000000000021,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-ongoing1", TEST_GUILD_ID)

    # Setup: Give sender resources
    sender_resources = PlayerResources(
        character_id=sender.id,
        ore=100,
        lumber=50,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await sender_resources.upsert(db_conn)

    recipient_resources = PlayerResources(
        character_id=recipient.id,
        ore=0,
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await recipient_resources.upsert(db_conn)

    # Setup: Create ONGOING transfer order
    transfer_order = Order(
        order_id="TRANSFER-ONGOING-001",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=1,
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 10,
            'lumber': 5,
            'coal': 0,
            'rations': 0,
            'cloth': 0,
            'term': None,
            'turns_executed': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await transfer_order.upsert(db_conn)

    # Execute
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 1)

    # Verify order status (should stay ONGOING)
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-ONGOING-001", TEST_GUILD_ID)
    assert transfer_order.status == OrderStatus.ONGOING.value
    assert transfer_order.order_data['turns_executed'] == 1

    # Verify resources transferred
    sender_resources = await PlayerResources.fetch_by_character(db_conn, sender.id, TEST_GUILD_ID)
    assert sender_resources.ore == 90  # 100 - 10

    recipient_resources = await PlayerResources.fetch_by_character(db_conn, recipient.id, TEST_GUILD_ID)
    assert recipient_resources.ore == 10  # 0 + 10

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == 'RESOURCE_TRANSFER_SUCCESS'

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_resource_transfer_ongoing_partial_transfer(db_conn, test_server):
    """Test ongoing transfer with insufficient resources (stays ONGOING)."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-ongoing2", name="SenderOngoing2",
        user_id=100000000000000022, channel_id=900000000000000022,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-ongoing2", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-ongoing2", name="RecipientOngoing2",
        user_id=100000000000000023, channel_id=900000000000000023,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-ongoing2", TEST_GUILD_ID)

    # Setup: Give sender insufficient resources
    sender_resources = PlayerResources(
        character_id=sender.id,
        ore=5,  # Requested 10
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await sender_resources.upsert(db_conn)

    recipient_resources = PlayerResources(
        character_id=recipient.id,
        ore=0,
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await recipient_resources.upsert(db_conn)

    # Setup: Create ONGOING transfer order
    transfer_order = Order(
        order_id="TRANSFER-ONGOING-002",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=1,
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 10,
            'lumber': 0,
            'coal': 0,
            'rations': 0,
            'cloth': 0,
            'term': None,
            'turns_executed': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await transfer_order.upsert(db_conn)

    # Execute
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 1)

    # Verify order status (should stay ONGOING)
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-ONGOING-002", TEST_GUILD_ID)
    assert transfer_order.status == OrderStatus.ONGOING.value
    assert transfer_order.order_data['turns_executed'] == 1

    # Verify partial transfer
    sender_resources = await PlayerResources.fetch_by_character(db_conn, sender.id, TEST_GUILD_ID)
    assert sender_resources.ore == 0  # Transferred all 5

    recipient_resources = await PlayerResources.fetch_by_character(db_conn, recipient.id, TEST_GUILD_ID)
    assert recipient_resources.ore == 5  # Received 5

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == 'RESOURCE_TRANSFER_PARTIAL'

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_resource_transfer_ongoing_term_expiration(db_conn, test_server):
    """Test ongoing transfer reaching term expiration."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-ongoing3", name="SenderOngoing3",
        user_id=100000000000000024, channel_id=900000000000000024,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-ongoing3", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-ongoing3", name="RecipientOngoing3",
        user_id=100000000000000025, channel_id=900000000000000025,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-ongoing3", TEST_GUILD_ID)

    # Setup: Give sender resources
    sender_resources = PlayerResources(
        character_id=sender.id,
        ore=100,
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await sender_resources.upsert(db_conn)

    recipient_resources = PlayerResources(
        character_id=recipient.id,
        ore=0,
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await recipient_resources.upsert(db_conn)

    # Setup: Create ONGOING transfer order with term=2 and turns_executed=1
    transfer_order = Order(
        order_id="TRANSFER-ONGOING-003",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=2,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=1,
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 10,
            'lumber': 0,
            'coal': 0,
            'rations': 0,
            'cloth': 0,
            'term': 2,
            'turns_executed': 1  # This is turn 2, so will reach term
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await transfer_order.upsert(db_conn)

    # Execute
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 2)

    # Verify order status (should become SUCCESS due to term expiration)
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-ONGOING-003", TEST_GUILD_ID)
    assert transfer_order.status == OrderStatus.SUCCESS.value
    assert transfer_order.order_data['turns_executed'] == 2
    assert transfer_order.result_data['term_completed'] == True

    # Verify final transfer occurred
    sender_resources = await PlayerResources.fetch_by_character(db_conn, sender.id, TEST_GUILD_ID)
    assert sender_resources.ore == 90  # 100 - 10

    recipient_resources = await PlayerResources.fetch_by_character(db_conn, recipient.id, TEST_GUILD_ID)
    assert recipient_resources.ore == 10  # 0 + 10

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_resource_transfer_ongoing_multi_turn(db_conn, test_server):
    """Test ongoing transfer executing across multiple turns."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-ongoing4", name="SenderOngoing4",
        user_id=100000000000000026, channel_id=900000000000000026,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-ongoing4", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-ongoing4", name="RecipientOngoing4",
        user_id=100000000000000027, channel_id=900000000000000027,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-ongoing4", TEST_GUILD_ID)

    # Setup: Give sender resources
    sender_resources = PlayerResources(
        character_id=sender.id,
        ore=100,
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await sender_resources.upsert(db_conn)

    recipient_resources = PlayerResources(
        character_id=recipient.id,
        ore=0,
        lumber=0,
        coal=0,
        rations=0,
        cloth=0,
        platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await recipient_resources.upsert(db_conn)

    # Setup: Create ONGOING transfer order
    transfer_order = Order(
        order_id="TRANSFER-ONGOING-004",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=1,
        phase=TurnPhase.RESOURCE_TRANSFER.value,
        priority=1,
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 10,
            'lumber': 0,
            'coal': 0,
            'rations': 0,
            'cloth': 0,
            'term': 5,
            'turns_executed': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await transfer_order.upsert(db_conn)

    # Execute Turn 1
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 1)
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-ONGOING-004", TEST_GUILD_ID)
    assert transfer_order.order_data['turns_executed'] == 1
    assert transfer_order.status == OrderStatus.ONGOING.value

    # Execute Turn 2
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 2)
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-ONGOING-004", TEST_GUILD_ID)
    assert transfer_order.order_data['turns_executed'] == 2
    assert transfer_order.status == OrderStatus.ONGOING.value

    # Execute Turn 3
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 3)
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-ONGOING-004", TEST_GUILD_ID)
    assert transfer_order.order_data['turns_executed'] == 3
    assert transfer_order.status == OrderStatus.ONGOING.value

    # Execute Turn 4
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 4)
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-ONGOING-004", TEST_GUILD_ID)
    assert transfer_order.order_data['turns_executed'] == 4
    assert transfer_order.status == OrderStatus.ONGOING.value

    # Execute Turn 5 (should reach term)
    events = await handle_resource_transfer_order(db_conn, transfer_order, TEST_GUILD_ID, 5)
    transfer_order = await Order.fetch_by_order_id(db_conn, "TRANSFER-ONGOING-004", TEST_GUILD_ID)
    assert transfer_order.order_data['turns_executed'] == 5
    assert transfer_order.status == OrderStatus.SUCCESS.value

    # Verify total resources transferred (10 ore × 5 turns = 50 ore)
    sender_resources = await PlayerResources.fetch_by_character(db_conn, sender.id, TEST_GUILD_ID)
    assert sender_resources.ore == 50  # 100 - 50

    recipient_resources = await PlayerResources.fetch_by_character(db_conn, recipient.id, TEST_GUILD_ID)
    assert recipient_resources.ore == 50  # 0 + 50

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
