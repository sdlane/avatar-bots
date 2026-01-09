"""
Pytest tests for character production phase in turn resolution.
Tests verify that character production values generate resources and events.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_character_production.py -v
"""
import pytest
from handlers.turn_handlers import _collect_character_production, execute_resource_collection_phase
from db import Character, PlayerResources
from tests.conftest import TEST_GUILD_ID


@pytest.mark.asyncio
async def test_character_production_basic(db_conn, test_server):
    """Test basic character production."""
    # Create character with production values
    character = Character(
        identifier="prod-char", name="Producer",
        channel_id=999000000000000001, guild_id=TEST_GUILD_ID,
        ore_production=5, lumber_production=3, rations_production=10, platinum_production=2
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "prod-char", TEST_GUILD_ID)

    # Execute character production
    events = await _collect_character_production(db_conn, TEST_GUILD_ID, 1)

    # Verify event generated
    assert len(events) == 1
    event = events[0]
    assert event.phase == 'RESOURCE_COLLECTION'
    assert event.event_type == 'CHARACTER_PRODUCTION'
    assert event.entity_type == 'character'
    assert event.entity_id == character.id
    assert event.event_data['resources']['ore'] == 5
    assert event.event_data['resources']['lumber'] == 3
    assert event.event_data['resources']['rations'] == 10
    assert event.event_data['resources']['platinum'] == 2

    # Verify PlayerResources created
    resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert resources is not None
    assert resources.ore == 5
    assert resources.lumber == 3
    assert resources.rations == 10
    assert resources.platinum == 2

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_character_production_zero(db_conn, test_server):
    """Test that zero production generates no events."""
    # Create character with NO production
    character = Character(
        identifier="zero-prod", name="No Production",
        channel_id=999000000000000002, guild_id=TEST_GUILD_ID
        # All production defaults to 0
    )
    await character.upsert(db_conn)

    # Execute character production
    events = await _collect_character_production(db_conn, TEST_GUILD_ID, 1)

    # Verify no events generated
    assert len(events) == 0

    # Cleanup
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_character_production_accumulation(db_conn, test_server):
    """Test that production accumulates with existing resources."""
    # Create character with production
    character = Character(
        identifier="accum-char", name="Accumulator",
        channel_id=999000000000000003, guild_id=TEST_GUILD_ID,
        ore_production=10
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "accum-char", TEST_GUILD_ID)

    # Create existing resources
    resources = PlayerResources(
        character_id=character.id, ore=50, guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute character production
    events = await _collect_character_production(db_conn, TEST_GUILD_ID, 1)

    # Verify resources accumulated
    resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert resources.ore == 60  # 50 + 10

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_character_production_multiple_characters(db_conn, test_server):
    """Test production with multiple characters."""
    # Create two characters with production
    char1 = Character(
        identifier="prod-char1", name="Producer 1",
        channel_id=999000000000000004, guild_id=TEST_GUILD_ID,
        platinum_production=5
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "prod-char1", TEST_GUILD_ID)

    char2 = Character(
        identifier="prod-char2", name="Producer 2",
        channel_id=999000000000000005, guild_id=TEST_GUILD_ID,
        ore_production=8, rations_production=12
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "prod-char2", TEST_GUILD_ID)

    # Create character with no production (should be skipped)
    char3 = Character(
        identifier="no-prod-char", name="No Producer",
        channel_id=999000000000000006, guild_id=TEST_GUILD_ID
    )
    await char3.upsert(db_conn)

    # Execute character production
    events = await _collect_character_production(db_conn, TEST_GUILD_ID, 1)

    # Verify two events generated (not three)
    assert len(events) == 2

    # Verify each character got their production
    res1 = await PlayerResources.fetch_by_character(db_conn, char1.id, TEST_GUILD_ID)
    res2 = await PlayerResources.fetch_by_character(db_conn, char2.id, TEST_GUILD_ID)
    res3 = await PlayerResources.fetch_by_character(db_conn, char3.id, TEST_GUILD_ID)

    assert res1.platinum == 5
    assert res2.ore == 8
    assert res2.rations == 12
    assert res3 is None  # No resources created for non-producer

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_character_production_before_territory(db_conn, test_server):
    """Test that character production runs before territory production in resource collection phase."""
    from db import Territory

    # Create character with production
    character = Character(
        identifier="both-prod", name="Both Producer",
        channel_id=999000000000000007, guild_id=TEST_GUILD_ID,
        ore_production=10  # Character produces 10 ore
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "both-prod", TEST_GUILD_ID)

    # Create territory controlled by same character
    territory = Territory(
        territory_id=200, name="Test Territory", terrain_type="plains",
        ore_production=5,  # Territory produces 5 ore
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Execute full resource collection phase
    events = await execute_resource_collection_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify two events generated (one for character production, one for territory)
    assert len(events) == 2

    # Verify character production event came first
    assert events[0].event_type == 'CHARACTER_PRODUCTION'
    assert events[1].event_type == 'TERRITORY_PRODUCTION'

    # Verify total resources = character production + territory production
    resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert resources.ore == 15  # 10 + 5

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)
