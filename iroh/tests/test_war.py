"""
Pytest tests for war functionality.
Tests verify war model, order submission, order execution, and handlers.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_war.py -v
"""
import pytest
from datetime import datetime
from db import (
    Character, Faction, FactionMember, WargameConfig, Order, Alliance, War, WarParticipant
)
from handlers.order_handlers import submit_declare_war_order
from handlers.faction_handlers import view_wars, edit_war, add_war_participant, remove_war_participant, delete_war
from orders.faction_orders import handle_declare_war_order
from order_types import OrderType, OrderStatus
from tests.conftest import TEST_GUILD_ID


# ============================================================================
# WAR MODEL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_war_insert(db_conn, test_server):
    """Test inserting a new war."""
    war = War(
        war_id="war-001",
        objective="Conquer the North",
        declared_turn=5,
        guild_id=TEST_GUILD_ID
    )
    await war.insert(db_conn)

    # Verify
    fetched = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)
    assert fetched is not None
    assert fetched.war_id == "war-001"
    assert fetched.objective == "Conquer the North"
    assert fetched.declared_turn == 5

    # Cleanup
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_war_fetch_by_objective(db_conn, test_server):
    """Test fetching war by objective (case-insensitive)."""
    war = War(
        war_id="war-002",
        objective="Defend the Kingdom",
        declared_turn=3,
        guild_id=TEST_GUILD_ID
    )
    await war.insert(db_conn)

    # Test case-insensitive match
    fetched = await War.fetch_by_objective(db_conn, "defend the kingdom", TEST_GUILD_ID)
    assert fetched is not None
    assert fetched.war_id == "war-002"

    # Test exact case match
    fetched2 = await War.fetch_by_objective(db_conn, "Defend the Kingdom", TEST_GUILD_ID)
    assert fetched2 is not None
    assert fetched2.war_id == "war-002"

    # Test non-matching
    fetched3 = await War.fetch_by_objective(db_conn, "Attack the Kingdom", TEST_GUILD_ID)
    assert fetched3 is None

    # Cleanup
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_war_fetch_all(db_conn, test_server):
    """Test fetching all wars."""
    war1 = War(war_id="war-001", objective="Obj 1", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war1.insert(db_conn)

    war2 = War(war_id="war-002", objective="Obj 2", declared_turn=2, guild_id=TEST_GUILD_ID)
    await war2.insert(db_conn)

    wars = await War.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(wars) == 2

    # Cleanup
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_war_delete(db_conn, test_server):
    """Test deleting a war."""
    war = War(war_id="war-del", objective="To be deleted", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.insert(db_conn)

    # Verify exists
    fetched = await War.fetch_by_id(db_conn, "war-del", TEST_GUILD_ID)
    assert fetched is not None

    # Delete
    deleted = await War.delete(db_conn, "war-del", TEST_GUILD_ID)
    assert deleted is True

    # Verify gone
    fetched = await War.fetch_by_id(db_conn, "war-del", TEST_GUILD_ID)
    assert fetched is None


# ============================================================================
# WAR PARTICIPANT MODEL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_war_participant_insert(db_conn, test_server):
    """Test inserting a war participant."""
    # Create faction
    leader = Character(
        identifier="leader1", name="Leader 1",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader1", TEST_GUILD_ID)

    faction = Faction(
        faction_id="faction-a", name="Faction A",
        leader_character_id=leader.id, guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "faction-a", TEST_GUILD_ID)

    # Create war
    war = War(war_id="war-001", objective="Test", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.insert(db_conn)
    war = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)

    # Add participant
    participant = WarParticipant(
        war_id=war.id,
        faction_id=faction.id,
        side="SIDE_A",
        joined_turn=1,
        is_original_declarer=True,
        guild_id=TEST_GUILD_ID
    )
    await participant.insert(db_conn)

    # Verify
    participants = await WarParticipant.fetch_by_war(db_conn, war.id, TEST_GUILD_ID)
    assert len(participants) == 1
    assert participants[0].side == "SIDE_A"
    assert participants[0].is_original_declarer is True

    # Cleanup
    await db_conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_war_participant_fetch_by_faction(db_conn, test_server):
    """Test fetching all wars a faction is in."""
    # Create faction
    leader = Character(
        identifier="leader1", name="Leader 1",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader1", TEST_GUILD_ID)

    faction = Faction(
        faction_id="faction-a", name="Faction A",
        leader_character_id=leader.id, guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "faction-a", TEST_GUILD_ID)

    # Create two wars
    war1 = War(war_id="war-001", objective="War 1", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war1.insert(db_conn)
    war1 = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)

    war2 = War(war_id="war-002", objective="War 2", declared_turn=2, guild_id=TEST_GUILD_ID)
    await war2.insert(db_conn)
    war2 = await War.fetch_by_id(db_conn, "war-002", TEST_GUILD_ID)

    # Add faction to both wars
    p1 = WarParticipant(war_id=war1.id, faction_id=faction.id, side="SIDE_A", joined_turn=1, guild_id=TEST_GUILD_ID)
    await p1.insert(db_conn)
    p2 = WarParticipant(war_id=war2.id, faction_id=faction.id, side="SIDE_B", joined_turn=2, guild_id=TEST_GUILD_ID)
    await p2.insert(db_conn)

    # Fetch by faction
    faction_wars = await WarParticipant.fetch_by_faction(db_conn, faction.id, TEST_GUILD_ID)
    assert len(faction_wars) == 2

    # Cleanup
    await db_conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# ORDER SUBMISSION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_submit_declare_war_success(db_conn, test_server):
    """Test successful war declaration order submission by faction leader."""
    # Create two faction leaders
    leader1 = Character(
        identifier="leader1", name="Leader 1",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader1.upsert(db_conn)
    leader1 = await Character.fetch_by_identifier(db_conn, "leader1", TEST_GUILD_ID)

    leader2 = Character(
        identifier="leader2", name="Leader 2",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await leader2.upsert(db_conn)
    leader2 = await Character.fetch_by_identifier(db_conn, "leader2", TEST_GUILD_ID)

    # Create factions
    faction1 = Faction(
        faction_id="faction-a", name="Faction A",
        leader_character_id=leader1.id, guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-a", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="faction-b", name="Faction B",
        leader_character_id=leader2.id, guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)

    # Make leader1 a member of faction1
    member1 = FactionMember(
        faction_id=faction1.id, character_id=leader1.id,
        joined_turn=1, guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit order
    success, message = await submit_declare_war_order(
        db_conn, leader1, ["faction-b"], "Conquer the enemy", TEST_GUILD_ID
    )

    assert success is True
    assert "faction-b" in message.lower() or "Faction B" in message

    # Verify order was created
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    assert len(orders) == 1
    assert orders[0]['order_type'] == OrderType.DECLARE_WAR.value
    assert orders[0]['status'] == OrderStatus.PENDING.value

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_declare_war_not_leader(db_conn, test_server):
    """Test that non-leaders cannot submit war declaration orders."""
    # Create leader and regular member
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    member = Character(
        identifier="member", name="Member",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)
    member = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)

    # Create factions
    faction1 = Faction(
        faction_id="faction-a", name="Faction A",
        leader_character_id=leader.id, guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-a", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="faction-b", name="Faction B",
        leader_character_id=None, guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)

    # Make member a member of faction1 (not leader)
    membership = FactionMember(
        faction_id=faction1.id, character_id=member.id,
        joined_turn=1, guild_id=TEST_GUILD_ID
    )
    await membership.insert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to submit order as non-leader
    success, message = await submit_declare_war_order(
        db_conn, member, ["faction-b"], "Attack!", TEST_GUILD_ID
    )

    assert success is False
    assert "leader" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_declare_war_self_target(db_conn, test_server):
    """Test that you cannot declare war on your own faction."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="faction-a", name="Faction A",
        leader_character_id=leader.id, guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "faction-a", TEST_GUILD_ID)

    # Make leader a member
    membership = FactionMember(
        faction_id=faction.id, character_id=leader.id,
        joined_turn=1, guild_id=TEST_GUILD_ID
    )
    await membership.insert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to declare war on own faction
    success, message = await submit_declare_war_order(
        db_conn, leader, ["faction-a"], "Self-destruction", TEST_GUILD_ID
    )

    assert success is False
    assert "own faction" in message.lower() or "your own" in message.lower() or "yourself" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# ORDER EXECUTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_handle_declare_war_new_war(db_conn, test_server):
    """Test that declaring war creates a new war with participants."""
    # Setup two factions with leaders
    leader1 = Character(
        identifier="leader1", name="Leader 1",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader1.upsert(db_conn)
    leader1 = await Character.fetch_by_identifier(db_conn, "leader1", TEST_GUILD_ID)

    leader2 = Character(
        identifier="leader2", name="Leader 2",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await leader2.upsert(db_conn)
    leader2 = await Character.fetch_by_identifier(db_conn, "leader2", TEST_GUILD_ID)

    faction1 = Faction(
        faction_id="faction-a", name="Faction A",
        leader_character_id=leader1.id, guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-a", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="faction-b", name="Faction B",
        leader_character_id=leader2.id, guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "faction-b", TEST_GUILD_ID)

    # Create memberships
    member1 = FactionMember(faction_id=faction1.id, character_id=leader1.id, joined_turn=1, guild_id=TEST_GUILD_ID)
    await member1.insert(db_conn)
    member2 = FactionMember(faction_id=faction2.id, character_id=leader2.id, joined_turn=1, guild_id=TEST_GUILD_ID)
    await member2.insert(db_conn)

    # Create order (use internal IDs as stored by order_handlers)
    order = Order(
        order_id="ORD-WAR-001",
        order_type=OrderType.DECLARE_WAR.value,
        character_id=leader1.id,
        turn_number=6,
        phase="BEGINNING",
        priority=5,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_ids': [faction2.id],
            'submitting_faction_id': faction1.id,
            'objective': 'Conquer the enemy'
        },
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute order
    events = await handle_declare_war_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify war created
    wars = await War.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(wars) == 1
    assert wars[0].objective == "Conquer the enemy"

    # Verify participants
    participants = await WarParticipant.fetch_by_war(db_conn, wars[0].id, TEST_GUILD_ID)
    assert len(participants) == 2  # Both factions should be participants

    # Check sides
    side_a_factions = [p for p in participants if p.side == "SIDE_A"]
    side_b_factions = [p for p in participants if p.side == "SIDE_B"]
    assert len(side_a_factions) == 1  # Declaring faction
    assert len(side_b_factions) == 1  # Target faction

    # Verify event
    assert len(events) >= 1
    assert any(e.event_type == "WAR_DECLARED" for e in events)

    # Cleanup
    await db_conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_declare_war_join_existing(db_conn, test_server):
    """Test that declaring war with matching objective joins existing war."""
    # Setup three factions
    leaders = []
    factions = []
    for i in range(1, 4):
        leader = Character(
            identifier=f"leader{i}", name=f"Leader {i}",
            user_id=100000000000000000 + i, channel_id=900000000000000000 + i,
            guild_id=TEST_GUILD_ID
        )
        await leader.upsert(db_conn)
        leader = await Character.fetch_by_identifier(db_conn, f"leader{i}", TEST_GUILD_ID)
        leaders.append(leader)

        faction = Faction(
            faction_id=f"faction-{i}", name=f"Faction {i}",
            leader_character_id=leader.id, guild_id=TEST_GUILD_ID
        )
        await faction.upsert(db_conn)
        faction = await Faction.fetch_by_faction_id(db_conn, f"faction-{i}", TEST_GUILD_ID)
        factions.append(faction)

        member = FactionMember(faction_id=faction.id, character_id=leader.id, joined_turn=1, guild_id=TEST_GUILD_ID)
        await member.insert(db_conn)

    # Create existing war between faction-1 (SIDE_A) and faction-2 (SIDE_B)
    war = War(war_id="war-001", objective="Conquer the Land", declared_turn=5, guild_id=TEST_GUILD_ID)
    await war.insert(db_conn)
    war = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)

    p1 = WarParticipant(war_id=war.id, faction_id=factions[0].id, side="SIDE_A", joined_turn=5, is_original_declarer=True, guild_id=TEST_GUILD_ID)
    await p1.insert(db_conn)
    p2 = WarParticipant(war_id=war.id, faction_id=factions[1].id, side="SIDE_B", joined_turn=5, is_original_declarer=False, guild_id=TEST_GUILD_ID)
    await p2.insert(db_conn)

    # faction-3 declares war on faction-1 with same objective (should join SIDE_B)
    order = Order(
        order_id="ORD-WAR-002",
        order_type=OrderType.DECLARE_WAR.value,
        character_id=leaders[2].id,
        turn_number=6,
        phase="BEGINNING",
        priority=5,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_ids': [factions[0].id],  # Targeting faction on SIDE_A (internal ID)
            'submitting_faction_id': factions[2].id,  # faction-3 internal ID
            'objective': 'Conquer the Land'  # Same objective
        },
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute order
    events = await handle_declare_war_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify no new war created
    wars = await War.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(wars) == 1  # Still just one war

    # Verify faction-3 joined on SIDE_B (opposite of target faction-1's SIDE_A)
    participants = await WarParticipant.fetch_by_war(db_conn, war.id, TEST_GUILD_ID)
    assert len(participants) == 3

    faction3_participation = next((p for p in participants if p.faction_id == factions[2].id), None)
    assert faction3_participation is not None
    assert faction3_participation.side == "SIDE_B"

    # Verify event
    assert any(e.event_type == "WAR_JOINED" for e in events)

    # Cleanup
    await db_conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_declare_war_first_war_bonus(db_conn, test_server):
    """Test that first war declaration sets has_declared_war flag."""
    # Setup two factions
    leader1 = Character(
        identifier="leader1", name="Leader 1",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader1.upsert(db_conn)
    leader1 = await Character.fetch_by_identifier(db_conn, "leader1", TEST_GUILD_ID)

    leader2 = Character(
        identifier="leader2", name="Leader 2",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await leader2.upsert(db_conn)
    leader2 = await Character.fetch_by_identifier(db_conn, "leader2", TEST_GUILD_ID)

    faction1 = Faction(
        faction_id="faction-a", name="Faction A",
        leader_character_id=leader1.id,
        has_declared_war=False,  # First war!
        guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-a", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="faction-b", name="Faction B",
        leader_character_id=leader2.id, guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "faction-b", TEST_GUILD_ID)

    # Create memberships
    member1 = FactionMember(faction_id=faction1.id, character_id=leader1.id, joined_turn=1, guild_id=TEST_GUILD_ID)
    await member1.insert(db_conn)
    member2 = FactionMember(faction_id=faction2.id, character_id=leader2.id, joined_turn=1, guild_id=TEST_GUILD_ID)
    await member2.insert(db_conn)

    # Verify faction1 has not declared war yet
    assert faction1.has_declared_war is False

    # Create order (use internal IDs as stored by order_handlers)
    order = Order(
        order_id="ORD-WAR-001",
        order_type=OrderType.DECLARE_WAR.value,
        character_id=leader1.id,
        turn_number=6,
        phase="BEGINNING",
        priority=5,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_ids': [faction2.id],
            'submitting_faction_id': faction1.id,
            'objective': 'First war!'
        },
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute order
    events = await handle_declare_war_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify has_declared_war is now True
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-a", TEST_GUILD_ID)
    assert faction1.has_declared_war is True

    # Verify order result_data has first_war_bonus
    updated_order = await Order.fetch_by_order_id(db_conn, "ORD-WAR-001", TEST_GUILD_ID)
    assert updated_order.result_data is not None
    assert updated_order.result_data.get('first_war_bonus') is True

    # Cleanup
    await db_conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# HANDLER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_view_wars(db_conn, test_server):
    """Test viewing all wars."""
    # Setup factions
    leader1 = Character(identifier="leader1", name="Leader 1", user_id=1, channel_id=1, guild_id=TEST_GUILD_ID)
    await leader1.upsert(db_conn)
    leader1 = await Character.fetch_by_identifier(db_conn, "leader1", TEST_GUILD_ID)

    leader2 = Character(identifier="leader2", name="Leader 2", user_id=2, channel_id=2, guild_id=TEST_GUILD_ID)
    await leader2.upsert(db_conn)
    leader2 = await Character.fetch_by_identifier(db_conn, "leader2", TEST_GUILD_ID)

    faction1 = Faction(faction_id="f1", name="Faction 1", leader_character_id=leader1.id, guild_id=TEST_GUILD_ID)
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "f1", TEST_GUILD_ID)

    faction2 = Faction(faction_id="f2", name="Faction 2", leader_character_id=leader2.id, guild_id=TEST_GUILD_ID)
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "f2", TEST_GUILD_ID)

    # Create war with participants
    war = War(war_id="war-001", objective="Test War", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.insert(db_conn)
    war = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)

    p1 = WarParticipant(war_id=war.id, faction_id=faction1.id, side="SIDE_A", joined_turn=1, is_original_declarer=True, guild_id=TEST_GUILD_ID)
    await p1.insert(db_conn)
    p2 = WarParticipant(war_id=war.id, faction_id=faction2.id, side="SIDE_B", joined_turn=1, is_original_declarer=False, guild_id=TEST_GUILD_ID)
    await p2.insert(db_conn)

    # View wars
    success, message, wars = await view_wars(db_conn, TEST_GUILD_ID)

    assert success is True
    assert len(wars) == 1
    assert wars[0]['war_id'] == "war-001"
    assert wars[0]['objective'] == "Test War"
    assert len(wars[0]['side_a']) == 1
    assert len(wars[0]['side_b']) == 1

    # Cleanup
    await db_conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_war(db_conn, test_server):
    """Test admin edit_war changes objective."""
    war = War(war_id="war-001", objective="Old Objective", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.insert(db_conn)

    # Edit objective
    success, message = await edit_war(db_conn, "war-001", "New Objective", TEST_GUILD_ID)

    assert success is True

    # Verify changed
    updated = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)
    assert updated.objective == "New Objective"

    # Cleanup
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_add_war_participant(db_conn, test_server):
    """Test admin add_war_participant adds faction to war."""
    # Setup faction
    leader = Character(identifier="leader", name="Leader", user_id=1, channel_id=1, guild_id=TEST_GUILD_ID)
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    faction = Faction(faction_id="f1", name="Faction 1", leader_character_id=leader.id, guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "f1", TEST_GUILD_ID)

    # Create war
    war = War(war_id="war-001", objective="Test", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.insert(db_conn)

    # Add participant
    success, message = await add_war_participant(db_conn, "war-001", "f1", "SIDE_A", TEST_GUILD_ID)

    assert success is True

    # Verify added
    war = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)
    participants = await WarParticipant.fetch_by_war(db_conn, war.id, TEST_GUILD_ID)
    assert len(participants) == 1
    assert participants[0].side == "SIDE_A"

    # Cleanup
    await db_conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_remove_war_participant(db_conn, test_server):
    """Test admin remove_war_participant removes faction from war."""
    # Setup faction
    leader = Character(identifier="leader", name="Leader", user_id=1, channel_id=1, guild_id=TEST_GUILD_ID)
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    faction = Faction(faction_id="f1", name="Faction 1", leader_character_id=leader.id, guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "f1", TEST_GUILD_ID)

    # Create war with participant
    war = War(war_id="war-001", objective="Test", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.insert(db_conn)
    war = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)

    participant = WarParticipant(war_id=war.id, faction_id=faction.id, side="SIDE_A", joined_turn=1, guild_id=TEST_GUILD_ID)
    await participant.insert(db_conn)

    # Remove participant
    success, message = await remove_war_participant(db_conn, "war-001", "f1", TEST_GUILD_ID)

    assert success is True

    # Verify removed
    participants = await WarParticipant.fetch_by_war(db_conn, war.id, TEST_GUILD_ID)
    assert len(participants) == 0

    # Cleanup
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_delete_war(db_conn, test_server):
    """Test admin delete_war removes war and all participants."""
    # Setup faction
    leader = Character(identifier="leader", name="Leader", user_id=1, channel_id=1, guild_id=TEST_GUILD_ID)
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    faction = Faction(faction_id="f1", name="Faction 1", leader_character_id=leader.id, guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "f1", TEST_GUILD_ID)

    # Create war with participant
    war = War(war_id="war-001", objective="Test", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.insert(db_conn)
    war = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)

    participant = WarParticipant(war_id=war.id, faction_id=faction.id, side="SIDE_A", joined_turn=1, guild_id=TEST_GUILD_ID)
    await participant.insert(db_conn)

    # Delete war
    success, message = await delete_war(db_conn, "war-001", TEST_GUILD_ID)

    assert success is True

    # Verify war deleted
    deleted_war = await War.fetch_by_id(db_conn, "war-001", TEST_GUILD_ID)
    assert deleted_war is None

    # Verify participants also deleted (cascade)
    all_participants = await db_conn.fetch("SELECT * FROM WarParticipant WHERE guild_id = $1;", TEST_GUILD_ID)
    assert len(all_participants) == 0

    # Cleanup
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
