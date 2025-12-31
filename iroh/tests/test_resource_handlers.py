"""
Pytest tests for resource handlers.
Tests verify resource management operations.

Run with: pytest tests/test_resource_handlers.py -v
"""
import pytest
from handlers.resource_handlers import modify_resources
from db import Character, PlayerResources, ServerConfig
from tests.conftest import TEST_GUILD_ID, TEST_GUILD_ID_2


@pytest.mark.asyncio
async def test_modify_resources_existing(db_conn, test_server):
    """Test modifying resources when they already exist."""
    # Create character
    char = Character(
        identifier="resource-char",
        name="Resource Character",
        user_id=100000000000000001,
        channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Refetch to get ID
    char = await Character.fetch_by_identifier(db_conn, "resource-char", TEST_GUILD_ID)

    # Create existing resources
    resources = PlayerResources(
        character_id=char.id,
        ore=100,
        lumber=50,
        coal=200,
        rations=150,
        cloth=75,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Call modify_resources
    success, message, data = await modify_resources(db_conn, "resource-char", TEST_GUILD_ID)

    # Verify success
    assert success is True
    assert data is not None
    assert 'character' in data
    assert 'resources' in data
    assert data['character'].identifier == "resource-char"
    assert data['resources'].ore == 100


@pytest.mark.asyncio
async def test_modify_resources_create_if_missing(db_conn, test_server):
    """Test that modify_resources creates resources if they don't exist."""
    # Create character without resources
    char = Character(
        identifier="no-resource-char",
        name="No Resource Character",
        user_id=100000000000000002,
        channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Call modify_resources
    success, message, data = await modify_resources(db_conn, "no-resource-char", TEST_GUILD_ID)

    # Verify success and resources created
    assert success is True
    assert data is not None
    assert 'resources' in data
    assert data['resources'].ore == 0
    assert data['resources'].lumber == 0
    assert data['resources'].coal == 0
    assert data['resources'].rations == 0
    assert data['resources'].cloth == 0

    # Verify in database
    char = await Character.fetch_by_identifier(db_conn, "no-resource-char", TEST_GUILD_ID)
    fetched_resources = await PlayerResources.fetch_by_character(db_conn, char.id, TEST_GUILD_ID)
    assert fetched_resources is not None


@pytest.mark.asyncio
async def test_modify_resources_nonexistent_character(db_conn, test_server):
    """Test that modify_resources fails for non-existent character."""
    success, message, data = await modify_resources(db_conn, "nonexistent-char", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_resources_guild_isolation(db_conn, test_server_multi_guild):
    """Test that resources are properly isolated between guilds."""
    # Create character with same identifier in both guilds
    char_a = Character(
        identifier="shared-char",
        name="Guild A Character",
        user_id=100000000000000003,
        channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)

    char_b = Character(
        identifier="shared-char",
        name="Guild B Character",
        user_id=100000000000000004,
        channel_id=900000000000000004,
        guild_id=TEST_GUILD_ID_2
    )
    await char_b.upsert(db_conn)

    # Refetch to get IDs
    char_a = await Character.fetch_by_identifier(db_conn, "shared-char", TEST_GUILD_ID)
    char_b = await Character.fetch_by_identifier(db_conn, "shared-char", TEST_GUILD_ID_2)

    # Create resources for guild A
    resources_a = PlayerResources(
        character_id=char_a.id,
        ore=100,
        lumber=50,
        coal=25,
        rations=200,
        cloth=75,
        guild_id=TEST_GUILD_ID
    )
    await resources_a.upsert(db_conn)

    # Create resources for guild B
    resources_b = PlayerResources(
        character_id=char_b.id,
        ore=200,
        lumber=100,
        coal=50,
        rations=300,
        cloth=150,
        guild_id=TEST_GUILD_ID_2
    )
    await resources_b.upsert(db_conn)

    # Modify resources in guild A
    success_a, _, data_a = await modify_resources(db_conn, "shared-char", TEST_GUILD_ID)
    assert success_a is True
    assert data_a['resources'].ore == 100

    # Verify guild B resources unchanged
    fetched_b = await PlayerResources.fetch_by_character(db_conn, char_b.id, TEST_GUILD_ID_2)
    assert fetched_b.ore == 200

    # Query resources for guild B - should return guild B's resources
    success_b, _, data_b = await modify_resources(db_conn, "shared-char", TEST_GUILD_ID_2)
    assert success_b is True
    assert data_b['resources'].ore == 200
    assert data_b['character'].name == "Guild B Character"

    # Verify operations are properly scoped
    assert data_a['character'].guild_id == TEST_GUILD_ID
    assert data_b['character'].guild_id == TEST_GUILD_ID_2
