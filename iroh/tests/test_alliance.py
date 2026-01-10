"""
Pytest tests for alliance functionality.
Tests verify alliance model, order submission, order execution, and handlers.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_alliance.py -v
"""
import pytest
from datetime import datetime
from db import (
    Character, Faction, FactionMember, WargameConfig, Order, Alliance
)
from handlers.order_handlers import submit_make_alliance_order
from handlers.alliance_handlers import view_alliances, add_alliance, edit_alliance, delete_alliance
from orders.alliance_orders import handle_make_alliance_order
from order_types import OrderType, OrderStatus
from tests.conftest import TEST_GUILD_ID


# ============================================================================
# ALLIANCE MODEL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_alliance_insert(db_conn, test_server):
    """Test inserting a new alliance."""
    # Create two factions
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

    # Insert alliance (canonical ordering)
    alliance = Alliance(
        faction_a_id=min(faction1.id, faction2.id),
        faction_b_id=max(faction1.id, faction2.id),
        status="PENDING_FACTION_A",
        initiated_by_faction_id=faction1.id,
        created_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await alliance.insert(db_conn)

    # Verify
    fetched = await Alliance.fetch_by_factions(db_conn, faction1.id, faction2.id, TEST_GUILD_ID)
    assert fetched is not None
    assert fetched.status == "PENDING_FACTION_A"
    assert fetched.initiated_by_faction_id == faction1.id

    # Cleanup
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_alliance_fetch_by_factions_both_orderings(db_conn, test_server):
    """Test that fetch_by_factions handles both orderings correctly."""
    # Create two factions
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

    # Insert alliance
    alliance = Alliance(
        faction_a_id=min(faction1.id, faction2.id),
        faction_b_id=max(faction1.id, faction2.id),
        status="ACTIVE",
        initiated_by_faction_id=faction1.id,
        guild_id=TEST_GUILD_ID
    )
    await alliance.insert(db_conn)

    # Test both orderings
    fetched1 = await Alliance.fetch_by_factions(db_conn, faction1.id, faction2.id, TEST_GUILD_ID)
    fetched2 = await Alliance.fetch_by_factions(db_conn, faction2.id, faction1.id, TEST_GUILD_ID)

    assert fetched1 is not None
    assert fetched2 is not None
    assert fetched1.id == fetched2.id

    # Cleanup
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_alliance_fetch_all_active(db_conn, test_server):
    """Test fetching only active alliances."""
    # Create three factions
    for i in range(1, 4):
        leader = Character(
            identifier=f"leader{i}", name=f"Leader {i}",
            user_id=100000000000000000 + i, channel_id=900000000000000000 + i,
            guild_id=TEST_GUILD_ID
        )
        await leader.upsert(db_conn)
        leader = await Character.fetch_by_identifier(db_conn, f"leader{i}", TEST_GUILD_ID)

        faction = Faction(
            faction_id=f"faction-{i}", name=f"Faction {i}",
            leader_character_id=leader.id, guild_id=TEST_GUILD_ID
        )
        await faction.upsert(db_conn)

    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-1", TEST_GUILD_ID)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "faction-2", TEST_GUILD_ID)
    faction3 = await Faction.fetch_by_faction_id(db_conn, "faction-3", TEST_GUILD_ID)

    # Create one active and one pending alliance
    active_alliance = Alliance(
        faction_a_id=min(faction1.id, faction2.id),
        faction_b_id=max(faction1.id, faction2.id),
        status="ACTIVE",
        initiated_by_faction_id=faction1.id,
        guild_id=TEST_GUILD_ID
    )
    await active_alliance.insert(db_conn)

    pending_alliance = Alliance(
        faction_a_id=min(faction1.id, faction3.id),
        faction_b_id=max(faction1.id, faction3.id),
        status="PENDING_FACTION_A",
        initiated_by_faction_id=faction3.id,
        guild_id=TEST_GUILD_ID
    )
    await pending_alliance.insert(db_conn)

    # Fetch only active
    active_alliances = await Alliance.fetch_all_active(db_conn, TEST_GUILD_ID)
    assert len(active_alliances) == 1
    assert active_alliances[0].status == "ACTIVE"

    # Cleanup
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# ORDER SUBMISSION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_submit_make_alliance_order_success(db_conn, test_server):
    """Test successful alliance order submission by faction leader."""
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
    success, message = await submit_make_alliance_order(
        db_conn, leader1, "faction-b", TEST_GUILD_ID
    )

    assert success is True
    assert "faction-b" in message.lower() or "Faction B" in message

    # Verify order was created
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    assert len(orders) == 1
    assert orders[0]['order_type'] == OrderType.MAKE_ALLIANCE.value
    assert orders[0]['status'] == OrderStatus.PENDING.value

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_make_alliance_order_not_leader(db_conn, test_server):
    """Test that non-leaders cannot submit alliance orders."""
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
    success, message = await submit_make_alliance_order(
        db_conn, member, "faction-b", TEST_GUILD_ID
    )

    assert success is False
    assert "leader" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_make_alliance_order_same_faction(db_conn, test_server):
    """Test that you cannot ally with your own faction."""
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

    # Try to ally with own faction
    success, message = await submit_make_alliance_order(
        db_conn, leader, "faction-a", TEST_GUILD_ID
    )

    assert success is False
    assert "own faction" in message.lower() or "your own" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# ORDER EXECUTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_handle_make_alliance_first_proposal(db_conn, test_server):
    """Test that first alliance proposal creates a pending alliance."""
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

    # Create order
    order = Order(
        order_id="ORD-0001",
        order_type=OrderType.MAKE_ALLIANCE.value,
        character_id=leader1.id,
        turn_number=6,
        phase="BEGINNING",
        priority=4,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': 'faction-b',
            'submitting_faction_id': 'faction-a'
        },
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute order
    events = await handle_make_alliance_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify pending alliance created
    alliance = await Alliance.fetch_by_factions(db_conn, faction1.id, faction2.id, TEST_GUILD_ID)
    assert alliance is not None
    assert alliance.status in ["PENDING_FACTION_A", "PENDING_FACTION_B"]

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == "ALLIANCE_PENDING"

    # Cleanup
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_handle_make_alliance_matching_proposal(db_conn, test_server):
    """Test that matching proposals activate the alliance."""
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

    # Create existing pending alliance (faction1 proposed)
    fa_id = min(faction1.id, faction2.id)
    fb_id = max(faction1.id, faction2.id)
    pending_status = "PENDING_FACTION_B" if faction1.id < faction2.id else "PENDING_FACTION_A"

    existing_alliance = Alliance(
        faction_a_id=fa_id,
        faction_b_id=fb_id,
        status=pending_status,
        initiated_by_faction_id=faction1.id,
        guild_id=TEST_GUILD_ID
    )
    await existing_alliance.insert(db_conn)

    # Create order from faction2 (the responding faction)
    order = Order(
        order_id="ORD-0002",
        order_type=OrderType.MAKE_ALLIANCE.value,
        character_id=leader2.id,
        turn_number=6,
        phase="BEGINNING",
        priority=4,
        status=OrderStatus.PENDING.value,
        order_data={
            'target_faction_id': 'faction-a',
            'submitting_faction_id': 'faction-b'
        },
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute order
    events = await handle_make_alliance_order(db_conn, order, TEST_GUILD_ID, 6)

    # Verify alliance is now active
    alliance = await Alliance.fetch_by_factions(db_conn, faction1.id, faction2.id, TEST_GUILD_ID)
    assert alliance is not None
    assert alliance.status == "ACTIVE"

    # Verify event
    assert len(events) == 1
    assert events[0].event_type == "ALLIANCE_FORMED"

    # Cleanup
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# HANDLER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_view_alliances_public(db_conn, test_server):
    """Test that public view only shows active alliances."""
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

    # Create one active alliance
    active = Alliance(
        faction_a_id=min(faction1.id, faction2.id),
        faction_b_id=max(faction1.id, faction2.id),
        status="ACTIVE",
        initiated_by_faction_id=faction1.id,
        guild_id=TEST_GUILD_ID
    )
    await active.insert(db_conn)

    # Public view (not admin, not faction leader)
    success, message, alliances = await view_alliances(db_conn, TEST_GUILD_ID, False, None)

    assert success is True
    assert len(alliances) == 1
    assert alliances[0]['status'] == 'ACTIVE'

    # Cleanup
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_add_alliance(db_conn, test_server):
    """Test admin add_alliance creates an active alliance."""
    # Setup factions
    leader1 = Character(identifier="leader1", name="Leader 1", user_id=1, channel_id=1, guild_id=TEST_GUILD_ID)
    await leader1.upsert(db_conn)
    leader1 = await Character.fetch_by_identifier(db_conn, "leader1", TEST_GUILD_ID)

    leader2 = Character(identifier="leader2", name="Leader 2", user_id=2, channel_id=2, guild_id=TEST_GUILD_ID)
    await leader2.upsert(db_conn)
    leader2 = await Character.fetch_by_identifier(db_conn, "leader2", TEST_GUILD_ID)

    faction1 = Faction(faction_id="f1", name="Faction 1", leader_character_id=leader1.id, guild_id=TEST_GUILD_ID)
    await faction1.upsert(db_conn)

    faction2 = Faction(faction_id="f2", name="Faction 2", leader_character_id=leader2.id, guild_id=TEST_GUILD_ID)
    await faction2.upsert(db_conn)

    # Add alliance via admin handler
    success, message = await add_alliance(db_conn, "f1", "f2", TEST_GUILD_ID)

    assert success is True

    # Verify alliance exists and is active
    faction1 = await Faction.fetch_by_faction_id(db_conn, "f1", TEST_GUILD_ID)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "f2", TEST_GUILD_ID)
    alliance = await Alliance.fetch_by_factions(db_conn, faction1.id, faction2.id, TEST_GUILD_ID)

    assert alliance is not None
    assert alliance.status == "ACTIVE"

    # Cleanup
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_alliance(db_conn, test_server):
    """Test admin edit_alliance changes status."""
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

    # Create pending alliance
    alliance = Alliance(
        faction_a_id=min(faction1.id, faction2.id),
        faction_b_id=max(faction1.id, faction2.id),
        status="PENDING_FACTION_A",
        initiated_by_faction_id=faction2.id,
        guild_id=TEST_GUILD_ID
    )
    await alliance.insert(db_conn)

    # Edit to active
    success, message = await edit_alliance(db_conn, "f1", "f2", "ACTIVE", TEST_GUILD_ID)

    assert success is True

    # Verify status changed
    updated = await Alliance.fetch_by_factions(db_conn, faction1.id, faction2.id, TEST_GUILD_ID)
    assert updated.status == "ACTIVE"

    # Cleanup
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
