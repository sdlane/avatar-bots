"""
Pytest tests for setting up and validating test server configuration.
These tests verify that server config setup and cleanup work correctly.

Run with: pytest test_setup_server.py -v
"""
import pytest
import asyncpg
from db import ServerConfig

# Test guild ID
TEST_GUILD_ID = 999999999999999999


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


# ============================================================================
# TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_setup_server(db_conn):
    """Test creating test server config."""
    # Create ServerConfig for test guild
    await db_conn.execute("""
        INSERT INTO ServerConfig (guild_id)
        VALUES ($1)
        ON CONFLICT (guild_id) DO NOTHING;
    """, TEST_GUILD_ID)

    # Verify it was created
    server = await db_conn.fetchrow(
        "SELECT * FROM ServerConfig WHERE guild_id = $1;",
        TEST_GUILD_ID
    )

    assert server is not None, "Server config should have been created"
    assert server['guild_id'] == TEST_GUILD_ID

    # Cleanup
    await db_conn.execute(
        "DELETE FROM ServerConfig WHERE guild_id = $1;",
        TEST_GUILD_ID
    )


@pytest.mark.asyncio
async def test_cleanup_server(db_conn):
    """Test removing test server config."""
    # First create it
    await db_conn.execute("""
        INSERT INTO ServerConfig (guild_id)
        VALUES ($1)
        ON CONFLICT (guild_id) DO NOTHING;
    """, TEST_GUILD_ID)

    # Verify it exists
    server = await db_conn.fetchrow(
        "SELECT * FROM ServerConfig WHERE guild_id = $1;",
        TEST_GUILD_ID
    )
    assert server is not None

    # Now delete it
    result = await db_conn.execute(
        "DELETE FROM ServerConfig WHERE guild_id = $1;",
        TEST_GUILD_ID
    )

    assert result == "DELETE 1", "Should have deleted exactly one row"

    # Verify it's gone
    server = await db_conn.fetchrow(
        "SELECT * FROM ServerConfig WHERE guild_id = $1;",
        TEST_GUILD_ID
    )
    assert server is None, "Server config should have been deleted"


@pytest.mark.asyncio
async def test_server_config_upsert(db_conn):
    """Test using ServerConfig dataclass upsert method."""
    try:
        # Create using dataclass
        server_config = ServerConfig(guild_id=TEST_GUILD_ID)
        await server_config.upsert(db_conn)

        # Verify it was created
        server = await db_conn.fetchrow(
            "SELECT * FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )
        assert server is not None
        assert server['guild_id'] == TEST_GUILD_ID

        # Try upsert again (should not error)
        await server_config.upsert(db_conn)

        # Verify still only one
        count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )
        assert count == 1

    finally:
        # Cleanup
        await db_conn.execute(
            "DELETE FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )


@pytest.mark.asyncio
async def test_server_config_foreign_key_constraint(db_conn):
    """Test that server config cannot be deleted while characters reference it."""
    from db import Character

    try:
        # Create server config
        server_config = ServerConfig(guild_id=TEST_GUILD_ID)
        await server_config.upsert(db_conn)

        # Create a character that depends on it
        char = Character(
            identifier="cascade-test-char",
            name="Cascade Test Character",
            user_id=100000000000000055,
            channel_id=900000000000000055,
            guild_id=TEST_GUILD_ID
        )
        await char.upsert(db_conn)

        # Verify character exists
        fetched_char = await Character.fetch_by_identifier(
            db_conn, "cascade-test-char", TEST_GUILD_ID
        )
        assert fetched_char is not None

        # Try to delete server config (should fail due to foreign key constraint)
        with pytest.raises(Exception):  # asyncpg.ForeignKeyViolationError
            await db_conn.execute(
                "DELETE FROM ServerConfig WHERE guild_id = $1;",
                TEST_GUILD_ID
            )

        # Verify server config still exists
        server = await db_conn.fetchrow(
            "SELECT * FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )
        assert server is not None, "Server config should still exist"

    finally:
        # Cleanup (in proper order)
        await db_conn.execute(
            "DELETE FROM Character WHERE guild_id = $1;",
            TEST_GUILD_ID
        )
        await db_conn.execute(
            "DELETE FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )


@pytest.mark.asyncio
async def test_multiple_server_configs(db_conn):
    """Test that multiple server configs can coexist."""
    guild_ids = [TEST_GUILD_ID, TEST_GUILD_ID + 1, TEST_GUILD_ID + 2]

    try:
        # Create multiple server configs
        for guild_id in guild_ids:
            server_config = ServerConfig(guild_id=guild_id)
            await server_config.upsert(db_conn)

        # Verify all exist
        for guild_id in guild_ids:
            server = await db_conn.fetchrow(
                "SELECT * FROM ServerConfig WHERE guild_id = $1;",
                guild_id
            )
            assert server is not None
            assert server['guild_id'] == guild_id

        # Delete one
        await db_conn.execute(
            "DELETE FROM ServerConfig WHERE guild_id = $1;",
            guild_ids[1]
        )

        # Verify only that one was deleted
        server = await db_conn.fetchrow(
            "SELECT * FROM ServerConfig WHERE guild_id = $1;",
            guild_ids[1]
        )
        assert server is None

        # Verify others still exist
        for guild_id in [guild_ids[0], guild_ids[2]]:
            server = await db_conn.fetchrow(
                "SELECT * FROM ServerConfig WHERE guild_id = $1;",
                guild_id
            )
            assert server is not None

    finally:
        # Cleanup all
        for guild_id in guild_ids:
            await db_conn.execute(
                "DELETE FROM ServerConfig WHERE guild_id = $1;",
                guild_id
            )


@pytest.mark.asyncio
async def test_server_config_unique_constraint(db_conn):
    """Test that guild_id is unique (can't insert duplicate)."""
    try:
        # Create first server config
        await db_conn.execute("""
            INSERT INTO ServerConfig (guild_id)
            VALUES ($1);
        """, TEST_GUILD_ID)

        # Try to create duplicate (should fail)
        with pytest.raises(Exception):  # asyncpg.UniqueViolationError
            await db_conn.execute("""
                INSERT INTO ServerConfig (guild_id)
                VALUES ($1);
            """, TEST_GUILD_ID)

        # But ON CONFLICT DO NOTHING should work
        await db_conn.execute("""
            INSERT INTO ServerConfig (guild_id)
            VALUES ($1)
            ON CONFLICT (guild_id) DO NOTHING;
        """, TEST_GUILD_ID)

        # Verify still only one
        count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )
        assert count == 1

    finally:
        # Cleanup
        await db_conn.execute(
            "DELETE FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )
