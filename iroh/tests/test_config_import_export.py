"""
Comprehensive pytest tests for config import/export functionality.

Tests the full workflow of exporting wargame state to YAML,
importing YAML configurations, and ensuring data integrity.

Run with: pytest test_config_import_export.py -v
"""
import pytest
import asyncpg
import yaml

from db import (
    Territory, Faction, FactionMember, Unit, UnitType,
    PlayerResources, TerritoryAdjacency, WargameConfig, Character,
    ServerConfig
)
from config_manager import ConfigManager


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


@pytest.fixture(scope="function", autouse=True)
async def test_setup(db_conn):
    """Set up test database with required data for each test."""
    # Create test server config
    server_config = ServerConfig(guild_id=TEST_GUILD_ID)
    await server_config.upsert(db_conn)

    # Create test characters for use in imports
    test_characters = [
        Character(
            identifier="test-char-1",
            name="Test Character 1",
            user_id=100000000000000001,
            channel_id=900000000000000001,
            guild_id=TEST_GUILD_ID
        ),
        Character(
            identifier="test-char-2",
            name="Test Character 2",
            user_id=100000000000000002,
            channel_id=900000000000000002,
            guild_id=TEST_GUILD_ID
        ),
        Character(
            identifier="test-char-3",
            name="Test Character 3",
            user_id=100000000000000003,
            channel_id=900000000000000003,
            guild_id=TEST_GUILD_ID
        ),
    ]

    for char in test_characters:
        await char.upsert(db_conn)

    yield

    # Cleanup after each test
    # Delete in reverse dependency order
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


@pytest.fixture(scope="function")
async def clean_wargame_data(db_conn):
    """Clean wargame data before a specific test (but keep characters)."""
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    yield


# ============================================================================
# TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_export_empty_config(db_conn):
    """Test exporting when there's no wargame data."""
    yaml_output = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)

    # Parse YAML to verify it's valid
    config_dict = yaml.safe_load(yaml_output)
    assert 'wargame' in config_dict
    assert 'factions' in config_dict
    assert 'territories' in config_dict
    assert 'unit_types' in config_dict
    assert len(config_dict['factions']) == 0
    assert len(config_dict['territories']) == 0


@pytest.mark.asyncio
async def test_import_basic_config(db_conn, clean_wargame_data):
    """Test importing a basic configuration."""
    basic_config = """
wargame:
  turn: 5
  max_movement_stat: 4
  turn_resolution_enabled: false

factions:
  - faction_id: "test-faction-1"
    name: "Test Faction Alpha"
    leader: "test-char-1"
    members:
      - "test-char-1"
      - "test-char-2"

territories:
  - territory_id: "1"
    name: "Test Territory"
    terrain_type: "plains"
    original_nation: "test-faction-1"
    controller_character_identifier: "test-char-1"
    production:
      ore: 5
      lumber: 3
      coal: 2
      rations: 8
      cloth: 4
      platinum: 0
    adjacent_to: ["2"]

  - territory_id: "2"
    name: "Adjacent Territory"
    terrain_type: "mountain"
    production:
      ore: 10
      lumber: 1
      coal: 5
      rations: 2
      cloth: 0
      platinum: 0
    adjacent_to: ["1"]

unit_types:
  - type_id: "test-infantry"
    name: "Test Infantry"
    nation: "test-faction-1"
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
      rations: 10
      cloth: 5
      platinum: 0
    upkeep:
      rations: 2
      cloth: 1
      platinum: 0

player_resources:
  - character: "test-char-1"
    resources:
      ore: 100
      lumber: 50
      coal: 200
      rations: 150
      cloth: 75
      platinum: 0
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, basic_config)
    assert success, f"Import failed: {message}"

    # Verify imported data
    wargame_config = await WargameConfig.fetch(db_conn, TEST_GUILD_ID)
    assert wargame_config.current_turn == 5

    factions = await Faction.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(factions) == 1
    assert factions[0].name == "Test Faction Alpha"

    territories = await Territory.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(territories) == 2

    unit_types = await UnitType.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(unit_types) == 1

    # Check adjacency
    adjacent_ids = await TerritoryAdjacency.fetch_adjacent(db_conn, "1", TEST_GUILD_ID)
    assert "2" in adjacent_ids

    # Check faction members
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction-1", TEST_GUILD_ID)
    members = await FactionMember.fetch_by_faction(db_conn, faction.id, TEST_GUILD_ID)
    assert len(members) == 2


@pytest.mark.asyncio
async def test_import_with_units(db_conn):
    """Test importing configuration with units."""
    # First set up the required base data (factions, territories, unit types)
    base_config = """
wargame:
  turn: 5

factions:
  - faction_id: "test-faction-1"
    name: "Test Faction"
    members:
      - "test-char-1"
      - "test-char-2"

territories:
  - territory_id: "1"
    terrain_type: "plains"
    original_nation: "test-faction-1"
    controller_character_identifier: "test-char-1"
    production:
      ore: 0
      lumber: 0
      coal: 0
      rations: 0
      cloth: 0
      platinum: 0

  - territory_id: "2"
    terrain_type: "plains"
    controller_character_identifier: "test-char-2"
    production:
      ore: 0
      lumber: 0
      coal: 0
      rations: 0
      cloth: 0
      platinum: 0

unit_types:
  - type_id: "test-infantry"
    name: "Test Infantry"
    nation: "test-faction-1"
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
      rations: 10
      cloth: 5
      platinum: 0
    upkeep:
      rations: 2
      cloth: 1
      platinum: 0
"""
    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, base_config)
    assert success, f"Base config import failed: {message}"

    # Now import units
    config_with_units = """
units:
  - unit_id: "TEST-INF-001"
    name: "First Test Unit"
    type: "test-infantry"
    owner: "test-char-1"
    commander: "test-char-1"
    faction_id: "test-faction-1"
    current_territory_id: "1"

  - unit_id: "TEST-INF-002"
    type: "test-infantry"
    owner: "test-char-2"
    faction_id: "test-faction-1"
    current_territory_id: "2"
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, config_with_units)
    assert success, f"Import failed: {message}"

    # Verify units were created
    units = await Unit.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(units) == 2

    unit1 = await Unit.fetch_by_unit_id(db_conn, "TEST-INF-001", TEST_GUILD_ID)
    assert unit1 is not None
    assert unit1.name == "First Test Unit"
    assert unit1.commander_character_id is not None

    unit2 = await Unit.fetch_by_unit_id(db_conn, "TEST-INF-002", TEST_GUILD_ID)
    assert unit2 is not None
    assert unit2.commander_character_id is None


@pytest.mark.asyncio
async def test_export_full_config(db_conn):
    """Test exporting a full configuration."""
    # First set up a complete configuration
    full_config = """
wargame:
  turn: 5

factions:
  - faction_id: "export-faction"
    name: "Export Faction"
    members:
      - "test-char-1"
      - "test-char-2"

territories:
  - territory_id: "101"
    terrain_type: "plains"
    original_nation: "export-faction"
    controller_character_identifier: "test-char-1"
    production:
      ore: 5
      lumber: 3
      coal: 2
      rations: 8
      cloth: 4
      platinum: 0
    adjacent_to: ["102"]

  - territory_id: "102"
    terrain_type: "mountain"
    production:
      ore: 10
      lumber: 1
      coal: 5
      rations: 2
      cloth: 0
      platinum: 0
    adjacent_to: ["101"]

unit_types:
  - type_id: "export-infantry"
    name: "Export Infantry"
    nation: "export-faction"
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
      rations: 10
      cloth: 5
      platinum: 0
    upkeep:
      rations: 2
      cloth: 1
      platinum: 0

units:
  - unit_id: "EXPORT-001"
    type: "export-infantry"
    owner: "test-char-1"
    faction_id: "export-faction"
    current_territory_id: "101"

  - unit_id: "EXPORT-002"
    type: "export-infantry"
    owner: "test-char-2"
    faction_id: "export-faction"
    current_territory_id: "102"
"""
    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, full_config)
    assert success, f"Import failed: {message}"

    # Now export and verify
    yaml_output = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)
    config_dict = yaml.safe_load(yaml_output)

    # Verify all sections present
    assert 'wargame' in config_dict
    assert 'factions' in config_dict
    assert 'territories' in config_dict
    assert 'unit_types' in config_dict
    assert 'units' in config_dict
    assert 'player_resources' in config_dict

    # Verify content
    assert config_dict['wargame']['turn'] == 5
    assert len(config_dict['factions']) == 1
    assert len(config_dict['territories']) == 2
    assert len(config_dict['unit_types']) == 1
    assert len(config_dict['units']) == 2

    # Verify faction has members
    faction = config_dict['factions'][0]
    assert 'members' in faction
    assert len(faction['members']) == 2

    # Verify units have proper fields
    unit = config_dict['units'][0]
    assert 'unit_id' in unit
    assert 'type' in unit
    assert 'owner' in unit

    # Verify territories have adjacency
    territories_with_adj = [t for t in config_dict['territories'] if 'adjacent_to' in t]
    assert len(territories_with_adj) == 2


@pytest.mark.asyncio
async def test_roundtrip(db_conn, clean_wargame_data):
    """Test export -> import -> export produces same result."""
    # First, import some data
    basic_config = """
wargame:
  turn: 10

factions:
  - faction_id: "roundtrip-faction"
    name: "Roundtrip Faction"
    members:
      - "test-char-1"

territories:
  - territory_id: "99"
    terrain_type: "plains"
    controller_character_identifier: "test-char-1"
    production:
      ore: 1
      lumber: 2
      coal: 3
      rations: 4
      cloth: 5
      platinum: 0
"""
    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, basic_config)
    assert success

    # First export
    yaml_output_1 = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)
    config_dict_1 = yaml.safe_load(yaml_output_1)

    # Clean and reimport
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, yaml_output_1)
    assert success, f"Reimport failed: {message}"

    # Second export
    yaml_output_2 = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)
    config_dict_2 = yaml.safe_load(yaml_output_2)

    # Compare key metrics
    assert config_dict_1['wargame']['turn'] == config_dict_2['wargame']['turn']
    assert len(config_dict_1['factions']) == len(config_dict_2['factions'])
    assert len(config_dict_1['territories']) == len(config_dict_2['territories'])


@pytest.mark.asyncio
async def test_import_validation_missing_characters(db_conn, clean_wargame_data):
    """Test that import fails when referenced characters don't exist."""
    invalid_config = """
wargame:
  turn: 0

factions:
  - faction_id: "test-faction"
    name: "Test Faction"
    leader: "nonexistent-character"
    members:
      - "test-char-1"
      - "another-nonexistent-char"
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, invalid_config)
    assert not success
    assert "Missing characters" in message
    assert "nonexistent-character" in message
    assert "another-nonexistent-char" in message


@pytest.mark.asyncio
async def test_import_validation_malformed_yaml(db_conn):
    """Test that import fails gracefully with malformed YAML."""
    malformed_yaml = """
wargame:
  turn: 0
  this is not valid yaml: [unclosed bracket
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, malformed_yaml)
    assert not success
    assert "Invalid YAML format" in message


@pytest.mark.asyncio
async def test_import_unit_with_nonexistent_type(db_conn, clean_wargame_data):
    """Test that units with nonexistent types are skipped."""
    config_with_bad_unit = """
wargame:
  turn: 0

factions:
  - faction_id: "test-faction"
    name: "Test Faction"
    members:
      - "test-char-1"

territories:
  - territory_id: "1"
    terrain_type: "plains"
    controller_character_identifier: "test-char-1"
    production:
      ore: 0
      lumber: 0
      coal: 0
      rations: 0
      cloth: 0
      platinum: 0

units:
  - unit_id: "BAD-UNIT"
    type: "nonexistent-unit-type"
    owner: "test-char-1"
    faction_id: "test-faction"
    current_territory_id: "1"
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, config_with_bad_unit)
    # Import should succeed but skip the unit
    assert success

    # Verify unit was not created
    units = await Unit.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(units) == 0


@pytest.mark.asyncio
async def test_partial_config_import(db_conn, clean_wargame_data):
    """Test importing configs with only some sections."""
    # Config with only factions
    factions_only = """
factions:
  - faction_id: "faction-1"
    name: "Faction One"
  - faction_id: "faction-2"
    name: "Faction Two"
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, factions_only)
    assert success

    factions = await Faction.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(factions) == 2

    # Now add territories
    territories_only = """
territories:
  - territory_id: "10"
    terrain_type: "plains"
    production:
      ore: 1
      lumber: 1
      coal: 1
      rations: 1
      cloth: 1
      platinum: 0
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, territories_only)
    assert success

    territories = await Territory.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(territories) == 1

    # Verify factions still exist
    factions = await Faction.fetch_all(db_conn, TEST_GUILD_ID)
    assert len(factions) == 2


# ============================================================================
# CHARACTER PRODUCTION AND VP TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_import_character_production(db_conn, clean_wargame_data):
    """Test importing character production values."""
    config_with_production = """
wargame:
  turn: 0

characters:
  - character: "test-char-1"
    production:
      ore: 5
      lumber: 3
      coal: 0
      rations: 0
      cloth: 0
      platinum: 2
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, config_with_production)
    assert success, f"Import failed: {message}"

    # Verify production values were set
    char = await Character.fetch_by_identifier(db_conn, "test-char-1", TEST_GUILD_ID)
    assert char is not None
    assert char.ore_production == 5
    assert char.lumber_production == 3
    assert char.platinum_production == 2
    assert char.coal_production == 0


@pytest.mark.asyncio
async def test_import_character_victory_points(db_conn, clean_wargame_data):
    """Test importing character victory points."""
    config_with_vp = """
wargame:
  turn: 0

characters:
  - character: "test-char-1"
    victory_points: 7

  - character: "test-char-2"
    victory_points: 3
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, config_with_vp)
    assert success, f"Import failed: {message}"

    # Verify VP values were set
    char1 = await Character.fetch_by_identifier(db_conn, "test-char-1", TEST_GUILD_ID)
    assert char1.victory_points == 7

    char2 = await Character.fetch_by_identifier(db_conn, "test-char-2", TEST_GUILD_ID)
    assert char2.victory_points == 3


@pytest.mark.asyncio
async def test_import_character_production_and_vp(db_conn, clean_wargame_data):
    """Test importing both production and VP for a character."""
    config_with_both = """
wargame:
  turn: 0

characters:
  - character: "test-char-1"
    production:
      ore: 10
      lumber: 5
      coal: 0
      rations: 0
      cloth: 0
      platinum: 0
    victory_points: 4
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, config_with_both)
    assert success, f"Import failed: {message}"

    char = await Character.fetch_by_identifier(db_conn, "test-char-1", TEST_GUILD_ID)
    assert char.ore_production == 10
    assert char.lumber_production == 5
    assert char.victory_points == 4


@pytest.mark.asyncio
async def test_export_includes_character_production_and_vp(db_conn, clean_wargame_data):
    """Test that export includes character production and VP values."""
    # Set up character with production and VP
    char = await Character.fetch_by_identifier(db_conn, "test-char-1", TEST_GUILD_ID)
    await db_conn.execute("""
        UPDATE Character
        SET ore_production = 8, lumber_production = 4, platinum_production = 1, victory_points = 5
        WHERE id = $1
    """, char.id)

    # Export
    yaml_output = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)
    config_dict = yaml.safe_load(yaml_output)

    # Verify characters section present
    assert 'characters' in config_dict
    assert len(config_dict['characters']) >= 1

    # Find test-char-1 in exported config
    char_data = None
    for c in config_dict['characters']:
        if c['character'] == 'test-char-1':
            char_data = c
            break

    assert char_data is not None
    assert char_data['production']['ore'] == 8
    assert char_data['production']['lumber'] == 4
    assert char_data['production']['platinum'] == 1
    assert char_data['victory_points'] == 5


@pytest.mark.asyncio
async def test_character_config_roundtrip(db_conn, clean_wargame_data):
    """Test export -> import -> export preserves character production and VP."""
    # Set up character with production and VP
    char = await Character.fetch_by_identifier(db_conn, "test-char-1", TEST_GUILD_ID)
    await db_conn.execute("""
        UPDATE Character
        SET ore_production = 12, lumber_production = 6, rations_production = 20,
            platinum_production = 3, victory_points = 10
        WHERE id = $1
    """, char.id)

    # First export
    yaml_output_1 = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)
    config_dict_1 = yaml.safe_load(yaml_output_1)

    # Reset character values
    await db_conn.execute("""
        UPDATE Character
        SET ore_production = 0, lumber_production = 0, rations_production = 0,
            platinum_production = 0, victory_points = 0
        WHERE id = $1
    """, char.id)

    # Reimport
    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, yaml_output_1)
    assert success, f"Reimport failed: {message}"

    # Second export
    yaml_output_2 = await ConfigManager.export_config(db_conn, TEST_GUILD_ID)
    config_dict_2 = yaml.safe_load(yaml_output_2)

    # Find test-char-1 in both exports
    char_data_1 = next((c for c in config_dict_1['characters'] if c['character'] == 'test-char-1'), None)
    char_data_2 = next((c for c in config_dict_2['characters'] if c['character'] == 'test-char-1'), None)

    assert char_data_1 is not None
    assert char_data_2 is not None

    # Compare production values
    assert char_data_1['production']['ore'] == char_data_2['production']['ore']
    assert char_data_1['production']['lumber'] == char_data_2['production']['lumber']
    assert char_data_1['production']['rations'] == char_data_2['production']['rations']
    assert char_data_1['production']['platinum'] == char_data_2['production']['platinum']
    assert char_data_1['victory_points'] == char_data_2['victory_points']


@pytest.mark.asyncio
async def test_import_character_validates_character_exists(db_conn, clean_wargame_data):
    """Test that import fails when characters section references nonexistent character."""
    config_with_bad_char = """
wargame:
  turn: 0

characters:
  - character: "nonexistent-character"
    production:
      ore: 5
      lumber: 0
      coal: 0
      rations: 0
      cloth: 0
      platinum: 0
"""

    success, message = await ConfigManager.import_config(db_conn, TEST_GUILD_ID, config_with_bad_char)
    assert not success
    assert "Missing characters" in message
    assert "nonexistent-character" in message
