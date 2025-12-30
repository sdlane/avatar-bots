"""
Test script to set up test server configuration.
"""
import asyncio
import asyncpg
import logging
from db import ServerConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - TestSetupServer - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://AVATAR:password@db:5432/AVATAR"
TEST_GUILD_ID = 999999999  # Use a test guild ID


async def setup_test_server():
    """Create test server config"""
    conn = await asyncpg.connect(DB_URL)

    try:
        logger.info(f"Setting up test server config for guild {TEST_GUILD_ID}...")

        # Create ServerConfig for test guild
        await conn.execute("""
            INSERT INTO ServerConfig (guild_id)
            VALUES ($1)
            ON CONFLICT (guild_id) DO NOTHING;
        """, TEST_GUILD_ID)

        # Verify it was created
        server = await conn.fetchrow(
            "SELECT * FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )

        if server:
            logger.info(f"✅ Test server config created successfully: guild_id={TEST_GUILD_ID}")
            return True
        else:
            logger.error("❌ Failed to create test server config")
            return False

    finally:
        await conn.close()


async def cleanup_test_server():
    """Remove test server config and all related data"""
    conn = await asyncpg.connect(DB_URL)

    try:
        logger.info(f"Cleaning up test server config for guild {TEST_GUILD_ID}...")

        # Delete server config (CASCADE will delete all related data)
        result = await conn.execute(
            "DELETE FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )

        logger.info(f"✅ Test server config cleaned up: {result}")
        return True

    finally:
        await conn.close()


if __name__ == "__main__":
    # Run setup
    success = asyncio.run(setup_test_server())

    if success:
        print("\n" + "="*60)
        print("Test server setup complete!")
        print("Run cleanup with: python -c 'import asyncio; from test_setup_server import cleanup_test_server; asyncio.run(cleanup_test_server())'")
        print("="*60)
