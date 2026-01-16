"""
Pytest tests for unit type handlers.
Tests verify unit type creation, editing, and deletion operations.

Run with: pytest tests/test_unit_type_handlers.py -v
"""
import pytest
from handlers.unit_type_handlers import create_unit_type, edit_unit_type, delete_unit_type
from db import UnitType, Unit, Character, Faction, Territory
from tests.conftest import TEST_GUILD_ID, TEST_GUILD_ID_2


@pytest.mark.asyncio
async def test_create_unit_type_success(db_conn, test_server):
    """Test creating a unit type with valid parameters."""
    success, message, data = await create_unit_type(
        db_conn, "infantry", "Infantry Division", TEST_GUILD_ID
    )

    # Verify - nation is now set via modal, not handler
    assert success is True
    assert data is not None
    assert data['type_id'] == "infantry"
    assert data['name'] == "Infantry Division"


@pytest.mark.asyncio
async def test_create_unit_type_duplicate(db_conn, test_server):
    """Test creating a unit type with duplicate type_id."""
    # Create first unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Try to create duplicate
    success, message, data = await create_unit_type(
        db_conn, "infantry", "Another Infantry", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "already exists" in message.lower()
    assert data is None

    # Cleanup
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_unit_type_success(db_conn, test_server):
    """Test editing an existing unit type."""
    # Create unit type
    unit_type = UnitType(
        type_id="cavalry", name="Cavalry Division",
        nation="earth-kingdom", guild_id=TEST_GUILD_ID,
        movement=4, organization=8, attack=7, defense=3,
        siege_attack=1, siege_defense=2,
        cost_ore=3, cost_lumber=5, cost_coal=0, cost_rations=15, cost_cloth=8,
        upkeep_rations=3, upkeep_cloth=2
    )
    await unit_type.upsert(db_conn)

    # Edit unit type
    success, message, data = await edit_unit_type(
        db_conn, "cavalry", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert data is not None
    assert isinstance(data, UnitType)
    assert data.type_id == "cavalry"
    assert data.name == "Cavalry Division"
    assert data.nation == "earth-kingdom"
    assert data.movement == 4

    # Cleanup
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_edit_unit_type_nonexistent(db_conn, test_server):
    """Test editing a non-existent unit type."""
    success, message, data = await edit_unit_type(
        db_conn, "nonexistent-unit", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_delete_unit_type_success(db_conn, test_server):
    """Test deleting a unit type with no units using it."""
    # Create unit type
    unit_type = UnitType(
        type_id="artillery", name="Artillery Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
        movement=1, organization=6, attack=10, defense=2,
        siege_attack=8, siege_defense=1,
        cost_ore=10, cost_lumber=3, cost_coal=5, cost_rations=8, cost_cloth=2,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Delete unit type
    success, message = await delete_unit_type(
        db_conn, "artillery", TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "deleted" in message.lower()

    # Verify deleted from database
    fetched = await UnitType.fetch_by_type_id(db_conn, "artillery", TEST_GUILD_ID)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_unit_type_with_units(db_conn, test_server):
    """Test that deleting a unit type with units using it fails."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Create unit type
    unit_type = UnitType(
        type_id="tank", name="Tank Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
        movement=3, organization=12, attack=9, defense=8,
        siege_attack=5, siege_defense=7,
        cost_ore=15, cost_lumber=5, cost_coal=10, cost_rations=12, cost_cloth=3,
        upkeep_rations=3, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id="1", terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit using this type
    unit = Unit(
        unit_id="TANK-001", name="First Tank",
        unit_type="tank",
        owner_character_id=char.id, faction_id=faction.id,
        current_territory_id="1", guild_id=TEST_GUILD_ID,
        movement=3, organization=12, attack=9, defense=8,
        siege_attack=5, siege_defense=7
    )
    await unit.upsert(db_conn)

    # Try to delete unit type
    success, message = await delete_unit_type(
        db_conn, "tank", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "cannot delete" in message.lower()
    assert "units" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_delete_unit_type_nonexistent(db_conn, test_server):
    """Test deleting a non-existent unit type."""
    success, message = await delete_unit_type(
        db_conn, "nonexistent-unit", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_unit_type_guild_isolation(db_conn, test_server_multi_guild):
    """Test that unit type operations are properly isolated between guilds."""
    # Create unit type with same type_id in both guilds (nation can be different or same)
    unit_type_a = UnitType(
        type_id="infantry", name="Guild A Infantry",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type_a.upsert(db_conn)

    unit_type_b = UnitType(
        type_id="infantry", name="Guild B Infantry",
        nation="fire-nation", guild_id=TEST_GUILD_ID_2,
        movement=3, organization=12, attack=6, defense=6,
        siege_attack=3, siege_defense=4,
        cost_ore=6, cost_lumber=3, cost_coal=1, cost_rations=12, cost_cloth=6,
        upkeep_rations=3, upkeep_cloth=2
    )
    await unit_type_b.upsert(db_conn)

    # Edit unit type in guild A
    success_a, _, data_a = await edit_unit_type(
        db_conn, "infantry", TEST_GUILD_ID
    )

    # Verify guild A's unit type
    assert success_a is True
    assert data_a.name == "Guild A Infantry"
    assert data_a.movement == 2

    # Verify guild B's unit type is unchanged
    success_b, _, data_b = await edit_unit_type(
        db_conn, "infantry", TEST_GUILD_ID_2
    )
    assert success_b is True
    assert data_b.name == "Guild B Infantry"
    assert data_b.movement == 3

    # Verify same type_id exists independently in each guild
    assert data_a.type_id == data_b.type_id == "infantry"
    assert data_a.nation == data_b.nation == "fire-nation"

    # But they are different entities
    assert data_a.name != data_b.name
    assert data_a.movement != data_b.movement
    assert data_a.guild_id == TEST_GUILD_ID
    assert data_b.guild_id == TEST_GUILD_ID_2

    # Delete unit type in guild A
    success_delete_a = await delete_unit_type(
        db_conn, "infantry", TEST_GUILD_ID
    )
    assert success_delete_a[0] is True

    # Verify guild B's unit type still exists
    fetched_b = await UnitType.fetch_by_type_id(db_conn, "infantry", TEST_GUILD_ID_2)
    assert fetched_b is not None
    assert fetched_b.name == "Guild B Infantry"

    # Cleanup
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
