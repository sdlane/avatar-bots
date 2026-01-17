"""
Pytest tests for building handlers.
Tests verify building creation, editing, deletion, viewing, and territory integration.

Run with: pytest tests/test_building_handlers.py -v
"""
import pytest
from handlers.building_handlers import create_building, edit_building, delete_building
from handlers.view_handlers import view_building, view_territory
from db import Building, BuildingType, Territory
from tests.conftest import TEST_GUILD_ID, TEST_GUILD_ID_2


async def setup_building_type(db_conn, guild_id):
    """Helper to create a building type for testing."""
    building_type = BuildingType(
        type_id="barracks", name="Military Barracks",
        description="A training facility for soldiers",
        guild_id=guild_id,
        cost_ore=10, cost_lumber=10, cost_rations=5,
        upkeep_lumber=1, upkeep_rations=2
    )
    await building_type.upsert(db_conn)
    return building_type


async def setup_territory(db_conn, guild_id):
    """Helper to create a territory for testing."""
    territory = Territory(
        territory_id="1",
        name="Test Territory",
        terrain_type="plains",
        guild_id=guild_id
    )
    await territory.upsert(db_conn)
    return territory


@pytest.mark.asyncio
async def test_create_building_success(db_conn, test_server):
    """Test creating a building with valid parameters."""
    # Setup dependencies
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Create building
    success, message = await create_building(
        db_conn, "test-barracks", "barracks", "1", TEST_GUILD_ID, name="Test Barracks"
    )

    # Verify
    assert success is True
    assert "created" in message.lower()

    # Verify in database
    building = await Building.fetch_by_building_id(db_conn, "test-barracks", TEST_GUILD_ID)
    assert building is not None
    assert building.name == "Test Barracks"
    assert building.building_type == "barracks"
    assert building.territory_id == "1"
    assert building.durability == 10
    assert building.status == "ACTIVE"
    # Verify upkeep copied from building type
    assert building.upkeep_lumber == 1
    assert building.upkeep_rations == 2

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_building_duplicate(db_conn, test_server):
    """Test creating a building with duplicate building_id."""
    # Setup dependencies
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Create first building
    await create_building(
        db_conn, "test-barracks", "barracks", "1", TEST_GUILD_ID
    )

    # Try to create duplicate
    success, message = await create_building(
        db_conn, "test-barracks", "barracks", "1", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "already exists" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_building_invalid_type(db_conn, test_server):
    """Test creating a building with invalid building type."""
    # Setup territory only (no building type)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Try to create building with nonexistent type
    success, message = await create_building(
        db_conn, "test-building", "nonexistent-type", "1", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_building_invalid_territory(db_conn, test_server):
    """Test creating a building with invalid territory."""
    # Setup building type only (no territory)
    await setup_building_type(db_conn, TEST_GUILD_ID)

    # Try to create building in nonexistent territory
    success, message = await create_building(
        db_conn, "test-building", "barracks", "999", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_building_success(db_conn, test_server):
    """Test editing an existing building."""
    # Setup dependencies
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Create building
    await create_building(
        db_conn, "test-barracks", "barracks", "1", TEST_GUILD_ID, name="Old Name"
    )

    # Edit building
    success, message = await edit_building(
        db_conn, "test-barracks", TEST_GUILD_ID, name="New Name", durability=5
    )

    # Verify
    assert success is True
    assert "updated" in message.lower()

    # Verify in database
    building = await Building.fetch_by_building_id(db_conn, "test-barracks", TEST_GUILD_ID)
    assert building.name == "New Name"
    assert building.durability == 5

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_building_status(db_conn, test_server):
    """Test editing building status."""
    # Setup dependencies
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Create building
    await create_building(
        db_conn, "test-barracks", "barracks", "1", TEST_GUILD_ID
    )

    # Edit building status to DESTROYED
    success, message = await edit_building(
        db_conn, "test-barracks", TEST_GUILD_ID, status="DESTROYED"
    )

    # Verify
    assert success is True
    building = await Building.fetch_by_building_id(db_conn, "test-barracks", TEST_GUILD_ID)
    assert building.status == "DESTROYED"

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_building_invalid_status(db_conn, test_server):
    """Test editing building with invalid status."""
    # Setup dependencies
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Create building
    await create_building(
        db_conn, "test-barracks", "barracks", "1", TEST_GUILD_ID
    )

    # Try to edit with invalid status
    success, message = await edit_building(
        db_conn, "test-barracks", TEST_GUILD_ID, status="INVALID"
    )

    # Verify failure
    assert success is False
    assert "status" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_building_nonexistent(db_conn, test_server):
    """Test editing a non-existent building."""
    success, message = await edit_building(
        db_conn, "nonexistent-building", TEST_GUILD_ID, name="New Name"
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_delete_building_success(db_conn, test_server):
    """Test deleting a building."""
    # Setup dependencies
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Create building
    await create_building(
        db_conn, "test-barracks", "barracks", "1", TEST_GUILD_ID
    )

    # Delete building
    success, message = await delete_building(
        db_conn, "test-barracks", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "deleted" in message.lower()

    # Verify deleted from database
    building = await Building.fetch_by_building_id(db_conn, "test-barracks", TEST_GUILD_ID)
    assert building is None

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_delete_building_nonexistent(db_conn, test_server):
    """Test deleting a non-existent building."""
    success, message = await delete_building(
        db_conn, "nonexistent-building", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_view_building_success(db_conn, test_server):
    """Test viewing an existing building."""
    # Setup dependencies
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Create building
    await create_building(
        db_conn, "test-barracks", "barracks", "1", TEST_GUILD_ID, name="Test Barracks"
    )

    # View building
    success, message, data = await view_building(
        db_conn, "test-barracks", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert data is not None
    assert 'building' in data
    assert data['building'].building_id == "test-barracks"
    assert data['building'].name == "Test Barracks"
    assert 'building_type' in data
    assert data['building_type'].name == "Military Barracks"
    assert 'territory' in data
    assert data['territory'].name == "Test Territory"

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_building_nonexistent(db_conn, test_server):
    """Test viewing a non-existent building."""
    success, message, data = await view_building(
        db_conn, "nonexistent-building", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_fetch_buildings_by_territory(db_conn, test_server):
    """Test fetching buildings by territory."""
    # Setup dependencies
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Create second territory
    territory2 = Territory(
        territory_id="2",
        name="Test Territory 2",
        terrain_type="mountains",
        guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # Create buildings in different territories
    await create_building(
        db_conn, "building-1", "barracks", "1", TEST_GUILD_ID, name="Building 1"
    )
    await create_building(
        db_conn, "building-2", "barracks", "1", TEST_GUILD_ID, name="Building 2"
    )
    await create_building(
        db_conn, "building-3", "barracks", "2", TEST_GUILD_ID, name="Building 3"
    )

    # Fetch buildings in territory 1
    buildings = await Building.fetch_by_territory(db_conn, "1", TEST_GUILD_ID)

    # Verify
    assert len(buildings) == 2
    building_ids = [b.building_id for b in buildings]
    assert "building-1" in building_ids
    assert "building-2" in building_ids
    assert "building-3" not in building_ids

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_territory_includes_buildings(db_conn, test_server):
    """Test that view_territory includes buildings in returned data."""
    # Setup dependencies
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID)

    # Create buildings
    await create_building(
        db_conn, "test-barracks-1", "barracks", "1", TEST_GUILD_ID, name="Barracks 1"
    )
    await create_building(
        db_conn, "test-barracks-2", "barracks", "1", TEST_GUILD_ID, name="Barracks 2"
    )

    # View territory
    success, message, data = await view_territory(
        db_conn, "1", TEST_GUILD_ID
    )

    # Verify buildings included
    assert success is True
    assert 'buildings' in data
    assert len(data['buildings']) == 2
    building_ids = [b.building_id for b in data['buildings']]
    assert "test-barracks-1" in building_ids
    assert "test-barracks-2" in building_ids

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_guild_isolation(db_conn, test_server_multi_guild):
    """Test that building operations are properly isolated between guilds."""
    # Setup dependencies in both guilds
    await setup_building_type(db_conn, TEST_GUILD_ID)
    await setup_building_type(db_conn, TEST_GUILD_ID_2)
    await setup_territory(db_conn, TEST_GUILD_ID)
    await setup_territory(db_conn, TEST_GUILD_ID_2)

    # Create building with same ID in both guilds
    await create_building(
        db_conn, "shared-barracks", "barracks", "1", TEST_GUILD_ID, name="Guild A Barracks"
    )
    await create_building(
        db_conn, "shared-barracks", "barracks", "1", TEST_GUILD_ID_2, name="Guild B Barracks"
    )

    # Verify guild isolation
    building_a = await Building.fetch_by_building_id(db_conn, "shared-barracks", TEST_GUILD_ID)
    building_b = await Building.fetch_by_building_id(db_conn, "shared-barracks", TEST_GUILD_ID_2)

    assert building_a is not None
    assert building_b is not None
    assert building_a.name == "Guild A Barracks"
    assert building_b.name == "Guild B Barracks"
    assert building_a.guild_id == TEST_GUILD_ID
    assert building_b.guild_id == TEST_GUILD_ID_2

    # Delete building in guild A
    await delete_building(db_conn, "shared-barracks", TEST_GUILD_ID)

    # Verify guild B's building still exists
    building_b_after = await Building.fetch_by_building_id(db_conn, "shared-barracks", TEST_GUILD_ID_2)
    assert building_b_after is not None
    assert building_b_after.name == "Guild B Barracks"

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)


@pytest.mark.asyncio
async def test_building_verify(db_conn, test_server):
    """Test the Building.verify() method."""
    # Valid building
    valid_building = Building(
        building_id="valid",
        building_type="barracks",
        guild_id=TEST_GUILD_ID
    )
    success, message = valid_building.verify()
    assert success is True

    # Empty building_id
    invalid_b1 = Building(
        building_id="",
        building_type="barracks",
        guild_id=TEST_GUILD_ID
    )
    success, message = invalid_b1.verify()
    assert success is False
    assert "building id" in message.lower()

    # Empty building_type
    invalid_b2 = Building(
        building_id="test",
        building_type="",
        guild_id=TEST_GUILD_ID
    )
    success, message = invalid_b2.verify()
    assert success is False
    assert "building type" in message.lower()

    # Negative durability
    invalid_b3 = Building(
        building_id="test",
        building_type="barracks",
        durability=-5,
        guild_id=TEST_GUILD_ID
    )
    success, message = invalid_b3.verify()
    assert success is False
    assert "durability" in message.lower()

    # Invalid status
    invalid_b4 = Building(
        building_id="test",
        building_type="barracks",
        status="INVALID",
        guild_id=TEST_GUILD_ID
    )
    success, message = invalid_b4.verify()
    assert success is False
    assert "status" in message.lower()

    # Negative upkeep
    invalid_b5 = Building(
        building_id="test",
        building_type="barracks",
        upkeep_ore=-1,
        guild_id=TEST_GUILD_ID
    )
    success, message = invalid_b5.verify()
    assert success is False
    assert "upkeep_ore" in message.lower()

    # Invalid guild_id
    invalid_b6 = Building(
        building_id="test",
        building_type="barracks",
        guild_id=None
    )
    success, message = invalid_b6.verify()
    assert success is False
    assert "guild_id" in message.lower()
