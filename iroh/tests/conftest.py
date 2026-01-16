"""
Pytest configuration for test path setup and shared fixtures.
"""
import sys
from pathlib import Path
import pytest
import asyncpg

# Add parent directory to path so tests can import from iroh modules
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Import DB models after path is set
from db import ServerConfig

# Test guild IDs
TEST_GUILD_ID = 999999999999999999
TEST_GUILD_ID_2 = 999999999999999998


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
    """Set up test server config for TEST_GUILD_ID."""
    server_config = ServerConfig(guild_id=TEST_GUILD_ID)
    await server_config.upsert(db_conn)

    yield

    # Cleanup in reverse dependency order
    await db_conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM War WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM ServerConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.fixture(scope="function")
async def test_server_multi_guild(db_conn):
    """Set up test server configs for both TEST_GUILD_ID and TEST_GUILD_ID_2."""
    server_config_1 = ServerConfig(guild_id=TEST_GUILD_ID)
    await server_config_1.upsert(db_conn)

    server_config_2 = ServerConfig(guild_id=TEST_GUILD_ID_2)
    await server_config_2.upsert(db_conn)

    yield

    # Cleanup in reverse dependency order
    await db_conn.execute("DELETE FROM WarParticipant WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM War WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Alliance WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Unit WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM BuildingType WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM FactionResources WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Character WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM ServerConfig WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
