"""
Pytest tests for resource collection phase in turn resolution.
Tests verify resource aggregation, PlayerResources creation/update, and event generation.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_resource_collection.py -v
"""
import pytest
from handlers.turn_handlers import execute_resource_collection_phase
from db import Character, Territory, PlayerResources
from tests.conftest import TEST_GUILD_ID


@pytest.mark.asyncio
async def test_resource_collection_basic(db_conn, test_server):
    """Test basic resource collection from a single territory."""
    # Create character
    character = Character(
        identifier="resource-char", name="Resource Collector",
        channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "resource-char", TEST_GUILD_ID)

    # Create territory with production
    territory = Territory(
        territory_id=100, name="Resource Territory", terrain_type="plains",
        ore_production=10, lumber_production=5, coal_production=3,
        rations_production=15, cloth_production=7,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify event generated
    assert len(events) == 1
    event = events[0]
    assert event.phase == 'RESOURCE_COLLECTION'
    assert event.event_type == 'RESOURCE_COLLECTION'
    assert event.entity_type == 'character'
    assert event.entity_id == character.id
    assert 'affected_character_ids' in event.event_data
    assert event.event_data['affected_character_ids'] == [character.id]
    assert event.event_data['character_name'] == character.name
    assert event.event_data['resources']['ore'] == 10
    assert event.event_data['resources']['lumber'] == 5
    assert event.event_data['resources']['coal'] == 3
    assert event.event_data['resources']['rations'] == 15
    assert event.event_data['resources']['cloth'] == 7
    assert event.event_data['resources']['platinum'] == 0

    # Verify PlayerResources created and updated
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is not None
    assert player_resources.ore == 10
    assert player_resources.lumber == 5
    assert player_resources.coal == 3
    assert player_resources.rations == 15
    assert player_resources.cloth == 7
    assert player_resources.platinum == 0

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_resource_collection_multiple_territories(db_conn, test_server):
    """Test resource collection aggregates across multiple territories."""
    # Create character
    character = Character(
        identifier="multi-terr-char", name="Multi Territory Owner",
        channel_id=999000000000000002, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "multi-terr-char", TEST_GUILD_ID)

    # Create three territories with different production
    territory1 = Territory(
        territory_id=101, name="Territory 1", terrain_type="plains",
        ore_production=10, lumber_production=5, coal_production=2,
        rations_production=8, cloth_production=3,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id=102, name="Territory 2", terrain_type="mountain",
        ore_production=15, lumber_production=2, coal_production=8,
        rations_production=4, cloth_production=1,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    territory3 = Territory(
        territory_id=103, name="Territory 3", terrain_type="plains",
        ore_production=5, lumber_production=10, coal_production=3,
        rations_production=12, cloth_production=6,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory3.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify single event generated (aggregated)
    assert len(events) == 1
    event = events[0]
    assert event.entity_id == character.id
    assert 'affected_character_ids' in event.event_data
    assert event.event_data['affected_character_ids'] == [character.id]

    # Verify aggregated totals
    assert event.event_data['resources']['ore'] == 30  # 10+15+5
    assert event.event_data['resources']['lumber'] == 17  # 5+2+10
    assert event.event_data['resources']['coal'] == 13  # 2+8+3
    assert event.event_data['resources']['rations'] == 24  # 8+4+12
    assert event.event_data['resources']['cloth'] == 10  # 3+1+6
    assert event.event_data['resources']['platinum'] == 0

    # Verify PlayerResources has aggregated totals
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources.ore == 30
    assert player_resources.lumber == 17
    assert player_resources.coal == 13
    assert player_resources.rations == 24
    assert player_resources.cloth == 10
    assert player_resources.platinum == 0

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_resource_collection_no_controller(db_conn, test_server):
    """Test that uncontrolled territories produce nothing."""
    # Create territory with NO controller
    territory = Territory(
        territory_id=104, name="Uncontrolled Territory", terrain_type="plains",
        ore_production=20, lumber_production=15, coal_production=10,
        rations_production=25, cloth_production=12,
        controller_character_id=None,  # No controller
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify no events generated
    assert len(events) == 0

    # Verify no PlayerResources created
    all_resources = await db_conn.fetch(
        "SELECT * FROM PlayerResources WHERE guild_id = $1;",
        TEST_GUILD_ID
    )
    assert len(all_resources) == 0

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_resource_collection_zero_production(db_conn, test_server):
    """Test that territories with zero production generate no events."""
    # Create character
    character = Character(
        identifier="zero-prod-char", name="Zero Production Owner",
        channel_id=999000000000000003, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "zero-prod-char", TEST_GUILD_ID)

    # Create territory with ZERO production
    territory = Territory(
        territory_id=105, name="Barren Territory", terrain_type="desert",
        ore_production=0, lumber_production=0, coal_production=0,
        rations_production=0, cloth_production=0,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify no events generated (skip zero production)
    assert len(events) == 0

    # Verify no PlayerResources created
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is None

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_resource_collection_new_player(db_conn, test_server):
    """Test that PlayerResources is created for new players."""
    # Create character (no existing PlayerResources)
    character = Character(
        identifier="new-player", name="New Player",
        channel_id=999000000000000004, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "new-player", TEST_GUILD_ID)

    # Verify no PlayerResources exists yet
    assert await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID) is None

    # Create territory
    territory = Territory(
        territory_id=106, name="First Territory", terrain_type="plains",
        ore_production=5, lumber_production=3, coal_production=2,
        rations_production=10, cloth_production=4,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify event generated
    assert len(events) == 1
    event = events[0]
    assert 'affected_character_ids' in event.event_data
    assert event.event_data['affected_character_ids'] == [character.id]

    # Verify PlayerResources created with correct values
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources is not None
    assert player_resources.ore == 5
    assert player_resources.lumber == 3
    assert player_resources.coal == 2
    assert player_resources.rations == 10
    assert player_resources.cloth == 4

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_resource_collection_accumulation(db_conn, test_server):
    """Test that resources accumulate over multiple turns."""
    # Create character with existing resources
    character = Character(
        identifier="accum-char", name="Accumulating Player",
        channel_id=999000000000000005, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "accum-char", TEST_GUILD_ID)

    # Create initial PlayerResources
    initial_resources = PlayerResources(
        character_id=character.id,
        ore=100, lumber=50, coal=75, rations=200, cloth=60, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await initial_resources.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=107, name="Productive Territory", terrain_type="plains",
        ore_production=10, lumber_production=5, coal_production=8,
        rations_production=20, cloth_production=12,
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify event generated
    assert len(events) == 1
    event = events[0]
    assert 'affected_character_ids' in event.event_data
    assert event.event_data['affected_character_ids'] == [character.id]

    # Verify resources accumulated (added to existing)
    player_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert player_resources.ore == 110  # 100 + 10
    assert player_resources.lumber == 55  # 50 + 5
    assert player_resources.coal == 83  # 75 + 8
    assert player_resources.rations == 220  # 200 + 20
    assert player_resources.cloth == 72  # 60 + 12
    assert player_resources.platinum == 0  # 0 + 0

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_resource_collection_multiple_characters(db_conn, test_server):
    """Test resource collection with multiple characters controlling territories."""
    # Create two characters
    char1 = Character(
        identifier="player1", name="Player One",
        channel_id=999000000000000006, guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "player1", TEST_GUILD_ID)

    char2 = Character(
        identifier="player2", name="Player Two",
        channel_id=999000000000000007, guild_id=TEST_GUILD_ID
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "player2", TEST_GUILD_ID)

    # Create territories for each character
    territory1 = Territory(
        territory_id=108, terrain_type="plains",
        ore_production=10, lumber_production=5,
        controller_character_id=char1.id,
        guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id=109, terrain_type="mountain",
        ore_production=15, coal_production=8,
        controller_character_id=char2.id,
        guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # Execute resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify two events generated (one per character)
    assert len(events) == 2

    # Verify each character got their own event
    char1_event = next(e for e in events if e.entity_id == char1.id)
    char2_event = next(e for e in events if e.entity_id == char2.id)

    assert 'affected_character_ids' in char1_event.event_data
    assert char1_event.event_data['affected_character_ids'] == [char1.id]
    assert 'affected_character_ids' in char2_event.event_data
    assert char2_event.event_data['affected_character_ids'] == [char2.id]

    assert char1_event.event_data['resources']['ore'] == 10
    assert char1_event.event_data['resources']['lumber'] == 5
    assert char2_event.event_data['resources']['ore'] == 15
    assert char2_event.event_data['resources']['coal'] == 8

    # Verify PlayerResources for both characters
    res1 = await PlayerResources.fetch_by_character(db_conn, char1.id, TEST_GUILD_ID)
    res2 = await PlayerResources.fetch_by_character(db_conn, char2.id, TEST_GUILD_ID)

    assert res1.ore == 10
    assert res1.lumber == 5
    assert res2.ore == 15
    assert res2.coal == 8

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)
