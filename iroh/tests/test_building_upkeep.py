"""
Pytest tests for building upkeep in turn resolution.
Tests verify resource deduction, durability penalties, and building destruction.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_building_upkeep.py -v
"""
import pytest
from handlers.turn_handlers import (
    execute_upkeep_phase,
    execute_organization_phase,
    execute_building_upkeep,
    destroy_low_durability_buildings
)
from db import Character, Building, Territory, PlayerResources, Faction, FactionResources, FactionPermission
from tests.conftest import TEST_GUILD_ID
from event_logging.building_upkeep_events import (
    building_upkeep_paid_character_line,
    building_upkeep_paid_gm_line,
    building_upkeep_deficit_character_line,
    building_upkeep_deficit_gm_line,
    building_destroyed_character_line,
    building_destroyed_gm_line,
)


@pytest.mark.asyncio
async def test_building_upkeep_fully_paid(db_conn, test_server):
    """Test building upkeep is deducted when controller has sufficient resources."""
    # Create character
    character = Character(
        identifier="building-owner", name="Building Owner",
        channel_id=999000000000000101, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "building-owner", TEST_GUILD_ID)

    # Create territory controlled by character
    territory = Territory(
        territory_id="test-territory-1", name="Test Territory",
        terrain_type="plains", controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building with upkeep
    building = Building(
        building_id="test-building-1", name="Test Building",
        building_type="barracks", territory_id="test-territory-1",
        durability=10,
        upkeep_ore=5, upkeep_lumber=3,
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Create player resources (more than enough)
    resources = PlayerResources(
        character_id=character.id,
        ore=100, lumber=50, coal=0, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute building upkeep
    events = await execute_building_upkeep(db_conn, TEST_GUILD_ID, 1)

    # Verify BUILDING_UPKEEP_PAID event generated
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'BUILDING_UPKEEP_PAID'
    assert event.event_data['building_id'] == 'test-building-1'
    assert event.event_data['resources_paid'] == {'ore': 5, 'lumber': 3}
    assert character.id in event.event_data['affected_character_ids']

    # Verify resources were deducted
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 95  # 100 - 5
    assert updated_resources.lumber == 47  # 50 - 3

    # Verify building durability unchanged
    updated_building = await Building.fetch_by_building_id(db_conn, "test-building-1", TEST_GUILD_ID)
    assert updated_building.durability == 10

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_upkeep_deficit_single_type(db_conn, test_server):
    """Test durability penalty when short on single resource type."""
    # Create character
    character = Character(
        identifier="deficit-building-owner", name="Deficit Building Owner",
        channel_id=999000000000000102, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "deficit-building-owner", TEST_GUILD_ID)

    # Create territory controlled by character
    territory = Territory(
        territory_id="test-territory-2", name="Test Territory 2",
        terrain_type="plains", controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building with upkeep
    building = Building(
        building_id="test-building-2", name="Test Building 2",
        building_type="barracks", territory_id="test-territory-2",
        durability=10,
        upkeep_ore=10, upkeep_lumber=5,
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Create player resources (short on ore)
    resources = PlayerResources(
        character_id=character.id,
        ore=7, lumber=10, coal=0, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute building upkeep
    events = await execute_building_upkeep(db_conn, TEST_GUILD_ID, 1)

    # Verify BUILDING_UPKEEP_DEFICIT event generated
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'BUILDING_UPKEEP_DEFICIT'
    assert event.event_data['building_id'] == 'test-building-2'
    assert event.event_data['deficit_types'] == ['ore']
    assert event.event_data['durability_penalty'] == 1  # 1 type missing
    assert event.event_data['new_durability'] == 9  # 10 - 1

    # Verify resources were deducted (all available consumed)
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 0  # 7 - 7 (only 7 available)
    assert updated_resources.lumber == 5  # 10 - 5

    # Verify building durability reduced
    updated_building = await Building.fetch_by_building_id(db_conn, "test-building-2", TEST_GUILD_ID)
    assert updated_building.durability == 9  # 10 - 1

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_upkeep_deficit_multiple_types(db_conn, test_server):
    """Test durability penalty when short on multiple resource types."""
    # Create character
    character = Character(
        identifier="multi-deficit-owner", name="Multi Deficit Owner",
        channel_id=999000000000000103, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "multi-deficit-owner", TEST_GUILD_ID)

    # Create territory controlled by character
    territory = Territory(
        territory_id="test-territory-3", name="Test Territory 3",
        terrain_type="plains", controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building with upkeep on multiple resources
    building = Building(
        building_id="test-building-3", name="Test Building 3",
        building_type="barracks", territory_id="test-territory-3",
        durability=10,
        upkeep_ore=5, upkeep_lumber=5, upkeep_coal=5,
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Create player resources (short on ore and lumber)
    resources = PlayerResources(
        character_id=character.id,
        ore=3, lumber=2, coal=10, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute building upkeep
    events = await execute_building_upkeep(db_conn, TEST_GUILD_ID, 1)

    # Verify BUILDING_UPKEEP_DEFICIT event generated
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'BUILDING_UPKEEP_DEFICIT'
    assert 'ore' in event.event_data['deficit_types']
    assert 'lumber' in event.event_data['deficit_types']
    assert event.event_data['durability_penalty'] == 2  # 2 types missing
    assert event.event_data['new_durability'] == 8  # 10 - 2

    # Verify building durability reduced by count of missing types
    updated_building = await Building.fetch_by_building_id(db_conn, "test-building-3", TEST_GUILD_ID)
    assert updated_building.durability == 8

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_upkeep_sorting_order(db_conn, test_server):
    """Test buildings are processed in order: lowest durability first, then territory_id, then oldest."""
    # Create character
    character = Character(
        identifier="sort-test-owner", name="Sort Test Owner",
        channel_id=999000000000000104, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "sort-test-owner", TEST_GUILD_ID)

    # Create territories
    for i in range(2):
        territory = Territory(
            territory_id=f"sort-territory-{i}", name=f"Sort Territory {i}",
            terrain_type="plains", controller_character_id=character.id,
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    # Create buildings with different durabilities - all need 5 ore
    # Building A: durability 5, territory 1
    building_a = Building(
        building_id="sort-building-a", building_type="barracks",
        territory_id="sort-territory-1", durability=5,
        upkeep_ore=5, guild_id=TEST_GUILD_ID
    )
    await building_a.upsert(db_conn)

    # Building B: durability 3 (lowest), territory 0
    building_b = Building(
        building_id="sort-building-b", building_type="barracks",
        territory_id="sort-territory-0", durability=3,
        upkeep_ore=5, guild_id=TEST_GUILD_ID
    )
    await building_b.upsert(db_conn)

    # Building C: durability 5 (same as A), territory 0 (lower than A's territory)
    building_c = Building(
        building_id="sort-building-c", building_type="barracks",
        territory_id="sort-territory-0", durability=5,
        upkeep_ore=5, guild_id=TEST_GUILD_ID
    )
    await building_c.upsert(db_conn)

    # Only enough resources for 2 buildings
    resources = PlayerResources(
        character_id=character.id,
        ore=10, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute building upkeep
    events = await execute_building_upkeep(db_conn, TEST_GUILD_ID, 1)

    # Verify buildings processed in order:
    # 1. sort-building-b (durability 3 - lowest)
    # 2. sort-building-c (durability 5, territory 0 - lower territory than A)
    # 3. sort-building-a (durability 5, territory 1 - gets deficit)

    paid_events = [e for e in events if e.event_type == 'BUILDING_UPKEEP_PAID']
    deficit_events = [e for e in events if e.event_type == 'BUILDING_UPKEEP_DEFICIT']

    assert len(paid_events) == 2
    assert len(deficit_events) == 1

    # The deficit event should be for building A (last one processed)
    assert deficit_events[0].event_data['building_id'] == 'sort-building-a'

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_upkeep_faction_controlled_territory(db_conn, test_server):
    """Test building upkeep uses faction resources when territory is faction-controlled."""
    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Create character with FINANCIAL permission
    character = Character(
        identifier="faction-treasurer", name="Faction Treasurer",
        channel_id=999000000000000105, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "faction-treasurer", TEST_GUILD_ID)

    # Grant FINANCIAL permission
    permission = FactionPermission(
        faction_id=faction.id, character_id=character.id,
        permission_type="FINANCIAL", guild_id=TEST_GUILD_ID
    )
    await permission.upsert(db_conn)

    # Create territory controlled by faction
    territory = Territory(
        territory_id="faction-territory", name="Faction Territory",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building with upkeep
    building = Building(
        building_id="faction-building", name="Faction Building",
        building_type="barracks", territory_id="faction-territory",
        durability=10, upkeep_ore=5, upkeep_lumber=3,
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Create faction resources
    faction_resources = FactionResources(
        faction_id=faction.id,
        ore=100, lumber=50, coal=0, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await faction_resources.upsert(db_conn)

    # Execute building upkeep
    events = await execute_building_upkeep(db_conn, TEST_GUILD_ID, 1)

    # Verify event generated
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'BUILDING_UPKEEP_PAID'
    assert character.id in event.event_data['affected_character_ids']

    # Verify faction resources were deducted
    updated_resources = await FactionResources.fetch_by_faction(db_conn, faction.id, TEST_GUILD_ID)
    assert updated_resources.ore == 95  # 100 - 5
    assert updated_resources.lumber == 47  # 50 - 3

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_upkeep_uncontrolled_territory(db_conn, test_server):
    """Test building in uncontrolled territory takes full durability penalty."""
    # Create territory with no controller
    territory = Territory(
        territory_id="uncontrolled-territory", name="Uncontrolled Territory",
        terrain_type="plains",
        controller_character_id=None, controller_faction_id=None,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building with upkeep on multiple resources
    building = Building(
        building_id="uncontrolled-building", name="Uncontrolled Building",
        building_type="barracks", territory_id="uncontrolled-territory",
        durability=10,
        upkeep_ore=5, upkeep_lumber=3, upkeep_coal=2,
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Execute building upkeep
    events = await execute_building_upkeep(db_conn, TEST_GUILD_ID, 1)

    # Verify BUILDING_UPKEEP_DEFICIT event with all types missing
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'BUILDING_UPKEEP_DEFICIT'
    assert 'ore' in event.event_data['deficit_types']
    assert 'lumber' in event.event_data['deficit_types']
    assert 'coal' in event.event_data['deficit_types']
    assert event.event_data['durability_penalty'] == 3  # 3 types
    assert event.event_data['new_durability'] == 7  # 10 - 3

    # Verify building durability reduced
    updated_building = await Building.fetch_by_building_id(db_conn, "uncontrolled-building", TEST_GUILD_ID)
    assert updated_building.durability == 7

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_destroyed_in_organization_phase(db_conn, test_server):
    """Test buildings with durability <= 0 are destroyed in organization phase."""
    # Create character
    character = Character(
        identifier="destroy-test-owner", name="Destroy Test Owner",
        channel_id=999000000000000106, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "destroy-test-owner", TEST_GUILD_ID)

    # Create territory
    territory = Territory(
        territory_id="destroy-territory", name="Destroy Territory",
        terrain_type="plains", controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building with 0 durability
    building = Building(
        building_id="destroy-building", name="Destroy Building",
        building_type="barracks", territory_id="destroy-territory",
        durability=0, status='ACTIVE',
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Execute organization phase
    events = await destroy_low_durability_buildings(db_conn, TEST_GUILD_ID, 1)

    # Verify BUILDING_DESTROYED event
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'BUILDING_DESTROYED'
    assert event.event_data['building_id'] == 'destroy-building'
    assert event.event_data['territory_id'] == 'destroy-territory'
    assert character.id in event.event_data['affected_character_ids']

    # Verify building status is DESTROYED
    updated_building = await Building.fetch_by_building_id(db_conn, "destroy-building", TEST_GUILD_ID)
    assert updated_building.status == 'DESTROYED'

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_negative_durability_destroyed(db_conn, test_server):
    """Test buildings with negative durability are also destroyed."""
    # Create territory with no controller (for simpler test)
    territory = Territory(
        territory_id="negative-territory", name="Negative Territory",
        terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building with negative durability
    building = Building(
        building_id="negative-building", name="Negative Building",
        building_type="barracks", territory_id="negative-territory",
        durability=-5, status='ACTIVE',
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Execute building destruction
    events = await destroy_low_durability_buildings(db_conn, TEST_GUILD_ID, 1)

    # Verify building is destroyed
    assert len(events) == 1
    assert events[0].event_type == 'BUILDING_DESTROYED'

    updated_building = await Building.fetch_by_building_id(db_conn, "negative-building", TEST_GUILD_ID)
    assert updated_building.status == 'DESTROYED'

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_already_destroyed_building_not_processed(db_conn, test_server):
    """Test that already DESTROYED buildings are not processed for upkeep."""
    # Create character
    character = Character(
        identifier="destroyed-owner", name="Destroyed Owner",
        channel_id=999000000000000107, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "destroyed-owner", TEST_GUILD_ID)

    # Create territory
    territory = Territory(
        territory_id="destroyed-territory", name="Destroyed Territory",
        terrain_type="plains", controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create already destroyed building
    destroyed_building = Building(
        building_id="already-destroyed", name="Already Destroyed",
        building_type="barracks", territory_id="destroyed-territory",
        durability=0, status='DESTROYED',
        upkeep_ore=10,
        guild_id=TEST_GUILD_ID
    )
    await destroyed_building.upsert(db_conn)

    # Create resources
    resources = PlayerResources(
        character_id=character.id,
        ore=100, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute building upkeep
    events = await execute_building_upkeep(db_conn, TEST_GUILD_ID, 1)

    # Verify no events (destroyed building not processed)
    assert len(events) == 0

    # Verify resources unchanged
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 100

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_upkeep_before_unit_upkeep(db_conn, test_server):
    """Test that building upkeep is processed before unit upkeep (building gets resources first)."""
    from db import Unit

    # Create character
    character = Character(
        identifier="priority-owner", name="Priority Owner",
        channel_id=999000000000000108, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "priority-owner", TEST_GUILD_ID)

    # Create territory
    territory = Territory(
        territory_id="priority-territory", name="Priority Territory",
        terrain_type="plains", controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building that needs 7 ore
    building = Building(
        building_id="priority-building", name="Priority Building",
        building_type="barracks", territory_id="priority-territory",
        durability=10, upkeep_ore=7,
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Create unit that also needs 5 ore
    unit = Unit(
        unit_id="priority-unit", name="Priority Unit", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=5,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Only 10 ore available (enough for building 7, but unit would get 3 and be 2 short)
    resources = PlayerResources(
        character_id=character.id,
        ore=10, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute full upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify building upkeep was paid fully
    building_paid_events = [e for e in events if e.event_type == 'BUILDING_UPKEEP_PAID']
    assert len(building_paid_events) == 1
    assert building_paid_events[0].event_data['resources_paid'] == {'ore': 7}

    # Verify unit had deficit (only got 3 ore, was short 2)
    unit_deficit_events = [e for e in events if e.event_type == 'UPKEEP_DEFICIT']
    assert len(unit_deficit_events) == 1
    assert unit_deficit_events[0].event_data['resources_deficit'] == {'ore': 2}

    # Verify building durability unchanged
    updated_building = await Building.fetch_by_building_id(db_conn, "priority-building", TEST_GUILD_ID)
    assert updated_building.durability == 10

    # Verify unit organization reduced (1 type missing)
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "priority-unit", TEST_GUILD_ID)
    assert updated_unit.organization == 9  # 10 - 1

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_building_zero_upkeep_no_event(db_conn, test_server):
    """Test building with zero upkeep generates no events."""
    # Create character
    character = Character(
        identifier="zero-upkeep-owner", name="Zero Upkeep Owner",
        channel_id=999000000000000109, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "zero-upkeep-owner", TEST_GUILD_ID)

    # Create territory
    territory = Territory(
        territory_id="zero-upkeep-territory", name="Zero Upkeep Territory",
        terrain_type="plains", controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create building with zero upkeep
    building = Building(
        building_id="zero-upkeep-building", name="Zero Upkeep Building",
        building_type="monument", territory_id="zero-upkeep-territory",
        durability=10,
        upkeep_ore=0, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0, upkeep_platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    # Execute building upkeep
    events = await execute_building_upkeep(db_conn, TEST_GUILD_ID, 1)

    # Verify no events
    assert len(events) == 0

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


# Event formatting tests

def test_building_upkeep_paid_character_line_format():
    """Test BUILDING_UPKEEP_PAID character line formatting."""
    event_data = {
        'building_id': 'test-bldg',
        'building_name': 'Test Building',
        'resources_paid': {'ore': 5, 'lumber': 3},
        'affected_character_ids': [123]
    }
    line = building_upkeep_paid_character_line(event_data)
    assert 'Test Building' in line
    assert 'ore:5' in line
    assert 'lumber:3' in line


def test_building_upkeep_paid_gm_line_format():
    """Test BUILDING_UPKEEP_PAID GM line formatting."""
    event_data = {
        'building_id': 'test-bldg',
        'building_name': 'Test Building',
        'resources_paid': {'ore': 5, 'lumber': 3},
        'affected_character_ids': [123]
    }
    line = building_upkeep_paid_gm_line(event_data)
    assert 'test-bldg' in line
    assert 'ore:5' in line


def test_building_upkeep_deficit_character_line_format():
    """Test BUILDING_UPKEEP_DEFICIT character line formatting."""
    event_data = {
        'building_id': 'test-bldg',
        'building_name': 'Test Building',
        'deficit_types': ['ore', 'lumber'],
        'durability_penalty': 2,
        'new_durability': 8,
        'affected_character_ids': [123]
    }
    line = building_upkeep_deficit_character_line(event_data)
    assert 'Test Building' in line
    assert 'ore' in line
    assert 'lumber' in line
    assert '-2' in line
    assert '8' in line


def test_building_upkeep_deficit_gm_line_format():
    """Test BUILDING_UPKEEP_DEFICIT GM line formatting."""
    event_data = {
        'building_id': 'test-bldg',
        'durability_penalty': 2,
        'new_durability': 8,
        'affected_character_ids': [123]
    }
    line = building_upkeep_deficit_gm_line(event_data)
    assert 'test-bldg' in line
    assert '-2' in line
    assert '8' in line


def test_building_destroyed_character_line_format():
    """Test BUILDING_DESTROYED character line formatting."""
    event_data = {
        'building_id': 'test-bldg',
        'building_name': 'Test Building',
        'territory_id': 'territory-1',
        'affected_character_ids': [123]
    }
    line = building_destroyed_character_line(event_data)
    assert 'Test Building' in line
    assert 'destroyed' in line
    assert 'territory-1' in line


def test_building_destroyed_gm_line_format():
    """Test BUILDING_DESTROYED GM line formatting."""
    event_data = {
        'building_id': 'test-bldg',
        'building_name': 'Test Building',
        'territory_id': 'territory-1',
        'affected_character_ids': [123]
    }
    line = building_destroyed_gm_line(event_data)
    assert 'test-bldg' in line
    assert 'destroyed' in line
    assert 'territory-1' in line
