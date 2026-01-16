"""
Pytest tests for the wargame configuration import/export system.
These tests use the test characters created by fixtures.

Run with: pytest test_config.py -v
"""
import pytest
import asyncpg
from config_manager import ConfigManager
from db import ServerConfig, Character

# Test guild ID
TEST_GUILD_ID = 999999999999999999

# Sample configuration for testing
SAMPLE_CONFIG = """
wargame:
  turn: 0
  max_movement_stat: 4

factions:
  - faction_id: "fire-nation"
    name: "Fire Nation"
    leader: "taiso"
    members:
      - "taiso"
      - "zhao"

  - faction_id: "earth-kingdom"
    name: "Earth Kingdom"
    leader: "jialun"
    members:
      - "jialun"

player_resources:
  - character: "taiso"
    resources:
      ore: 100
      lumber: 50
      coal: 200
      rations: 150
      cloth: 75
  - character: "jialun"
    resources:
      ore: 150
      lumber: 100
      coal: 50
      rations: 200
      cloth: 100

territories:
  - territory_id: "1"
    name: "Fire Nation Capital"
    terrain_type: "plains"
    original_nation: "fire-nation"
    controller_character_identifier: "taiso"
    production:
      ore: 5
      lumber: 3
      coal: 2
      rations: 8
      cloth: 4
    adjacent_to: ["2"]

  - territory_id: "2"
    name: "Earth Kingdom Territory"
    terrain_type: "mountain"
    original_nation: "earth-kingdom"
    controller_character_identifier: "jialun"
    production:
      ore: 10
      lumber: 1
      coal: 5
      rations: 2
      cloth: 0
    adjacent_to: ["1"]

unit_types:
  - type_id: "infantry"
    name: "Infantry Division"
    nation: "fire-nation"
    stats:
      movement: 2
      organization: 10
      attack: 5
      defense: 5
      siege_attack: 2
      siege_defense: 3
    cost:
      ore: 5
      lumber: 2
      coal: 0
      rations: 10
      cloth: 5
    upkeep:
      rations: 2
      cloth: 1

  - type_id: "cavalry"
    name: "Cavalry Division"
    nation: "earth-kingdom"
    stats:
      movement: 4
      organization: 8
      attack: 7
      defense: 3
      siege_attack: 1
      siege_defense: 2
    cost:
      ore: 3
      lumber: 5
      coal: 0
      rations: 15
      cloth: 8
    upkeep:
      rations: 3
      cloth: 2

units:
  - unit_id: "FN-INF-001"
    name: "First Fire Nation Infantry"
    type: "infantry"
    owner: "taiso"
    commander: "taiso"
    faction_id: "fire-nation"
    current_territory_id: "1"

  - unit_id: "EK-CAV-001"
    name: "Earth Kingdom Cavalry"
    type: "cavalry"
    owner: "jialun"
    commander: "jialun"
    faction_id: "earth-kingdom"
    current_territory_id: "2"
"""


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


@pytest.fixture(scope="function", autouse=True)
async def test_setup(db_conn):
    """Set up test database with required data for each test."""
    # Create test server config
    server_config = ServerConfig(guild_id=TEST_GUILD_ID)
    await server_config.upsert(db_conn)

    # Create test characters for the sample config
    test_characters = [
        Character(
            identifier="taiso",
            name="Fire Lord Taiso",
            user_id=100000000000000001,
            channel_id=900000000000000001,
            guild_id=TEST_GUILD_ID
        ),
        Character(
            identifier="zhao",
            name="Admiral Zhao",
            user_id=100000000000000002,
            channel_id=900000000000000002,
            guild_id=TEST_GUILD_ID
        ),
        Character(
            identifier="jialun",
            name="General Jialun",
            user_id=100000000000000003,
            channel_id=900000000000000003,
            guild_id=TEST_GUILD_ID
        ),
    ]

    for char in test_characters:
        await char.upsert(db_conn)

    yield

    # Cleanup after each test
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM ServerConfig WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================================
# TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_import(db_conn):
    """Test importing a configuration."""
    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, SAMPLE_CONFIG)
    assert success, f"Import failed: {message}"

    # Verify data was imported
    factions = await db_conn.fetch("SELECT * FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    assert len(factions) == 2

    territories = await db_conn.fetch("SELECT * FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    assert len(territories) == 2

    unit_types = await db_conn.fetch("SELECT * FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    assert len(unit_types) == 2

    units = await db_conn.fetch("SELECT * FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    assert len(units) == 2

    resources = await db_conn.fetch("SELECT * FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    assert len(resources) == 2

    adjacencies = await db_conn.fetch("SELECT * FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    assert len(adjacencies) >= 1  # At least one adjacency relationship


@pytest.mark.asyncio
async def test_export(db_conn):
    """Test exporting a configuration."""
    # First import the sample config
    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, SAMPLE_CONFIG)
    assert success, f"Import failed: {message}"

    # Now export
    exported_yaml = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)
    assert exported_yaml is not None
    assert len(exported_yaml) > 0
    assert 'wargame:' in exported_yaml
    assert 'factions:' in exported_yaml
    assert 'territories:' in exported_yaml


@pytest.mark.asyncio
async def test_roundtrip(db_conn):
    """Test import -> export -> import to verify consistency."""
    # First import
    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, SAMPLE_CONFIG)
    assert success, f"Initial import failed: {message}"

    # Export
    exported_yaml = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)

    # Clean and re-import
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, exported_yaml)
    assert success, f"Re-import failed: {message}"

    # Verify counts match
    factions = await db_conn.fetch("SELECT COUNT(*) as count FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    territories = await db_conn.fetch("SELECT COUNT(*) as count FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    units = await db_conn.fetch("SELECT COUNT(*) as count FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)

    assert factions[0]['count'] == 2
    assert territories[0]['count'] == 2
    assert units[0]['count'] == 2


@pytest.mark.asyncio
async def test_validation(db_conn):
    """Test validation - should fail with missing character."""
    invalid_config = """
wargame:
  turn: 0

factions:
  - faction_id: "test-faction"
    name: "Test Faction"
    leader: "nonexistent-character"
    members:
      - "nonexistent-character"
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, invalid_config)
    assert not success, "Validation should have rejected config with missing character"
    assert "Missing characters" in message
