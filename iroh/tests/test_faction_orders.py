"""
Pytest tests for faction order handlers.
Tests verify JOIN_FACTION, LEAVE_FACTION, and KICK_FROM_FACTION order processing.

Run with: pytest tests/test_faction_orders.py -v
"""
import pytest
from orders.faction_orders import (
    handle_leave_faction_order,
    handle_join_faction_order,
    handle_kick_from_faction_order
)
from db import Character, Faction, FactionMember, Unit, UnitType, Territory, WargameConfig, Order
from db.faction_join_request import FactionJoinRequest
from order_types import OrderStatus, TurnPhase
from tests.conftest import TEST_GUILD_ID
from datetime import datetime


@pytest.mark.asyncio
async def test_handle_leave_faction_order_success(db_conn, test_server):
    """Test successfully leaving a faction."""
    # Setup: Create character
    char = Character(
        identifier="leaving-char", name="Leaving Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "leaving-char", TEST_GUILD_ID)

    # Setup: Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Setup: Add character to faction
    faction_member = FactionMember(
        character_id=char.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await faction_member.insert(db_conn)

    # Setup: Create unit owned by character
    unit_type = UnitType(
        type_id="infantry", name="Infantry",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    territory = Territory(
        territory_id="1", terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    unit = Unit(
        unit_id="UNIT-001", name="Test Unit",
        unit_type="infantry",
        owner_character_id=char.id, faction_id=faction.id,
        current_territory_id="1", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # Setup: Create order
    order = Order(
        order_id="ORDER-001",
        order_type="LEAVE_FACTION",
        character_id=char.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_leave_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order status
    order = await Order.fetch_by_order_id(db_conn, "ORDER-001", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value
    assert order.result_data['faction_name'] == "Test Faction"

    # Verify member removed
    member = await FactionMember.fetch_by_character(db_conn, char.id, TEST_GUILD_ID)
    assert member is None

    # Verify unit faction_id cleared
    unit = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert unit.faction_id is None

    # Verify event generated
    assert len(events) == 1
    assert events[0].event_type == 'LEAVE_FACTION'
    assert events[0].entity_id == char.id
    assert char.id in events[0].event_data['affected_character_ids']

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_leave_faction_order_not_in_faction(db_conn, test_server):
    """Test leaving faction when character is not in a faction."""
    # Setup: Create character
    char = Character(
        identifier="solo-char", name="Solo Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "solo-char", TEST_GUILD_ID)

    # Setup: Create order
    order = Order(
        order_id="ORDER-003",
        order_type="LEAVE_FACTION",
        character_id=char.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_leave_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order failed
    order = await Order.fetch_by_order_id(db_conn, "ORDER-003", TEST_GUILD_ID)
    assert order.status == OrderStatus.FAILED.value
    assert 'not in' in order.result_data['error'].lower()

    # Verify failure event
    assert len(events) == 1
    assert events[0].event_type == 'ORDER_FAILED'

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_leave_faction_order_notifies_all_members(db_conn, test_server):
    """Test that leaving faction notifies all remaining members."""
    # Setup: Create characters
    char1 = Character(
        identifier="leaving-char", name="Leaving Character",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "leaving-char", TEST_GUILD_ID)

    char2 = Character(
        identifier="staying-char", name="Staying Character",
        user_id=100000000000000004, channel_id=900000000000000004,
        guild_id=TEST_GUILD_ID
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "staying-char", TEST_GUILD_ID)

    # Setup: Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Setup: Add both characters to faction
    member1 = FactionMember(
        character_id=char1.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)

    member2 = FactionMember(
        character_id=char2.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member2.insert(db_conn)

    # Setup: Create order
    order = Order(
        order_id="ORDER-004",
        order_type="LEAVE_FACTION",
        character_id=char1.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_leave_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify both characters in affected_character_ids
    assert len(events) == 1
    affected_ids = events[0].event_data['affected_character_ids']
    assert char1.id in affected_ids
    assert char2.id in affected_ids

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_join_faction_order_completed_immediately(db_conn, test_server):
    """Test joining faction when matching request exists."""
    # Setup: Create character
    char = Character(
        identifier="joining-char", name="Joining Character",
        user_id=100000000000000005, channel_id=900000000000000005,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "joining-char", TEST_GUILD_ID)

    # Setup: Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Setup: Create matching request from leader
    join_request = FactionJoinRequest(
        character_id=char.id,
        faction_id=faction.id,
        submitted_by='leader',
        guild_id=TEST_GUILD_ID
    )
    await join_request.insert(db_conn)

    # Setup: Create order from character
    order = Order(
        order_id="ORDER-005",
        order_type="JOIN_FACTION",
        character_id=char.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': 'test-faction',
            'submitted_by': 'character'
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_join_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order success
    order = await Order.fetch_by_order_id(db_conn, "ORDER-005", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value
    assert order.result_data['joined'] is True

    # Verify member added
    member = await FactionMember.fetch_by_character(db_conn, char.id, TEST_GUILD_ID)
    assert member is not None
    assert member.faction_id == faction.id

    # Verify request deleted
    remaining_requests = await db_conn.fetch(
        "SELECT * FROM FactionJoinRequest WHERE character_id = $1 AND guild_id = $2;",
        char.id, TEST_GUILD_ID
    )
    assert len(remaining_requests) == 0

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == 'JOIN_FACTION_COMPLETED'
    assert events[0].event_data['status'] == 'completed'

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_join_faction_order_pending(db_conn, test_server):
    """Test joining faction creates pending request when no match exists."""
    # Setup: Create character
    char = Character(
        identifier="joining-char", name="Joining Character",
        user_id=100000000000000006, channel_id=900000000000000006,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "joining-char", TEST_GUILD_ID)

    # Setup: Create faction with leader
    leader = Character(
        identifier="faction-leader", name="Faction Leader",
        user_id=100000000000000007, channel_id=900000000000000007,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "faction-leader", TEST_GUILD_ID)

    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID,
        leader_character_id=leader.id
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Setup: Create order from character (no matching request exists)
    order = Order(
        order_id="ORDER-006",
        order_type="JOIN_FACTION",
        character_id=char.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': 'test-faction',
            'submitted_by': 'character'
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_join_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order success with pending status
    order = await Order.fetch_by_order_id(db_conn, "ORDER-006", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value
    assert order.result_data['joined'] is False
    assert 'waiting_for' in order.result_data

    # Verify member NOT added
    member = await FactionMember.fetch_by_character(db_conn, char.id, TEST_GUILD_ID)
    assert member is None

    # Verify request created
    requests = await db_conn.fetch(
        "SELECT * FROM FactionJoinRequest WHERE character_id = $1 AND guild_id = $2;",
        char.id, TEST_GUILD_ID
    )
    assert len(requests) == 1

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == 'JOIN_FACTION_PENDING'
    assert events[0].event_data['status'] == 'pending'

    # Verify both character and leader are in affected_character_ids
    affected_ids = events[0].event_data['affected_character_ids']
    assert char.id in affected_ids
    assert leader.id in affected_ids

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionJoinRequest WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_join_faction_order_already_in_same_faction(db_conn, test_server):
    """Test joining the SAME faction again fails (multi-faction allows joining OTHER factions)."""
    # Setup: Create character
    char = Character(
        identifier="member-char", name="Member Character",
        user_id=100000000000000008, channel_id=900000000000000008,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "member-char", TEST_GUILD_ID)

    # Setup: Create leader for faction
    leader = Character(
        identifier="faction-leader", name="Faction Leader",
        user_id=100000000000000088, channel_id=900000000000000088,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "faction-leader", TEST_GUILD_ID)

    # Setup: Create faction and add character
    faction1 = Faction(
        faction_id="faction-1", name="Faction 1",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-1", TEST_GUILD_ID)

    # Add leader as member
    await FactionMember(
        character_id=leader.id, faction_id=faction1.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    ).insert(db_conn)

    # Add character as member
    member = FactionMember(
        character_id=char.id, faction_id=faction1.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # Setup: Create join requests for same faction (character wants to join again)
    await FactionJoinRequest(
        character_id=char.id, faction_id=faction1.id,
        submitted_by='character', guild_id=TEST_GUILD_ID
    ).insert(db_conn)
    await FactionJoinRequest(
        character_id=char.id, faction_id=faction1.id,
        submitted_by='leader', guild_id=TEST_GUILD_ID
    ).insert(db_conn)

    # Setup: Create order to join the SAME faction
    order = Order(
        order_id="ORDER-007",
        order_type="JOIN_FACTION",
        character_id=char.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': 'faction-1',  # Same faction they're already in
            'submitted_by': 'character'
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_join_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order failed - can't join same faction twice
    order = await Order.fetch_by_order_id(db_conn, "ORDER-007", TEST_GUILD_ID)
    assert order.status == OrderStatus.FAILED.value
    assert 'already in this faction' in order.result_data['error']

    # Verify failure event
    assert len(events) == 1
    assert events[0].event_type == 'ORDER_FAILED'

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionJoinRequest WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_join_faction_order_nonexistent_faction(db_conn, test_server):
    """Test joining nonexistent faction fails."""
    # Setup: Create character
    char = Character(
        identifier="joining-char", name="Joining Character",
        user_id=100000000000000009, channel_id=900000000000000009,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "joining-char", TEST_GUILD_ID)

    # Setup: Create order for nonexistent faction
    order = Order(
        order_id="ORDER-008",
        order_type="JOIN_FACTION",
        character_id=char.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': 'nonexistent-faction',
            'submitted_by': 'character'
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_join_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order failed
    order = await Order.fetch_by_order_id(db_conn, "ORDER-008", TEST_GUILD_ID)
    assert order.status == OrderStatus.FAILED.value
    assert 'Faction not found' in order.result_data['error']

    # Verify failure event
    assert len(events) == 1
    assert events[0].event_type == 'ORDER_FAILED'

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_join_faction_order_updates_units(db_conn, test_server):
    """Test that joining faction updates unit faction_id."""
    # Setup: Create character
    char = Character(
        identifier="joining-char", name="Joining Character",
        user_id=100000000000000010, channel_id=900000000000000010,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "joining-char", TEST_GUILD_ID)

    # Setup: Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Setup: Create unit owned by character
    unit_type = UnitType(
        type_id="infantry", name="Infantry",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    territory = Territory(
        territory_id="1", terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    unit = Unit(
        unit_id="UNIT-002", name="Test Unit",
        unit_type="infantry",
        owner_character_id=char.id, faction_id=None,
        current_territory_id="1", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # Setup: Create matching request from leader
    join_request = FactionJoinRequest(
        character_id=char.id,
        faction_id=faction.id,
        submitted_by='leader',
        guild_id=TEST_GUILD_ID
    )
    await join_request.insert(db_conn)

    # Setup: Create order from character
    order = Order(
        order_id="ORDER-009",
        order_type="JOIN_FACTION",
        character_id=char.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=1,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': 'test-faction',
            'submitted_by': 'character'
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_join_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify unit faction_id updated
    unit = await Unit.fetch_by_unit_id(db_conn, "UNIT-002", TEST_GUILD_ID)
    assert unit.faction_id == faction.id

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_kick_from_faction_order_success(db_conn, test_server):
    """Test successfully kicking a member from a faction."""
    # Setup: Create characters
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000011, channel_id=900000000000000011,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    member = Character(
        identifier="member", name="Member",
        user_id=100000000000000012, channel_id=900000000000000012,
        guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)
    member = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)

    # Setup: Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID,
        leader_character_id=leader.id
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Setup: Add both as members
    leader_member = FactionMember(
        character_id=leader.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await leader_member.insert(db_conn)

    member_member = FactionMember(
        character_id=member.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member_member.insert(db_conn)

    # Setup: Create unit owned by member
    unit_type = UnitType(
        type_id="infantry", name="Infantry",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    territory = Territory(
        territory_id="1", terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    unit = Unit(
        unit_id="UNIT-003", name="Test Unit",
        unit_type="infantry",
        owner_character_id=member.id, faction_id=faction.id,
        current_territory_id="1", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # Setup: Create order
    order = Order(
        order_id="ORDER-010",
        order_type="KICK_FROM_FACTION",
        character_id=leader.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_character_id': member.id,
            'faction_id': faction.id
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_kick_from_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order success
    order = await Order.fetch_by_order_id(db_conn, "ORDER-010", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value
    assert order.result_data['target_character_name'] == "Member"

    # Verify member removed
    member_check = await FactionMember.fetch_by_character(db_conn, member.id, TEST_GUILD_ID)
    assert member_check is None

    # Verify unit faction_id cleared
    unit = await Unit.fetch_by_unit_id(db_conn, "UNIT-003", TEST_GUILD_ID)
    assert unit.faction_id is None

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == 'KICK_FROM_FACTION'
    assert events[0].entity_id == member.id

    # Verify both characters in affected_character_ids
    affected_ids = events[0].event_data['affected_character_ids']
    assert member.id in affected_ids
    assert leader.id in affected_ids

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_kick_from_faction_order_target_not_found(db_conn, test_server):
    """Test kicking nonexistent character fails."""
    # Setup: Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000013, channel_id=900000000000000013,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Setup: Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Setup: Create order to kick nonexistent character
    order = Order(
        order_id="ORDER-011",
        order_type="KICK_FROM_FACTION",
        character_id=leader.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_character_id': 99999,  # Nonexistent
            'faction_id': faction.id
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_kick_from_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order failed
    order = await Order.fetch_by_order_id(db_conn, "ORDER-011", TEST_GUILD_ID)
    assert order.status == OrderStatus.FAILED.value
    assert 'Target character not found' in order.result_data['error']

    # Verify failure event
    assert len(events) == 1
    assert events[0].event_type == 'ORDER_FAILED'

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_kick_from_faction_order_target_not_in_faction(db_conn, test_server):
    """Test kicking character not in the faction fails."""
    # Setup: Create characters
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000014, channel_id=900000000000000014,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    outsider = Character(
        identifier="outsider", name="Outsider",
        user_id=100000000000000015, channel_id=900000000000000015,
        guild_id=TEST_GUILD_ID
    )
    await outsider.upsert(db_conn)
    outsider = await Character.fetch_by_identifier(db_conn, "outsider", TEST_GUILD_ID)

    # Setup: Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Setup: Create order to kick character not in faction
    order = Order(
        order_id="ORDER-012",
        order_type="KICK_FROM_FACTION",
        character_id=leader.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_character_id': outsider.id,
            'faction_id': faction.id
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_kick_from_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order failed
    order = await Order.fetch_by_order_id(db_conn, "ORDER-012", TEST_GUILD_ID)
    assert order.status == OrderStatus.FAILED.value
    assert 'no longer in the faction' in order.result_data['error']

    # Verify failure event
    assert len(events) == 1
    assert events[0].event_type == 'ORDER_FAILED'

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_kick_from_faction_order_nonexistent_faction(db_conn, test_server):
    """Test kicking from nonexistent faction fails."""
    # Setup: Create characters
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000016, channel_id=900000000000000016,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    member = Character(
        identifier="member", name="Member",
        user_id=100000000000000017, channel_id=900000000000000017,
        guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)
    member = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)

    # Setup: Create order for nonexistent faction
    order = Order(
        order_id="ORDER-013",
        order_type="KICK_FROM_FACTION",
        character_id=leader.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_character_id': member.id,
            'faction_id': 99999  # Nonexistent
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_kick_from_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify order failed
    order = await Order.fetch_by_order_id(db_conn, "ORDER-013", TEST_GUILD_ID)
    assert order.status == OrderStatus.FAILED.value
    assert 'Faction not found' in order.result_data['error']

    # Verify failure event
    assert len(events) == 1
    assert events[0].event_type == 'ORDER_FAILED'

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)


# =========================
# Multi-Faction Membership Tests
# =========================


@pytest.mark.asyncio
async def test_join_faction_order_sets_representation_on_first_join(db_conn, test_server):
    """Test that joining first faction auto-sets representation."""
    # Setup: Create character with no faction
    char = Character(
        identifier="new-member", name="New Member",
        user_id=100000000000000101, channel_id=900000000000000101,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "new-member", TEST_GUILD_ID)

    # Verify no representation
    assert char.represented_faction_id is None

    # Setup: Create faction with leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000102, channel_id=900000000000000102,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add leader as member
    leader_member = FactionMember(
        character_id=leader.id, faction_id=faction.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await leader_member.insert(db_conn)

    # Create join requests from both sides
    request1 = FactionJoinRequest(
        character_id=char.id, faction_id=faction.id,
        submitted_by='character', guild_id=TEST_GUILD_ID
    )
    await request1.insert(db_conn)
    request2 = FactionJoinRequest(
        character_id=char.id, faction_id=faction.id,
        submitted_by='leader', guild_id=TEST_GUILD_ID
    )
    await request2.insert(db_conn)

    # Create order
    order = Order(
        order_id="ORDER-101",
        order_type="JOIN_FACTION",
        character_id=char.id,
        turn_number=1,
        phase=TurnPhase.BEGINNING.value,
        priority=10,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': faction.faction_id,
            'submitted_by': 'character'
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_join_faction_order(db_conn, order, TEST_GUILD_ID, 1)

    # Verify success
    order = await Order.fetch_by_order_id(db_conn, "ORDER-101", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value

    # Verify representation was set
    char = await Character.fetch_by_identifier(db_conn, "new-member", TEST_GUILD_ID)
    assert char.represented_faction_id == faction.id

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionJoinRequest WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_join_second_faction_does_not_change_representation(db_conn, test_server):
    """Test that joining a second faction doesn't change representation."""
    # Setup: Create character
    char = Character(
        identifier="multi-member", name="Multi Member",
        user_id=100000000000000103, channel_id=900000000000000103,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "multi-member", TEST_GUILD_ID)

    # Setup: Create two factions with leaders
    leader1 = Character(
        identifier="leader1", name="Leader 1",
        user_id=100000000000000104, channel_id=900000000000000104,
        guild_id=TEST_GUILD_ID
    )
    await leader1.upsert(db_conn)
    leader1 = await Character.fetch_by_identifier(db_conn, "leader1", TEST_GUILD_ID)

    leader2 = Character(
        identifier="leader2", name="Leader 2",
        user_id=100000000000000105, channel_id=900000000000000105,
        guild_id=TEST_GUILD_ID
    )
    await leader2.upsert(db_conn)
    leader2 = await Character.fetch_by_identifier(db_conn, "leader2", TEST_GUILD_ID)

    faction1 = Faction(
        faction_id="faction-1", name="Faction One",
        leader_character_id=leader1.id,
        guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-1", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="faction-2", name="Faction Two",
        leader_character_id=leader2.id,
        guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "faction-2", TEST_GUILD_ID)

    # Add leaders as members
    await FactionMember(character_id=leader1.id, faction_id=faction1.id, joined_turn=0, guild_id=TEST_GUILD_ID).insert(db_conn)
    await FactionMember(character_id=leader2.id, faction_id=faction2.id, joined_turn=0, guild_id=TEST_GUILD_ID).insert(db_conn)

    # Character already in faction1 and representing it
    member1 = FactionMember(
        character_id=char.id, faction_id=faction1.id,
        joined_turn=1, guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)
    char.represented_faction_id = faction1.id
    await char.upsert(db_conn)

    # Create join requests for faction2
    await FactionJoinRequest(
        character_id=char.id, faction_id=faction2.id,
        submitted_by='character', guild_id=TEST_GUILD_ID
    ).insert(db_conn)
    await FactionJoinRequest(
        character_id=char.id, faction_id=faction2.id,
        submitted_by='leader', guild_id=TEST_GUILD_ID
    ).insert(db_conn)

    # Create order to join faction2
    order = Order(
        order_id="ORDER-102",
        order_type="JOIN_FACTION",
        character_id=char.id,
        turn_number=5,
        phase=TurnPhase.BEGINNING.value,
        priority=10,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': faction2.faction_id,
            'submitted_by': 'character'
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_join_faction_order(db_conn, order, TEST_GUILD_ID, 5)

    # Verify success
    order = await Order.fetch_by_order_id(db_conn, "ORDER-102", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value

    # Verify character has two memberships
    memberships = await FactionMember.fetch_all_by_character(db_conn, char.id, TEST_GUILD_ID)
    assert len(memberships) == 2

    # Verify representation still points to faction1
    char = await Character.fetch_by_identifier(db_conn, "multi-member", TEST_GUILD_ID)
    assert char.represented_faction_id == faction1.id

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionJoinRequest WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_leave_represented_faction_auto_reassigns(db_conn, test_server):
    """Test leaving represented faction auto-assigns to most recent remaining."""
    # Setup: Create character
    char = Character(
        identifier="leaving-member", name="Leaving Member",
        user_id=100000000000000106, channel_id=900000000000000106,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "leaving-member", TEST_GUILD_ID)

    # Setup: Create two factions
    faction1 = Faction(
        faction_id="faction-1", name="Faction One",
        guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-1", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="faction-2", name="Faction Two",
        guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "faction-2", TEST_GUILD_ID)

    # Add character to both factions - faction2 joined more recently
    await FactionMember(
        character_id=char.id, faction_id=faction1.id,
        joined_turn=1, guild_id=TEST_GUILD_ID
    ).insert(db_conn)
    await FactionMember(
        character_id=char.id, faction_id=faction2.id,
        joined_turn=5, guild_id=TEST_GUILD_ID
    ).insert(db_conn)

    # Character representing faction1
    char.represented_faction_id = faction1.id
    await char.upsert(db_conn)

    # Create order to leave faction1 (represented)
    order = Order(
        order_id="ORDER-103",
        order_type="LEAVE_FACTION",
        character_id=char.id,
        turn_number=10,
        phase=TurnPhase.BEGINNING.value,
        priority=0,
        status=OrderStatus.PENDING.value,
        order_data={'faction_id': faction1.id},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_leave_faction_order(db_conn, order, TEST_GUILD_ID, 10)

    # Verify success
    order = await Order.fetch_by_order_id(db_conn, "ORDER-103", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value
    assert order.result_data.get('new_represented_faction') == 'Faction Two'

    # Verify auto-reassigned to faction2 (most recent)
    char = await Character.fetch_by_identifier(db_conn, "leaving-member", TEST_GUILD_ID)
    assert char.represented_faction_id == faction2.id

    # Verify only one membership remains
    memberships = await FactionMember.fetch_all_by_character(db_conn, char.id, TEST_GUILD_ID)
    assert len(memberships) == 1
    assert memberships[0].faction_id == faction2.id

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_kick_from_represented_faction_resets_cooldown(db_conn, test_server):
    """Test that being kicked from represented faction resets representation cooldown."""
    # Setup: Create characters
    leader = Character(
        identifier="kicker", name="Kicker",
        user_id=100000000000000107, channel_id=900000000000000107,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "kicker", TEST_GUILD_ID)

    target = Character(
        identifier="kicked", name="Kicked",
        user_id=100000000000000108, channel_id=900000000000000108,
        guild_id=TEST_GUILD_ID,
        representation_changed_turn=5  # Had changed representation at turn 5
    )
    await target.upsert(db_conn)
    target = await Character.fetch_by_identifier(db_conn, "kicked", TEST_GUILD_ID)

    # Setup: Create two factions
    faction1 = Faction(
        faction_id="faction-1", name="Faction One",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-1", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="faction-2", name="Faction Two",
        guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "faction-2", TEST_GUILD_ID)

    # Add members
    await FactionMember(character_id=leader.id, faction_id=faction1.id, joined_turn=0, guild_id=TEST_GUILD_ID).insert(db_conn)
    await FactionMember(character_id=target.id, faction_id=faction1.id, joined_turn=1, guild_id=TEST_GUILD_ID).insert(db_conn)
    await FactionMember(character_id=target.id, faction_id=faction2.id, joined_turn=3, guild_id=TEST_GUILD_ID).insert(db_conn)

    # Target representing faction1
    target.represented_faction_id = faction1.id
    await target.upsert(db_conn)

    # Create kick order
    order = Order(
        order_id="ORDER-104",
        order_type="KICK_FROM_FACTION",
        character_id=leader.id,
        turn_number=10,
        phase=TurnPhase.BEGINNING.value,
        priority=5,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_character_id': target.id,
            'faction_id': faction1.id
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await handle_kick_from_faction_order(db_conn, order, TEST_GUILD_ID, 10)

    # Verify success
    order = await Order.fetch_by_order_id(db_conn, "ORDER-104", TEST_GUILD_ID)
    assert order.status == OrderStatus.SUCCESS.value

    # Verify cooldown was reset to current turn (10)
    target = await Character.fetch_by_identifier(db_conn, "kicked", TEST_GUILD_ID)
    assert target.representation_changed_turn == 10

    # Verify auto-reassigned to faction2
    assert target.represented_faction_id == faction2.id

    # Cleanup
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
