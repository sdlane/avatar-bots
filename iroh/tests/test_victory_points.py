"""
Pytest tests for victory points system.
Tests verify VP field on territories, VP assignment orders, and VP view handler.

Run with: pytest tests/test_victory_points.py -v
"""
import pytest
from orders.victory_point_orders import handle_assign_victory_points_order
from handlers.order_handlers import submit_assign_victory_points_order, cancel_order
from handlers.view_handlers import view_victory_points
from db import Character, Faction, FactionMember, Territory, WargameConfig, Order
from order_types import OrderType, OrderStatus, TurnPhase
from tests.conftest import TEST_GUILD_ID
from datetime import datetime


async def setup_vp_test_data(db_conn):
    """Helper to set up test data for VP tests."""
    # Create characters
    char1 = Character(
        identifier="vp-char-1", name="VP Character One",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "vp-char-1", TEST_GUILD_ID)

    char2 = Character(
        identifier="vp-char-2", name="VP Character Two",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "vp-char-2", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="vp-faction", name="VP Faction",
        leader_character_id=char2.id, guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "vp-faction", TEST_GUILD_ID)

    # Add char2 to faction
    char2_member = FactionMember(
        character_id=char2.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await char2_member.insert(db_conn)

    # Create territories with VP
    territory1 = Territory(
        territory_id="1", name="High VP Territory",
        terrain_type="plains", victory_points=5,
        controller_character_id=char1.id,
        guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id="2", name="Medium VP Territory",
        terrain_type="mountain", victory_points=3,
        controller_character_id=char1.id,
        guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    territory3 = Territory(
        territory_id="3", name="Faction Territory",
        terrain_type="plains", victory_points=2,
        controller_character_id=char2.id,
        guild_id=TEST_GUILD_ID
    )
    await territory3.upsert(db_conn)

    # Create wargame config
    config = WargameConfig(
        guild_id=TEST_GUILD_ID,
        current_turn=5
    )
    await config.upsert(db_conn)

    return char1, char2, faction


async def cleanup_vp_test_data(db_conn):
    """Helper to clean up test data."""
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


# ============ Territory VP Tests ============

@pytest.mark.asyncio
async def test_territory_vp_persists(db_conn, test_server):
    """Test that territory victory_points field persists correctly."""
    territory = Territory(
        territory_id="100", name="VP Test Territory",
        terrain_type="plains", victory_points=10,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Fetch and verify
    fetched = await Territory.fetch_by_territory_id(db_conn, "100", TEST_GUILD_ID)
    assert fetched is not None
    assert fetched.victory_points == 10

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE territory_id = $1 AND guild_id = $2;", "100", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_territory_fetch_by_controller_returns_vp(db_conn, test_server):
    """Test that fetch_by_controller returns VP values."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    territories = await Territory.fetch_by_controller(db_conn, char1.id, TEST_GUILD_ID)
    total_vps = sum(t.victory_points for t in territories)

    assert len(territories) == 2
    assert total_vps == 8  # 5 + 3

    await cleanup_vp_test_data(db_conn)


# ============ Order Submission Tests ============

@pytest.mark.asyncio
async def test_submit_assign_vp_order_success(db_conn, test_server):
    """Test successfully submitting a VP assignment order."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    success, message = await submit_assign_victory_points_order(
        db_conn, char1, "vp-faction", TEST_GUILD_ID
    )

    assert success is True
    assert "VP assignment order submitted" in message
    assert "vp-faction" in message.lower() or "VP Faction" in message

    # Verify order was created as PENDING
    orders = await Order.fetch_by_character_and_type(
        db_conn, char1.id, TEST_GUILD_ID,
        OrderType.ASSIGN_VICTORY_POINTS.value, OrderStatus.PENDING.value
    )
    assert len(orders) == 1
    assert orders[0].order_data['target_faction_id'] == "vp-faction"

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_vp_order_supercedes_existing(db_conn, test_server):
    """Test that new VP order supercedes existing one."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Create second faction
    faction2 = Faction(
        faction_id="vp-faction-2", name="VP Faction Two",
        guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)

    # Submit first order
    success1, message1 = await submit_assign_victory_points_order(
        db_conn, char1, "vp-faction", TEST_GUILD_ID
    )
    assert success1 is True

    # Get the first order ID
    first_orders = await Order.fetch_by_character_and_type(
        db_conn, char1.id, TEST_GUILD_ID,
        OrderType.ASSIGN_VICTORY_POINTS.value, OrderStatus.PENDING.value
    )
    first_order_id = first_orders[0].order_id

    # Submit second order (should supercede)
    success2, message2 = await submit_assign_victory_points_order(
        db_conn, char1, "vp-faction-2", TEST_GUILD_ID
    )
    assert success2 is True
    assert "superceded" in message2

    # Verify first order is cancelled
    old_order = await Order.fetch_by_order_id(db_conn, first_order_id, TEST_GUILD_ID)
    assert old_order.status == OrderStatus.CANCELLED.value

    # Verify new order exists
    new_orders = await Order.fetch_by_character_and_type(
        db_conn, char1.id, TEST_GUILD_ID,
        OrderType.ASSIGN_VICTORY_POINTS.value, OrderStatus.PENDING.value
    )
    assert len(new_orders) == 1
    assert new_orders[0].order_data['target_faction_id'] == "vp-faction-2"

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_vp_order_faction_not_found(db_conn, test_server):
    """Test submitting order with non-existent faction."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    success, message = await submit_assign_victory_points_order(
        db_conn, char1, "nonexistent-faction", TEST_GUILD_ID
    )

    assert success is False
    assert "not found" in message.lower()

    await cleanup_vp_test_data(db_conn)


# ============ Order Execution Tests ============

@pytest.mark.asyncio
async def test_handle_vp_order_pending_to_ongoing(db_conn, test_server):
    """Test that first execution transitions PENDING to ONGOING."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Create PENDING order
    order = Order(
        order_id="VP-ORDER-001",
        order_type=OrderType.ASSIGN_VICTORY_POINTS.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=3,
        status=OrderStatus.PENDING.value,
        order_data={'target_faction_id': "vp-faction"},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_assign_victory_points_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify order transitioned to ONGOING
    order = await Order.fetch_by_order_id(db_conn, "VP-ORDER-001", TEST_GUILD_ID)
    assert order.status == OrderStatus.ONGOING.value

    # Verify event generated
    assert len(events) == 1
    assert events[0].event_type == 'VP_ASSIGNMENT_STARTED'
    assert events[0].event_data['vps_controlled'] == 8  # char1 controls 5+3 VP

    # Verify affected_character_ids includes submitter and faction leader
    affected = events[0].event_data['affected_character_ids']
    assert char1.id in affected
    assert char2.id in affected  # faction leader

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_handle_vp_order_ongoing_persists(db_conn, test_server):
    """Test that ONGOING order persists on subsequent turns."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Create ONGOING order
    order = Order(
        order_id="VP-ORDER-002",
        order_type=OrderType.ASSIGN_VICTORY_POINTS.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=3,
        status=OrderStatus.ONGOING.value,
        order_data={'target_faction_id': "vp-faction"},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute on turn 7
    events = await handle_assign_victory_points_order(db_conn, order, TEST_GUILD_ID, 7)

    # Verify order still ONGOING
    order = await Order.fetch_by_order_id(db_conn, "VP-ORDER-002", TEST_GUILD_ID)
    assert order.status == OrderStatus.ONGOING.value

    # Verify VP_ASSIGNMENT_ACTIVE event
    assert len(events) == 1
    assert events[0].event_type == 'VP_ASSIGNMENT_ACTIVE'

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_handle_vp_order_faction_deleted_fails(db_conn, test_server):
    """Test that order fails if target faction is deleted."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Create ONGOING order
    order = Order(
        order_id="VP-ORDER-003",
        order_type=OrderType.ASSIGN_VICTORY_POINTS.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=3,
        status=OrderStatus.ONGOING.value,
        order_data={'target_faction_id': "vp-faction"},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Delete the faction
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)

    # Execute
    events = await handle_assign_victory_points_order(db_conn, order, TEST_GUILD_ID, 7)

    # Verify order failed
    order = await Order.fetch_by_order_id(db_conn, "VP-ORDER-003", TEST_GUILD_ID)
    assert order.status == OrderStatus.FAILED.value
    assert "faction" in order.result_data.get('error', '').lower()

    # Verify failure event
    assert len(events) == 1
    assert events[0].event_type == 'ORDER_FAILED'

    await cleanup_vp_test_data(db_conn)


# ============ Cancel Order Tests ============

@pytest.mark.asyncio
async def test_cancel_vp_order_before_minimum_commitment(db_conn, test_server):
    """Test that VP order cannot be cancelled before 3 turns."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Current turn is 5, order starts at turn 6
    # Create ONGOING order
    order = Order(
        order_id="VP-ORDER-004",
        order_type=OrderType.ASSIGN_VICTORY_POINTS.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=6,  # Order started turn 6
        phase=TurnPhase.BEGINNING.value,
        priority=3,
        status=OrderStatus.ONGOING.value,
        order_data={'target_faction_id': "vp-faction"},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Current turn is 5, order starts turn 6, so turns_active = 5-6 = -1
    # This means the order hasn't even started yet
    # Let's set current turn to 7 (turns_active = 7-6 = 1, less than 3)
    await db_conn.execute(
        "UPDATE WargameConfig SET current_turn = 7 WHERE guild_id = $1;",
        TEST_GUILD_ID
    )

    # Try to cancel
    success, message = await cancel_order(
        db_conn, "VP-ORDER-004", TEST_GUILD_ID, char1.id
    )

    assert success is False
    assert "minimum commitment" in message.lower() or "remaining" in message.lower()

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_cancel_vp_order_after_minimum_commitment(db_conn, test_server):
    """Test that VP order can be cancelled after 3 turns."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Create ONGOING order
    order = Order(
        order_id="VP-ORDER-005",
        order_type=OrderType.ASSIGN_VICTORY_POINTS.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=6,  # Order started turn 6
        phase=TurnPhase.BEGINNING.value,
        priority=3,
        status=OrderStatus.ONGOING.value,
        order_data={'target_faction_id': "vp-faction"},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Set current turn to 9 (turns_active = 9-6 = 3, meets minimum)
    await db_conn.execute(
        "UPDATE WargameConfig SET current_turn = 9 WHERE guild_id = $1;",
        TEST_GUILD_ID
    )

    # Try to cancel
    success, message = await cancel_order(
        db_conn, "VP-ORDER-005", TEST_GUILD_ID, char1.id
    )

    assert success is True
    assert "cancelled" in message.lower()

    # Verify order is cancelled
    order = await Order.fetch_by_order_id(db_conn, "VP-ORDER-005", TEST_GUILD_ID)
    assert order.status == OrderStatus.CANCELLED.value

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_cancel_pending_order_immediately(db_conn, test_server):
    """Test that PENDING orders can be cancelled immediately."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Create PENDING order
    order = Order(
        order_id="VP-ORDER-006",
        order_type=OrderType.ASSIGN_VICTORY_POINTS.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=3,
        status=OrderStatus.PENDING.value,
        order_data={'target_faction_id': "vp-faction"},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Cancel immediately
    success, message = await cancel_order(
        db_conn, "VP-ORDER-006", TEST_GUILD_ID, char1.id
    )

    assert success is True
    assert "cancelled" in message.lower()

    await cleanup_vp_test_data(db_conn)


# ============ View Handler Tests ============

@pytest.mark.asyncio
async def test_view_victory_points_personal(db_conn, test_server):
    """Test view_victory_points shows personal VPs correctly."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    success, message, data = await view_victory_points(
        db_conn, char1.user_id, TEST_GUILD_ID
    )

    assert success is True
    assert data['personal_vps'] == 8  # 5 + 3
    assert len(data['territories']) == 2
    assert data['faction'] is None  # char1 not in faction

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_view_victory_points_faction_member(db_conn, test_server):
    """Test view_victory_points shows faction VPs correctly."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    success, message, data = await view_victory_points(
        db_conn, char2.user_id, TEST_GUILD_ID
    )

    assert success is True
    assert data['personal_vps'] == 2  # char2 controls territory3
    assert data['faction'] is not None
    assert data['faction_total_vps'] == 2  # only char2 in faction

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_view_victory_points_assigned_to_faction(db_conn, test_server):
    """Test view_victory_points shows assigned VPs correctly."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Create ONGOING VP assignment from char1 to faction
    order = Order(
        order_id="VP-ORDER-VIEW",
        order_type=OrderType.ASSIGN_VICTORY_POINTS.value,
        unit_ids=[],
        character_id=char1.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=3,
        status=OrderStatus.ONGOING.value,
        order_data={'target_faction_id': "vp-faction"},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # View as faction member
    success, message, data = await view_victory_points(
        db_conn, char2.user_id, TEST_GUILD_ID
    )

    assert success is True
    assert len(data['assigned_to_faction']) == 1
    assigning_char, vps = data['assigned_to_faction'][0]
    assert assigning_char.id == char1.id
    assert vps == 8  # char1's VPs

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_view_victory_points_no_character(db_conn, test_server):
    """Test view_victory_points with no character assigned."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    success, message, data = await view_victory_points(
        db_conn, 999999999999999999, TEST_GUILD_ID  # Non-existent user
    )

    assert success is False
    assert "don't have a character" in message.lower()
    assert data is None

    await cleanup_vp_test_data(db_conn)


# ============ Character VP Tests ============

@pytest.mark.asyncio
async def test_character_vp_included_in_personal_total(db_conn, test_server):
    """Test that character.victory_points is included in personal VP total."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Set character VPs directly on char1
    await db_conn.execute(
        "UPDATE Character SET victory_points = 7 WHERE id = $1;",
        char1.id
    )

    success, message, data = await view_victory_points(
        db_conn, char1.user_id, TEST_GUILD_ID
    )

    assert success is True
    # char1 controls territories with 5+3=8 VPs, plus 7 character VPs = 15 total
    assert data['character_vps'] == 7
    assert data['territory_vps'] == 8
    assert data['personal_vps'] == 15

    await cleanup_vp_test_data(db_conn)


@pytest.mark.asyncio
async def test_character_vp_in_faction_total(db_conn, test_server):
    """Test that character.victory_points is included in faction VP total."""
    char1, char2, faction = await setup_vp_test_data(db_conn)

    # Set character VPs on char2 (who is in faction)
    await db_conn.execute(
        "UPDATE Character SET victory_points = 5 WHERE id = $1;",
        char2.id
    )

    success, message, data = await view_victory_points(
        db_conn, char2.user_id, TEST_GUILD_ID
    )

    assert success is True
    # char2 controls territory3 with 2 VPs, plus 5 character VPs = 7 total
    assert data['personal_vps'] == 7
    # Faction total should include char2's 7 VPs (territory + character)
    assert data['faction_total_vps'] == 7

    await cleanup_vp_test_data(db_conn)
