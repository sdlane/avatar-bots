"""
Pytest tests for turn resolution handlers.
Tests verify turn resolution, phase execution, and turn status retrieval.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_turn_handlers.py -v
"""
import pytest
from handlers.turn_handlers import (
    resolve_turn, execute_beginning_phase, get_turn_status
)
from db import (
    Character, Faction, FactionMember, WargameConfig, Order, TurnLog
)
from order_types import OrderType, OrderStatus, TurnPhase
from tests.conftest import TEST_GUILD_ID
from datetime import datetime


@pytest.mark.asyncio
async def test_resolve_turn_no_config(db_conn, test_server):
    """Test that resolve_turn fails when wargame is not configured."""
    # Don't create WargameConfig
    success, message, events = await resolve_turn(db_conn, TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not configured" in message.lower()
    assert events == []


@pytest.mark.asyncio
async def test_resolve_turn_empty_turn(db_conn, test_server):
    """Test resolving a turn with no orders."""
    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Resolve turn
    success, message, events = await resolve_turn(db_conn, TEST_GUILD_ID)

    # Verify success
    assert success is True
    assert "resolved successfully" in message.lower()
    assert events == []

    # Verify turn incremented
    updated_config = await WargameConfig.fetch(db_conn, TEST_GUILD_ID)
    assert updated_config.current_turn == 6
    assert updated_config.last_turn_time is not None

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_resolve_turn_with_orders(db_conn, test_server):
    """Test resolving a turn with pending orders."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add leader as member
    leader_member = FactionMember(
        faction_id=faction.id, character_id=leader.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await leader_member.insert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Create a pending join faction order
    order = Order(
        order_id="ORD-0001",
        order_type=OrderType.JOIN_FACTION.value,
        character_id=char.id,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        turn_number=6,
        submitted_at=datetime.now(),
        order_data={'faction_id': 'test-faction', 'requested_by': char.id},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Resolve turn
    success, message, events = await resolve_turn(db_conn, TEST_GUILD_ID)

    # Verify success
    assert success is True
    assert "resolved successfully" in message.lower()
    assert len(events) > 0

    # Verify turn incremented
    updated_config = await WargameConfig.fetch(db_conn, TEST_GUILD_ID)
    assert updated_config.current_turn == 6

    # Verify order was processed
    processed_order = await Order.fetch_by_order_id(db_conn, "ORD-0001", TEST_GUILD_ID)
    assert processed_order.status in [OrderStatus.SUCCESS.value, OrderStatus.FAILED.value]

    # Verify TurnLog entries created
    turn_logs = await db_conn.fetch(
        'SELECT * FROM TurnLog WHERE guild_id = $1 AND turn_number = $2;',
        TEST_GUILD_ID, 6
    )
    assert len(turn_logs) == len(events)

    # Cleanup
    await db_conn.execute('DELETE FROM TurnLog WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute('DELETE FROM "Order" WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_resolve_turn_multiple_phases(db_conn, test_server):
    """Test that resolve_turn executes all phases in order."""
    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Resolve turn (all phases should execute even if they're placeholders)
    success, message, events = await resolve_turn(db_conn, TEST_GUILD_ID)

    # Verify success
    assert success is True

    # Verify config was updated with new turn
    updated_config = await WargameConfig.fetch(db_conn, TEST_GUILD_ID)
    assert updated_config.current_turn == 6

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_execute_beginning_phase_no_orders(db_conn, test_server):
    """Test beginning phase with no pending orders."""
    events = await execute_beginning_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify no events
    assert events == []


@pytest.mark.asyncio
async def test_execute_beginning_phase_with_join_order(db_conn, test_server):
    """Test beginning phase processes join faction orders."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add leader as member
    leader_member = FactionMember(
        faction_id=faction.id, character_id=leader.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await leader_member.insert(db_conn)

    # Create a pending join faction order
    order = Order(
        order_id="ORD-0001",
        order_type=OrderType.JOIN_FACTION.value,
        character_id=char.id,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        turn_number=6,
        submitted_at=datetime.now(),
        order_data={'faction_id': 'test-faction', 'requested_by': char.id},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute phase
    events = await execute_beginning_phase(db_conn, TEST_GUILD_ID, 6)

    # Verify events returned
    assert len(events) > 0
    assert events[0]['phase'] == TurnPhase.BEGINNING.value

    # Verify order was updated
    processed_order = await Order.fetch_by_order_id(db_conn, "ORD-0001", TEST_GUILD_ID)
    assert processed_order.status in [OrderStatus.SUCCESS.value, OrderStatus.FAILED.value]

    # Cleanup
    await db_conn.execute('DELETE FROM "Order" WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_execute_beginning_phase_with_leave_order(db_conn, test_server):
    """Test beginning phase processes leave faction orders."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create member
    member = Character(
        identifier="member", name="Member",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)
    member = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add both as members
    leader_member = FactionMember(
        faction_id=faction.id, character_id=leader.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await leader_member.insert(db_conn)

    regular_member = FactionMember(
        faction_id=faction.id, character_id=member.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await regular_member.insert(db_conn)

    # Create a pending leave faction order
    order = Order(
        order_id="ORD-0001",
        order_type=OrderType.LEAVE_FACTION.value,
        character_id=member.id,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        turn_number=6,
        submitted_at=datetime.now(),
        order_data={},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute phase
    events = await execute_beginning_phase(db_conn, TEST_GUILD_ID, 6)

    # Verify events returned
    assert len(events) > 0
    assert events[0]['phase'] == TurnPhase.BEGINNING.value
    assert events[0]['event_type'] in ['LEAVE_FACTION']

    # Verify order was updated
    processed_order = await Order.fetch_by_order_id(db_conn, "ORD-0001", TEST_GUILD_ID)
    assert processed_order.status in [OrderStatus.SUCCESS.value, OrderStatus.FAILED.value]

    # If successful, verify member was removed
    if processed_order.status == OrderStatus.SUCCESS.value:
        remaining_member = await FactionMember.fetch_by_character(db_conn, member.id, TEST_GUILD_ID)
        assert remaining_member is None

    # Cleanup
    await db_conn.execute('DELETE FROM "Order" WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_execute_beginning_phase_with_unknown_order_type(db_conn, test_server):
    """Test beginning phase handles unknown order types gracefully."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create an order with an unknown type (manually insert to bypass validation)
    await db_conn.execute("""
        INSERT INTO "Order" (
            order_id, order_type, character_id, phase, priority,
            status, turn_number, submitted_at, order_data, guild_id
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);
    """, "ORD-0001", "UNKNOWN_TYPE", char.id, TurnPhase.BEGINNING.value, 0,
        OrderStatus.PENDING.value, 6, datetime.now(), "{}", TEST_GUILD_ID)

    # Execute phase
    events = await execute_beginning_phase(db_conn, TEST_GUILD_ID, 6)

    # Verify no events from unknown order
    # (Unknown orders are marked as FAILED but don't generate events in this implementation)

    # Verify order was marked as failed
    failed_order = await Order.fetch_by_order_id(db_conn, "ORD-0001", TEST_GUILD_ID)
    assert failed_order.status == OrderStatus.FAILED.value
    assert 'no handler found' in failed_order.result_data.get('error', '').lower()

    # Cleanup
    await db_conn.execute('DELETE FROM "Order" WHERE guild_id = $1;', TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_execute_beginning_phase_multiple_orders(db_conn, test_server):
    """Test beginning phase processes multiple orders in priority order."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create members
    member1 = Character(
        identifier="member1", name="Member 1",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await member1.upsert(db_conn)
    member1 = await Character.fetch_by_identifier(db_conn, "member1", TEST_GUILD_ID)

    member2 = Character(
        identifier="member2", name="Member 2",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await member2.upsert(db_conn)
    member2 = await Character.fetch_by_identifier(db_conn, "member2", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add leader and member1 as members
    leader_member = FactionMember(
        faction_id=faction.id, character_id=leader.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await leader_member.insert(db_conn)

    member1_fm = FactionMember(
        faction_id=faction.id, character_id=member1.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member1_fm.insert(db_conn)

    # Create leave order (priority 0) - should execute first
    leave_order = Order(
        order_id="ORD-0001",
        order_type=OrderType.LEAVE_FACTION.value,
        character_id=member1.id,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        turn_number=6,
        submitted_at=datetime.now(),
        order_data={},
        guild_id=TEST_GUILD_ID
    )
    await leave_order.upsert(db_conn)

    # Create join order (priority 1) - should execute second
    join_order = Order(
        order_id="ORD-0002",
        order_type=OrderType.JOIN_FACTION.value,
        character_id=member2.id,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        turn_number=6,
        submitted_at=datetime.now(),
        order_data={'faction_id': 'test-faction', 'requested_by': member2.id},
        guild_id=TEST_GUILD_ID
    )
    await join_order.upsert(db_conn)

    # Execute phase
    events = await execute_beginning_phase(db_conn, TEST_GUILD_ID, 6)

    # Verify both orders processed
    assert len(events) >= 2

    # Verify both orders were updated
    processed_leave = await Order.fetch_by_order_id(db_conn, "ORD-0001", TEST_GUILD_ID)
    processed_join = await Order.fetch_by_order_id(db_conn, "ORD-0002", TEST_GUILD_ID)
    assert processed_leave.status in [OrderStatus.SUCCESS.value, OrderStatus.FAILED.value]
    assert processed_join.status in [OrderStatus.SUCCESS.value, OrderStatus.FAILED.value]

    # Cleanup
    await db_conn.execute('DELETE FROM "Order" WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_get_turn_status_no_config(db_conn, test_server):
    """Test get_turn_status when wargame is not configured."""
    success, message, status = await get_turn_status(db_conn, TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not configured" in message.lower()
    assert status is None


@pytest.mark.asyncio
async def test_get_turn_status_no_orders(db_conn, test_server):
    """Test get_turn_status with no pending orders."""
    # Create WargameConfig
    config = WargameConfig(
        guild_id=TEST_GUILD_ID,
        current_turn=5,
        turn_resolution_enabled=True
    )
    await config.upsert(db_conn)

    # Get status
    success, message, status = await get_turn_status(db_conn, TEST_GUILD_ID)

    # Verify success
    assert success is True
    assert "retrieved" in message.lower()
    assert status is not None
    assert status['current_turn'] == 5
    assert status['turn_resolution_enabled'] is True
    assert status['total_pending'] == 0

    # Verify all phases have 0 pending
    for phase in TurnPhase:
        assert status['pending_orders'][phase.value] == 0

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_get_turn_status_with_pending_orders(db_conn, test_server):
    """Test get_turn_status with pending orders."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create WargameConfig
    config = WargameConfig(
        guild_id=TEST_GUILD_ID,
        current_turn=5,
        turn_resolution_enabled=True
    )
    await config.upsert(db_conn)

    # Create pending orders in different phases
    order1 = Order(
        order_id="ORD-0001",
        order_type=OrderType.JOIN_FACTION.value,
        character_id=char.id,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        turn_number=6,
        submitted_at=datetime.now(),
        order_data={},
        guild_id=TEST_GUILD_ID
    )
    await order1.upsert(db_conn)

    order2 = Order(
        order_id="ORD-0002",
        order_type=OrderType.TRANSIT.value,
        character_id=char.id,
        phase=TurnPhase.MOVEMENT.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        turn_number=6,
        submitted_at=datetime.now(),
        order_data={},
        guild_id=TEST_GUILD_ID
    )
    await order2.upsert(db_conn)

    # Create an ONGOING order (should also be counted)
    order3 = Order(
        order_id="ORD-0003",
        order_type=OrderType.TRANSIT.value,
        character_id=char.id,
        phase=TurnPhase.MOVEMENT.value,
        priority=0,
        status=OrderStatus.ONGOING.value,
        turn_number=6,
        submitted_at=datetime.now(),
        order_data={},
        guild_id=TEST_GUILD_ID
    )
    await order3.upsert(db_conn)

    # Get status
    success, message, status = await get_turn_status(db_conn, TEST_GUILD_ID)

    # Verify success
    assert success is True
    assert status['current_turn'] == 5
    assert status['total_pending'] == 3
    assert status['pending_orders'][TurnPhase.BEGINNING.value] == 1
    assert status['pending_orders'][TurnPhase.MOVEMENT.value] == 2

    # Cleanup
    await db_conn.execute('DELETE FROM "Order" WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_get_turn_status_with_completed_orders(db_conn, test_server):
    """Test that completed orders are not counted in turn status."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create WargameConfig
    config = WargameConfig(
        guild_id=TEST_GUILD_ID,
        current_turn=5
    )
    await config.upsert(db_conn)

    # Create a completed order
    order = Order(
        order_id="ORD-0001",
        order_type=OrderType.JOIN_FACTION.value,
        character_id=char.id,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.SUCCESS.value,
        turn_number=5,
        submitted_at=datetime.now(),
        order_data={},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Get status
    success, message, status = await get_turn_status(db_conn, TEST_GUILD_ID)

    # Verify no pending orders counted
    assert success is True
    assert status['total_pending'] == 0

    # Cleanup
    await db_conn.execute('DELETE FROM "Order" WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_get_turn_status_last_turn_time_format(db_conn, test_server):
    """Test that last_turn_time is properly formatted as ISO string."""
    # Create WargameConfig with last_turn_time
    config = WargameConfig(
        guild_id=TEST_GUILD_ID,
        current_turn=5,
        last_turn_time=datetime.now()
    )
    await config.upsert(db_conn)

    # Get status
    success, message, status = await get_turn_status(db_conn, TEST_GUILD_ID)

    # Verify last_turn_time is ISO formatted string
    assert success is True
    assert status['last_turn_time'] is not None
    assert isinstance(status['last_turn_time'], str)
    # Should be parseable as ISO format
    from datetime import datetime as dt
    parsed_time = dt.fromisoformat(status['last_turn_time'])
    assert parsed_time is not None

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_get_turn_status_null_last_turn_time(db_conn, test_server):
    """Test get_turn_status handles null last_turn_time."""
    # Create WargameConfig without last_turn_time
    config = WargameConfig(
        guild_id=TEST_GUILD_ID,
        current_turn=0,
        last_turn_time=None
    )
    await config.upsert(db_conn)

    # Get status
    success, message, status = await get_turn_status(db_conn, TEST_GUILD_ID)

    # Verify null is handled
    assert success is True
    assert status['last_turn_time'] is None

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_resolve_turn_logs_all_events(db_conn, test_server):
    """Test that resolve_turn writes all events to TurnLog."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create member
    member = Character(
        identifier="member", name="Member",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)
    member = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add leader as member
    leader_fm = FactionMember(
        faction_id=faction.id, character_id=leader.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await leader_fm.insert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Create multiple orders
    order1 = Order(
        order_id="ORD-0001",
        order_type=OrderType.JOIN_FACTION.value,
        character_id=member.id,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        turn_number=6,
        submitted_at=datetime.now(),
        order_data={'faction_id': 'test-faction', 'requested_by': member.id},
        guild_id=TEST_GUILD_ID
    )
    await order1.upsert(db_conn)

    # Resolve turn
    success, message, events = await resolve_turn(db_conn, TEST_GUILD_ID)

    # Verify success
    assert success is True

    # Verify all events logged
    turn_logs = await db_conn.fetch(
        'SELECT * FROM TurnLog WHERE guild_id = $1 AND turn_number = $2;',
        TEST_GUILD_ID, 6
    )
    assert len(turn_logs) == len(events)

    # Verify log structure
    for log in turn_logs:
        assert log['turn_number'] == 6
        assert log['phase'] is not None
        assert log['event_type'] is not None
        assert log['guild_id'] == TEST_GUILD_ID

    # Cleanup
    await db_conn.execute('DELETE FROM TurnLog WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute('DELETE FROM "Order" WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
