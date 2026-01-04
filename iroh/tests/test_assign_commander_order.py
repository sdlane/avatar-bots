"""
Pytest tests for ASSIGN_COMMANDER order handlers.
Tests verify commander assignment order processing.

Run with: pytest tests/test_assign_commander_order.py -v
"""
import pytest
from orders.unit_orders import handle_assign_commander_order
from handlers.order_handlers import submit_assign_commander_order
from db import Character, Faction, FactionMember, Unit, UnitType, Territory, WargameConfig, Order
from order_types import OrderType, OrderStatus, TurnPhase
from tests.conftest import TEST_GUILD_ID
from datetime import datetime


async def setup_basic_test_data(db_conn):
    """Helper to set up basic test data for commander assignment tests."""
    # Create owner character
    owner = Character(
        identifier="owner-char", name="Owner Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "owner-char", TEST_GUILD_ID)

    # Create new commander character
    new_commander = Character(
        identifier="new-commander", name="New Commander",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await new_commander.upsert(db_conn)
    new_commander = await Character.fetch_by_identifier(db_conn, "new-commander", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=owner.id, guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add both to faction
    owner_member = FactionMember(
        character_id=owner.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await owner_member.insert(db_conn)

    commander_member = FactionMember(
        character_id=new_commander.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await commander_member.insert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit
    unit = Unit(
        unit_id="UNIT-001", name="Test Unit",
        unit_type="infantry",
        owner_character_id=owner.id, faction_id=faction.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)

    # Create wargame config
    config = WargameConfig(
        guild_id=TEST_GUILD_ID,
        current_turn=5
    )
    await config.upsert(db_conn)

    return owner, new_commander, faction, unit


async def cleanup_test_data(db_conn):
    """Helper to clean up test data."""
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


# ============ Submission Handler Tests ============

@pytest.mark.asyncio
async def test_submit_assign_commander_order_success(db_conn, test_server):
    """Test successfully submitting a commander assignment order."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    success, message, needs_confirmation = await submit_assign_commander_order(
        db_conn, "UNIT-001", "new-commander", TEST_GUILD_ID, owner.id
    )

    assert success is True
    assert "Order submitted" in message
    assert needs_confirmation is False

    # Verify order was created
    orders = await Order.fetch_by_units(db_conn, [unit.id], [OrderStatus.PENDING.value], TEST_GUILD_ID)
    assert len(orders) == 1
    assert orders[0].order_type == OrderType.ASSIGN_COMMANDER.value

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_commander_order_not_owner(db_conn, test_server):
    """Test that non-owner cannot submit commander assignment order."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Try to submit as new_commander (not owner)
    success, message, needs_confirmation = await submit_assign_commander_order(
        db_conn, "UNIT-001", "new-commander", TEST_GUILD_ID, new_commander.id
    )

    assert success is False
    assert "owner" in message.lower()
    assert needs_confirmation is False

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_commander_order_unit_not_found(db_conn, test_server):
    """Test submitting order for non-existent unit."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    success, message, needs_confirmation = await submit_assign_commander_order(
        db_conn, "NONEXISTENT-UNIT", "new-commander", TEST_GUILD_ID, owner.id
    )

    assert success is False
    assert "not found" in message.lower()
    assert needs_confirmation is False

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_commander_order_commander_not_found(db_conn, test_server):
    """Test submitting order with non-existent commander."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    success, message, needs_confirmation = await submit_assign_commander_order(
        db_conn, "UNIT-001", "nonexistent-commander", TEST_GUILD_ID, owner.id
    )

    assert success is False
    assert "not found" in message.lower()
    assert needs_confirmation is False

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_commander_order_same_commander(db_conn, test_server):
    """Test that assigning same commander is rejected."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # First, set commander
    unit.commander_character_id = new_commander.id
    await unit.upsert(db_conn)

    # Try to assign same commander again
    success, message, needs_confirmation = await submit_assign_commander_order(
        db_conn, "UNIT-001", "new-commander", TEST_GUILD_ID, owner.id
    )

    assert success is False
    assert "already" in message.lower()
    assert needs_confirmation is False

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_commander_order_wrong_faction_needs_confirm(db_conn, test_server):
    """Test that faction mismatch returns needs_confirmation=True."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Remove new_commander from faction
    await db_conn.execute(
        "DELETE FROM FactionMember WHERE character_id = $1 AND guild_id = $2;",
        new_commander.id, TEST_GUILD_ID
    )

    success, message, needs_confirmation = await submit_assign_commander_order(
        db_conn, "UNIT-001", "new-commander", TEST_GUILD_ID, owner.id
    )

    assert success is False
    assert needs_confirmation is True
    assert "Warning" in message

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_commander_order_wrong_faction_confirmed(db_conn, test_server):
    """Test that faction mismatch proceeds when confirmed=True."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Remove new_commander from faction
    await db_conn.execute(
        "DELETE FROM FactionMember WHERE character_id = $1 AND guild_id = $2;",
        new_commander.id, TEST_GUILD_ID
    )

    success, message, needs_confirmation = await submit_assign_commander_order(
        db_conn, "UNIT-001", "new-commander", TEST_GUILD_ID, owner.id, confirmed=True
    )

    assert success is True
    assert "Order submitted" in message
    assert needs_confirmation is False

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_commander_order_cooldown_active(db_conn, test_server):
    """Test that 2-turn cooldown is enforced."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Set commander_assigned_turn to current turn (5) - should block
    unit.commander_assigned_turn = 5
    await unit.upsert(db_conn)

    success, message, needs_confirmation = await submit_assign_commander_order(
        db_conn, "UNIT-001", "new-commander", TEST_GUILD_ID, owner.id
    )

    assert success is False
    assert "turn" in message.lower()
    assert needs_confirmation is False

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_submit_assign_commander_order_cooldown_expired(db_conn, test_server):
    """Test that assignment is allowed after cooldown expires."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Set commander_assigned_turn to 2 turns ago (current is 5, so 3 works)
    unit.commander_assigned_turn = 3
    await unit.upsert(db_conn)

    success, message, needs_confirmation = await submit_assign_commander_order(
        db_conn, "UNIT-001", "new-commander", TEST_GUILD_ID, owner.id
    )

    assert success is True
    assert "Order submitted" in message
    assert needs_confirmation is False

    await cleanup_test_data(db_conn)


# ============ Order Handler Tests ============

@pytest.mark.asyncio
async def test_handle_assign_commander_order_success(db_conn, test_server):
    """Test successfully executing a commander assignment order."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Create order
    order = Order(
        order_id="ORDER-001",
        order_type=OrderType.ASSIGN_COMMANDER.value,
        unit_ids=[unit.id],
        character_id=owner.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=2,
        status=OrderStatus.PENDING.value,
        order_data={
            'unit_id': "UNIT-001",
            'new_commander_id': new_commander.id,
            'new_commander_name': new_commander.name
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_assign_commander_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify order status
    order = await Order.fetch_by_order_id(db_conn, "ORDER-001", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value

    # Verify unit updated
    unit = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert unit.commander_character_id == new_commander.id
    assert unit.commander_assigned_turn == 6

    # Verify event generated
    assert len(events) == 1
    assert events[0].event_type == 'COMMANDER_ASSIGNED'
    assert owner.id in events[0].event_data['affected_character_ids']
    assert new_commander.id in events[0].event_data['affected_character_ids']

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_handle_assign_commander_order_notifies_all_parties(db_conn, test_server):
    """Test that owner, new commander, and old commander are all notified."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Create old commander character
    old_commander = Character(
        identifier="old-commander", name="Old Commander",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await old_commander.upsert(db_conn)
    old_commander = await Character.fetch_by_identifier(db_conn, "old-commander", TEST_GUILD_ID)

    # Add old commander to faction
    old_commander_member = FactionMember(
        character_id=old_commander.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await old_commander_member.insert(db_conn)

    # Set unit's current commander to old_commander
    unit.commander_character_id = old_commander.id
    await unit.upsert(db_conn)

    # Create order
    order = Order(
        order_id="ORDER-002",
        order_type=OrderType.ASSIGN_COMMANDER.value,
        unit_ids=[unit.id],
        character_id=owner.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=2,
        status=OrderStatus.PENDING.value,
        order_data={
            'unit_id': "UNIT-001",
            'new_commander_id': new_commander.id,
            'new_commander_name': new_commander.name
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_assign_commander_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify all three are in affected_character_ids
    affected = events[0].event_data['affected_character_ids']
    assert owner.id in affected
    assert new_commander.id in affected
    assert old_commander.id in affected

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_handle_assign_commander_order_owner_as_commander(db_conn, test_server):
    """Test that owner can assign themselves as commander."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Create order to assign owner as commander
    order = Order(
        order_id="ORDER-003",
        order_type=OrderType.ASSIGN_COMMANDER.value,
        unit_ids=[unit.id],
        character_id=owner.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=2,
        status=OrderStatus.PENDING.value,
        order_data={
            'unit_id': "UNIT-001",
            'new_commander_id': owner.id,
            'new_commander_name': owner.name
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_assign_commander_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify order succeeded
    order = await Order.fetch_by_order_id(db_conn, "ORDER-003", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value

    # Verify unit updated
    unit = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert unit.commander_character_id == owner.id

    # Verify owner appears only once in affected_character_ids
    affected = events[0].event_data['affected_character_ids']
    assert affected.count(owner.id) == 1

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_handle_assign_commander_order_unit_no_faction(db_conn, test_server):
    """Test that units without faction can have any commander assigned."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Remove unit from faction
    unit.faction_id = None
    await unit.upsert(db_conn)

    # Remove owner and commander from factions
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)

    # Create order
    order = Order(
        order_id="ORDER-004",
        order_type=OrderType.ASSIGN_COMMANDER.value,
        unit_ids=[unit.id],
        character_id=owner.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=2,
        status=OrderStatus.PENDING.value,
        order_data={
            'unit_id': "UNIT-001",
            'new_commander_id': new_commander.id,
            'new_commander_name': new_commander.name
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute - should succeed since both have no faction (None == None)
    events = await handle_assign_commander_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify order succeeded
    order = await Order.fetch_by_order_id(db_conn, "ORDER-004", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_handle_assign_commander_order_faction_diverged(db_conn, test_server):
    """Test that order fails if owner and commander are no longer in same faction."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Create order
    order = Order(
        order_id="ORDER-005",
        order_type=OrderType.ASSIGN_COMMANDER.value,
        unit_ids=[unit.id],
        character_id=owner.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=2,
        status=OrderStatus.PENDING.value,
        order_data={
            'unit_id': "UNIT-001",
            'new_commander_id': new_commander.id,
            'new_commander_name': new_commander.name
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Now remove new_commander from faction (simulating faction change during BEGINNING phase)
    await db_conn.execute(
        "DELETE FROM FactionMember WHERE character_id = $1 AND guild_id = $2;",
        new_commander.id, TEST_GUILD_ID
    )

    # Execute - should fail
    events = await handle_assign_commander_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify order failed
    order = await Order.fetch_by_order_id(db_conn, "ORDER-005", TEST_GUILD_ID)
    assert order.status == OrderStatus.FAILED.value
    assert "faction" in order.result_data.get('error', '').lower()

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_handle_assign_commander_order_faction_changed_together(db_conn, test_server):
    """Test that order succeeds if both owner and commander changed to same faction."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Create a second faction
    faction2 = Faction(
        faction_id="faction-2", name="Faction Two",
        guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "faction-2", TEST_GUILD_ID)

    # Create order
    order = Order(
        order_id="ORDER-006",
        order_type=OrderType.ASSIGN_COMMANDER.value,
        unit_ids=[unit.id],
        character_id=owner.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=2,
        status=OrderStatus.PENDING.value,
        order_data={
            'unit_id': "UNIT-001",
            'new_commander_id': new_commander.id,
            'new_commander_name': new_commander.name
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Move both to faction2 (simulating faction change during BEGINNING phase)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    owner_member = FactionMember(
        character_id=owner.id, faction_id=faction2.id,
        joined_turn=6, guild_id=TEST_GUILD_ID
    )
    await owner_member.insert(db_conn)
    commander_member = FactionMember(
        character_id=new_commander.id, faction_id=faction2.id,
        joined_turn=6, guild_id=TEST_GUILD_ID
    )
    await commander_member.insert(db_conn)

    # Execute - should succeed since they're both in the same new faction
    events = await handle_assign_commander_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify order succeeded
    order = await Order.fetch_by_order_id(db_conn, "ORDER-006", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_handle_assign_commander_order_failure_notifies_recipient(db_conn, test_server):
    """Test that failure events include new commander info and notify the recipient."""
    owner, new_commander, faction, unit = await setup_basic_test_data(db_conn)

    # Create order
    order = Order(
        order_id="ORDER-007",
        order_type=OrderType.ASSIGN_COMMANDER.value,
        unit_ids=[unit.id],
        character_id=owner.id,
        turn_number=6,
        phase=TurnPhase.BEGINNING.value,
        priority=2,
        status=OrderStatus.PENDING.value,
        order_data={
            'unit_id': "UNIT-001",
            'new_commander_id': new_commander.id,
            'new_commander_name': new_commander.name
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Remove new_commander from faction to cause failure
    await db_conn.execute(
        "DELETE FROM FactionMember WHERE character_id = $1 AND guild_id = $2;",
        new_commander.id, TEST_GUILD_ID
    )

    # Execute - should fail
    events = await handle_assign_commander_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify failure event contains recipient info
    assert len(events) == 1
    assert events[0].event_type == 'ORDER_FAILED'
    event_data = events[0].event_data

    # Check that unit and commander info is in event_data
    assert event_data.get('unit_id') == "UNIT-001"
    assert event_data.get('unit_name') is not None
    assert event_data.get('new_commander_id') == new_commander.id
    assert event_data.get('new_commander_name') == new_commander.name

    # Check that both owner AND new commander are notified
    affected = event_data.get('affected_character_ids', [])
    assert owner.id in affected
    assert new_commander.id in affected

    await cleanup_test_data(db_conn)


@pytest.mark.asyncio
async def test_order_failed_event_formatter_assign_commander(db_conn, test_server):
    """Test that ORDER_FAILED event formatter shows context for ASSIGN_COMMANDER."""
    from event_logging.faction_events import order_failed_character_line, order_failed_gm_line

    event_data = {
        'order_type': 'ASSIGN_COMMANDER',
        'order_id': 'ORDER-TEST',
        'error': 'Owner and new commander are no longer in the same faction',
        'unit_id': 'UNIT-001',
        'unit_name': 'Test Unit',
        'new_commander_id': 123,
        'new_commander_name': 'Bob Smith',
        'affected_character_ids': [1, 123]
    }

    # Test character line
    char_line = order_failed_character_line(event_data)
    assert 'Bob Smith' in char_line
    assert 'Test Unit' in char_line
    assert 'faction' in char_line.lower()

    # Test GM line
    gm_line = order_failed_gm_line(event_data)
    assert 'UNIT-001' in gm_line
    assert 'Bob Smith' in gm_line
    assert 'faction' in gm_line.lower()
