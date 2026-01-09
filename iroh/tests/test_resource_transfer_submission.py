"""
Pytest tests for resource transfer order submission handlers.
Tests verify submit_resource_transfer_order and submit_cancel_transfer_order functions.

Run with: pytest tests/test_resource_transfer_submission.py -v
"""
import pytest
from handlers.order_handlers import (
    submit_resource_transfer_order,
    submit_cancel_transfer_order
)
from db import Character, WargameConfig, Order
from order_types import OrderType, OrderStatus
from tests.conftest import TEST_GUILD_ID
from datetime import datetime


# ============================================================================
# Tests for submit_resource_transfer_order
# ============================================================================

@pytest.mark.asyncio
async def test_submit_one_time_transfer(db_conn, test_server):
    """Test submitting a one-time resource transfer."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-submit1", name="SenderSubmit1",
        user_id=100000000000000100, channel_id=900000000000000100,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-submit1", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-submit1", name="RecipientSubmit1",
        user_id=100000000000000101, channel_id=900000000000000101,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Execute
    resources = {'ore': 100, 'lumber': 50, 'coal': 0, 'rations': 0, 'cloth': 0, 'platinum': 0}
    success, message = await submit_resource_transfer_order(
        db_conn, sender, "recipient-submit1", resources, False, None, TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "One-time transfer order submitted" in message

    # Verify order was created
    orders = await db_conn.fetch(
        'SELECT * FROM WargameOrder WHERE guild_id = $1 AND order_type = $2;',
        TEST_GUILD_ID, OrderType.RESOURCE_TRANSFER.value
    )
    assert len(orders) == 1
    assert orders[0]['status'] == OrderStatus.PENDING.value
    assert orders[0]['turn_number'] == 6  # Current turn + 1
    assert orders[0]['character_id'] == sender.id

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_ongoing_transfer_with_term(db_conn, test_server):
    """Test submitting an ongoing transfer with a specified term."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-submit2", name="SenderSubmit2",
        user_id=100000000000000102, channel_id=900000000000000102,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-submit2", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-submit2", name="RecipientSubmit2",
        user_id=100000000000000103, channel_id=900000000000000103,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Execute
    resources = {'ore': 10, 'lumber': 5, 'coal': 0, 'rations': 0, 'cloth': 0, 'platinum': 0}
    success, message = await submit_resource_transfer_order(
        db_conn, sender, "recipient-submit2", resources, True, 5, TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "Ongoing transfer order submitted" in message
    assert "(for 5 turns)" in message

    # Verify order was created with correct status and data
    orders = await db_conn.fetch(
        'SELECT * FROM WargameOrder WHERE guild_id = $1 AND order_type = $2;',
        TEST_GUILD_ID, OrderType.RESOURCE_TRANSFER.value
    )
    assert len(orders) == 1
    assert orders[0]['status'] == OrderStatus.ONGOING.value

    # Fetch order to check order_data
    order = await Order.fetch_by_order_id(db_conn, orders[0]['order_id'], TEST_GUILD_ID)
    assert order.order_data['term'] == 5
    assert order.order_data['turns_executed'] == 0

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_ongoing_transfer_indefinite(db_conn, test_server):
    """Test submitting an ongoing transfer with no term (indefinite)."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-submit3", name="SenderSubmit3",
        user_id=100000000000000104, channel_id=900000000000000104,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-submit3", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-submit3", name="RecipientSubmit3",
        user_id=100000000000000105, channel_id=900000000000000105,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Execute
    resources = {'ore': 10, 'lumber': 5, 'coal': 0, 'rations': 0, 'cloth': 0, 'platinum': 0}
    success, message = await submit_resource_transfer_order(
        db_conn, sender, "recipient-submit3", resources, True, None, TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "Ongoing transfer order submitted" in message
    assert "(indefinite)" in message

    # Verify order was created
    orders = await db_conn.fetch(
        'SELECT * FROM WargameOrder WHERE guild_id = $1 AND order_type = $2;',
        TEST_GUILD_ID, OrderType.RESOURCE_TRANSFER.value
    )
    assert len(orders) == 1
    assert orders[0]['status'] == OrderStatus.ONGOING.value

    # Fetch order to check order_data
    order = await Order.fetch_by_order_id(db_conn, orders[0]['order_id'], TEST_GUILD_ID)
    assert order.order_data['term'] is None

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transfer_invalid_term(db_conn, test_server):
    """Test submitting an ongoing transfer with invalid term (< 2)."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-submit4", name="SenderSubmit4",
        user_id=100000000000000106, channel_id=900000000000000106,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-submit4", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-submit4", name="RecipientSubmit4",
        user_id=100000000000000107, channel_id=900000000000000107,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Execute with invalid term
    resources = {'ore': 10, 'lumber': 0, 'coal': 0, 'rations': 0, 'cloth': 0, 'platinum': 0}
    success, message = await submit_resource_transfer_order(
        db_conn, sender, "recipient-submit4", resources, True, 1, TEST_GUILD_ID
    )

    # Verify
    assert success is False
    assert "at least 2 turns" in message

    # Verify no order was created
    orders = await db_conn.fetch(
        'SELECT * FROM WargameOrder WHERE guild_id = $1 AND order_type = $2;',
        TEST_GUILD_ID, OrderType.RESOURCE_TRANSFER.value
    )
    assert len(orders) == 0

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transfer_no_resources(db_conn, test_server):
    """Test submitting a transfer with no resources (all zero)."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-submit5", name="SenderSubmit5",
        user_id=100000000000000108, channel_id=900000000000000108,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-submit5", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-submit5", name="RecipientSubmit5",
        user_id=100000000000000109, channel_id=900000000000000109,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Execute with all zero resources
    resources = {'ore': 0, 'lumber': 0, 'coal': 0, 'rations': 0, 'cloth': 0, 'platinum': 0}
    success, message = await submit_resource_transfer_order(
        db_conn, sender, "recipient-submit5", resources, False, None, TEST_GUILD_ID
    )

    # Verify
    assert success is False
    assert "at least one resource" in message

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transfer_negative_resources(db_conn, test_server):
    """Test submitting a transfer with negative resources."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-submit6", name="SenderSubmit6",
        user_id=100000000000000110, channel_id=900000000000000110,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-submit6", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-submit6", name="RecipientSubmit6",
        user_id=100000000000000111, channel_id=900000000000000111,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Execute with negative resources
    resources = {'ore': 100, 'lumber': -10, 'coal': 0, 'rations': 0, 'cloth': 0, 'platinum': 0}
    success, message = await submit_resource_transfer_order(
        db_conn, sender, "recipient-submit6", resources, False, None, TEST_GUILD_ID
    )

    # Verify
    assert success is False
    assert "cannot be negative" in message

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transfer_recipient_not_found(db_conn, test_server):
    """Test submitting a transfer to non-existent recipient."""
    # Setup: Create sender
    sender = Character(
        identifier="sender-submit7", name="SenderSubmit7",
        user_id=100000000000000112, channel_id=900000000000000112,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-submit7", TEST_GUILD_ID)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Execute with non-existent recipient
    resources = {'ore': 100, 'lumber': 0, 'coal': 0, 'rations': 0, 'cloth': 0, 'platinum': 0}
    success, message = await submit_resource_transfer_order(
        db_conn, sender, "non-existent", resources, False, None, TEST_GUILD_ID
    )

    # Verify
    assert success is False
    assert "not found" in message

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transfer_to_self(db_conn, test_server):
    """Test submitting a transfer to self (should fail)."""
    # Setup: Create character
    sender = Character(
        identifier="sender-submit8", name="SenderSubmit8",
        user_id=100000000000000113, channel_id=900000000000000113,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-submit8", TEST_GUILD_ID)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Execute transfer to self
    resources = {'ore': 100, 'lumber': 0, 'coal': 0, 'rations': 0, 'cloth': 0, 'platinum': 0}
    success, message = await submit_resource_transfer_order(
        db_conn, sender, "sender-submit8", resources, False, None, TEST_GUILD_ID
    )

    # Verify
    assert success is False
    assert "yourself" in message

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# Tests for submit_cancel_transfer_order
# ============================================================================

@pytest.mark.asyncio
async def test_submit_cancel_transfer_success(db_conn, test_server):
    """Test successfully submitting a cancel transfer order."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-cancel1", name="SenderCancel1",
        user_id=100000000000000120, channel_id=900000000000000120,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-cancel1", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-cancel1", name="RecipientCancel1",
        user_id=100000000000000121, channel_id=900000000000000121,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-cancel1", TEST_GUILD_ID)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Setup: Create ongoing transfer order
    transfer_order = Order(
        order_id="TRANSFER-CANCEL-001",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=4,  # Previous turn
        phase="RESOURCE_TRANSFER",
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

    # Execute
    success, message = await submit_cancel_transfer_order(
        db_conn, sender, "TRANSFER-CANCEL-001", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "Cancel transfer order submitted" in message

    # Verify cancel order was created
    orders = await db_conn.fetch(
        'SELECT * FROM WargameOrder WHERE guild_id = $1 AND order_type = $2;',
        TEST_GUILD_ID, OrderType.CANCEL_TRANSFER.value
    )
    assert len(orders) == 1
    assert orders[0]['status'] == OrderStatus.PENDING.value
    assert orders[0]['turn_number'] == 6  # Current turn + 1

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_cancel_transfer_order_not_found(db_conn, test_server):
    """Test submitting cancel for non-existent order."""
    # Setup: Create character
    sender = Character(
        identifier="sender-cancel2", name="SenderCancel2",
        user_id=100000000000000122, channel_id=900000000000000122,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-cancel2", TEST_GUILD_ID)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Execute with non-existent order ID
    success, message = await submit_cancel_transfer_order(
        db_conn, sender, "NON-EXISTENT", TEST_GUILD_ID
    )

    # Verify
    assert success is False
    assert "not found" in message

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_cancel_transfer_not_ongoing(db_conn, test_server):
    """Test submitting cancel for order that is not ONGOING."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-cancel3", name="SenderCancel3",
        user_id=100000000000000123, channel_id=900000000000000123,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-cancel3", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-cancel3", name="RecipientCancel3",
        user_id=100000000000000124, channel_id=900000000000000124,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-cancel3", TEST_GUILD_ID)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Setup: Create PENDING transfer order (not ONGOING)
    transfer_order = Order(
        order_id="TRANSFER-CANCEL-003",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=4,
        phase="RESOURCE_TRANSFER",
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
    success, message = await submit_cancel_transfer_order(
        db_conn, sender, "TRANSFER-CANCEL-003", TEST_GUILD_ID
    )

    # Verify
    assert success is False
    assert "not ONGOING" in message

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_cancel_transfer_not_owner(db_conn, test_server):
    """Test submitting cancel for another character's order."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-cancel4", name="SenderCancel4",
        user_id=100000000000000125, channel_id=900000000000000125,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-cancel4", TEST_GUILD_ID)

    other_character = Character(
        identifier="other-char4", name="OtherChar4",
        user_id=100000000000000126, channel_id=900000000000000126,
        guild_id=TEST_GUILD_ID
    )
    await other_character.upsert(db_conn)
    other_character = await Character.fetch_by_identifier(db_conn, "other-char4", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-cancel4", name="RecipientCancel4",
        user_id=100000000000000127, channel_id=900000000000000127,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-cancel4", TEST_GUILD_ID)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Setup: Create ongoing transfer order owned by sender
    transfer_order = Order(
        order_id="TRANSFER-CANCEL-004",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=4,
        phase="RESOURCE_TRANSFER",
        priority=1,
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 100,
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

    # Execute with other_character trying to cancel sender's order
    success, message = await submit_cancel_transfer_order(
        db_conn, other_character, "TRANSFER-CANCEL-004", TEST_GUILD_ID
    )

    # Verify
    assert success is False
    assert "does not belong to you" in message

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_cancel_transfer_same_turn(db_conn, test_server):
    """Test submitting cancel on same turn as order submission (should fail)."""
    # Setup: Create characters
    sender = Character(
        identifier="sender-cancel5", name="SenderCancel5",
        user_id=100000000000000128, channel_id=900000000000000128,
        guild_id=TEST_GUILD_ID
    )
    await sender.upsert(db_conn)
    sender = await Character.fetch_by_identifier(db_conn, "sender-cancel5", TEST_GUILD_ID)

    recipient = Character(
        identifier="recipient-cancel5", name="RecipientCancel5",
        user_id=100000000000000129, channel_id=900000000000000129,
        guild_id=TEST_GUILD_ID
    )
    await recipient.upsert(db_conn)
    recipient = await Character.fetch_by_identifier(db_conn, "recipient-cancel5", TEST_GUILD_ID)

    # Setup: Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Setup: Create ongoing transfer order for current turn
    transfer_order = Order(
        order_id="TRANSFER-CANCEL-005",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        character_id=sender.id,
        turn_number=5,  # Current turn - submitted this turn
        phase="RESOURCE_TRANSFER",
        priority=1,
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': recipient.id,
            'ore': 100,
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
    success, message = await submit_cancel_transfer_order(
        db_conn, sender, "TRANSFER-CANCEL-005", TEST_GUILD_ID
    )

    # Verify
    assert success is False
    assert "same turn" in message

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
