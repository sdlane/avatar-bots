"""
Pytest tests for building type handlers.
Tests verify building type creation, editing, deletion, viewing, and listing operations.

Run with: pytest tests/test_building_type_handlers.py -v
"""
import pytest
from handlers.building_type_handlers import create_building_type, edit_building_type, delete_building_type
from handlers.view_handlers import view_building_type
from handlers.list_handlers import list_building_types
from db import BuildingType
from tests.conftest import TEST_GUILD_ID, TEST_GUILD_ID_2


@pytest.mark.asyncio
async def test_create_building_type_success(db_conn, test_server):
    """Test creating a building type with valid parameters."""
    success, message, data = await create_building_type(
        db_conn, "barracks", "Military Barracks", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert data is not None
    assert data['type_id'] == "barracks"
    assert data['name'] == "Military Barracks"


@pytest.mark.asyncio
async def test_create_building_type_duplicate(db_conn, test_server):
    """Test creating a building type with duplicate type_id."""
    # Create first building type
    building_type = BuildingType(
        type_id="barracks", name="Military Barracks",
        description="A training facility for soldiers",
        guild_id=TEST_GUILD_ID,
        cost_ore=10, cost_lumber=10, cost_rations=5,
        upkeep_lumber=1, upkeep_rations=2
    )
    await building_type.upsert(db_conn)

    # Try to create duplicate
    success, message, data = await create_building_type(
        db_conn, "barracks", "Another Barracks", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "already exists" in message.lower()
    assert data is None

    # Cleanup
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_building_type_success(db_conn, test_server):
    """Test editing an existing building type."""
    # Create building type
    building_type = BuildingType(
        type_id="workshop", name="Craftsman Workshop",
        description="A place for crafting equipment",
        guild_id=TEST_GUILD_ID,
        cost_ore=5, cost_lumber=15,
        upkeep_lumber=2
    )
    await building_type.upsert(db_conn)

    # Edit building type
    success, message, data = await edit_building_type(
        db_conn, "workshop", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert data is not None
    assert isinstance(data, BuildingType)
    assert data.type_id == "workshop"
    assert data.name == "Craftsman Workshop"
    assert data.description == "A place for crafting equipment"
    assert data.cost_lumber == 15

    # Cleanup
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_building_type_nonexistent(db_conn, test_server):
    """Test editing a non-existent building type."""
    success, message, data = await edit_building_type(
        db_conn, "nonexistent-building", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_delete_building_type_success(db_conn, test_server):
    """Test deleting a building type."""
    # Create building type
    building_type = BuildingType(
        type_id="warehouse", name="Storage Warehouse",
        description="A building for storing resources",
        guild_id=TEST_GUILD_ID,
        cost_ore=8, cost_lumber=20,
        upkeep_lumber=1
    )
    await building_type.upsert(db_conn)

    # Delete building type
    success, message = await delete_building_type(
        db_conn, "warehouse", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "deleted" in message.lower()

    # Verify deleted from database
    fetched = await BuildingType.fetch_by_type_id(db_conn, "warehouse", TEST_GUILD_ID)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_building_type_nonexistent(db_conn, test_server):
    """Test deleting a non-existent building type."""
    success, message = await delete_building_type(
        db_conn, "nonexistent-building", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_view_building_type_success(db_conn, test_server):
    """Test viewing an existing building type."""
    # Create building type
    building_type = BuildingType(
        type_id="forge", name="Blacksmith Forge",
        description="A smithy for forging metal items",
        guild_id=TEST_GUILD_ID,
        cost_ore=15, cost_lumber=10, cost_coal=5,
        upkeep_ore=1, upkeep_coal=2
    )
    await building_type.upsert(db_conn)

    # View building type
    success, message, data = await view_building_type(
        db_conn, "forge", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert data is not None
    assert 'building_type' in data
    assert data['building_type'].type_id == "forge"
    assert data['building_type'].name == "Blacksmith Forge"
    assert data['building_type'].description == "A smithy for forging metal items"
    assert data['building_type'].cost_ore == 15
    assert data['building_type'].upkeep_coal == 2

    # Cleanup
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_building_type_nonexistent(db_conn, test_server):
    """Test viewing a non-existent building type."""
    success, message, data = await view_building_type(
        db_conn, "nonexistent-building", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_list_building_types_success(db_conn, test_server):
    """Test listing building types."""
    # Create multiple building types
    bt1 = BuildingType(
        type_id="barracks", name="Military Barracks",
        guild_id=TEST_GUILD_ID,
        cost_ore=10, cost_lumber=10
    )
    await bt1.upsert(db_conn)

    bt2 = BuildingType(
        type_id="workshop", name="Craftsman Workshop",
        guild_id=TEST_GUILD_ID,
        cost_lumber=15
    )
    await bt2.upsert(db_conn)

    # List building types
    success, message, data = await list_building_types(
        db_conn, TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert data is not None
    assert len(data) == 2
    type_ids = [bt.type_id for bt in data]
    assert "barracks" in type_ids
    assert "workshop" in type_ids

    # Cleanup
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_list_building_types_empty(db_conn, test_server):
    """Test listing building types when none exist."""
    success, message, data = await list_building_types(
        db_conn, TEST_GUILD_ID
    )

    # Verify failure (no building types found)
    assert success is False
    assert "no building types found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_building_type_guild_isolation(db_conn, test_server_multi_guild):
    """Test that building type operations are properly isolated between guilds."""
    # Create building type with same type_id in both guilds
    building_type_a = BuildingType(
        type_id="barracks", name="Guild A Barracks",
        description="Barracks for guild A",
        guild_id=TEST_GUILD_ID,
        cost_ore=10, cost_lumber=10
    )
    await building_type_a.upsert(db_conn)

    building_type_b = BuildingType(
        type_id="barracks", name="Guild B Barracks",
        description="Barracks for guild B",
        guild_id=TEST_GUILD_ID_2,
        cost_ore=15, cost_lumber=15
    )
    await building_type_b.upsert(db_conn)

    # Edit building type in guild A
    success_a, _, data_a = await edit_building_type(
        db_conn, "barracks", TEST_GUILD_ID
    )

    # Verify guild A's building type
    assert success_a is True
    assert data_a.name == "Guild A Barracks"
    assert data_a.cost_ore == 10

    # Verify guild B's building type is unchanged
    success_b, _, data_b = await edit_building_type(
        db_conn, "barracks", TEST_GUILD_ID_2
    )
    assert success_b is True
    assert data_b.name == "Guild B Barracks"
    assert data_b.cost_ore == 15

    # Verify same type_id exists independently in each guild
    assert data_a.type_id == data_b.type_id == "barracks"

    # But they are different entities
    assert data_a.name != data_b.name
    assert data_a.cost_ore != data_b.cost_ore
    assert data_a.guild_id == TEST_GUILD_ID
    assert data_b.guild_id == TEST_GUILD_ID_2

    # Delete building type in guild A
    success_delete_a = await delete_building_type(
        db_conn, "barracks", TEST_GUILD_ID
    )
    assert success_delete_a[0] is True

    # Verify guild B's building type still exists
    fetched_b = await BuildingType.fetch_by_type_id(db_conn, "barracks", TEST_GUILD_ID_2)
    assert fetched_b is not None
    assert fetched_b.name == "Guild B Barracks"

    # Cleanup
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)


@pytest.mark.asyncio
async def test_building_type_verify(db_conn, test_server):
    """Test the BuildingType.verify() method."""
    # Valid building type
    valid_bt = BuildingType(
        type_id="valid", name="Valid Building",
        guild_id=TEST_GUILD_ID,
        cost_ore=5
    )
    success, message = valid_bt.verify()
    assert success is True

    # Empty type_id
    invalid_bt1 = BuildingType(
        type_id="", name="Invalid Building",
        guild_id=TEST_GUILD_ID
    )
    success, message = invalid_bt1.verify()
    assert success is False
    assert "type id" in message.lower()

    # Empty name
    invalid_bt2 = BuildingType(
        type_id="invalid", name="",
        guild_id=TEST_GUILD_ID
    )
    success, message = invalid_bt2.verify()
    assert success is False
    assert "name" in message.lower()

    # Negative cost
    invalid_bt3 = BuildingType(
        type_id="invalid", name="Invalid Building",
        guild_id=TEST_GUILD_ID,
        cost_ore=-5
    )
    success, message = invalid_bt3.verify()
    assert success is False
    assert "cost_ore" in message.lower()

    # Negative upkeep
    invalid_bt4 = BuildingType(
        type_id="invalid", name="Invalid Building",
        guild_id=TEST_GUILD_ID,
        upkeep_lumber=-1
    )
    success, message = invalid_bt4.verify()
    assert success is False
    assert "upkeep_lumber" in message.lower()

    # Invalid guild_id
    invalid_bt5 = BuildingType(
        type_id="invalid", name="Invalid Building",
        guild_id=None
    )
    success, message = invalid_bt5.verify()
    assert success is False
    assert "guild_id" in message.lower()
