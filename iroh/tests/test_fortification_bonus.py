"""
Pytest tests for fortification building keyword and siege defense.
Tests verify:
- Fortification buildings can only be built in cities
- Siege defense calculation includes base + fortification bonuses
- DESTROYED buildings don't contribute to siege defense
- Fortification bonuses stack
- Territory siege defense can be edited via handler
- Config import/export includes siege_defense
- City terrain type works in create_territory

Run with: pytest tests/test_fortification_bonus.py -v
"""
import pytest
from handlers.building_handlers import create_building
from handlers.territory_handlers import create_territory, edit_territory_siege_defense
from handlers.turn_handlers import calculate_territory_siege_defense, FORTIFICATION_BONUS
from config_manager import ConfigManager
from db import Building, BuildingType, Territory
from tests.conftest import TEST_GUILD_ID


async def setup_fortress_building_type(db_conn, guild_id):
    """Helper to create a fortification building type for testing."""
    building_type = BuildingType(
        type_id="fortress",
        name="Fortress",
        description="A fortified defensive structure",
        keywords=["fortification"],
        guild_id=guild_id,
        cost_ore=20, cost_lumber=15, cost_coal=5,
        upkeep_ore=1, upkeep_lumber=1
    )
    await building_type.upsert(db_conn)
    return building_type


async def setup_city_territory(db_conn, guild_id, territory_id="CITY-1", siege_defense=0):
    """Helper to create a city territory for testing."""
    territory = Territory(
        territory_id=territory_id,
        name="Test City",
        terrain_type="city",
        siege_defense=siege_defense,
        guild_id=guild_id
    )
    await territory.upsert(db_conn)
    return territory


async def setup_plains_territory(db_conn, guild_id, territory_id="PLAINS-1"):
    """Helper to create a plains territory for testing."""
    territory = Territory(
        territory_id=territory_id,
        name="Test Plains",
        terrain_type="plains",
        guild_id=guild_id
    )
    await territory.upsert(db_conn)
    return territory


@pytest.mark.asyncio
async def test_fortification_building_city_only(db_conn, test_server):
    """Test that fortification buildings can only be built in cities."""
    # Setup
    await setup_fortress_building_type(db_conn, TEST_GUILD_ID)
    await setup_city_territory(db_conn, TEST_GUILD_ID, "CITY-TEST")
    await setup_plains_territory(db_conn, TEST_GUILD_ID, "PLAINS-TEST")

    # Try to build fortification in plains - should fail
    success, message = await create_building(
        db_conn, "fort-plains", "fortress", "PLAINS-TEST", TEST_GUILD_ID
    )
    assert success is False
    assert "fortification" in message.lower()
    assert "cities" in message.lower()

    # Build fortification in city - should succeed
    success, message = await create_building(
        db_conn, "fort-city", "fortress", "CITY-TEST", TEST_GUILD_ID
    )
    assert success is True

    # Verify building was created
    building = await Building.fetch_by_building_id(db_conn, "fort-city", TEST_GUILD_ID)
    assert building is not None
    assert building.territory_id == "CITY-TEST"


@pytest.mark.asyncio
async def test_fortification_bonus_calculation(db_conn, test_server):
    """Test that siege defense = base + (ACTIVE fortification buildings * 2)."""
    # Setup city with base siege defense of 5
    await setup_fortress_building_type(db_conn, TEST_GUILD_ID)
    territory = await setup_city_territory(db_conn, TEST_GUILD_ID, "CITY-CALC", siege_defense=5)

    # Create a second fortification building type to test multiple buildings
    building_type2 = BuildingType(
        type_id="wall",
        name="City Wall",
        description="A defensive wall",
        keywords=["fortification"],
        guild_id=TEST_GUILD_ID,
        cost_ore=10, cost_lumber=10
    )
    await building_type2.upsert(db_conn)

    # Create 2 fortification buildings
    await create_building(db_conn, "fort-1", "fortress", "CITY-CALC", TEST_GUILD_ID)
    await create_building(db_conn, "wall-1", "wall", "CITY-CALC", TEST_GUILD_ID)

    # Calculate siege defense: base 5 + 2 buildings * 2 = 9
    total_defense = await calculate_territory_siege_defense(db_conn, territory, TEST_GUILD_ID)
    assert total_defense == 5 + (2 * FORTIFICATION_BONUS)


@pytest.mark.asyncio
async def test_fortification_destroyed_no_bonus(db_conn, test_server):
    """Test that DESTROYED buildings don't contribute to siege defense."""
    # Setup
    await setup_fortress_building_type(db_conn, TEST_GUILD_ID)
    territory = await setup_city_territory(db_conn, TEST_GUILD_ID, "CITY-DESTROYED", siege_defense=3)

    # Create fortification building
    await create_building(db_conn, "fort-destroyed", "fortress", "CITY-DESTROYED", TEST_GUILD_ID)

    # Verify building contributes to defense
    total_defense = await calculate_territory_siege_defense(db_conn, territory, TEST_GUILD_ID)
    assert total_defense == 3 + FORTIFICATION_BONUS

    # Mark building as DESTROYED
    building = await Building.fetch_by_building_id(db_conn, "fort-destroyed", TEST_GUILD_ID)
    building.status = "DESTROYED"
    await building.upsert(db_conn)

    # Verify destroyed building doesn't contribute
    total_defense = await calculate_territory_siege_defense(db_conn, territory, TEST_GUILD_ID)
    assert total_defense == 3  # Only base defense


@pytest.mark.asyncio
async def test_fortification_stacking(db_conn, test_server):
    """Test that multiple fortification buildings stack their bonuses."""
    # Setup
    territory = await setup_city_territory(db_conn, TEST_GUILD_ID, "CITY-STACK", siege_defense=0)

    # Create 3 different fortification building types
    for i, type_id in enumerate(["fort-type-1", "fort-type-2", "fort-type-3"]):
        building_type = BuildingType(
            type_id=type_id,
            name=f"Fortification {i+1}",
            keywords=["fortification"],
            guild_id=TEST_GUILD_ID
        )
        await building_type.upsert(db_conn)
        await create_building(db_conn, f"building-{i+1}", type_id, "CITY-STACK", TEST_GUILD_ID)

    # 3 buildings * 2 bonus = 6 total
    total_defense = await calculate_territory_siege_defense(db_conn, territory, TEST_GUILD_ID)
    assert total_defense == 3 * FORTIFICATION_BONUS


@pytest.mark.asyncio
async def test_edit_territory_siege_defense(db_conn, test_server):
    """Test that edit_territory_siege_defense updates the value."""
    # Create territory
    territory = Territory(
        territory_id="TEST-EDIT-DEFENSE",
        terrain_type="plains",
        siege_defense=0,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Edit siege defense
    success, message = await edit_territory_siege_defense(
        db_conn, "TEST-EDIT-DEFENSE", 10, TEST_GUILD_ID
    )
    assert success is True
    assert "10" in message

    # Verify update
    territory = await Territory.fetch_by_territory_id(db_conn, "TEST-EDIT-DEFENSE", TEST_GUILD_ID)
    assert territory.siege_defense == 10

    # Test negative value fails
    success, message = await edit_territory_siege_defense(
        db_conn, "TEST-EDIT-DEFENSE", -5, TEST_GUILD_ID
    )
    assert success is False
    assert "negative" in message.lower()

    # Test non-existent territory
    success, message = await edit_territory_siege_defense(
        db_conn, "NON-EXISTENT", 5, TEST_GUILD_ID
    )
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_config_import_export_siege_defense(db_conn, test_server):
    """Test that siege_defense is exported and imported correctly."""
    # Create territory with siege defense
    territory = Territory(
        territory_id="CONFIG-TEST",
        name="Config Test Territory",
        terrain_type="city",
        siege_defense=7,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Export config
    config_yaml = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)

    # Verify siege_defense is in the export
    assert "siege_defense: 7" in config_yaml

    # Delete the territory
    await Territory.delete(db_conn, "CONFIG-TEST", TEST_GUILD_ID)

    # Import config
    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, config_yaml)
    assert success is True

    # Verify siege_defense was imported
    imported_territory = await Territory.fetch_by_territory_id(db_conn, "CONFIG-TEST", TEST_GUILD_ID)
    assert imported_territory is not None
    assert imported_territory.siege_defense == 7


@pytest.mark.asyncio
async def test_create_city_via_command(db_conn, test_server):
    """Test that city terrain type works in create_territory."""
    success, message = await create_territory(
        db_conn, "CITY-CMD-TEST", "city", TEST_GUILD_ID, name="Command Test City"
    )

    assert success is True
    assert "CITY-CMD-TEST" in message

    # Verify territory was created with correct terrain type
    territory = await Territory.fetch_by_territory_id(db_conn, "CITY-CMD-TEST", TEST_GUILD_ID)
    assert territory is not None
    assert territory.terrain_type == "city"
    assert territory.name == "Command Test City"
