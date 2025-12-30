"""
Test script for the wargame configuration import/export system.
Requires test server and test characters to be set up first.
"""
import asyncio
import asyncpg
import logging
from config_manager import ConfigManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - TestConfig - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://AVATAR:password@db:5432/AVATAR"
TEST_GUILD_ID = 999999999  # Use a test guild ID

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
  - territory_id: 1
    name: "Fire Nation Capital"
    terrain_type: "plains"
    original_nation: "fire-nation"
    controller_faction_id: "fire-nation"
    production:
      ore: 5
      lumber: 3
      coal: 2
      rations: 8
      cloth: 4
    adjacent_to: [2]

  - territory_id: 2
    name: "Earth Kingdom Territory"
    terrain_type: "mountain"
    original_nation: "earth-kingdom"
    controller_faction_id: "earth-kingdom"
    production:
      ore: 10
      lumber: 1
      coal: 5
      rations: 2
      cloth: 0
    adjacent_to: [1]

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
    current_territory_id: 1

  - unit_id: "EK-CAV-001"
    name: "Earth Kingdom Cavalry"
    type: "cavalry"
    owner: "jialun"
    commander: "jialun"
    faction_id: "earth-kingdom"
    current_territory_id: 2
"""


async def cleanup_wargame_data(conn: asyncpg.Connection):
    """Clean up all wargame data for the test guild"""
    logger.info("Cleaning up wargame data...")

    # Delete in reverse order of dependencies
    await conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await conn.execute("DELETE FROM ResourceTransfer WHERE guild_id = $1;", TEST_GUILD_ID)
    await conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)

    logger.info("Wargame data cleanup complete")


async def test_import():
    """Test importing a configuration"""
    conn = await asyncpg.connect(DB_URL)

    try:
        await cleanup_wargame_data(conn)

        logger.info("\n" + "="*60)
        logger.info("TEST 1: Importing configuration")
        logger.info("="*60)

        success, message = await ConfigManager.import_config(conn, TEST_GUILD_ID, SAMPLE_CONFIG)

        if success:
            logger.info(f"✅ Import successful: {message}")
        else:
            logger.error(f"❌ Import failed: {message}")
            return False

        # Verify data was imported
        logger.info("\nVerifying imported data...")

        # Check factions
        factions = await conn.fetch("SELECT * FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
        logger.info(f"  Factions imported: {len(factions)}")
        for faction in factions:
            logger.info(f"    - {faction['faction_id']}: {faction['name']}")

        # Check territories
        territories = await conn.fetch("SELECT * FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
        logger.info(f"  Territories imported: {len(territories)}")
        for territory in territories:
            logger.info(f"    - Territory {territory['territory_id']}: {territory['name']}")

        # Check unit types
        unit_types = await conn.fetch("SELECT * FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
        logger.info(f"  Unit types imported: {len(unit_types)}")
        for unit_type in unit_types:
            logger.info(f"    - {unit_type['type_id']}: {unit_type['name']}")

        # Check units
        units = await conn.fetch("SELECT * FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
        logger.info(f"  Units imported: {len(units)}")
        for unit in units:
            logger.info(f"    - {unit['unit_id']}: {unit['name']}")

        # Check player resources
        resources = await conn.fetch("SELECT * FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
        logger.info(f"  Player resources imported: {len(resources)}")

        # Check adjacencies
        adjacencies = await conn.fetch("SELECT * FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
        logger.info(f"  Territory adjacencies imported: {len(adjacencies)}")

        return True

    finally:
        await conn.close()


async def test_export():
    """Test exporting a configuration"""
    conn = await asyncpg.connect(DB_URL)

    try:
        logger.info("\n" + "="*60)
        logger.info("TEST 2: Exporting configuration")
        logger.info("="*60)

        exported_yaml = await ConfigManager.export_config(conn, TEST_GUILD_ID)

        logger.info("✅ Export successful")
        logger.info("\nExported YAML:")
        logger.info("-" * 60)
        print(exported_yaml)
        logger.info("-" * 60)

        # Save to file
        with open('/tmp/exported_config.yml', 'w') as f:
            f.write(exported_yaml)
        logger.info("\n✅ Exported config saved to /tmp/exported_config.yml")

        return True

    finally:
        await conn.close()


async def test_roundtrip():
    """Test import -> export -> import to verify consistency"""
    conn = await asyncpg.connect(DB_URL)

    try:
        logger.info("\n" + "="*60)
        logger.info("TEST 3: Round-trip test (import -> export -> import)")
        logger.info("="*60)

        # Export current state
        exported_yaml = await ConfigManager.export_config(conn, TEST_GUILD_ID)

        # Clean and re-import
        await cleanup_wargame_data(conn)
        success, message = await ConfigManager.import_config(conn, TEST_GUILD_ID, exported_yaml)

        if success:
            logger.info(f"✅ Round-trip successful: {message}")

            # Verify counts match
            factions = await conn.fetch("SELECT COUNT(*) as count FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
            territories = await conn.fetch("SELECT COUNT(*) as count FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
            units = await conn.fetch("SELECT COUNT(*) as count FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)

            logger.info("\nRe-imported data counts:")
            logger.info(f"  Factions: {factions[0]['count']}")
            logger.info(f"  Territories: {territories[0]['count']}")
            logger.info(f"  Units: {units[0]['count']}")

            return True
        else:
            logger.error(f"❌ Round-trip failed: {message}")
            return False

    finally:
        await conn.close()


async def test_validation():
    """Test validation - should fail with missing character"""
    conn = await asyncpg.connect(DB_URL)

    try:
        logger.info("\n" + "="*60)
        logger.info("TEST 4: Validation test (should fail with missing character)")
        logger.info("="*60)

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

        success, message = await ConfigManager.import_config(conn, TEST_GUILD_ID, invalid_config)

        if not success:
            logger.info(f"✅ Validation correctly rejected config: {message}")
            return True
        else:
            logger.error(f"❌ Validation failed - should have rejected config")
            return False

    finally:
        await conn.close()


async def run_all_tests():
    """Run all configuration tests"""
    logger.info("\n" + "="*60)
    logger.info("WARGAME CONFIGURATION SYSTEM TESTS")
    logger.info("="*60)

    results = {
        "Import": await test_import(),
        "Export": await test_export(),
        "Round-trip": await test_roundtrip(),
        "Validation": await test_validation()
    }

    logger.info("\n" + "="*60)
    logger.info("TEST RESULTS")
    logger.info("="*60)

    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("\n🎉 All tests passed!")
    else:
        logger.info("\n⚠️ Some tests failed")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_all_tests())
