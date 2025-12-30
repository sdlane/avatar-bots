import asyncpg
import asyncio
import logging
from utils import *

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - DB - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def ensure_tables():
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")

    # --- ServerConfig table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS ServerConfig (
        guild_id BIGINT PRIMARY KEY,
        default_limit SMALLINT,
        letter_delay BIGINT,
        category_id BIGINT,
        reset_time TIME,
        admin_response_channel_id BIGINT
    );
    """)

    # Ensure all expected columns exist
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS default_limit SMALLINT;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS letter_delay BIGINT;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS category_id BIGINT;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS reset_time TIME;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS admin_response_channel_id BIGINT;")

    # --- Character table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Character (
        id SERIAL PRIMARY KEY,
        identifier TEXT NOT NULL,
        name TEXT NOT NULL,
        user_id BIGINT,
        channel_id BIGINT NOT NULL,
        letter_limit SMALLINT,
        letter_count SMALLINT NOT NULL DEFAULT 0,
        guild_id BIGINT NOT NULL
    );
    """)

    # --- Column Synchronization ---

    # Ensure all expected columns exist
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS identifier TEXT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS name TEXT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS user_id BIGINT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS channel_id BIGINT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS letter_limit SMALLINT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS letter_count SMALLINT DEFAULT 0;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # --- Constraint Synchronization ---
    # Unique constraint on (identifier, guild_id)
    await conn.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'unique_identifier_per_guild'
        ) THEN
            ALTER TABLE Character
            ADD CONSTRAINT unique_identifier_per_guild UNIQUE (identifier, guild_id);
        END IF;
    END$$;
    """)

    # --- Alias table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Alias (
        id SERIAL PRIMARY KEY,
        character_id INTEGER NOT NULL REFERENCES Character(id) ON DELETE CASCADE,
        alias TEXT NOT NULL,
        guild_id BIGINT NOT NULL,
        UNIQUE (alias, guild_id)
    );
    """)

    # Ensure all expected columns exist
    await conn.execute("ALTER TABLE Alias ADD COLUMN IF NOT EXISTS character_id INTEGER;")
    await conn.execute("ALTER TABLE Alias ADD COLUMN IF NOT EXISTS alias TEXT;")
    await conn.execute("ALTER TABLE Alias ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Foreign key constraint linking guild_id -> ServerConfig.guild_id
    await conn.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'character_guild_id_fkey'
        ) THEN
            ALTER TABLE Character
            ADD CONSTRAINT character_guild_id_fkey
            FOREIGN KEY (guild_id) REFERENCES ServerConfig (guild_id);
        END IF;
    END$$;
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS HawkyTask (
        id SERIAL PRIMARY KEY,
        task TEXT NOT NULL,
        recipient_identifier TEXT,
        sender_identifier TEXT,
        parameter TEXT,
        scheduled_time TIMESTAMP,
        guild_int BIGINT NOT NULL
    );
    """)

    # --- Ensure hawky_tasks columns match the desired schema ---
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS id SERIAL PRIMARY KEY;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS task TEXT NOT NULL;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS recipient_identifier TEXT;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS sender_identifier TEXT;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS parameter TEXT;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS scheduled_time TIMESTAMP;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL;")

    # --- SentLetter table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS SentLetter (
        id SERIAL PRIMARY KEY,
        message_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL,
        sender_identifier TEXT NOT NULL,
        recipient_identifier TEXT NOT NULL,
        original_message_channel_id BIGINT NOT NULL,
        original_message_id BIGINT NOT NULL,
        has_response BOOLEAN NOT NULL DEFAULT FALSE,
        guild_id BIGINT NOT NULL,
        sent_time TIMESTAMP NOT NULL
    );
    """)

    # --- Ensure SentLetter columns match the desired schema ---
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS id SERIAL PRIMARY KEY;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS message_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS channel_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS sender_identifier TEXT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS recipient_identifier TEXT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS original_message_channel_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS original_message_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS has_response BOOLEAN DEFAULT FALSE;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS sent_time TIMESTAMP NOT NULL;")

    logger.info("Schema verified and updated successfully.")
    await conn.close()

    
# Run
if __name__ == "__main__":
    asyncio.run(ensure_tables())
    asyncio.run(inspect_database())

