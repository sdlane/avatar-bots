"""
Script to verify that wargame tables are clean after test cleanup.
Prints the row counts for all wargame-related tables.
"""
import asyncio
import asyncpg
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - VerifyCleanup - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://AVATAR:password@db:5432/AVATAR"
TEST_GUILD_ID = 999999999  # Use a test guild ID


async def verify_cleanup():
    """Verify all wargame tables are empty for test guild"""
    conn = await asyncpg.connect(DB_URL)

    try:
        logger.info("Verifying cleanup of wargame tables...")

        # List of all wargame tables to check
        tables = [
            'Unit',
            'UnitType',
            'TerritoryAdjacency',
            'Territory',
            'ResourceTransfer',
            'PlayerResources',
            'FactionMember',
            'Faction',
            'WargameConfig'
        ]

        all_clean = True
        total_rows = 0

        for table in tables:
            count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {table} WHERE guild_id = $1;",
                TEST_GUILD_ID
            )

            if count > 0:
                logger.warning(f"  ⚠️  {table}: {count} rows remaining")
                all_clean = False
                total_rows += count

                # Show sample rows for debugging
                rows = await conn.fetch(
                    f"SELECT * FROM {table} WHERE guild_id = $1 LIMIT 3;",
                    TEST_GUILD_ID
                )
                for row in rows:
                    logger.warning(f"      Sample: {dict(row)}")
            else:
                logger.info(f"  ✅ {table}: 0 rows")

        # Also check Character and ServerConfig tables
        logger.info("\nChecking test infrastructure tables...")

        char_count = await conn.fetchval(
            "SELECT COUNT(*) FROM Character WHERE guild_id = $1;",
            TEST_GUILD_ID
        )
        logger.info(f"  Character: {char_count} rows")

        server_count = await conn.fetchval(
            "SELECT COUNT(*) FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )
        logger.info(f"  ServerConfig: {server_count} rows")

        # Summary
        logger.info("\n" + "="*60)
        if all_clean and char_count == 0 and server_count == 0:
            logger.info("✅ All tables clean - cleanup successful!")
        elif all_clean:
            logger.info(f"✅ Wargame tables clean")
            logger.info(f"ℹ️  Test infrastructure remains: {char_count} characters, {server_count} servers")
        else:
            logger.error(f"❌ Cleanup incomplete - {total_rows} wargame rows remaining")
            return False

        logger.info("="*60)
        return all_clean

    finally:
        await conn.close()


if __name__ == "__main__":
    success = asyncio.run(verify_cleanup())
    exit(0 if success else 1)
