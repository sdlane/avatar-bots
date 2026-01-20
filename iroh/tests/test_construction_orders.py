"""
Tests for construction order submission and execution.
"""
import pytest
from datetime import datetime

from db import (
    Character, Faction, FactionMember, Territory, Building, BuildingType,
    Order, TurnLog, PlayerResources, FactionResources, FactionPermission
)
from handlers.order_handlers import submit_construction_order
from orders.construction_orders import handle_construction_order
from order_types import OrderType, OrderStatus, TurnPhase

TEST_GUILD_ID = 999999999999999999


@pytest.fixture
async def construction_setup(db_conn, test_server):
    """Set up test data for construction tests."""
    # Create characters
    char_leader = Character(
        identifier="const-leader", name="Construction Leader",
        user_id=100000000000000401, channel_id=900000000000000401,
        guild_id=TEST_GUILD_ID
    )
    await char_leader.upsert(db_conn)
    char_leader = await Character.fetch_by_identifier(db_conn, "const-leader", TEST_GUILD_ID)

    char_member = Character(
        identifier="const-member", name="Construction Member",
        user_id=100000000000000402, channel_id=900000000000000402,
        guild_id=TEST_GUILD_ID
    )
    await char_member.upsert(db_conn)
    char_member = await Character.fetch_by_identifier(db_conn, "const-member", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="const-faction",
        name="Construction Faction",
        leader_character_id=char_leader.id,
        nation="fire-nation",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "const-faction", TEST_GUILD_ID)

    # Add members
    member1 = FactionMember(
        character_id=char_leader.id,
        faction_id=faction.id,
        joined_turn=0,
        guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)

    member2 = FactionMember(
        character_id=char_member.id,
        faction_id=faction.id,
        joined_turn=0,
        guild_id=TEST_GUILD_ID
    )
    await member2.insert(db_conn)

    # Create territory
    territory = Territory(
        territory_id="const-territory-1",
        name="Construction Territory",
        terrain_type="plains",
        original_nation="fire-nation",
        controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building type
    building_type = BuildingType(
        type_id="const-barracks",
        name="Test Barracks",
        description="A test building",
        cost_ore=10,
        cost_lumber=10,
        cost_rations=5,
        upkeep_rations=2,
        guild_id=TEST_GUILD_ID
    )
    await building_type.upsert(db_conn)

    # Give leader resources
    resources = PlayerResources(
        character_id=char_leader.id,
        ore=100, lumber=100, coal=100, rations=100, cloth=100, platinum=100,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    yield {
        'leader': char_leader,
        'member': char_member,
        'faction': faction,
        'territory': territory,
        'building_type': building_type
    }

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


# =============================================================================
# Submission Tests
# =============================================================================


@pytest.mark.asyncio
async def test_submit_construction_order_personal_success(db_conn, construction_setup):
    """Test submitting a personal construction order."""
    setup = construction_setup

    success, message = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )

    assert success is True
    assert "Construction order submitted" in message
    assert "Test Barracks" in message


@pytest.mark.asyncio
async def test_submit_construction_order_faction_success(db_conn, construction_setup):
    """Test submitting a faction construction order with CONSTRUCTION permission."""
    setup = construction_setup

    # Grant CONSTRUCTION permission
    perm = FactionPermission(
        faction_id=setup['faction'].id,
        character_id=setup['leader'].id,
        permission_type="CONSTRUCTION",
        guild_id=TEST_GUILD_ID
    )
    await perm.upsert(db_conn)

    # Give faction resources
    faction_resources = FactionResources(
        faction_id=setup['faction'].id,
        ore=100, lumber=100, coal=100, rations=100, cloth=100, platinum=100,
        guild_id=TEST_GUILD_ID
    )
    await faction_resources.upsert(db_conn)

    success, message = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        faction_id="const-faction"
    )

    assert success is True
    assert "Construction order submitted" in message
    assert "Construction Faction" in message


@pytest.mark.asyncio
async def test_submit_construction_order_no_permission_fails(db_conn, construction_setup):
    """Test that faction construction fails without CONSTRUCTION permission."""
    setup = construction_setup

    success, message = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        faction_id="const-faction"
    )

    assert success is False
    assert "CONSTRUCTION permission" in message


@pytest.mark.asyncio
async def test_submit_construction_order_invalid_building_type_fails(db_conn, construction_setup):
    """Test that construction fails with invalid building type."""
    setup = construction_setup

    success, message = await submit_construction_order(
        db_conn,
        building_type_id="nonexistent-building",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )

    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_submit_construction_order_invalid_territory_fails(db_conn, construction_setup):
    """Test that construction fails with invalid territory."""
    setup = construction_setup

    success, message = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="nonexistent-territory",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )

    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_submit_construction_order_invalid_faction_fails(db_conn, construction_setup):
    """Test that construction fails with invalid faction."""
    setup = construction_setup

    success, message = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        faction_id="nonexistent-faction"
    )

    assert success is False
    assert "not found" in message.lower()


# =============================================================================
# Execution Tests
# =============================================================================


@pytest.mark.asyncio
async def test_execute_construction_order_success(db_conn, construction_setup):
    """Test executing a construction order creates a building."""
    setup = construction_setup

    # Submit order
    success, message = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )
    assert success is True

    # Get the order
    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    const_order = [o for o in orders if o.order_type == OrderType.CONSTRUCTION.value][0]

    # Execute the order
    events = await handle_construction_order(db_conn, const_order, TEST_GUILD_ID, 1)

    assert len(events) == 1
    assert events[0].event_type == 'BUILDING_CONSTRUCTED'
    assert events[0].event_data['building_type'] == 'Test Barracks'
    assert events[0].event_data['territory_id'] == 'const-territory-1'

    # Verify building was created
    buildings = await Building.fetch_all(db_conn, TEST_GUILD_ID)
    new_buildings = [b for b in buildings if b.building_type == 'const-barracks']
    assert len(new_buildings) == 1
    assert new_buildings[0].territory_id == 'const-territory-1'
    assert new_buildings[0].status == 'ACTIVE'


@pytest.mark.asyncio
async def test_execute_construction_order_insufficient_resources(db_conn, construction_setup):
    """Test that construction fails at execution if resources are insufficient."""
    setup = construction_setup

    # Remove resources
    await db_conn.execute(
        "UPDATE PlayerResources SET ore = 0, lumber = 0, rations = 0 WHERE character_id = $1;",
        setup['leader'].id
    )

    # Submit order (should succeed - validation happens at execution)
    success, message = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )
    assert success is True

    # Get and execute the order
    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    const_order = [o for o in orders if o.order_type == OrderType.CONSTRUCTION.value][0]

    events = await handle_construction_order(db_conn, const_order, TEST_GUILD_ID, 1)

    assert len(events) == 1
    assert events[0].event_type == 'CONSTRUCTION_FAILED'
    assert 'insufficient' in events[0].event_data['error'].lower()


@pytest.mark.asyncio
async def test_execute_construction_order_deducts_resources(db_conn, construction_setup):
    """Test that construction deducts resources correctly."""
    setup = construction_setup

    # Check initial resources
    initial_resources = await PlayerResources.fetch_by_character(
        db_conn, setup['leader'].id, TEST_GUILD_ID
    )
    initial_ore = initial_resources.ore
    initial_lumber = initial_resources.lumber
    initial_rations = initial_resources.rations

    # Submit and execute order
    success, _ = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )
    assert success is True

    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    const_order = [o for o in orders if o.order_type == OrderType.CONSTRUCTION.value][0]
    await handle_construction_order(db_conn, const_order, TEST_GUILD_ID, 1)

    # Check resources were deducted (cost: ore=10, lumber=10, rations=5)
    final_resources = await PlayerResources.fetch_by_character(
        db_conn, setup['leader'].id, TEST_GUILD_ID
    )
    assert final_resources.ore == initial_ore - 10
    assert final_resources.lumber == initial_lumber - 10
    assert final_resources.rations == initial_rations - 5


@pytest.mark.asyncio
async def test_execute_construction_order_uses_faction_resources(db_conn, construction_setup):
    """Test that faction construction uses faction resources."""
    setup = construction_setup

    # Grant CONSTRUCTION permission
    perm = FactionPermission(
        faction_id=setup['faction'].id,
        character_id=setup['leader'].id,
        permission_type="CONSTRUCTION",
        guild_id=TEST_GUILD_ID
    )
    await perm.upsert(db_conn)

    # Give faction resources
    faction_resources = FactionResources(
        faction_id=setup['faction'].id,
        ore=100, lumber=100, coal=100, rations=100, cloth=100, platinum=100,
        guild_id=TEST_GUILD_ID
    )
    await faction_resources.upsert(db_conn)

    # Submit and execute faction construction order
    success, _ = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        faction_id="const-faction"
    )
    assert success is True

    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    const_order = [o for o in orders if o.order_type == OrderType.CONSTRUCTION.value][0]
    await handle_construction_order(db_conn, const_order, TEST_GUILD_ID, 1)

    # Check faction resources were deducted
    final_faction_resources = await FactionResources.fetch_by_faction(
        db_conn, setup['faction'].id, TEST_GUILD_ID
    )
    assert final_faction_resources.ore == 90  # 100 - 10
    assert final_faction_resources.lumber == 90  # 100 - 10
    assert final_faction_resources.rations == 95  # 100 - 5

    # Check personal resources were NOT deducted
    personal_resources = await PlayerResources.fetch_by_character(
        db_conn, setup['leader'].id, TEST_GUILD_ID
    )
    assert personal_resources.ore == 100  # Unchanged


@pytest.mark.asyncio
async def test_construction_phase_processes_orders_fifo(db_conn, construction_setup):
    """Test that construction orders are processed in FIFO order."""
    setup = construction_setup

    # Create second building type
    building_type_2 = BuildingType(
        type_id="const-workshop",
        name="Test Workshop",
        description="A test workshop",
        cost_ore=5,
        cost_lumber=5,
        guild_id=TEST_GUILD_ID
    )
    await building_type_2.upsert(db_conn)

    # Submit two orders
    success1, _ = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )
    assert success1 is True

    success2, _ = await submit_construction_order(
        db_conn,
        building_type_id="const-workshop",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )
    assert success2 is True

    # Get orders and check they're ordered by submitted_at
    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    const_orders = [o for o in orders if o.order_type == OrderType.CONSTRUCTION.value]
    const_orders.sort(key=lambda o: o.submitted_at or datetime.min)

    assert len(const_orders) == 2
    assert const_orders[0].order_data['building_type_id'] == 'const-barracks'
    assert const_orders[1].order_data['building_type_id'] == 'const-workshop'


@pytest.mark.asyncio
async def test_building_id_generation_increments(db_conn, construction_setup):
    """Test that building IDs increment correctly."""
    setup = construction_setup

    # Submit and execute first order
    success1, _ = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )
    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    const_order1 = [o for o in orders if o.order_type == OrderType.CONSTRUCTION.value][0]
    await handle_construction_order(db_conn, const_order1, TEST_GUILD_ID, 1)

    # Submit and execute second order
    success2, _ = await submit_construction_order(
        db_conn,
        building_type_id="const-barracks",
        territory_id="const-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )
    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    const_orders = [o for o in orders if o.order_type == OrderType.CONSTRUCTION.value and o.status == OrderStatus.PENDING.value]
    await handle_construction_order(db_conn, const_orders[0], TEST_GUILD_ID, 1)

    # Check building IDs
    buildings = await Building.fetch_all(db_conn, TEST_GUILD_ID)
    building_ids = sorted([b.building_id for b in buildings])

    assert len(building_ids) == 2
    assert building_ids[0] == "BLD-0001"
    assert building_ids[1] == "BLD-0002"
