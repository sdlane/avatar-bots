"""
Pytest tests for order handlers.
Tests verify order submission, validation, cancellation, and path checking.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_order_handlers.py -v
"""
import pytest
from handlers.order_handlers import (
    submit_join_faction_order, submit_leave_faction_order, submit_transit_order,
    cancel_order, view_pending_orders, validate_path
)
from db import (
    Character, Faction, FactionMember, Unit, UnitType, Territory,
    TerritoryAdjacency, WargameConfig, Order
)
from order_types import OrderType, OrderStatus
from tests.conftest import TEST_GUILD_ID


@pytest.mark.asyncio
async def test_submit_join_faction_order_by_character(db_conn, test_server):
    """Test submitting a join faction order by the character themselves."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create character wanting to join
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create faction with leader
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit order as character
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, char.id
    )

    # Verify
    assert success is True

    # Verify order was created
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    assert len(orders) == 1
    assert orders[0]['order_type'] == OrderType.JOIN_FACTION.value
    assert orders[0]['status'] == OrderStatus.PENDING.value
    assert orders[0]['turn_number'] == 6  # Current turn + 1

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_join_faction_order_by_leader(db_conn, test_server):
    """Test submitting a join faction order by the faction leader."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create character wanting to join
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create faction with leader
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit order as leader
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, leader.id
    )

    # Verify
    assert success is True

    # Verify order was created
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    assert len(orders) == 1
    assert orders[0]['order_type'] == OrderType.JOIN_FACTION.value
    assert orders[0]['status'] == OrderStatus.PENDING.value

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_join_faction_order_both_parties(db_conn, test_server):
    """Test submitting join faction orders from both character and leader."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create character wanting to join
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create faction with leader
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit order as character first
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, char.id
    )
    assert success is True

    # Submit order as leader second
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, leader.id
    )
    assert success is True
    

    # Verify both orders were created
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    assert len(orders) == 2

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_join_faction_order_unauthorized(db_conn, test_server):
    """Test that unauthorized character cannot submit join faction order."""
    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create character wanting to join
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create unauthorized character
    other = Character(
        identifier="other", name="Other Character",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await other.upsert(db_conn)
    other = await Character.fetch_by_identifier(db_conn, "other", TEST_GUILD_ID)

    # Create faction with leader
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to submit order as unauthorized character
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, other.id
    )

    # Verify failure
    assert success is False
    assert "not authorized" in message.lower() or "must be" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_join_faction_order_already_member(db_conn, test_server):
    """Test submitting join faction order when already a member."""
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

    # Add character as member
    member = FactionMember(
        faction_id=faction.id, character_id=char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to submit order
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, char.id
    )

    # Verify failure
    assert success is False
    assert "already a member" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_leave_faction_order_success(db_conn, test_server):
    """Test submitting a leave faction order."""
    # Create characters
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)

    member = Character(
        identifier="member", name="Member",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)

    # Fetch to get IDs
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)
    member = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)

    # Create faction with leader
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id, guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Fetch faction to get ID
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add member to faction
    faction_member = FactionMember(
        faction_id=faction.id, character_id=member.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await faction_member.insert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit leave order
    success, message = await submit_leave_faction_order(
        db_conn, member, TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "will leave" in message.lower()

    # Verify order was created
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    assert len(orders) == 1
    assert orders[0]['order_type'] == OrderType.LEAVE_FACTION.value
    assert orders[0]['status'] == OrderStatus.PENDING.value

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_leave_faction_order_is_leader(db_conn, test_server):
    """Test that faction leader cannot leave without assigning new leader."""
    # Create character
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)

    # Fetch to get ID
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create faction with leader
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id, guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Fetch faction to get ID
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add leader as member
    faction_member = FactionMember(
        faction_id=faction.id, character_id=leader.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await faction_member.insert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to submit leave order
    success, message = await submit_leave_faction_order(
        db_conn, leader, TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "leader" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transit_order_single_unit(db_conn, test_server):
    """Test submitting a transit order for a single unit."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Fetch to get ID
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create territories
    territory1 = Territory(
        territory_id="101", name="Territory 101", terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id="102", name="Territory 102", terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # Create adjacency
    adjacency = TerritoryAdjacency(
        territory_a_id="101", territory_b_id="102", guild_id=TEST_GUILD_ID
    )
    await adjacency.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Create unit
    unit = Unit(
        unit_id="TEST-001", unit_type="infantry",
        owner_character_id=char.id, movement=2,
        organization=100, max_organization=100,
        current_territory_id="101", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit transit order
    success, message = await submit_transit_order(
        db_conn, ["TEST-001"], ["101", "102"], TEST_GUILD_ID, char.id
    )

    # Verify
    assert success is True
    assert "transit order submitted" in message.lower()
    assert "TEST-001" in message

    # Verify order was created
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    assert len(orders) == 1
    assert orders[0]['order_type'] == OrderType.TRANSIT.value
    assert orders[0]['status'] == OrderStatus.PENDING.value

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transit_order_unit_group(db_conn, test_server):
    """Test submitting a transit order for multiple units."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Fetch to get ID
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create territories
    for i in range(101, 105):
        territory = Territory(
            territory_id=str(i), name=f"Territory {i}", terrain_type="plains",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    # Create adjacencies (101-102-103-104)
    for i in range(101, 104):
        adjacency = TerritoryAdjacency(
            territory_a_id=str(i), territory_b_id=str(i+1), guild_id=TEST_GUILD_ID
        )
        await adjacency.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Create multiple units in same territory
    for i in range(1, 4):
        unit = Unit(
            unit_id=f"TEST-{i:03d}", unit_type="infantry",
            owner_character_id=char.id, movement=2,
            organization=100, max_organization=100,
            current_territory_id="101", is_naval=False,
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit transit order for group
    success, message = await submit_transit_order(
        db_conn, ["TEST-001", "TEST-002", "TEST-003"], ["101", "102", "103"], TEST_GUILD_ID, char.id
    )

    # Verify
    assert success is True
    assert "transit order submitted" in message.lower()
    assert "TEST-001" in message

    # Verify order was created with all unit IDs
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    assert len(orders) == 1
    assert len(orders[0]['unit_ids']) == 3

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transit_order_naval_unit_rejected(db_conn, test_server):
    """Test that naval units cannot use transit orders."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Fetch to get ID
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create territories
    territory1 = Territory(
        territory_id="101", name="Territory 101", terrain_type="coast",
        guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id="102", name="Territory 102", terrain_type="coast",
        guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # Create adjacency
    adjacency = TerritoryAdjacency(
        territory_a_id="101", territory_b_id="102", guild_id=TEST_GUILD_ID
    )
    await adjacency.upsert(db_conn)

    # Create naval unit type
    unit_type = UnitType(
        type_id="ship", name="Ship", nation="test",
        movement=3, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, is_naval=True,
        guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Create naval unit
    unit = Unit(
        unit_id="SHIP-001", unit_type="ship",
        owner_character_id=char.id, movement=3,
        organization=100, max_organization=100,
        current_territory_id="101", is_naval=True,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to submit transit order
    success, message = await submit_transit_order(
        db_conn, ["SHIP-001"], ["101", "102"], TEST_GUILD_ID, char.id
    )

    # Verify failure
    assert success is False
    assert "naval units cannot use transit" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_validate_path_success(db_conn, test_server):
    """Test path validation with valid adjacent territories."""
    # Create territories
    for i in range(101, 104):
        territory = Territory(
            territory_id=str(i), name=f"Territory {i}", terrain_type="plains",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    # Create adjacencies (101-102-103)
    for i in range(101, 103):
        adjacency = TerritoryAdjacency(
            territory_a_id=str(i), territory_b_id=str(i+1), guild_id=TEST_GUILD_ID
        )
        await adjacency.upsert(db_conn)

    # Validate path
    valid, error = await validate_path(db_conn, ["101", "102", "103"], TEST_GUILD_ID)

    # Verify
    assert valid is True
    assert error == ""

    # Cleanup
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_validate_path_non_adjacent(db_conn, test_server):
    """Test path validation fails for non-adjacent territories."""
    # Create territories
    for i in [101, 102, 104]:  # Note: 103 is missing
        territory = Territory(
            territory_id=str(i), name=f"Territory {i}", terrain_type="plains",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    # Create adjacency only for 101-102 (not 102-104)
    adjacency = TerritoryAdjacency(
        territory_a_id="101", territory_b_id="102", guild_id=TEST_GUILD_ID
    )
    await adjacency.upsert(db_conn)

    # Try to validate path with non-adjacent territories
    valid, error = await validate_path(db_conn, ["101", "102", "104"], TEST_GUILD_ID)

    # Verify failure
    assert valid is False
    assert "not adjacent" in error.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_cancel_order_success(db_conn, test_server):
    """Test cancelling a pending order."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Fetch to get ID
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit order
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, char.id
    )
    assert success is True

    # Get order ID
    orders = await db_conn.fetch('SELECT order_id FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    order_id = orders[0]['order_id']

    # Cancel order
    success, message = await cancel_order(db_conn, order_id, TEST_GUILD_ID, char.id)

    # Verify
    assert success is True
    assert "cancelled" in message.lower()

    # Verify order status changed
    order = await Order.fetch_by_order_id(db_conn, order_id, TEST_GUILD_ID)
    assert order.status == OrderStatus.CANCELLED.value

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_pending_orders(db_conn, test_server):
    """Test viewing pending orders for a character."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit order
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, char.id
    )
    assert success is True

    # View orders
    success, message, orders = await view_pending_orders(
        db_conn, "test-char", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert orders is not None
    assert len(orders) == 1
    assert orders[0]['order_type'] == OrderType.JOIN_FACTION.value
    assert orders[0]['status'] == OrderStatus.PENDING.value

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# ADDITIONAL EDGE CASE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_submit_transit_order_units_different_territories(db_conn, test_server):
    """Test that transit order fails when units are in different territories."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create territories
    for i in range(101, 104):
        territory = Territory(
            territory_id=str(i), name=f"Territory {i}", terrain_type="plains",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    # Create adjacencies
    for i in range(101, 103):
        adjacency = TerritoryAdjacency(
            territory_a_id=str(i), territory_b_id=str(i+1), guild_id=TEST_GUILD_ID
        )
        await adjacency.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Create units in different territories
    unit1 = Unit(
        unit_id="TEST-001", unit_type="infantry",
        owner_character_id=char.id, movement=2,
        organization=100, max_organization=100,
        current_territory_id="101", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit1.upsert(db_conn)

    unit2 = Unit(
        unit_id="TEST-002", unit_type="infantry",
        owner_character_id=char.id, movement=2,
        organization=100, max_organization=100,
        current_territory_id="102", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit2.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to submit transit order
    success, message = await submit_transit_order(
        db_conn, ["TEST-001", "TEST-002"], ["101", "102", "103"], TEST_GUILD_ID, char.id
    )

    # Verify failure
    assert success is False
    assert "same territory" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transit_order_path_wrong_start(db_conn, test_server):
    """Test that transit order fails when path doesn't start with current territory."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create territories
    for i in range(101, 104):
        territory = Territory(
            territory_id=str(i), name=f"Territory {i}", terrain_type="plains",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    # Create adjacencies
    for i in range(101, 103):
        adjacency = TerritoryAdjacency(
            territory_a_id=str(i), territory_b_id=str(i+1), guild_id=TEST_GUILD_ID
        )
        await adjacency.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Create unit in territory 101
    unit = Unit(
        unit_id="TEST-001", unit_type="infantry",
        owner_character_id=char.id, movement=2,
        organization=100, max_organization=100,
        current_territory_id="101", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to submit transit order with wrong starting territory
    success, message = await submit_transit_order(
        db_conn, ["TEST-001"], ["102", "103"], TEST_GUILD_ID, char.id
    )

    # Verify failure
    assert success is False
    assert "must start with" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transit_order_unauthorized_character(db_conn, test_server):
    """Test that character cannot order units they don't own/command."""
    # Create two characters
    owner = Character(
        identifier="owner", name="Owner",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "owner", TEST_GUILD_ID)

    other = Character(
        identifier="other", name="Other",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await other.upsert(db_conn)
    other = await Character.fetch_by_identifier(db_conn, "other", TEST_GUILD_ID)

    # Create territories
    for i in range(101, 103):
        territory = Territory(
            territory_id=str(i), name=f"Territory {i}", terrain_type="plains",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    # Create adjacency
    adjacency = TerritoryAdjacency(
        territory_a_id="101", territory_b_id="102", guild_id=TEST_GUILD_ID
    )
    await adjacency.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Create unit owned by owner
    unit = Unit(
        unit_id="TEST-001", unit_type="infantry",
        owner_character_id=owner.id, movement=2,
        organization=100, max_organization=100,
        current_territory_id="101", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to submit transit order as other character
    success, message = await submit_transit_order(
        db_conn, ["TEST-001"], ["101", "102"], TEST_GUILD_ID, other.id
    )

    # Verify failure
    assert success is False
    assert "not authorized" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_submit_transit_order_with_existing_order(db_conn, test_server):
    """Test that unit with pending order cannot receive another order."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create territories
    for i in range(101, 104):
        territory = Territory(
            territory_id=str(i), name=f"Territory {i}", terrain_type="plains",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    # Create adjacencies
    for i in range(101, 103):
        adjacency = TerritoryAdjacency(
            territory_a_id=str(i), territory_b_id=str(i+1), guild_id=TEST_GUILD_ID
        )
        await adjacency.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Create unit
    unit = Unit(
        unit_id="TEST-001", unit_type="infantry",
        owner_character_id=char.id, movement=2,
        organization=100, max_organization=100,
        current_territory_id="101", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit first transit order
    success, message = await submit_transit_order(
        db_conn, ["TEST-001"], ["101", "102"], TEST_GUILD_ID, char.id
    )
    assert success is True

    # Try to submit second transit order for same unit
    success, message = await submit_transit_order(
        db_conn, ["TEST-001"], ["101", "102", "103"], TEST_GUILD_ID, char.id
    )

    # Verify failure
    assert success is False
    assert "already have pending orders" in message.lower()

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_validate_path_empty(db_conn, test_server):
    """Test that empty path is invalid."""
    valid, error = await validate_path(db_conn, [], TEST_GUILD_ID)
    assert valid is False
    assert "empty" in error.lower()


@pytest.mark.asyncio
async def test_validate_path_nonexistent_territory(db_conn, test_server):
    """Test that path with non-existent territory is invalid."""
    # Create one territory
    territory = Territory(
        territory_id="101", name="Territory 101", terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Try to validate path with non-existent territory
    valid, error = await validate_path(db_conn, ["101", "999"], TEST_GUILD_ID)

    # Verify failure
    assert valid is False
    assert "not found" in error.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_validate_path_long(db_conn, test_server):
    """Test path validation with longer path (5 territories)."""
    # Create territories
    for i in range(101, 106):
        territory = Territory(
            territory_id=str(i), name=f"Territory {i}", terrain_type="plains",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    # Create adjacencies (101-102-103-104-105)
    for i in range(101, 105):
        adjacency = TerritoryAdjacency(
            territory_a_id=str(i), territory_b_id=str(i+1), guild_id=TEST_GUILD_ID
        )
        await adjacency.upsert(db_conn)

    # Validate path
    valid, error = await validate_path(db_conn, ["101", "102", "103", "104", "105"], TEST_GUILD_ID)

    # Verify success
    assert valid is True
    assert error == ""

    # Cleanup
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_cancel_order_nonexistent(db_conn, test_server):
    """Test cancelling a non-existent order."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Try to cancel non-existent order
    success, message = await cancel_order(db_conn, "ORD-9999", TEST_GUILD_ID, char.id)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_cancel_order_wrong_character(db_conn, test_server):
    """Test that character cannot cancel someone else's order."""
    # Create two characters
    char1 = Character(
        identifier="char1", name="Character 1",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "char1", TEST_GUILD_ID)

    char2 = Character(
        identifier="char2", name="Character 2",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "char2", TEST_GUILD_ID)

    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit order as char1
    success, message = await submit_join_faction_order(
        db_conn, "char1", "test-faction", TEST_GUILD_ID, char1.id
    )
    assert success is True

    # Get order ID
    orders = await db_conn.fetch('SELECT order_id FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    order_id = orders[0]['order_id']

    # Try to cancel as char2
    success, message = await cancel_order(db_conn, order_id, TEST_GUILD_ID, char2.id)

    # Verify failure
    assert success is False
    assert "does not belong to you" in message.lower()

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_cancel_order_ongoing_status(db_conn, test_server):
    """Test that ONGOING orders can be cancelled (unless they have minimum commitment)."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit order
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, char.id
    )
    assert success is True

    # Get order and manually change status to ONGOING
    orders = await db_conn.fetch('SELECT order_id FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    order_id = orders[0]['order_id']
    await db_conn.execute(
        'UPDATE WargameOrder SET status = $1 WHERE order_id = $2 AND guild_id = $3;',
        OrderStatus.ONGOING.value, order_id, TEST_GUILD_ID
    )

    # Try to cancel ONGOING order (JOIN_FACTION has no minimum commitment, so should succeed)
    success, message = await cancel_order(db_conn, order_id, TEST_GUILD_ID, char.id)

    # Verify success (ONGOING orders without minimum commitment can be cancelled)
    assert success is True
    assert "cancelled" in message.lower()

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_pending_orders_multiple_types(db_conn, test_server):
    """Test viewing pending orders when character has multiple order types."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create territories for transit order
    for i in range(101, 103):
        territory = Territory(
            territory_id=str(i), name=f"Territory {i}", terrain_type="plains",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    adjacency = TerritoryAdjacency(
        territory_a_id="101", territory_b_id="102", guild_id=TEST_GUILD_ID
    )
    await adjacency.upsert(db_conn)

    # Create unit type and unit
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    unit = Unit(
        unit_id="TEST-001", unit_type="infantry",
        owner_character_id=char.id, movement=2,
        organization=100, max_organization=100,
        current_territory_id="101", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit join faction order
    success, message = await submit_join_faction_order(
        db_conn, "test-char", "test-faction", TEST_GUILD_ID, char.id
    )
    assert success is True

    # Submit transit order
    success, message = await submit_transit_order(
        db_conn, ["TEST-001"], ["101", "102"], TEST_GUILD_ID, char.id
    )
    assert success is True

    # View orders
    success, message, orders = await view_pending_orders(
        db_conn, "test-char", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert len(orders) == 2
    order_types = [o['order_type'] for o in orders]
    assert OrderType.JOIN_FACTION.value in order_types
    assert OrderType.TRANSIT.value in order_types

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_pending_orders_no_orders(db_conn, test_server):
    """Test viewing pending orders when character has no orders."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # View orders
    success, message, orders = await view_pending_orders(
        db_conn, "test-char", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "no pending orders" in message.lower()
    assert orders == []


@pytest.mark.asyncio
async def test_submit_transit_order_path_too_short(db_conn, test_server):
    """Test that transit order fails with path less than 2 territories."""
    # Create character
    char = Character(
        identifier="test-char", name="Test Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    # Create territory
    territory = Territory(
        territory_id="101", name="Territory 101", terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Create unit
    unit = Unit(
        unit_id="TEST-001", unit_type="infantry",
        owner_character_id=char.id, movement=2,
        organization=100, max_organization=100,
        current_territory_id="101", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Try to submit transit order with path of length 1
    success, message = await submit_transit_order(
        db_conn, ["TEST-001"], ["101"], TEST_GUILD_ID, char.id
    )

    # Verify failure
    assert success is False
    assert "at least" in message.lower() and "destination" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)

@pytest.mark.asyncio
async def test_order_id_uniqueness(db_conn, test_server):
    """Test that order IDs are unique and sequentially generated."""
    # Create two characters
    char1 = Character(
        identifier="char1", name="Character 1",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "char1", TEST_GUILD_ID)

    char2 = Character(
        identifier="char2", name="Character 2",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "char2", TEST_GUILD_ID)

    # Create leader
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)
    leader = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        leader_character_id=leader.id,
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Create WargameConfig
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=5)
    await config.upsert(db_conn)

    # Submit multiple orders
    await submit_join_faction_order(db_conn, "char1", "test-faction", TEST_GUILD_ID, char1.id)
    await submit_join_faction_order(db_conn, "char2", "test-faction", TEST_GUILD_ID, char2.id)

    # Get order IDs
    orders = await db_conn.fetch(
        'SELECT order_id FROM WargameOrder WHERE guild_id = $1 ORDER BY id;',
        TEST_GUILD_ID
    )

    # Verify unique and sequential
    assert len(orders) == 2
    assert orders[0]['order_id'] == "ORD-0001"
    assert orders[1]['order_id'] == "ORD-0002"

    # Cleanup
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
