"""
Test script to set up test characters.
Requires test server to be set up first.
"""
import asyncio
import asyncpg
import logging
from db import Character

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - TestSetupCharacters - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://AVATAR:password@db:5432/AVATAR"
TEST_GUILD_ID = 999999999  # Use a test guild ID

# Test characters to create
TEST_CHARACTERS = [
    ("taiso", "Fire Lord Taiso"),
    ("zhao", "Admiral Zhao"),
    ("jialun", "General Jialun")
]


async def setup_test_characters():
    """Create test characters"""
    conn = await asyncpg.connect(DB_URL)

    try:
        logger.info(f"Setting up test characters for guild {TEST_GUILD_ID}...")

        # Verify server config exists
        server = await conn.fetchrow(
            "SELECT * FROM ServerConfig WHERE guild_id = $1;",
            TEST_GUILD_ID
        )
        if not server:
            logger.error(f"❌ Server config not found for guild {TEST_GUILD_ID}. Run test_setup_server.py first!")
            return False

        created_count = 0
        for identifier, name in TEST_CHARACTERS:
            char = Character(
                identifier=identifier,
                name=name,
                channel_id=123456789,  # Dummy channel ID
                guild_id=TEST_GUILD_ID
            )
            await char.upsert(conn)
            logger.info(f"  Created test character: {identifier} ({name})")
            created_count += 1

        logger.info(f"✅ Created {created_count} test characters successfully")
        return True

    finally:
        await conn.close()


async def cleanup_test_characters():
    """Remove test characters"""
    conn = await asyncpg.connect(DB_URL)

    try:
        logger.info(f"Cleaning up test characters for guild {TEST_GUILD_ID}...")

        deleted_count = 0
        for identifier, _ in TEST_CHARACTERS:
            result = await conn.execute(
                "DELETE FROM Character WHERE identifier = $1 AND guild_id = $2;",
                identifier, TEST_GUILD_ID
            )
            if result.startswith("DELETE 1"):
                deleted_count += 1

        logger.info(f"✅ Cleaned up {deleted_count} test characters")
        return True

    finally:
        await conn.close()


if __name__ == "__main__":
    # Run setup
    success = asyncio.run(setup_test_characters())

    if success:
        print("\n" + "="*60)
        print("Test characters setup complete!")
        print("Run cleanup with: python -c 'import asyncio; from test_setup_characters import cleanup_test_characters; asyncio.run(cleanup_test_characters())'")
        print("="*60)
