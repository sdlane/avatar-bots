"""
Tests for resource transfer integration with turn resolution.
"""
import pytest
from tests.conftest import TEST_GUILD_ID
import asyncpg
from db import Character, PlayerResources, Order, WargameConfig, TurnLog
from order_types import OrderType, OrderStatus, TurnPhase, ORDER_PHASE_MAP, ORDER_PRIORITY_MAP
from handlers.turn_handlers import execute_resource_transfer_phase
from datetime import datetime


@pytest.mark.asyncio
async def test_execute_resource_transfer_phase_processes_cancel_first(db_conn, test_server):
    """Test that CANCEL orders are processed before RESOURCE_TRANSFER orders."""
    conn = db_conn
    guild_id = TEST_GUILD_ID

    # Create characters
    char1 = Character(identifier="alice", name="Alice", user_id=100, channel_id=900, guild_id=guild_id)
    await char1.upsert(conn)
    char1 = await Character.fetch_by_identifier(conn, "alice", guild_id)
    char2 = Character(identifier="bob", name="Bob", user_id=200, channel_id=901, guild_id=guild_id)
    await char2.upsert(conn)
    char2 = await Character.fetch_by_identifier(conn, "bob", guild_id)

    # Create resources for sender
    sender_resources = PlayerResources(
        character_id=char1.id, ore=100, lumber=50, guild_id=guild_id
    )
    await sender_resources.upsert(conn)

    # Create ONGOING transfer order
    ongoing_order = Order(
        order_id="ORD-0001",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.RESOURCE_TRANSFER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.RESOURCE_TRANSFER],
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': char2.id,
            'ore': 10,
            'lumber': 5,
            'coal': 0,
            'rations': 0,
            'cloth': 0,
            'term': None,
            'turns_executed': 0
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )
    await ongoing_order.upsert(conn)

    # Create CANCEL order
    cancel_order = Order(
        order_id="ORD-0002",
        order_type=OrderType.CANCEL_TRANSFER.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.CANCEL_TRANSFER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.CANCEL_TRANSFER],
        status=OrderStatus.PENDING.value,
        order_data={'original_order_id': 'ORD-0001'},
        submitted_at=datetime.now(),
        guild_id=guild_id
    )
    await cancel_order.upsert(conn)

    # Execute resource transfer phase
    events = await execute_resource_transfer_phase(conn, guild_id, 1)

    # Verify cancel was processed (should generate TRANSFER_CANCELLED event)
    assert len(events) == 1
    assert events[0].event_type == 'TRANSFER_CANCELLED'

    # Verify original order is now CANCELLED
    updated_ongoing = await Order.fetch_by_order_id(conn, "ORD-0001", guild_id)
    assert updated_ongoing.status == OrderStatus.CANCELLED.value

    # Verify cancel order is SUCCESS
    updated_cancel = await Order.fetch_by_order_id(conn, "ORD-0002", guild_id)
    assert updated_cancel.status == OrderStatus.SUCCESS.value

    # Verify no resources were transferred (cancel happened first)
    sender = await PlayerResources.fetch_by_character(conn, char1.id, guild_id)
    assert sender.ore == 100
    assert sender.lumber == 50

    # Cleanup
    await Order.delete(conn, "ORD-0001", guild_id)
    await Order.delete(conn, "ORD-0002", guild_id)
    await PlayerResources.delete(conn, char1.id, guild_id)
    await PlayerResources.delete(conn, char2.id, guild_id)
    await Character.delete(conn, char1.id)
    await Character.delete(conn, char2.id)


@pytest.mark.asyncio
async def test_execute_resource_transfer_phase_processes_pending_then_ongoing(db_conn, test_server):
    """Test that PENDING orders are processed before ONGOING orders."""
    conn = db_conn
    guild_id = TEST_GUILD_ID

    # Create characters
    char1 = Character(identifier="alice", name="Alice", user_id=100, channel_id=900, guild_id=guild_id)
    await char1.upsert(conn)
    char1 = await Character.fetch_by_identifier(conn, "alice", guild_id)
    char2 = Character(identifier="bob", name="Bob", user_id=200, channel_id=901, guild_id=guild_id)
    await char2.upsert(conn)
    char2 = await Character.fetch_by_identifier(conn, "bob", guild_id)

    # Create resources for sender
    sender_resources = PlayerResources(
        character_id=char1.id, ore=100, lumber=50, guild_id=guild_id
    )
    await sender_resources.upsert(conn)

    # Create PENDING one-time transfer order
    pending_order = Order(
        order_id="ORD-0001",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.RESOURCE_TRANSFER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.RESOURCE_TRANSFER],
        status=OrderStatus.PENDING.value,
        order_data={
            'to_character_id': char2.id,
            'ore': 20,
            'lumber': 10,
            'coal': 0,
            'rations': 0,
            'cloth': 0
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )
    await pending_order.upsert(conn)

    # Create ONGOING recurring transfer order
    ongoing_order = Order(
        order_id="ORD-0002",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.RESOURCE_TRANSFER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.RESOURCE_TRANSFER],
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': char2.id,
            'ore': 10,
            'lumber': 5,
            'coal': 0,
            'rations': 0,
            'cloth': 0,
            'term': None,
            'turns_executed': 0
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )
    await ongoing_order.upsert(conn)

    # Execute resource transfer phase
    events = await execute_resource_transfer_phase(conn, guild_id, 1)

    # Verify both transfers were processed
    assert len(events) == 2
    assert all(e.event_type == 'RESOURCE_TRANSFER_SUCCESS' for e in events)

    # Verify PENDING order is now SUCCESS
    updated_pending = await Order.fetch_by_order_id(conn, "ORD-0001", guild_id)
    assert updated_pending.status == OrderStatus.SUCCESS.value

    # Verify ONGOING order stays ONGOING and turns_executed incremented
    updated_ongoing = await Order.fetch_by_order_id(conn, "ORD-0002", guild_id)
    assert updated_ongoing.status == OrderStatus.ONGOING.value
    assert updated_ongoing.order_data['turns_executed'] == 1

    # Verify resources transferred correctly (20+10 ore, 10+5 lumber)
    sender = await PlayerResources.fetch_by_character(conn, char1.id, guild_id)
    assert sender.ore == 70  # 100 - 20 - 10
    assert sender.lumber == 35  # 50 - 10 - 5

    recipient = await PlayerResources.fetch_by_character(conn, char2.id, guild_id)
    assert recipient.ore == 30  # 20 + 10
    assert recipient.lumber == 15  # 10 + 5

    # Cleanup
    await Order.delete(conn, "ORD-0001", guild_id)
    await Order.delete(conn, "ORD-0002", guild_id)
    await PlayerResources.delete(conn, char1.id, guild_id)
    await PlayerResources.delete(conn, char2.id, guild_id)
    await Character.delete(conn, char1.id)
    await Character.delete(conn, char2.id)


@pytest.mark.asyncio
async def test_execute_resource_transfer_phase_multiple_transfers_same_turn(db_conn, test_server):
    """Test that multiple transfers in the same turn are processed correctly."""
    conn = db_conn
    guild_id = TEST_GUILD_ID

    # Create characters
    char1 = Character(identifier="alice", name="Alice", user_id=100, channel_id=900, guild_id=guild_id)
    await char1.upsert(conn)
    char1 = await Character.fetch_by_identifier(conn, "alice", guild_id)
    char2 = Character(identifier="bob", name="Bob", user_id=200, channel_id=901, guild_id=guild_id)
    await char2.upsert(conn)
    char2 = await Character.fetch_by_identifier(conn, "bob", guild_id)
    char3 = Character(identifier="charlie", name="Charlie", user_id=300, channel_id=902, guild_id=guild_id)
    await char3.upsert(conn)
    char3 = await Character.fetch_by_identifier(conn, "charlie", guild_id)

    # Create resources
    sender1_resources = PlayerResources(
        character_id=char1.id, ore=100, lumber=50, guild_id=guild_id
    )
    await sender1_resources.upsert(conn)

    sender2_resources = PlayerResources(
        character_id=char2.id, ore=80, coal=40, guild_id=guild_id
    )
    await sender2_resources.upsert(conn)

    # Create transfer order: Alice -> Charlie
    order1 = Order(
        order_id="ORD-0001",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.RESOURCE_TRANSFER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.RESOURCE_TRANSFER],
        status=OrderStatus.PENDING.value,
        order_data={
            'to_character_id': char3.id,
            'ore': 30,
            'lumber': 10,
            'coal': 0,
            'rations': 0,
            'cloth': 0
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )
    await order1.upsert(conn)

    # Create transfer order: Bob -> Charlie
    order2 = Order(
        order_id="ORD-0002",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        unit_ids=[],
        character_id=char2.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.RESOURCE_TRANSFER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.RESOURCE_TRANSFER],
        status=OrderStatus.PENDING.value,
        order_data={
            'to_character_id': char3.id,
            'ore': 20,
            'lumber': 0,
            'coal': 15,
            'rations': 0,
            'cloth': 0
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )
    await order2.upsert(conn)

    # Execute resource transfer phase
    events = await execute_resource_transfer_phase(conn, guild_id, 1)

    # Verify both transfers were processed
    assert len(events) == 2
    assert all(e.event_type == 'RESOURCE_TRANSFER_SUCCESS' for e in events)

    # Verify both orders are SUCCESS
    updated1 = await Order.fetch_by_order_id(conn, "ORD-0001", guild_id)
    assert updated1.status == OrderStatus.SUCCESS.value
    updated2 = await Order.fetch_by_order_id(conn, "ORD-0002", guild_id)
    assert updated2.status == OrderStatus.SUCCESS.value

    # Verify resources transferred correctly
    sender1 = await PlayerResources.fetch_by_character(conn, char1.id, guild_id)
    assert sender1.ore == 70  # 100 - 30
    assert sender1.lumber == 40  # 50 - 10

    sender2 = await PlayerResources.fetch_by_character(conn, char2.id, guild_id)
    assert sender2.ore == 60  # 80 - 20
    assert sender2.coal == 25  # 40 - 15

    recipient = await PlayerResources.fetch_by_character(conn, char3.id, guild_id)
    assert recipient.ore == 50  # 30 + 20
    assert recipient.lumber == 10
    assert recipient.coal == 15

    # Cleanup
    await Order.delete(conn, "ORD-0001", guild_id)
    await Order.delete(conn, "ORD-0002", guild_id)
    await PlayerResources.delete(conn, char1.id, guild_id)
    await PlayerResources.delete(conn, char2.id, guild_id)
    await PlayerResources.delete(conn, char3.id, guild_id)
    await Character.delete(conn, char1.id)
    await Character.delete(conn, char2.id)
    await Character.delete(conn, char3.id)


@pytest.mark.asyncio
async def test_execute_resource_transfer_phase_ongoing_term_expiration(db_conn, test_server):
    """Test that ongoing transfers with term expire correctly."""
    conn = db_conn
    guild_id = TEST_GUILD_ID

    # Create characters
    char1 = Character(identifier="alice", name="Alice", user_id=100, channel_id=900, guild_id=guild_id)
    await char1.upsert(conn)
    char1 = await Character.fetch_by_identifier(conn, "alice", guild_id)
    char2 = Character(identifier="bob", name="Bob", user_id=200, channel_id=901, guild_id=guild_id)
    await char2.upsert(conn)
    char2 = await Character.fetch_by_identifier(conn, "bob", guild_id)

    # Create resources for sender
    sender_resources = PlayerResources(
        character_id=char1.id, ore=100, lumber=50, guild_id=guild_id
    )
    await sender_resources.upsert(conn)

    # Create ONGOING transfer order with term=2
    ongoing_order = Order(
        order_id="ORD-0001",
        order_type=OrderType.RESOURCE_TRANSFER.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.RESOURCE_TRANSFER].value,
        priority=ORDER_PRIORITY_MAP[OrderType.RESOURCE_TRANSFER],
        status=OrderStatus.ONGOING.value,
        order_data={
            'to_character_id': char2.id,
            'ore': 10,
            'lumber': 5,
            'coal': 0,
            'rations': 0,
            'cloth': 0,
            'term': 2,
            'turns_executed': 1  # Already executed 1 turn
        },
        submitted_at=datetime.now(),
        guild_id=guild_id
    )
    await ongoing_order.upsert(conn)

    # Execute resource transfer phase (should be turn 2, term expires)
    events = await execute_resource_transfer_phase(conn, guild_id, 2)

    # Verify transfer was processed
    assert len(events) == 1
    assert events[0].event_type == 'RESOURCE_TRANSFER_SUCCESS'

    # Verify order is now SUCCESS (term expired)
    updated_order = await Order.fetch_by_order_id(conn, "ORD-0001", guild_id)
    assert updated_order.status == OrderStatus.SUCCESS.value
    assert updated_order.order_data['turns_executed'] == 2

    # Verify resources transferred
    sender = await PlayerResources.fetch_by_character(conn, char1.id, guild_id)
    assert sender.ore == 90  # 100 - 10
    assert sender.lumber == 45  # 50 - 5

    recipient = await PlayerResources.fetch_by_character(conn, char2.id, guild_id)
    assert recipient.ore == 10
    assert recipient.lumber == 5

    # Cleanup
    await Order.delete(conn, "ORD-0001", guild_id)
    await PlayerResources.delete(conn, char1.id, guild_id)
    await PlayerResources.delete(conn, char2.id, guild_id)
    await Character.delete(conn, char1.id)
    await Character.delete(conn, char2.id)


@pytest.mark.asyncio
async def test_execute_resource_transfer_phase_empty(db_conn, test_server):
    """Test that phase handles no orders gracefully."""
    conn = db_conn
    guild_id = TEST_GUILD_ID

    # Execute resource transfer phase with no orders
    events = await execute_resource_transfer_phase(conn, guild_id, 1)

    # Verify no events generated
    assert len(events) == 0
