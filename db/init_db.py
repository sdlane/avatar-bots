import asyncpg
import asyncio
from utils import *

async def ensure_tables():
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")

    # --- ServerConfig table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS ServerConfig (
        guild_id BIGINT PRIMARY KEY,
        default_limit SMALLINT,
        letter_delay BIGINT,
        category_id BIGINT
    );
    """)

    # Ensure all expected columns exist
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS default_limit SMALLINT;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS letter_delay BIGINT;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS category_id BIGINT;")

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

    # If the old column `limit` exists, rename it to `letter_limit`
    await conn.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'character' AND column_name = 'limit'
        ) THEN
            ALTER TABLE Character RENAME COLUMN "limit" TO letter_limit;
        END IF;
    END$$;
    """)

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

    print("✅ Schema verified and updated successfully.")
    await conn.close()

    
# Run
if __name__ == "__main__":
    asyncio.run(ensure_tables())
    asyncio.run(inspect_database())

