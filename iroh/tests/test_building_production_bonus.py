"""
Pytest tests for building keyword production bonuses in resource collection.

Tests verify:
- Basic keyword bonus with natural production
- No bonus without natural production (non-industrial)
- Industrial buildings produce regardless of natural production
- Industrial chaining enables non-industrial bonuses
- Stacking multiple buildings with same keyword
- Industrial-only buildings produce nothing
- Duplicate building type constraint
- DESTROYED buildings don't contribute bonuses

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_building_production_bonus.py -v
"""
import pytest
from handlers.turn_handlers import execute_resource_collection_phase, _calculate_building_production_bonus
from handlers.building_handlers import create_building
from db import Character, Territory, PlayerResources, Building, BuildingType
from tests.conftest import TEST_GUILD_ID


@pytest.mark.asyncio
async def test_basic_keyword_bonus_with_natural_production(db_conn, test_server):
    """Test that a lumber mill in territory with lumber production gives +2 lumber."""
    # Create character
    character = Character(
        identifier="lumber-char", name="Lumber Collector",
        channel_id=999000000000000101, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "lumber-char", TEST_GUILD_ID)

    # Create territory WITH lumber production
    territory = Territory(
        territory_id="B100", name="Lumber Territory", terrain_type="forest",
        ore_production=0, lumber_production=5, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building type with lumber keyword
    building_type = BuildingType(
        type_id="test-lumber-mill", name="Test Lumber Mill",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await building_type.upsert(db_conn)

    # Create ACTIVE building
    building = Building(
        building_id="lumber-mill-1", name="Forest Mill",
        building_type="test-lumber-mill", territory_id="B100",
        durability=10, status="ACTIVE",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify resources: natural (5) + building bonus (2) = 7
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is not None
    assert player_resources.lumber == 7  # 5 natural + 2 bonus

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_no_bonus_without_natural_production(db_conn, test_server):
    """Test that a non-industrial lumber mill in territory WITHOUT lumber production gives no bonus."""
    # Create character
    character = Character(
        identifier="no-lumber-char", name="No Lumber",
        channel_id=999000000000000102, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "no-lumber-char", TEST_GUILD_ID)

    # Create territory WITHOUT lumber production
    territory = Territory(
        territory_id="B101", name="Barren Territory", terrain_type="desert",
        ore_production=5, lumber_production=0, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building type with lumber keyword (NOT industrial)
    building_type = BuildingType(
        type_id="test-lumber-mill-2", name="Test Lumber Mill",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await building_type.upsert(db_conn)

    # Create ACTIVE building
    building = Building(
        building_id="lumber-mill-2", name="Desert Mill",
        building_type="test-lumber-mill-2", territory_id="B101",
        durability=10, status="ACTIVE",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify resources: only ore (5), no lumber bonus
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is not None
    assert player_resources.ore == 5
    assert player_resources.lumber == 0  # No bonus without natural production

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_industrial_produces_without_natural(db_conn, test_server):
    """Test that an industrial foundry produces ore even if territory has 0 ore production."""
    # Create character
    character = Character(
        identifier="industrial-char", name="Industrial Owner",
        channel_id=999000000000000103, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "industrial-char", TEST_GUILD_ID)

    # Create territory WITHOUT ore production
    territory = Territory(
        territory_id="B102", name="No Ore Territory", terrain_type="plains",
        ore_production=0, lumber_production=5, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create industrial building type
    building_type = BuildingType(
        type_id="test-foundry", name="Test Foundry",
        keywords=["industrial", "ore"],
        guild_id=TEST_GUILD_ID
    )
    await building_type.upsert(db_conn)

    # Create ACTIVE industrial building
    building = Building(
        building_id="foundry-1", name="Industrial Foundry",
        building_type="test-foundry", territory_id="B102",
        durability=10, status="ACTIVE",
        keywords=["industrial", "ore"],
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify resources: lumber (5) + industrial ore bonus (2)
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is not None
    assert player_resources.ore == 2  # Industrial produces even without natural
    assert player_resources.lumber == 5

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_industrial_chaining(db_conn, test_server):
    """Test that industrial production enables non-industrial building bonuses (chaining)."""
    # Create character
    character = Character(
        identifier="chaining-char", name="Chain Owner",
        channel_id=999000000000000104, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "chaining-char", TEST_GUILD_ID)

    # Create territory WITHOUT ore production
    territory = Territory(
        territory_id="B103", name="No Ore Territory", terrain_type="plains",
        ore_production=0, lumber_production=0, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create industrial foundry type
    foundry_type = BuildingType(
        type_id="test-foundry-chain", name="Test Foundry",
        keywords=["industrial", "ore"],
        guild_id=TEST_GUILD_ID
    )
    await foundry_type.upsert(db_conn)

    # Create non-industrial ore refinery type
    refinery_type = BuildingType(
        type_id="test-ore-refinery", name="Test Ore Refinery",
        keywords=["ore"],
        guild_id=TEST_GUILD_ID
    )
    await refinery_type.upsert(db_conn)

    # Create ACTIVE industrial foundry
    foundry = Building(
        building_id="foundry-chain-1", name="Industrial Foundry",
        building_type="test-foundry-chain", territory_id="B103",
        durability=10, status="ACTIVE",
        keywords=["industrial", "ore"],
        guild_id=TEST_GUILD_ID
    )
    await foundry.upsert(db_conn)

    # Create ACTIVE non-industrial ore refinery
    refinery = Building(
        building_id="refinery-1", name="Ore Refinery",
        building_type="test-ore-refinery", territory_id="B103",
        durability=10, status="ACTIVE",
        keywords=["ore"],
        guild_id=TEST_GUILD_ID
    )
    await refinery.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify resources: industrial ore (2) + refinery bonus enabled by industrial (2) = 4
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is not None
    assert player_resources.ore == 4  # 2 from foundry + 2 from refinery (enabled by foundry)

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_stacking_same_keyword(db_conn, test_server):
    """Test that two buildings with lumber keyword stack (+4 lumber total)."""
    # Create character
    character = Character(
        identifier="stacking-char", name="Stacking Owner",
        channel_id=999000000000000105, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "stacking-char", TEST_GUILD_ID)

    # Create territory WITH lumber production
    territory = Territory(
        territory_id="B104", name="Lumber Territory", terrain_type="forest",
        ore_production=0, lumber_production=3, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create two building types with lumber keyword
    mill_type = BuildingType(
        type_id="test-lumber-mill-stack", name="Test Lumber Mill",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await mill_type.upsert(db_conn)

    sawmill_type = BuildingType(
        type_id="test-sawmill", name="Test Sawmill",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await sawmill_type.upsert(db_conn)

    # Create two ACTIVE lumber buildings
    mill = Building(
        building_id="lumber-mill-stack", name="Lumber Mill",
        building_type="test-lumber-mill-stack", territory_id="B104",
        durability=10, status="ACTIVE",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await mill.upsert(db_conn)

    sawmill = Building(
        building_id="sawmill-1", name="Sawmill",
        building_type="test-sawmill", territory_id="B104",
        durability=10, status="ACTIVE",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await sawmill.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify resources: natural (3) + mill bonus (2) + sawmill bonus (2) = 7
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is not None
    assert player_resources.lumber == 7  # 3 natural + 2 + 2 bonuses

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_industrial_only_no_production(db_conn, test_server):
    """Test that a power plant (industrial only, no resource keywords) produces nothing."""
    # Create character
    character = Character(
        identifier="power-char", name="Power Plant Owner",
        channel_id=999000000000000106, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "power-char", TEST_GUILD_ID)

    # Create territory
    territory = Territory(
        territory_id="B105", name="Power Territory", terrain_type="plains",
        ore_production=0, lumber_production=0, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create industrial-only building type
    power_type = BuildingType(
        type_id="test-power-plant", name="Test Power Plant",
        keywords=["industrial"],
        guild_id=TEST_GUILD_ID
    )
    await power_type.upsert(db_conn)

    # Create ACTIVE power plant
    power_plant = Building(
        building_id="power-plant-1", name="Power Plant",
        building_type="test-power-plant", territory_id="B105",
        durability=10, status="ACTIVE",
        keywords=["industrial"],
        guild_id=TEST_GUILD_ID
    )
    await power_plant.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify no events (no production)
    assert len(events) == 0

    # Verify no resources collected
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is None

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_duplicate_building_type_constraint(db_conn, test_server):
    """Test that a second barracks in the same territory fails."""
    # Create character
    character = Character(
        identifier="dup-char", name="Duplicate Builder",
        channel_id=999000000000000107, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "dup-char", TEST_GUILD_ID)

    # Create territory
    territory = Territory(
        territory_id="B106", name="Barracks Territory", terrain_type="plains",
        ore_production=0, lumber_production=0, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create barracks building type
    barracks_type = BuildingType(
        type_id="test-barracks", name="Test Barracks",
        keywords=[],
        guild_id=TEST_GUILD_ID
    )
    await barracks_type.upsert(db_conn)

    # Create first barracks successfully
    success1, msg1 = await create_building(
        db_conn, "barracks-1", "test-barracks", "B106", TEST_GUILD_ID, "First Barracks"
    )
    assert success1 is True

    # Try to create second barracks - should fail
    success2, msg2 = await create_building(
        db_conn, "barracks-2", "test-barracks", "B106", TEST_GUILD_ID, "Second Barracks"
    )
    assert success2 is False
    assert "already has a building of type" in msg2

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_destroyed_building_no_bonus(db_conn, test_server):
    """Test that DESTROYED buildings don't contribute production bonuses."""
    # Create character
    character = Character(
        identifier="destroyed-char", name="Destroyed Building Owner",
        channel_id=999000000000000108, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "destroyed-char", TEST_GUILD_ID)

    # Create territory WITH lumber production
    territory = Territory(
        territory_id="B107", name="Destroyed Mill Territory", terrain_type="forest",
        ore_production=0, lumber_production=5, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building type with lumber keyword
    building_type = BuildingType(
        type_id="test-lumber-mill-destroyed", name="Test Lumber Mill",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await building_type.upsert(db_conn)

    # Create DESTROYED building (should not contribute)
    building = Building(
        building_id="destroyed-mill-1", name="Destroyed Mill",
        building_type="test-lumber-mill-destroyed", territory_id="B107",
        durability=0, status="DESTROYED",
        keywords=["lumber"],
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify resources: only natural (5), no building bonus
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is not None
    assert player_resources.lumber == 5  # Only natural, no bonus from destroyed building

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_multi_keyword_building(db_conn, test_server):
    """Test that a factory with multiple resource keywords gets +2 per matching keyword."""
    # Create character
    character = Character(
        identifier="multi-kw-char", name="Multi Keyword Owner",
        channel_id=999000000000000109, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "multi-kw-char", TEST_GUILD_ID)

    # Create territory (industrial will produce regardless of natural)
    territory = Territory(
        territory_id="B108", name="Factory Territory", terrain_type="plains",
        ore_production=0, lumber_production=0, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create industrial factory with ore AND cloth keywords
    factory_type = BuildingType(
        type_id="test-factory", name="Test Factory",
        keywords=["industrial", "ore", "cloth"],
        guild_id=TEST_GUILD_ID
    )
    await factory_type.upsert(db_conn)

    # Create ACTIVE factory
    factory = Building(
        building_id="factory-1", name="General Factory",
        building_type="test-factory", territory_id="B108",
        durability=10, status="ACTIVE",
        keywords=["industrial", "ore", "cloth"],
        guild_id=TEST_GUILD_ID
    )
    await factory.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify resources: ore (2) + cloth (2) = 4 total
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is not None
    assert player_resources.ore == 2  # Industrial ore
    assert player_resources.cloth == 2  # Industrial cloth

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_calculate_building_production_bonus_helper(db_conn, test_server):
    """Test the _calculate_building_production_bonus helper function directly."""
    # Create territory with some natural production
    territory = Territory(
        territory_id="B109", name="Test Territory", terrain_type="plains",
        ore_production=5, lumber_production=3, coal_production=0,
        rations_production=0, cloth_production=0, platinum_production=0,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building types
    ore_type = BuildingType(
        type_id="test-ore-bonus", name="Ore Bonus Building",
        keywords=["ore"],
        guild_id=TEST_GUILD_ID
    )
    await ore_type.upsert(db_conn)

    industrial_type = BuildingType(
        type_id="test-industrial-coal", name="Industrial Coal",
        keywords=["industrial", "coal"],
        guild_id=TEST_GUILD_ID
    )
    await industrial_type.upsert(db_conn)

    # Create buildings
    ore_building = Building(
        building_id="ore-bonus-1", building_type="test-ore-bonus",
        territory_id="B109", status="ACTIVE", keywords=["ore"],
        guild_id=TEST_GUILD_ID
    )
    await ore_building.upsert(db_conn)

    industrial_building = Building(
        building_id="ind-coal-1", building_type="test-industrial-coal",
        territory_id="B109", status="ACTIVE", keywords=["industrial", "coal"],
        guild_id=TEST_GUILD_ID
    )
    await industrial_building.upsert(db_conn)

    # Calculate bonus
    bonus = await _calculate_building_production_bonus(db_conn, territory, TEST_GUILD_ID)

    # Verify bonuses
    assert bonus['ore'] == 2  # Non-industrial ore building with natural production
    assert bonus['lumber'] == 0  # No lumber buildings
    assert bonus['coal'] == 2  # Industrial coal (doesn't need natural production)
    assert bonus['rations'] == 0
    assert bonus['cloth'] == 0
    assert bonus['platinum'] == 0

    # Cleanup
    await db_conn.execute("DELETE FROM Building WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
