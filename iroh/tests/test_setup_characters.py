"""
Pytest tests for setting up and validating test characters.
These tests verify that test character setup and cleanup work correctly.

Run with: pytest test_setup_characters.py -v
"""
import pytest
import asyncpg
from db import Character, ServerConfig

# Test guild ID
TEST_GUILD_ID = 999999999999999999

# Test characters to create
TEST_CHARACTERS = [
    ("taiso", "Fire Lord Taiso"),
    ("zhao", "Admiral Zhao"),
    ("jialun", "General Jialun")
]


@pytest.fixture(scope="function")
async def db_conn():
    """Provide a database connection for each test."""
    pool = await asyncpg.create_pool(
        host='db',
        port=5432,
        user='AVATAR',
        password='password',
        database='AVATAR',
        min_size=1,
        max_size=3
    )
    try:
        async with pool.acquire() as conn:
            yield conn
    finally:
        await pool.close()


@pytest.fixture(scope="function")
async def test_server(db_conn):
    """Set up test server config before tests."""
    # Create test server config
    server_config = ServerConfig(guild_id=TEST_GUILD_ID)
    await server_config.upsert(db_conn)

    yield

    # Cleanup server config after test
    await db_conn.execute("DELETE FROM ServerConfig WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_setup_characters(db_conn, test_server):
    """Test creating test characters."""
    # Verify server config exists
    server = await db_conn.fetchrow(
        "SELECT * FROM ServerConfig WHERE guild_id = $1;",
        TEST_GUILD_ID
    )
    assert server is not None, "Server config should exist"

    # Create test characters
    created_count = 0
    for identifier, name in TEST_CHARACTERS:
        char = Character(
            identifier=identifier,
            name=name,
            user_id=100000000000000000 + created_count + 1,
            channel_id=900000000000000000 + created_count + 1,
            guild_id=TEST_GUILD_ID
        )
        await char.upsert(db_conn)
        created_count += 1

    assert created_count == len(TEST_CHARACTERS)

    # Verify characters were created
    for identifier, name in TEST_CHARACTERS:
        char = await Character.fetch_by_identifier(db_conn, identifier, TEST_GUILD_ID)
        assert char is not None, f"Character {identifier} should exist"
        assert char.name == name
        assert char.identifier == identifier
        assert char.guild_id == TEST_GUILD_ID

    # Cleanup
    for identifier, _ in TEST_CHARACTERS:
        await db_conn.execute(
            "DELETE FROM Character WHERE identifier = $1 AND guild_id = $2;",
            identifier, TEST_GUILD_ID
        )


@pytest.mark.asyncio
async def test_cleanup_characters(db_conn, test_server):
    """Test cleaning up test characters."""
    # First create the characters
    for idx, (identifier, name) in enumerate(TEST_CHARACTERS):
        char = Character(
            identifier=identifier,
            name=name,
            user_id=100000000000000000 + idx + 1,
            channel_id=900000000000000000 + idx + 1,
            guild_id=TEST_GUILD_ID
        )
        await char.upsert(db_conn)

    # Verify they exist
    for identifier, _ in TEST_CHARACTERS:
        char = await Character.fetch_by_identifier(db_conn, identifier, TEST_GUILD_ID)
        assert char is not None

    # Now cleanup
    deleted_count = 0
    for identifier, _ in TEST_CHARACTERS:
        result = await db_conn.execute(
            "DELETE FROM Character WHERE identifier = $1 AND guild_id = $2;",
            identifier, TEST_GUILD_ID
        )
        if result.startswith("DELETE 1"):
            deleted_count += 1

    assert deleted_count == len(TEST_CHARACTERS)

    # Verify they were deleted
    for identifier, _ in TEST_CHARACTERS:
        char = await Character.fetch_by_identifier(db_conn, identifier, TEST_GUILD_ID)
        assert char is None, f"Character {identifier} should have been deleted"


@pytest.mark.asyncio
async def test_character_upsert(db_conn, test_server):
    """Test that character upsert works correctly (insert and update)."""
    identifier = "test-upsert-char"
    original_name = "Original Name"
    updated_name = "Updated Name"

    # First insert
    char = Character(
        identifier=identifier,
        name=original_name,
        user_id=100000000000000099,
        channel_id=900000000000000099,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Verify it was created
    fetched = await Character.fetch_by_identifier(db_conn, identifier, TEST_GUILD_ID)
    assert fetched is not None
    assert fetched.name == original_name

    # Now update (upsert with same identifier)
    char.name = updated_name
    await char.upsert(db_conn)

    # Verify it was updated
    fetched = await Character.fetch_by_identifier(db_conn, identifier, TEST_GUILD_ID)
    assert fetched is not None
    assert fetched.name == updated_name

    # Cleanup
    await db_conn.execute(
        "DELETE FROM Character WHERE identifier = $1 AND guild_id = $2;",
        identifier, TEST_GUILD_ID
    )


@pytest.mark.asyncio
async def test_character_requires_server_config(db_conn):
    """Test that creating a character without server config fails."""
    # Don't create server config

    char = Character(
        identifier="orphan-char",
        name="Orphan Character",
        user_id=100000000000000088,
        channel_id=900000000000000088,
        guild_id=TEST_GUILD_ID
    )

    # This should fail due to foreign key constraint
    with pytest.raises(Exception):  # asyncpg.ForeignKeyViolationError
        await char.upsert(db_conn)


@pytest.mark.asyncio
async def test_character_isolation_by_guild(db_conn, test_server):
    """Test that characters are properly isolated by guild_id."""
    other_guild_id = TEST_GUILD_ID + 1

    # Create server config for other guild
    other_server = ServerConfig(guild_id=other_guild_id)
    await other_server.upsert(db_conn)

    try:
        # Create character in test guild
        char1 = Character(
            identifier="shared-identifier",
            name="Test Guild Character",
            user_id=100000000000000077,
            channel_id=900000000000000077,
            guild_id=TEST_GUILD_ID
        )
        await char1.upsert(db_conn)

        # Create character with same identifier in other guild (should succeed)
        char2 = Character(
            identifier="shared-identifier",
            name="Other Guild Character",
            user_id=100000000000000078,
            channel_id=900000000000000078,
            guild_id=other_guild_id
        )
        await char2.upsert(db_conn)

        # Verify both exist independently
        fetched1 = await Character.fetch_by_identifier(db_conn, "shared-identifier", TEST_GUILD_ID)
        fetched2 = await Character.fetch_by_identifier(db_conn, "shared-identifier", other_guild_id)

        assert fetched1 is not None
        assert fetched2 is not None
        assert fetched1.name == "Test Guild Character"
        assert fetched2.name == "Other Guild Character"
        assert fetched1.guild_id == TEST_GUILD_ID
        assert fetched2.guild_id == other_guild_id

    finally:
        # Cleanup
        await db_conn.execute(
            "DELETE FROM Character WHERE identifier = $1 AND guild_id IN ($2, $3);",
            "shared-identifier", TEST_GUILD_ID, other_guild_id
        )
        await db_conn.execute(
            "DELETE FROM ServerConfig WHERE guild_id = $1;",
            other_guild_id
        )
